/*
 * Прилипание карандаша к инструменту: линейка, угольник и транспортир ВЕДУТ
 * руку, а не лежат картинкой.
 *
 * Смысл настоящей линейки не в том, чтобы лежать на листе: к ней приставляют
 * карандаш и проводят прямую. Пока инструмент был просто набором линий, он
 * ничем не помогал — это и была главная недоделка.
 *
 * КАК ЭТО СДЕЛАНО, не залезая внутрь редактора. Excalidraw не даёт перехватить
 * рисование, но событие указателя можно забрать РАНЬШЕ него: слушатель на
 * обёртке в фазе перехвата (capture) срабатывает до обработчиков холста.
 * Дальше два случая:
 *
 *   • указатель у рабочей кромки инструмента И выбран карандаш → забираем
 *     событие себе (stopPropagation), ведём свою линию строго по кромке и на
 *     отпускании кладём в сцену готовый отрезок или дугу;
 *   • иначе не делаем ничего — холст рисует как обычно.
 *
 * Поэтому линейку можно и двигать (стрелкой), и чертить по ней (карандашом):
 * инструмент выбора мы не трогаем вовсе. И поэтому же ничего не ломается,
 * когда инструментов на холсте нет.
 *
 * Геометрию кромок кладёт в customData тела инструмента elements.js — долями
 * от рамки, чтобы пережить растяжение; здесь мы её только поворачиваем вместе
 * с элементом и переводим в координаты сцены.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
	CaptureUpdateAction,
	sceneCoordsToViewportCoords,
	viewportCoordsToSceneCoords,
} from "@excalidraw/excalidraw";
import { assemble, EXACT, rotateGroup } from "./elements.js";

/** На сколько экранных пикселей карандаш «чувствует» кромку. */
const GRAB = 18;
/** Короче этого — не линия, а тычок (для транспортира это отметка градуса). */
const MIN_DRAW = 6;

const rad = (deg) => (deg * Math.PI) / 180;
const degOf = (dx, dy) => {
	const a = (Math.atan2(-dy, dx) * 180) / Math.PI;
	return a < 0 ? a + 360 : a;
};

/** Инструменты сцены с кромками, уже повёрнутыми и переведёнными в сцену. */
function instrumentsOf(elements) {
	const out = [];
	for (const el of elements) {
		const data = el.customData;
		if (!data || !data.pbTool || el.isDeleted) { continue; }
		/* ⚠️ Центр рамки НЕЛЬЗЯ брать как (x + width/2): у ломаной x,y — это её
		   ПЕРВАЯ ТОЧКА, а рамка растёт от неё в ту сторону, куда идут точки. У
		   транспортира они уходят влево и вверх, поэтому рамка лежит на полшага
		   левее и выше x,y. С наивной формулой шкала «находилась» в пустоте
		   рядом с инструментом — и, что хуже, проверка ошибалась ровно так же,
		   поэтому была зелёной. Поймал только снимок экрана. */
		const px = el.points ? el.points.map((pt) => pt[0]) : [0, el.width];
		const py = el.points ? el.points.map((pt) => pt[1]) : [0, el.height];
		const minX = Math.min(...px), maxX = Math.max(...px);
		const minY = Math.min(...py), maxY = Math.max(...py);
		const cx = el.x + (minX + maxX) / 2, cy = el.y + (minY + maxY) / 2;
		const boxW = maxX - minX || el.width, boxH = maxY - minY || el.height;
		const angle = el.angle || 0;
		const cos = Math.cos(angle), sin = Math.sin(angle);
		const place = ([fx, fy]) => {
			const lx = fx * boxW, ly = fy * boxH;
			return { x: cx + lx * cos - ly * sin, y: cy + lx * sin + ly * cos };
		};
		/* Точка внутри инструмента: переводим её в его собственную систему
		   (обратный поворот вокруг центра рамки) и сравниваем с полурамкой. */
		const contains = (p, pad) => {
			const dx = p.x - cx, dy = p.y - cy;
			const lx = dx * cos + dy * sin, ly = -dx * sin + dy * cos;
			return Math.abs(lx) <= boxW / 2 + pad && Math.abs(ly) <= boxH / 2 + pad;
		};
		out.push({
			kind: data.pbTool,
			angle,
			contains,
			center: { x: cx, y: cy },
			group: (el.groupIds || [])[0] || null,
			compass: data.compass
				? { needle: place(data.compass.needle), pencil: place(data.compass.pencil) }
				: null,
			edges: (data.edges || []).map(([a, b]) => ({ a: place(a), b: place(b) })),
			arc: data.arc
				? { c: place(data.arc.center), r: data.arc.radius * boxW, from: data.arc.from, to: data.arc.to }
				: null,
		});
	}
	return out;
}

