/*
 * Учительские инструменты: превращаем параметры в элементы сцены.
 *
 * Здесь нет ни React, ни обращений к API — только чистые функции «параметры →
 * массив элементов Excalidraw». Так их видно целиком и можно проверять по
 * числам, а не по скриншоту.
 *
 * ПОЧЕМУ ЭЛЕМЕНТЫ СЦЕНЫ, А НЕ НАКЛАДКА ПОВЕРХ ХОЛСТА. Линовку и инструменты
 * можно было нарисовать своим слоем над холстом — вышло бы бесконечно и
 * дёшево. Но тогда они не попадут ни в выгрузку PNG, ни в сохранённый файл: у
 * Excalidraw экспорт рисует ТОЛЬКО элементы сцены. Учителю нужен лист в клетку
 * именно на картинке, которую он отдаёт классу, поэтому лист — настоящие
 * элементы: он масштабируется, двигается и экспортируется сам собой.
 * Бесконечную сетку на экране при этом даёт штатный режим сетки (Ctrl+'), она
 * тут ни при чём и остаётся доступной.
 *
 * Всё вставленное заперто (locked) и собрано в группу: лист не должен
 * выделяться, когда учитель тянет рамку вокруг своего чертежа. Инструменты
 * (линейка, транспортир, угольник) — наоборот, группа БЕЗ замка: их берут и
 * поворачивают штатной ручкой, как настоящие.
 *
 * Сама разлиновка живёт в ruling.js: она настраивается слоями и выросла в
 * отдельную задачу. Здесь остались общие кирпичики (poly, label, assemble),
 * инструменты и точные фигуры.
 */

import { convertToExcalidrawElements } from "@excalidraw/excalidraw";

/* Масштаб холста. Клетка 20 px — это же значение по умолчанию у штатной сетки
   Excalidraw, поэтому наш лист и его сетка совпадают клетка-в-клетку. */
export const CELL = 20;      /* 5 мм */
export const CM = 40;        /* 1 см = две клетки */

export const SHEET_GROUP = "pb-sheet";
const uid = () => Math.random().toString(36).slice(2, 10);

const GRID_COLOR = "#94a3b8";
const MARGIN_COLOR = "#e03131";
const AXIS_COLOR = "#1e1e1e";

/* Общее для всего, что мы вставляем: чёткие линии, а не «от руки». Набросок
   хорош для мысли, но лист в клетку и транспортир обязаны быть точными —
   иначе по ним нельзя мерить, а мерить по ним и будут. */
export const EXACT = { roughness: 0, strokeWidth: 1, roundness: null };

/**
 * Ломаная в каноническом виде.
 *
 * ⚠️ ГРАБЛЯ, которую видно только по числам. Конвертер апстрима НЕ считает
 * рамку элемента по точкам: `width`/`height` остаются значениями по умолчанию
 * (100×0). Нарисуется такая ломаная правильно — рисование идёт по точкам, — но
 * выделение, поворот и попадание указателя считаются по рамке, поэтому
 * транспортир брался бы за воздух, а угольник поворачивался вокруг чужой
 * точки. Поэтому рамку считаем сами.
 *
 * Заодно приводим к канону: первая точка в начале координат элемента, а сдвиг
 * уходит в x/y — именно так выглядят ломаные, нарисованные самим редактором.
 */
export function poly(x, y, points, extra) {
	const [ox, oy] = points[0];
	const local = points.map(([px, py]) => [px - ox, py - oy]);
	const xs = local.map((p) => p[0]);
	const ys = local.map((p) => p[1]);
	return {
		type: "line",
		x: x + ox,
		y: y + oy,
		points: local,
		width: Math.max(...xs) - Math.min(...xs),
		height: Math.max(...ys) - Math.min(...ys),
		...EXACT,
		...extra,
	};
}

const line = (x, y, dx, dy, extra) => poly(x, y, [[0, 0], [dx, dy]], extra);

export const label = (x, y, text, extra) => ({
	type: "text",
	x, y, text,
	fontSize: 12,
	fontFamily: 2,          /* Nunito: цифры на линейке должны читаться, а не быть от руки */
	strokeColor: AXIS_COLOR,
	...extra,
});

/** Дуга как ломаная: одним элементом вместо десятков отрезков. */
function arcPoints(radius, fromDeg, toDeg, stepDeg) {
	const points = [];
	const step = toDeg >= fromDeg ? Math.abs(stepDeg) : -Math.abs(stepDeg);
	for (let a = fromDeg; step > 0 ? a <= toDeg : a >= toDeg; a += step) {
		const rad = (a * Math.PI) / 180;
		points.push([radius * Math.cos(rad), -radius * Math.sin(rad)]);
	}
	return points;
}

