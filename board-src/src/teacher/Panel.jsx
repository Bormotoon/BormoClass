/*
 * Панель «Учителю»: лист, фон, сетка, инструменты и точные фигуры.
 *
 * Всё делается публичным API компонента (updateScene / getSceneElements /
 * getAppState), поэтому панель ничего не знает о внутренностях редактора и
 * переживёт его обновление. Сами элементы собирает elements.js — здесь только
 * интерфейс и подстановка на середину экрана.
 */

import { useRef, useState } from "react";
import {
	CaptureUpdateAction,
	viewportCoordsToSceneCoords,
} from "@excalidraw/excalidraw";
import { buildInstrument, buildFigure, groupFrame, rotateGroup, selectedInstrument, SHEET_GROUP, translateGroup } from "./elements.js";
import { buildRulingSheet, presetSheet } from "./ruling.js";
import RulingDialog from "./RulingDialog.jsx";
import "./panel.css";

/* Быстрые разлиновки — четыре самых частых. Всё остальное (двойная линовка,
   миллиметровка, изометрия, свои слои) живёт в конструкторе: держать девять
   кнопок в колонке шириной 330 px незачем. */
const QUICK = ["cells5", "lined", "slanted", "coords"];
const QUICK_NAMES = { cells5: "Клетка 5 мм", lined: "Линовка", slanted: "Косая линейка", coords: "Координаты" };

/* Настройки листа живут в localStorage, а не в IndexedDB рядом с рисунком:
   это десяток чисел, и переживать они должны не сцену, а самого учителя —
   разлиновку настраивают один раз и потом ставят тем же составом весь год. */
const RULING_KEY = "pb-board-ruling";
const loadRuling = () => {
	try {
		const raw = localStorage.getItem(RULING_KEY);
		return raw ? JSON.parse(raw) : presetSheet("cells5");
	} catch (error) {
		return presetSheet("cells5");
	}
};
const saveRuling = (sheet) => {
	try { localStorage.setItem(RULING_KEY, JSON.stringify(sheet)); } catch (error) { /* приватный режим */ }
};

/* Фон холста. Тёмные варианты переключают и цвет пера: белым по зелёной доске
   пишут мелом, а чёрным по ней не видно ничего — и это первое, обо что
   спотыкаются, выбрав «школьную доску». */
const BACKGROUNDS = [
	{ id: "#ffffff", name: "Белый", dark: false },
	{ id: "#fdf6e3", name: "Кремовый", dark: false },
	{ id: "#eef2f7", name: "Светло-серый", dark: false },
	{ id: "#2f5d50", name: "Зелёная доска", dark: true },
	{ id: "#1f2937", name: "Тёмная", dark: true },
	{ id: "#111111", name: "Чёрная доска", dark: true },
];

const GRID_STEPS = [
	{ size: 20, name: "5 мм" },
	{ size: 40, name: "1 см" },
	{ size: 80, name: "2 см" },
];

const TOOL_NAMES = {
	ruler: "Линейка", protractor: "Транспортир", compass: "Циркуль",
	square30: "Угольник 30-60-90", square45: "Угольник 45-45-90",
};

/**
 * Числовое поле, которое применяется по Enter и по уходу фокуса, а не на
 * каждое нажатие клавиши: иначе «12» по дороге успело бы пересобрать
 * инструмент как «1».
 */
function NumberField({ label, value, min, max, step, onApply }) {
	const [draft, setDraft] = useState(String(value));
	const shown = useRef(value);
	if (shown.current !== value) { shown.current = value; if (String(value) !== draft) { setDraft(String(value)); } }
	const apply = () => {
		const next = Number(draft);
		if (Number.isFinite(next) && next !== value) { onApply(next); }
	};
	return (
		<label>{label}
			<input type="number" min={min} max={max} step={step} value={draft}
				onChange={(e) => setDraft(e.target.value)}
				onBlur={apply}
				onKeyDown={(e) => { if ("Enter" === e.key) { e.preventDefault(); apply(); } }} />
		</label>
	);
}