/** Проекция точки на отрезок, зажатая его концами: карандаш не уезжает за линейку. */
function project(p, a, b) {
	const vx = b.x - a.x, vy = b.y - a.y;
	const len2 = vx * vx + vy * vy || 1;
	const t = Math.max(0, Math.min(1, ((p.x - a.x) * vx + (p.y - a.y) * vy) / len2));
	return { x: a.x + vx * t, y: a.y + vy * t };
}

/** У этих инструментов чертят по кромке, поэтому нажатие ВНУТРИ тела тоже считается. */
const STRAIGHT = { ruler: true, square30: true, square45: true };

/**
 * Ближайшая рабочая кромка (или дуга) в пределах досягаемости.
 *
 * У эталона (UBGraphicsRuler::StartLine, UBGraphicsTriangle::StartLine) перо
 * можно поставить ГДЕ УГОДНО на инструменте: сторона выбирается по тому, в
 * какой его половине (у угольника — в какой зоне) оказалось нажатие. Это
 * заметно удобнее узкой полосы у кромки, особенно пальцем на панели, поэтому
 * у линейки и угольников нажатие внутри тела тоже ловится.
 */
function findGrab(scenePoint, instruments, tolerance) {
	let best = null;
	for (const tool of instruments) {
		const inside = STRAIGHT[tool.kind] && tool.contains(scenePoint, 0);
		for (const edge of tool.edges) {
			const at = project(scenePoint, edge.a, edge.b);
			const distance = Math.hypot(scenePoint.x - at.x, scenePoint.y - at.y);
			if ((distance <= tolerance || inside) && (!best || distance < best.distance)) {
				best = { kind: "edge", tool, edge, at, distance };
			}
		}
		if (tool.compass) {
			/* Циркуль берут ЗА ГРИФЕЛЬ — как настоящий: игла остаётся на месте,
			   а плечо ведут по дуге. */
			const p = tool.compass.pencil;
			const distance = Math.hypot(scenePoint.x - p.x, scenePoint.y - p.y);
			if (distance <= tolerance * 2 && (!best || distance < best.distance)) {
				best = { kind: "compass", tool, distance };
			}
		}
		if (tool.arc) {
			const dx = scenePoint.x - tool.arc.c.x, dy = scenePoint.y - tool.arc.c.y;
			const distance = Math.abs(Math.hypot(dx, dy) - tool.arc.r);
			/* Угол считаем в системе самого инструмента: транспортир поворачивают,
			   и «60°» должно остаться шестьюдесятью градусами по его шкале. */
			const local = (degOf(dx, dy) + (tool.angle * 180) / Math.PI + 360) % 360;
			if (distance <= tolerance && local >= tool.arc.from && local <= tool.arc.to
				&& (!best || distance < best.distance)) {
				best = { kind: "arc", tool, arc: tool.arc, local, distance };
			}
		}
	}
	return best;
}

/** Смещение наружу от тела инструмента: перпендикуляр к кромке от её центра. */
function outwardShift(state, distance) {
	const { edge, center } = state;
	const dx = edge.b.x - edge.a.x, dy = edge.b.y - edge.a.y;
	const len = Math.hypot(dx, dy) || 1;
	let nx = -dy / len, ny = dx / len;
	const mid = { x: (edge.a.x + edge.b.x) / 2, y: (edge.a.y + edge.b.y) / 2 };
	/* Нормалей две; берём ту, что смотрит ОТ центра инструмента. */
	if ((mid.x + nx - center.x) ** 2 + (mid.y + ny - center.y) ** 2
		< (mid.x - center.x) ** 2 + (mid.y - center.y) ** 2) {
		nx = -nx; ny = -ny;
	}
	return { x: nx * distance, y: ny * distance };
}

/** Точка на окружности по углу в градусах (ноль — вправо, отсчёт против часовой). */
const circlePoint = (c, r, deg) => ({ x: c.x + r * Math.cos(rad(deg)), y: c.y - r * Math.sin(rad(deg)) });