/**
 * Собирает готовые элементы: скелеты → элементы → общая группа и замок.
 *
 * groupIds и locked проставляются ПОСЛЕ преобразования, а не в скелете: так
 * они не зависят от того, какие поля конвертер апстрима решит пропустить.
 */
export function assemble(skeletons, { group, locked }) {
	return convertToExcalidrawElements(skeletons).map((element) => ({
		...element,
		groupIds: [group],
		locked: !!locked,
	}));
}

/* ── Инструменты: линейка, транспортир, угольник, циркуль ────────────────
 *
 * Цвета зависят от фона холста — так же, как у эталона (UBAbstractDrawRuler
 * держит две тройки цветов и выбирает по isDarkBackground). Жёлтая линейка на
 * зелёной доске выглядит грязным пятном, а её деления просто не читаются;
 * на тёмном фоне инструмент должен быть светлым и полупрозрачным.
 */
const SKIN = {
	light: {
		rulerFill: "#ffec99", rulerEdge: "#b08900", rulerInk: "#665500",
		protractorFill: "#a5d8ff", protractorEdge: "#1864ab", protractorInk: "#0b4a86",
		squareFill: "#b2f2bb", squareEdge: "#2b8a3e", squareInk: "#1b5e2a",
		metal: "#495057", hinge: "#ced4da",
	},
	dark: {
		rulerFill: "#dddddd", rulerEdge: "#ffffff", rulerInk: "#f8f9fa",
		protractorFill: "#c8d9ec", protractorEdge: "#e7f5ff", protractorInk: "#f1f3f5",
		squareFill: "#cfe8d4", squareEdge: "#ebfbee", squareInk: "#f1f3f5",
		metal: "#dee2e6", hinge: "#adb5bd",
	},
};

/* ── Инструменты: линейка, транспортир, угольник ─────────────────────────── */

/**
 * Шкала одной кромки ОДНОЙ ломаной: зубчатый путь вдоль края.
 *
 * У эталона (OpenBoard, UBGraphicsRuler::paintGraduations) деления идут через
 * миллиметр тремя высотами — миллиметр, полсантиметра, сантиметр — и по обеим
 * длинным кромкам. Двести отдельных отрезков на линейку мы бы не потянули,
 * поэтому вся шкала — один элемент: путь идёт по кромке и на каждом делении
 * ныряет внутрь и возвращается. Обратный ход рисуется поверх прямого и не
 * виден, зато элементов ровно один вместо двухсот.
 */
function scalePoints(lengthMm, direction) {
	const points = [[0, 0]];
	for (let mm = 0; mm <= lengthMm; mm++) {
		const x = (mm * CM) / 10;
		const tick = 0 === mm % 10 ? 16 : 0 === mm % 5 ? 11 : 6;
		points.push([x, 0], [x, direction * tick], [x, 0]);
	}
	return points;
}

function rulerSkeletons(skin, params) {
	const lengthCm = Math.min(60, Math.max(5, params.length || 20));
	const length = lengthCm * CM;
	const height = Math.round(2.6 * CM);
	const ink = skin.rulerInk;
	const out = [{
		type: "rectangle",
		x: 0, y: 0, width: length, height,
		backgroundColor: skin.rulerFill,
		fillStyle: "solid",
		strokeColor: skin.rulerEdge,
		opacity: 75,
		...EXACT,
	}];
	/* Шкала по ОБЕИМ кромкам — как у эталона: линейку кладут любой стороной. */
	out.push(poly(0, 0, scalePoints(lengthCm * 10, 1), { strokeColor: ink }));
	out.push(poly(0, height, scalePoints(lengthCm * 10, -1), { strokeColor: ink }));
	for (let cm = 0; cm <= lengthCm; cm++) {
		out.push(label(cm * CM + 3, 19, String(cm), { strokeColor: ink }));
	}
	return out;
}