/** Где у пересобранного циркуля игла (в координатах сцены). */
function selectedNeedle(elements, group) {
	const body = elements.find((el) => el.customData && el.customData.compass && (el.groupIds || []).includes(group));
	if (!body) { return null; }
	const px = body.points ? body.points.map((pt) => pt[0]) : [0, body.width];
	const py = body.points ? body.points.map((pt) => pt[1]) : [0, body.height];
	const cx = body.x + (Math.min(...px) + Math.max(...px)) / 2;
	const cy = body.y + (Math.min(...py) + Math.max(...py)) / 2;
	const w = Math.max(...px) - Math.min(...px), h = Math.max(...py) - Math.min(...py);
	const [fx, fy] = body.customData.compass.needle;
	const a = body.angle || 0;
	const lx = fx * w, ly = fy * h;
	return { x: cx + lx * Math.cos(a) - ly * Math.sin(a), y: cy + lx * Math.sin(a) + ly * Math.cos(a) };
}

const INSTRUMENTS = [
	{ id: "ruler", name: "Линейка 20 см" },
	{ id: "protractor", name: "Транспортир" },
	{ id: "square30", name: "Угольник 30-60-90" },
	{ id: "square45", name: "Угольник 45-45-90" },
];

export default function TeacherPanel({ api, onClose, gridOn, gridSize, tool }) {
	const [segment, setSegment] = useState({ length: 5, angle: 30 });
	const [circle, setCircle] = useState({ radius: 3 });
	const [polygon, setPolygon] = useState({ sides: 6, radius: 3 });
	const [angle, setAngle] = useState({ angle: 60 });
	const [compass, setCompass] = useState({ radius: 5 });
	const [note, setNote] = useState("");
	const [dialog, setDialog] = useState(false);
	const [sheet, setSheet] = useState(loadRuling);

	/* Середина видимой части холста в координатах сцены: вставленное должно
	   появляться там, куда человек смотрит, а не в начале координат. */
	const center = () =>
		viewportCoordsToSceneCoords(
			{ clientX: window.innerWidth / 2, clientY: window.innerHeight / 2 },
			api.getAppState(),
		);

	const insert = (elements, what) => {
		api.updateScene({
			elements: [...api.getSceneElements(), ...elements],
			captureUpdate: CaptureUpdateAction.IMMEDIATELY,
		});
		setNote(what + " — на холсте. Не туда? Ctrl+Z.");
	};

	const putSheet = (next) => {
		setSheet(next);
		saveRuling(next);
		insert(buildRulingSheet(next, center()), "Лист");
		setDialog(false);
	};

	const dropSheet = () => {
		const rest = api
			.getSceneElements()
			.filter((el) => !(el.groupIds || []).some((g) => 0 === String(g).indexOf(SHEET_GROUP)));
		api.updateScene({ elements: rest, captureUpdate: CaptureUpdateAction.IMMEDIATELY });
		setNote("Лист убран.");
	};

	const dropTools = () => {
		const rest = api
			.getSceneElements()
			.filter((el) => !(el.groupIds || []).some((g) => 0 === String(g).indexOf("pb-tool-")));
		api.updateScene({ elements: rest, captureUpdate: CaptureUpdateAction.IMMEDIATELY });
		setNote("Инструменты убраны — начерченное осталось.");
	};

	const setBackground = (bg) => {
		api.updateScene({
			appState: bg.dark
				? { viewBackgroundColor: bg.id, currentItemStrokeColor: "#ffffff" }
				: { viewBackgroundColor: bg.id },
			captureUpdate: CaptureUpdateAction.IMMEDIATELY,
		});
		setNote(bg.dark ? `Фон «${bg.name}», перо переключено на белое.` : `Фон «${bg.name}».`);
	};

	const setGrid = (enabled, size) => {
		api.updateScene({
			appState: { gridModeEnabled: enabled, gridSize: size, gridStep: 5 },
			captureUpdate: CaptureUpdateAction.IMMEDIATELY,
		});
		setNote(enabled ? `Сетка на экране: шаг ${size / 40 >= 1 ? size / 40 + " см" : "5 мм"}.` : "Сетка выключена.");
	};

	const strokeColor = () => api.getAppState().currentItemStrokeColor;

	/* Тёмный ли холст: инструмент на зелёной доске должен быть светлым, иначе
	   его деления не прочитать. Порог по яркости, как у эталона. */
	const darkCanvas = () => {
		const hex = String(api.getAppState().viewBackgroundColor || "#ffffff").replace("#", "");
		const full = 3 === hex.length ? hex.split("").map((c) => c + c).join("") : hex;
		const [r, g, b] = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16) || 0);
		return (0.299 * r + 0.587 * g + 0.114 * b) < 128;
	};

	/* Правка размера — ПЕРЕСБОРКА инструмента на прежнем месте и под прежним
	   углом. Растянуть нельзя: у растянутой линейки деления перестанут быть
	   сантиметрами, а у транспортира — градусами. */
	/* Инструмент берём ИЗ СЦЕНЫ в момент действия, а не из свойства: после
	   пересборки у группы новый идентификатор, и свойство успевает устареть на
	   один кадр — поворот тогда искал бы уже несуществующую группу. */
	const picked = () => selectedInstrument(api.getSceneElements(), api.getAppState().selectedElementIds) || tool;

	const rebuild = (patch) => {
		const tool = picked();
		if (!tool) { return; }
		const rest = api.getSceneElements().filter((el) => !(el.groupIds || []).includes(tool.group));
		const built = buildInstrument(tool.kind, tool.center, {
			...tool.params, ...patch, dark: darkCanvas(),
		});
		const group = built[0].groupIds[0];
		let next = built;
		if (tool.angle) {
			next = rotateGroup(next, group, groupFrame(next, group), tool.angle);
		}
		/* У циркуля важно сохранить ИГЛУ на месте: её ставят в точку чертежа. */
		if (tool.needle) {
			const info = selectedNeedle(next, group);
			if (info) { next = translateGroup(next, group, tool.needle.x - info.x, tool.needle.y - info.y); }
		}
		/* Пересобранный инструмент оставляем ВЫДЕЛЕННЫМ: иначе после правки
		   размера панель с полями исчезает, и следующее значение вводить негде. */
		const ids = {};
		next.filter((el) => (el.groupIds || []).includes(group)).forEach((el) => { ids[el.id] = true; });
		api.updateScene({
			elements: [...rest, ...next],
			appState: { selectedElementIds: ids, selectedGroupIds: { [group]: true } },
			captureUpdate: CaptureUpdateAction.IMMEDIATELY,
		});
		setNote("Размер применён.");
	};

	const spin = (degrees) => {
		const tool = picked();
		if (!tool) { return; }
		const delta = (degrees * Math.PI) / 180 - tool.angle;
		api.updateScene({
			elements: rotateGroup(api.getSceneElements(), tool.group,
				tool.needle || groupFrame(api.getSceneElements(), tool.group), delta),
			captureUpdate: CaptureUpdateAction.IMMEDIATELY,
		});
		setNote(`Поворот: ${Math.round(degrees)}°.`);
	};

	return (
		<aside className="pbt-panel" aria-label="Учительские инструменты">
			<header className="pbt__head">
				<b>Учителю</b>
				<button type="button" className="pbt__close" onClick={onClose} aria-label="Закрыть панель">×</button>
			</header>

			<div className="pbt__body">
				<section className="pbt__sec">
					<h3>Лист</h3>
					<p className="pbt__note">Настоящие элементы сцены: двигаются, масштабируются и попадают в выгрузку. Заперты, чтобы не выделяться вместе с чертежом.</p>
					<div className="pbt__grid">
						{QUICK.map((id) => (
							<button type="button" key={id} className="pbt__btn" onClick={() => putSheet(presetSheet(id))}>
								{QUICK_NAMES[id]}
							</button>
						))}
					</div>
					<button type="button" className="pbt__btn pbt__btn--quiet" onClick={() => setDialog(true)}>
						Настроить разлиновку…
					</button>
					<button type="button" className="pbt__btn pbt__btn--quiet" onClick={dropSheet}>Убрать лист</button>
				</section>

				<section className="pbt__sec">
					<h3>Фон холста</h3>
					<div className="pbt__swatches">
						{BACKGROUNDS.map((b) => (
							<button
								type="button" key={b.id} className="pbt__swatch" title={b.name}
								style={{ background: b.id }} aria-label={b.name}
								onClick={() => setBackground(b)}
							/>
						))}
					</div>
				</section>

				<section className="pbt__sec">
					<h3>Сетка на экране</h3>
					<p className="pbt__note">Бесконечная, к рисунку не относится и в выгрузку не попадает. По ней удобно ставить фигуры ровно: они к ней прилипают.</p>
					<div className="pbt__row">
						<button
							type="button"
							className={"pbt__btn" + (gridOn ? " is-on" : "")}
							onClick={() => setGrid(!gridOn, gridSize || 20)}
						>
							{gridOn ? "Выключить" : "Включить"}
						</button>
						{GRID_STEPS.map((g) => (
							<button
								type="button" key={g.size}
								className={"pbt__btn pbt__btn--small" + (gridOn && gridSize === g.size ? " is-on" : "")}
								onClick={() => setGrid(true, g.size)}
							>
								{g.name}
							</button>
						))}
					</div>
					<div className="pbt__form">
						<NumberField label="Свой шаг, мм" value={Math.round((gridSize || 20) / 4)} min="1" max="50" step="1"
							onApply={(mm) => setGrid(true, Math.max(4, Math.round(mm * 4)))} />
					</div>
				</section>

				<section className="pbt__sec">
					<h3>Инструменты</h3>
					<p className="pbt__note">Возьмите <b>карандаш</b> и ведите у кромки — линия пойдёт строго по ней. Циркуль берут за грифель: игла стоит, плечо ведёт дугу; раствор задаётся числом. По шкале транспортира тычок ставит отметку градуса, а ведение чертит дугу. Стрелкой инструмент двигают и поворачивают, потом просто убирают.</p>
					<div className="pbt__grid">
						{INSTRUMENTS.map((t) => (
							<button type="button" key={t.id} className="pbt__btn"
								onClick={() => insert(buildInstrument(t.id, center(), { dark: darkCanvas() }), t.name)}>
								{t.name}
							</button>
						))}
					</div>
					<div className="pbt__form">
						<label>Циркуль, раствор см
							<input type="number" min="1" max="12" step="0.5" value={compass.radius}
								onChange={(e) => setCompass({ radius: +e.target.value })} />
						</label>
						<button type="button" className="pbt__btn"
							onClick={() => insert(buildInstrument("compass", center(), { ...compass, dark: darkCanvas() }), "Циркуль")}>
							Положить
						</button>
					</div>
					<button type="button" className="pbt__btn pbt__btn--quiet" onClick={dropTools}>Убрать инструменты</button>
				</section>

				{tool && (
					<section className="pbt__sec pbt__sec--picked">
						<h3>{TOOL_NAMES[tool.kind] || "Инструмент"}: размеры</h3>
						<p className="pbt__note">Числом — точно, рукояткой — на глаз. Размер задаётся заново, а не растягивается: у растянутой линейки деления перестали бы быть сантиметрами.</p>
						<div className="pbt__form">
							{"ruler" === tool.kind && (
								<NumberField label="Длина, см" value={tool.params.length || 20} min="5" max="60" step="1"
									onApply={(v) => rebuild({ length: v })} />
							)}
							{"protractor" === tool.kind && (
								<NumberField label="Радиус, см" value={tool.params.radius || 6} min="2" max="20" step="0.5"
									onApply={(v) => rebuild({ radius: v })} />
							)}
							{("square30" === tool.kind || "square45" === tool.kind) && (
								<NumberField label="Катет, см" value={tool.params.leg || ("square45" === tool.kind ? 9 : 10)}
									min="3" max="40" step="1" onApply={(v) => rebuild({ leg: v })} />
							)}
							{"compass" === tool.kind && (
								<NumberField label="Раствор, см" value={tool.params.radius || 5} min="1" max="12" step="0.5"
									onApply={(v) => rebuild({ radius: v })} />
							)}
							<NumberField label="Поворот, °" value={Math.round((tool.angle * 180) / Math.PI)}
								min="-360" max="360" step="1" onApply={spin} />
						</div>
						<div className="pbt__row">
							{[0, 30, 45, 60, 90].map((d) => (
								<button type="button" key={d} className="pbt__btn pbt__btn--small" onClick={() => spin(d)}>{d}°</button>
							))}
						</div>
					</section>
				)}

				<section className="pbt__sec">
					<h3>Точные фигуры</h3>
					<p className="pbt__note">Строятся по числам, а не на глаз, — и текущим цветом пера.</p>

					<div className="pbt__form">
						<label>Отрезок, см
							<input type="number" min="0.5" step="0.5" value={segment.length}
								onChange={(e) => setSegment({ ...segment, length: +e.target.value })} />
						</label>
						<label>под углом °
							<input type="number" min="0" max="180" step="5" value={segment.angle}
								onChange={(e) => setSegment({ ...segment, angle: +e.target.value })} />
						</label>
						<button type="button" className="pbt__btn"
							onClick={() => insert(buildFigure("segment", segment, center(), strokeColor()), "Отрезок")}>
							Поставить
						</button>
					</div>

					<div className="pbt__form">
						<label>Окружность, радиус см
							<input type="number" min="0.5" step="0.5" value={circle.radius}
								onChange={(e) => setCircle({ radius: +e.target.value })} />
						</label>
						<button type="button" className="pbt__btn"
							onClick={() => insert(buildFigure("circle", circle, center(), strokeColor()), "Окружность")}>
							Поставить
						</button>
					</div>

					<div className="pbt__form">
						<label>Многоугольник, сторон
							<input type="number" min="3" max="12" step="1" value={polygon.sides}
								onChange={(e) => setPolygon({ ...polygon, sides: +e.target.value })} />
						</label>
						<label>радиус см
							<input type="number" min="0.5" step="0.5" value={polygon.radius}
								onChange={(e) => setPolygon({ ...polygon, radius: +e.target.value })} />
						</label>
						<button type="button" className="pbt__btn"
							onClick={() => insert(buildFigure("polygon", polygon, center(), strokeColor()), "Многоугольник")}>
							Поставить
						</button>
					</div>

					<div className="pbt__form">
						<label>Угол, градусов
							<input type="number" min="1" max="179" step="5" value={angle.angle}
								onChange={(e) => setAngle({ angle: +e.target.value })} />
						</label>
						<button type="button" className="pbt__btn"
							onClick={() => insert(buildFigure("angle", angle, center(), strokeColor()), "Угол")}>
							Поставить
						</button>
					</div>
				</section>

				<p className="pbt__status" role="status" aria-live="polite">{note}</p>
			</div>

			{dialog && (
				<RulingDialog
					initial={sheet}
					onApply={putSheet}
					onClose={() => setDialog(false)}
					onSnap={(stepMm) => {
						setGrid(true, Math.max(4, Math.round(stepMm * 4)));
					}}
				/>
			)}
		</aside>
	);
}

/**
 * Строка измерений внизу экрана.
 *
 * Показывается только когда есть что мерить, и не перехватывает указатель
 * (pointer-events: none в стилях): это подпись к выделенному, а не орган
 * управления, и она не должна отбирать щелчки у холста под собой.
 */
export function MeasureBar({ data }) {
	return (
		<div className="pbm" role="status" aria-live="polite">
			<span className="pbm__title">{data.title}</span>
			{data.rows.map(([label, value]) => (
				<span className="pbm__row" key={label}>
					<span className="pbm__label">{label}:</span>
					<span className="pbm__value">{value}</span>
				</span>
			))}
		</div>
	);
}