/** Точка на дуге по её собственному делению. */
function arcPoint(arc, localDeg, toolAngle) {
	const world = rad(localDeg - (toolAngle * 180) / Math.PI);
	return { x: arc.c.x + arc.r * Math.cos(world), y: arc.c.y - arc.r * Math.sin(world) };
}

export default function SnapLayer({ api, stage }) {
	const [hint, setHint] = useState(null);      /* подсветка кромки под указателем */
	const [draft, setDraft] = useState(null);    /* то, что чертится прямо сейчас */
	const drag = useRef(null);

	/* Экранные координаты для отрисовки поверх холста. */
	const toScreen = useCallback(
		(p) => sceneCoordsToViewportCoords({ sceneX: p.x, sceneY: p.y }, api.getAppState()),
		[api],
	);

	useEffect(() => {
		const node = stage.current;
		if (!node) { return undefined; }

		const scenePoint = (event) =>
			viewportCoordsToSceneCoords({ clientX: event.clientX, clientY: event.clientY }, api.getAppState());

		const grabAt = (event) => {
			const state = api.getAppState();
			if ("freedraw" !== state.activeTool.type) { return null; }
			return findGrab(scenePoint(event), instrumentsOf(api.getSceneElements()), GRAB / state.zoom.value);
		};

		const onDown = (event) => {
			if (0 !== event.button) { return; }
			const grab = grabAt(event);
			if (!grab) { return; }
			/* Забираем событие у холста: иначе он начнёт рисовать своё поверх нашего. */
			event.stopPropagation();
			event.preventDefault();
			node.setPointerCapture(event.pointerId);
			drag.current = "compass" === grab.kind
				? (() => {
					const { needle, pencil } = grab.tool.compass;
					return {
						kind: "compass",
						group: grab.tool.group,
						center: needle,
						radius: Math.hypot(pencil.x - needle.x, pencil.y - needle.y),
						from: degOf(pencil.x - needle.x, pencil.y - needle.y),
						span: 0,
					};
				})()
				: "arc" === grab.kind
				? { kind: "arc", tool: grab.tool, arc: grab.arc, from: Math.round(grab.local), to: Math.round(grab.local) }
				/* Кромку держим в состоянии: вести карандаш надо ВДОЛЬ НЕЁ, а не
				   вдоль уже нарисованного куска — на этом линия и не росла. */
				: { kind: "edge", edge: grab.edge, center: grab.tool.center, from: grab.at, to: grab.at };
			setHint(null);
			setDraft({ ...drag.current });
		};

		const onMove = (event) => {
			if (drag.current) {
				event.stopPropagation();
				const p = scenePoint(event);
				if ("compass" === drag.current.kind) {
					const state = drag.current;
					const now = degOf(p.x - state.center.x, p.y - state.center.y);
					let step = now - (state.from + state.span);
					/* Через ноль градусов прыжок в 360° — сглаживаем, иначе на
					   каждом обороте циркуль дёргался бы на полный круг. */
					if (step > 180) { step -= 360; } else if (step < -180) { step += 360; }
					const capped = Math.max(-360, Math.min(360, state.span + step));
					const applied = capped - state.span;
					state.span = capped;
					if (applied) {
						/* Инструмент поворачивается вокруг иглы, как настоящий.
						   Промежуточные повороты в историю не пишем — иначе одна
						   дуга съела бы полсотни шагов отмены. */
						api.updateScene({
							elements: rotateGroup(api.getSceneElements(), state.group, state.center, rad(applied)),
							captureUpdate: CaptureUpdateAction.NEVER,
						});
					}
					setDraft({ ...state });
					return;
				}
				if ("arc" === drag.current.kind) {
					const { arc, tool } = drag.current;
					const local = (degOf(p.x - arc.c.x, p.y - arc.c.y) + (tool.angle * 180) / Math.PI + 360) % 360;
					drag.current.to = Math.round(Math.max(arc.from, Math.min(arc.to, local)));
				} else {
					drag.current.to = project(p, drag.current.edge.a, drag.current.edge.b);
				}
				setDraft({ ...drag.current });
				return;
			}
			const grab = grabAt(event);
			setHint(
				!grab ? null
					: "edge" === grab.kind ? { a: grab.edge.a, b: grab.edge.b }
					: "compass" === grab.kind ? { dot: grab.tool.compass.pencil }
					: { arc: grab.arc, deg: Math.round(grab.local), tool: grab.tool },
			);
		};

		const onUp = (event) => {
			const state = drag.current;
			if (!state) { return; }
			event.stopPropagation();
			drag.current = null;
			setDraft(null);
			if (node.hasPointerCapture(event.pointerId)) { node.releasePointerCapture(event.pointerId); }
			commit(state);
		};

		/* Кромка перестала быть кромкой (инструмент убрали) — подсветку снять. */
		const onLeave = () => { if (!drag.current) { setHint(null); } };

		/* ⚠️ Двойной щелчок по инструменту гасим.
		   Штатно двойной щелчок ВХОДИТ В ГРУППУ и выделяет одну деталь — и
		   дальше перетаскивание уносит, например, только жёлтое тело линейки,
		   оставив её шкалу лежать на месте. Для чертёжного инструмента это
		   поломка: он обязан оставаться цельным. Заодно гасится и вторая
		   штатная реакция — вписать текст внутрь фигуры. */
		const onDoubleClick = (event) => {
			const p = viewportCoordsToSceneCoords(
				{ clientX: event.clientX, clientY: event.clientY }, api.getAppState(),
			);
			if (instrumentsOf(api.getSceneElements()).some((tool) => tool.contains(p, 4))) {
				event.stopPropagation();
				event.preventDefault();
			}
		};

		node.addEventListener("pointerdown", onDown, true);
		node.addEventListener("pointermove", onMove, true);
		node.addEventListener("pointerup", onUp, true);
		node.addEventListener("pointercancel", onUp, true);
		node.addEventListener("pointerleave", onLeave, true);
		node.addEventListener("dblclick", onDoubleClick, true);
		return () => {
			node.removeEventListener("pointerdown", onDown, true);
			node.removeEventListener("pointermove", onMove, true);
			node.removeEventListener("pointerup", onUp, true);
			node.removeEventListener("pointercancel", onUp, true);
			node.removeEventListener("pointerleave", onLeave, true);
			node.removeEventListener("dblclick", onDoubleClick, true);
		};
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [api, stage]);

	/** Кладём начерченное в сцену — цветом и толщиной текущего пера. */
	function commit(state) {
		const app = api.getAppState();
		const look = {
			strokeColor: app.currentItemStrokeColor,
			strokeWidth: app.currentItemStrokeWidth,
			/* Ровно: линию, проведённую по линейке, дрожащей делать незачем —
			   в этом и была просьба «чтобы чертилась прямая». */
			...EXACT,
		};

		if ("compass" === state.kind) {
			if (Math.abs(state.span) < 2) { return; }
			const step = state.span > 0 ? 2 : -2;
			const points = [];
			for (let a = 0; Math.abs(a) <= Math.abs(state.span); a += step) {
				points.push(circlePoint(state.center, state.radius, state.from + a));
			}
			points.push(circlePoint(state.center, state.radius, state.from + state.span));
			putPolyline(points, look);
			return;
		}

		if ("edge" === state.kind) {
			const { from, to } = state;
			if (Math.hypot(to.x - from.x, to.y - from.y) < MIN_DRAW) { return; }
			/* Линия ложится СНАРУЖИ кромки на полтолщины штриха — как у эталона
			   (UBGraphicsRuler::StartLine). Настоящий карандаш идёт вплотную к
			   линейке, а не по её осевой; заодно линия не прячется под
			   полупрозрачным телом инструмента. */
			const shift = outwardShift(state, (app.currentItemStrokeWidth || 1) / 2 + 1);
			putPolyline([
				{ x: from.x + shift.x, y: from.y + shift.y },
				{ x: to.x + shift.x, y: to.y + shift.y },
			], look);
			return;
		}

		const { arc, tool, from, to } = state;
		if (Math.abs(to - from) < 2) {
			/* Тычок по шкале — отметка градуса. Так и ставят точку у нужного
			   деления, чтобы потом убрать транспортир и провести луч. */
			const p = arcPoint(arc, to, tool.angle);
			put([{ type: "ellipse", x: p.x - 3, y: p.y - 3, width: 6, height: 6,
				...look, backgroundColor: app.currentItemStrokeColor, fillStyle: "solid" }]);
			return;
		}
		const step = to > from ? 2 : -2;
		const points = [];
		for (let a = from; step > 0 ? a <= to : a >= to; a += step) {
			points.push(arcPoint(arc, a, tool.angle));
		}
		points.push(arcPoint(arc, to, tool.angle));
		putPolyline(points, look);
	}

	/** Ломаная в сцену: точки приводим к первой и считаем рамку. */
	function putPolyline(points, look) {
		const origin = points[0];
		const local = points.map((p) => [p.x - origin.x, p.y - origin.y]);
		const xs = local.map((p) => p[0]), ys = local.map((p) => p[1]);
		put([{ type: "line", x: origin.x, y: origin.y, points: local,
			width: Math.max(...xs) - Math.min(...xs), height: Math.max(...ys) - Math.min(...ys), ...look }]);
	}

	function put(skeletons) {
		const elements = assemble(skeletons, { group: "pb-drawn-" + Math.random().toString(36).slice(2, 8), locked: false });
		api.updateScene({
			elements: [...api.getSceneElements(), ...elements],
			captureUpdate: CaptureUpdateAction.IMMEDIATELY,
		});
	}

	if (!hint && !draft) { return null; }

	const line = (from, to, cls) => {
		const a = toScreen(from), b = toScreen(to);
		return <line className={cls} x1={a.x} y1={a.y} x2={b.x} y2={b.y} />;
	};

	const compassPath = (state) => {
		const step = state.span > 0 ? 3 : -3;
		let d = "";
		for (let a = 0; Math.abs(a) <= Math.abs(state.span); a += step) {
			const p = toScreen(circlePoint(state.center, state.radius, state.from + a));
			d += (d ? "L" : "M") + p.x + " " + p.y;
		}
		const end = toScreen(circlePoint(state.center, state.radius, state.from + state.span));
		return d + "L" + end.x + " " + end.y;
	};

	const arcPath = (arc, from, to, tool) => {
		const step = to > from ? 2 : -2;
		let d = "";
		for (let a = from; step > 0 ? a <= to : a >= to; a += step) {
			const p = toScreen(arcPoint(arc, a, tool.angle));
			d += (d ? "L" : "M") + p.x + " " + p.y;
		}
		const end = toScreen(arcPoint(arc, to, tool.angle));
		return d + "L" + end.x + " " + end.y;
	};

	return (
		<svg className="pbs" aria-hidden="true">
			{hint && hint.a && line(hint.a, hint.b, "pbs__hint")}
			{hint && hint.dot && (
				<circle className="pbs__hint" cx={toScreen(hint.dot).x} cy={toScreen(hint.dot).y} r="12" fill="none" />
			)}
			{hint && hint.arc && hint.deg != null && (
				<text className="pbs__deg"
					x={toScreen(arcPoint(hint.arc, hint.deg, hint.tool.angle)).x + 12}
					y={toScreen(arcPoint(hint.arc, hint.deg, hint.tool.angle)).y - 10}>
					{hint.deg}°
				</text>
			)}
			{hint && hint.arc && (
				<circle className="pbs__hint" cx={toScreen(hint.arc.c).x} cy={toScreen(hint.arc.c).y}
					r={hint.arc.r * api.getAppState().zoom.value} fill="none" />
			)}
			{draft && "edge" === draft.kind && line(draft.from, draft.to, "pbs__draft")}
			{draft && "arc" === draft.kind && (
				<path className="pbs__draft" fill="none" d={arcPath(draft.arc, draft.from, draft.to, draft.tool)} />
			)}
			{draft && "compass" === draft.kind && (
				<path className="pbs__draft" fill="none" d={compassPath(draft)} />
			)}
			{draft && "compass" === draft.kind && (
				<text className="pbs__deg"
					x={toScreen(circlePoint(draft.center, draft.radius, draft.from + draft.span)).x + 10}
					y={toScreen(circlePoint(draft.center, draft.radius, draft.from + draft.span)).y - 8}>
					{`${Math.round(Math.abs(draft.span))}° · R ${(draft.radius / 40).toFixed(1)} см`}
				</text>
			)}
			{draft && "arc" === draft.kind && (
				<text className="pbs__deg"
					x={toScreen(arcPoint(draft.arc, draft.to, draft.tool.angle)).x + 10}
					y={toScreen(arcPoint(draft.arc, draft.to, draft.tool.angle)).y - 8}>
					{Math.abs(draft.to - draft.from) < 2 ? `${draft.to}°` : `${Math.abs(draft.to - draft.from)}°`}
				</text>
			)}
		</svg>
	);
}