function protractorSkeletons(skin, params) {
	const radius = Math.min(20, Math.max(2, params.radius || 6)) * CM;
	const out = [];

	/* Полукруг одним элементом: дуга плюс замыкание по диаметру.
	   ⚠️ Замыкать надо В ПЕРВУЮ точку, а не повторять последнюю: заливка у
	   ломаной появляется только когда контур замкнут, и с повтором последней
	   точки транспортир оставался прозрачным — видно лишь глазами, никакой
	   ошибки при этом нет. */
	const arc = arcPoints(radius, 0, 180, 2);
	arc.push([radius, 0]);
	out.push(poly(radius, radius, arc, {
		backgroundColor: skin.protractorFill,
		fillStyle: "solid",
		strokeColor: skin.protractorEdge,
		opacity: 65,
	}));

	for (let deg = 0; deg <= 180; deg += 10) {
		const rad = (deg * Math.PI) / 180;
		const big = 0 === deg % 30;
		const inner = radius - (big ? 26 : 14);
		const x1 = radius + inner * Math.cos(rad);
		const y1 = radius - inner * Math.sin(rad);
		const x2 = radius + radius * Math.cos(rad);
		const y2 = radius - radius * Math.sin(rad);
		out.push(line(x1, y1, x2 - x1, y2 - y1, { strokeColor: skin.protractorEdge }));
		if (big) {
			const t = radius - 44;
			out.push(label(radius + t * Math.cos(rad) - 9, radius - t * Math.sin(rad) - 7, String(deg), { strokeColor: skin.protractorInk }));
		}
	}
	/* Центр — по нему совмещают транспортир с вершиной угла. */
	out.push(line(radius - 8, radius, 16, 0, { strokeColor: skin.protractorInk, strokeWidth: 2 }));
	out.push(line(radius, radius - 8, 0, 16, { strokeColor: skin.protractorInk, strokeWidth: 2 }));
	return out;
}

/**
 * Циркуль: две ноги от шарнира, игла слева, грифель справа.
 *
 * Устройство подсмотрено у OpenBoard (src/tools/UBGraphicsCompass.cpp, GPL-3 —
 * только поведение, код не заимствован): у инструмента три зоны — шарнир,
 * раствор и плечо с грифелем; нажатие на грифель начинает дугу, а ведение
 * вращает циркуль вокруг иглы. Раствор там меняют кнопкой, у нас — растяжением
 * инструмента за уголок выделения: геометрия хранится долями от рамки, поэтому
 * радиус тянется вместе с ней.
 *
 * Ноги — ОДНА ломаная (игла → шарнир → грифель): так рамка тела охватывает весь
 * инструмент, а не половину, и попадание указателя считается по нему целиком.
 */
function compassSkeletons(radiusCm, skin) {
	const radius = Math.max(1, radiusCm || 5) * CM;
	const height = 6 * CM;        /* высота ног */
	const metal = skin.metal;
	const out = [
		poly(0, height, [[0, 0], [radius / 2, -height], [radius, 0]], {
			strokeColor: metal, strokeWidth: 4,
		}),
		/* Шарнир. */
		{ type: "ellipse", x: radius / 2 - 11, y: -11, width: 22, height: 22,
			strokeColor: metal, backgroundColor: skin.hinge, fillStyle: "solid", ...EXACT, strokeWidth: 2 },
		/* Игла: короткий острый штрих вниз. */
		poly(0, height - 14, [[0, 0], [0, 18]], { strokeColor: metal, strokeWidth: 2 }),
		/* Грифель: треугольник остриём вниз. */
		poly(radius - 7, height - 16, [[0, 0], [14, 0], [7, 18], [0, 0]], {
			strokeColor: skin.rulerEdge, backgroundColor: skin.rulerFill, fillStyle: "solid", strokeWidth: 1,
		}),
	];
	return out;
}

function setSquareSkeletons(kind, skin, params) {
	/* Два школьных угольника: 30-60-90 и 45-45-90. Задаётся длинный катет. */
	const leg = Math.min(40, Math.max(3, params.leg || ("45" === kind ? 9 : 10))) * CM;
	const legX = leg;
	const legY = "45" === kind ? leg : Math.round(leg * Math.tan(Math.PI / 6));
	const fill = { backgroundColor: skin.squareFill, fillStyle: "solid", strokeColor: skin.squareEdge, opacity: 70 };
	const out = [poly(0, 0, [[0, 0], [legX, 0], [0, legY], [0, 0]], fill)];
	const angles = "45" === kind ? ["90°", "45°", "45°"] : ["90°", "30°", "60°"];
	out.push(label(10, 8, angles[0], { strokeColor: skin.squareInk }));
	out.push(label(legX - 34, 8, angles[1], { strokeColor: skin.squareInk }));
	out.push(label(8, legY - 20, angles[2], { strokeColor: skin.squareInk }));
	return out;
}

/**
 * Рабочие кромки инструмента — в СКЕЛЕТНЫХ координатах (до сдвига на экран).
 *
 * Ради них всё и затевалось: карандаш должен вести по кромке, а не рядом с
 * картинкой. Кромки едут вместе с инструментом в customData его тела, и слой
 * прилипания (snap.js) достаёт их оттуда, поворачивая вместе с элементом.
 */
function instrumentGeometry(kind, options) {
	if ("ruler" === kind) {
		const length = Math.min(60, Math.max(5, options.length || 20)) * CM;
		const height = Math.round(2.6 * CM);
		/* Обе длинные кромки: линейку кладут любой стороной. */
		return { edges: [[[0, 0], [length, 0]], [[0, height], [length, height]]] };
	}
	if ("protractor" === kind) {
		const r = Math.min(20, Math.max(2, options.radius || 6)) * CM;
		/* Дуга плюс основание: по дуге отмечают градусы, по основанию чертят. */
		return { arc: { center: [r, r], radius: r, from: 0, to: 180 }, edges: [[[0, r], [2 * r, r]]] };
	}
	if ("compass" === kind) {
		const radius = Math.max(1, options.radius || 5) * CM, height = 6 * CM;
		/* Игла — центр будущей дуги, грифель — то, за что ведут. */
		return { compass: { needle: [0, height], pencil: [radius, height] } };
	}
	const leg = Math.min(40, Math.max(3, options.leg || ("square45" === kind ? 9 : 10))) * CM;
	const legX = leg;
	const legY = "square45" === kind ? leg : Math.round(leg * Math.tan(Math.PI / 6));
	/* Все три стороны: по двум катетам строят прямой угол, по гипотенузе — наклон. */
	return { edges: [[[0, 0], [legX, 0]], [[legX, 0], [0, legY]], [[0, legY], [0, 0]]] };
}

export function buildInstrument(kind, center, options) {
	const skin = options && options.dark ? SKIN.dark : SKIN.light;
	const params = options || {};
	const parts = "ruler" === kind ? rulerSkeletons(skin, params)
		: "protractor" === kind ? protractorSkeletons(skin, params)
		: "compass" === kind ? compassSkeletons(params.radius, skin)
		: setSquareSkeletons("square45" === kind ? "45" : "30", skin, params);

	/* Инструмент ставим по центру экрана и НЕ запираем: его берут, двигают и
	   поворачивают штатной ручкой — в этом весь смысл.
	   ⚠️ Центр считаем по ГРАНИЦАМ частей, а не по их началам. С началами
	   линейка вставала на 43 px выше центра: её деления начинаются в y=0, и
	   середина «по началам» приходилась на деления, а не на саму линейку.
	   Заметно это стало только когда карандаш начал искать её кромку. */
	const bounds = parts.reduce((box, part) => {
		/* ⚠️ У части С ТОЧКАМИ границы дают ТОЛЬКО точки: width/height у неё —
		   размер рамки, и складывать его с x,y нельзя, потому что x,y это первая
		   точка. Со сложением шкала линейки, у которой точки идут вверх (в
		   минус), задирала габарит на свою высоту, и инструмент вставал на
		   восемь пикселей мимо центра экрана. */
		const px = part.points ? part.points.map((pt) => pt[0]) : [0, part.width || 0];
		const py = part.points ? part.points.map((pt) => pt[1]) : [0, part.height || 0];
		return {
			x1: Math.min(box.x1, part.x + Math.min(...px)),
			y1: Math.min(box.y1, part.y + Math.min(...py)),
			x2: Math.max(box.x2, part.x + Math.max(...px)),
			y2: Math.max(box.y2, part.y + Math.max(...py)),
		};
	}, { x1: Infinity, y1: Infinity, x2: -Infinity, y2: -Infinity });
	const dx = center.x - (bounds.x1 + bounds.x2) / 2;
	const dy = center.y - (bounds.y1 + bounds.y2) / 2;
	const skeletons = parts.map((p) => ({ ...p, x: p.x + dx, y: p.y + dy }));
	const elements = assemble(skeletons, { group: "pb-tool-" + uid(), locked: false });

	/* Кромки кладём в тело инструмента (первый элемент) ДОЛЯМИ от его рамки, а
	   не пикселями: инструмент можно растянуть за уголок, и доли переживут
	   растяжение, а пиксели соврали бы.
	   ⚠️ Рамку считаем ПО СКЕЛЕТУ, а не по готовому элементу. У ломаной `x/y`
	   сразу после сборки — это начало её точек, а после того как сцена её
	   примет, редактор нормализует элемент, и `x/y` становится углом рамки. С
	   первым значением доли уезжали ровно на ширину инструмента, и транспортир
	   искал свою шкалу в стороне от себя. Доли от рамки не зависят ни от
	   сдвига, ни от того, какое из двух значений в элементе сейчас. */
	const bodyPart = parts[0];
	const px = bodyPart.points ? bodyPart.points.map((pt) => pt[0]) : [0, bodyPart.width || 0];
	const py = bodyPart.points ? bodyPart.points.map((pt) => pt[1]) : [0, bodyPart.height || 0];
	const x1 = bodyPart.x + Math.min(...px), x2 = bodyPart.x + Math.max(...px);
	const y1 = bodyPart.y + Math.min(...py), y2 = bodyPart.y + Math.max(...py);
	const boxW = x2 - x1 || 1, boxH = y2 - y1 || 1;
	const local = ([lx, ly]) => [(lx - (x1 + x2) / 2) / boxW, (ly - (y1 + y2) / 2) / boxH];
	const body = elements[0];
	const geometry = instrumentGeometry(kind, options || {});
	const data = {
		pbTool: kind,
		/* Размеры едут вместе с инструментом: панель показывает их числами и
		   пересобирает инструмент при правке. Пересобирает, а не растягивает —
		   растянутая линейка врала бы делениями. */
		params: { length: params.length, radius: params.radius, leg: params.leg, dark: !!params.dark },
		edges: (geometry.edges || []).map(([a, b]) => [local(a), local(b)]),
	};
	if (geometry.compass) {
		data.compass = { needle: local(geometry.compass.needle), pencil: local(geometry.compass.pencil) };
	}
	if (geometry.arc) {
		data.arc = {
			center: local(geometry.arc.center),
			radius: geometry.arc.radius / boxW,
			from: geometry.arc.from,
			to: geometry.arc.to,
		};
	}
	elements[0] = { ...body, customData: data };
	return elements;
}

/* ── Разбор и правка уже стоящего инструмента ────────────────────────────
 *
 * Панель показывает размеры выделенного инструмента числами и правит их. Правка
 * размера — это ПЕРЕСБОРКА инструмента на прежнем месте и под прежним углом:
 * растянуть линейку нельзя, иначе её деления перестанут быть сантиметрами.
 */

/** Рамка элемента с учётом того, что у ломаной x,y — первая точка. */
export function frameOf(el) {
	const px = el.points ? el.points.map((pt) => pt[0]) : [0, el.width || 0];
	const py = el.points ? el.points.map((pt) => pt[1]) : [0, el.height || 0];
	const minX = Math.min(...px), maxX = Math.max(...px);
	const minY = Math.min(...py), maxY = Math.max(...py);
	return {
		cx: el.x + (minX + maxX) / 2,
		cy: el.y + (minY + maxY) / 2,
		w: maxX - minX || el.width || 0,
		h: maxY - minY || el.height || 0,
	};
}

/**
 * Отметка «элемент изменился».
 *
 * ⚠️ Без неё правка не доживает до перезагрузки. Автосохранение сравнивает
 * СУММУ ВЕРСИЙ элементов (getSceneVersion): если подвинуть элемент, не подняв
 * версию, сумма не изменится, запись не состоится — и повёрнутая линейка после
 * перезагрузки прыгнет на прежнее место. На экране при этом всё правильно,
 * поэтому заметить можно только сравнив сцену с картинкой.
 */
const touched = (el, patch) => ({
	...el,
	...patch,
	version: (el.version || 1) + 1,
	versionNonce: Math.floor(Math.random() * 2 ** 31),
	updated: Date.now(),
});

/** Жёсткий поворот группы вокруг точки: вращаем ЦЕНТР РАМКИ каждого элемента. */
export function rotateGroup(elements, group, pivot, delta) {
	const cos = Math.cos(delta), sin = Math.sin(delta);
	return elements.map((el) => {
		if (!(el.groupIds || []).includes(group)) { return el; }
		const { cx, cy } = frameOf(el);
		const dx = cx - pivot.x, dy = cy - pivot.y;
		const nx = pivot.x + dx * cos - dy * sin;
		const ny = pivot.y + dx * sin + dy * cos;
		return touched(el, { x: el.x + (nx - cx), y: el.y + (ny - cy), angle: (el.angle || 0) + delta });
	});
}

export function translateGroup(elements, group, dx, dy) {
	return elements.map((el) =>
		(el.groupIds || []).includes(group) ? touched(el, { x: el.x + dx, y: el.y + dy }) : el);
}

/** Общая рамка группы. */
export function groupFrame(elements, group) {
	const box = { x1: Infinity, y1: Infinity, x2: -Infinity, y2: -Infinity };
	for (const el of elements) {
		if (!(el.groupIds || []).includes(group)) { continue; }
		const f = frameOf(el);
		box.x1 = Math.min(box.x1, f.cx - f.w / 2);
		box.y1 = Math.min(box.y1, f.cy - f.h / 2);
		box.x2 = Math.max(box.x2, f.cx + f.w / 2);
		box.y2 = Math.max(box.y2, f.cy + f.h / 2);
	}
	return { x: (box.x1 + box.x2) / 2, y: (box.y1 + box.y2) / 2 };
}

/**
 * Что за инструмент выделен: тело, группа, угол, размеры и точка иглы.
 * @returns {null|{kind,group,angle,params,center,needle}}
 */
export function selectedInstrument(elements, selectedIds) {
	const groups = new Set();
	for (const el of elements) {
		if (selectedIds && selectedIds[el.id]) {
			(el.groupIds || []).forEach((g) => { if (0 === String(g).indexOf("pb-tool-")) { groups.add(g); } });
		}
	}
	if (1 !== groups.size) { return null; }
	const group = [...groups][0];
	const body = elements.find((el) => el.customData && el.customData.pbTool && (el.groupIds || []).includes(group));
	if (!body) { return null; }
	const frame = frameOf(body);
	const angle = body.angle || 0;
	const place = ([fx, fy]) => {
		const lx = fx * frame.w, ly = fy * frame.h;
		return {
			x: frame.cx + lx * Math.cos(angle) - ly * Math.sin(angle),
			y: frame.cy + lx * Math.sin(angle) + ly * Math.cos(angle),
		};
	};
	return {
		kind: body.customData.pbTool,
		group,
		angle,
		params: body.customData.params || {},
		center: groupFrame(elements, group),
		needle: body.customData.compass ? place(body.customData.compass.needle) : null,
	};
}

/* ── Точные фигуры ───────────────────────────────────────────────────────── */

export function buildFigure(kind, params, center, stroke) {
	const color = stroke || AXIS_COLOR;
	const base = { ...EXACT, strokeColor: color, strokeWidth: 2 };
	const out = [];

	if ("segment" === kind) {
		const len = Math.max(0.5, params.length) * CM;
		const rad = (params.angle * Math.PI) / 180;
		const dx = len * Math.cos(rad), dy = -len * Math.sin(rad);
		out.push(poly(center.x - dx / 2, center.y - dy / 2, [[0, 0], [dx, dy]], base));
	}

	if ("circle" === kind) {
		const r = Math.max(0.5, params.radius) * CM;
		out.push({ type: "ellipse", x: center.x - r, y: center.y - r, width: 2 * r, height: 2 * r, ...base });
		out.push({ type: "ellipse", x: center.x - 3, y: center.y - 3, width: 6, height: 6, ...base, backgroundColor: color, fillStyle: "solid" });
	}

	if ("polygon" === kind) {
		const n = Math.min(12, Math.max(3, Math.round(params.sides)));
		const r = Math.max(0.5, params.radius) * CM;
		const points = [];
		for (let i = 0; i <= n; i++) {
			const a = (i / n) * Math.PI * 2 - Math.PI / 2;
			points.push([r * Math.cos(a), r * Math.sin(a)]);
		}
		out.push(poly(center.x, center.y, points, base));
	}

	if ("angle" === kind) {
		const deg = Math.min(179, Math.max(1, params.angle));
		const arm = 8 * CM;
		const rad = (deg * Math.PI) / 180;
		out.push(poly(center.x, center.y, [[0, 0], [arm, 0]], base));
		out.push(poly(center.x, center.y, [[0, 0], [arm * Math.cos(rad), -arm * Math.sin(rad)]], base));
		out.push(poly(center.x, center.y, arcPoints(2 * CM, 0, deg, 3), { ...base, strokeWidth: 1, opacity: 70 }));
		const mid = (rad / 2);
		out.push(label(center.x + 2.6 * CM * Math.cos(mid) - 10, center.y - 2.6 * CM * Math.sin(mid) - 8,
			deg + "°", { strokeColor: color, fontSize: 16 }));
	}

	return assemble(out, { group: "pb-figure-" + uid(), locked: false });
}
