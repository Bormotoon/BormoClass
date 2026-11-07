/*
 * Конструктор листа: линовка и сетка слоями.
 *
 * Устройство повторяет инструмент сетки ActivInspire, и не из подражания:
 * школьные разлиновки НЕ сводятся к «шагу клетки». Двойная линовка — это две
 * системы горизонталей с разным сдвигом и разным начертанием; косая линейка
 * для первого класса — те же две плюс наклонные под 65°; миллиметровка — три
 * системы с разной толщиной. Одним набором параметров это не описать, а
 * набором СЛОЁВ описывается ровно и без частных случаев.
 *
 * Слой:
 *   kind    h | v | slant   горизонтали, вертикали, наклонные
 *   step    шаг в миллиметрах (для наклонных — расстояние по горизонтали)
 *   offset  сдвиг первой линии в миллиметрах
 *   angle   наклон в градусах (только slant): 65° — стандарт прописей
 *   color / width / style / opacity — как выглядит
 *
 * Считаем в МИЛЛИМЕТРАХ, а в пиксели переводим на выходе. Причина простая:
 * учитель мыслит миллиметрами («клетка 5 мм», «строка 8 мм»), и любая другая
 * внутренняя единица превратила бы половину кода в перевод туда-обратно.
 */

import { assemble, EXACT, label, poly, SHEET_GROUP } from "./elements.js";

/** Пикселей в миллиметре. Согласовано с CM = 40 px в elements.js. */
export const MM = 4;

export const PAGES = {
	a4l: { w: 297, h: 210, name: "A4 альбомная" },
	a4p: { w: 210, h: 297, name: "A4 книжная" },
	a3l: { w: 420, h: 297, name: "A3 альбомная" },
};

export const LAYER_COLORS = ["#94a3b8", "#7ea6d8", "#86b892", "#d9a1b3", "#e03131", "#1e1e1e"];
export const LAYER_KINDS = [
	{ id: "h", name: "Горизонтали" },
	{ id: "v", name: "Вертикали" },
	{ id: "slant", name: "Наклонные" },
];

/* Потолок на число линий. Не из осторожности: лист — это заблокированные
   элементы сцены, и десять тысяч отрезков превращают панорамирование в кисель
   на школьном ноутбуке. 1500 проходит незаметно, миллиметровка на A4 в него
   укладывается (около тысячи). */
export const MAX_LINES = 1500;

let seq = 0;
const layer = (patch) => ({
	id: "L" + ++seq,
	on: true,
	kind: "h",
	step: 5,
	offset: 0,
	angle: 65,
	color: LAYER_COLORS[0],
	width: 1,
	style: "solid",
	opacity: 45,
	...patch,
});

/* ── Готовые разлиновки ──────────────────────────────────────────────────
   Это отправные точки, а не список возможного: любой пресет после выбора
   правится по слоям. */
export const PRESETS = [
	{
		id: "cells5", name: "Клетка 5 мм",
		sheet: { page: "a4l", margin: 0, axes: false, layers: [layer({ kind: "h", step: 5 }), layer({ kind: "v", step: 5 })] },
	},
	{
		id: "cells10", name: "Клетка 1 см",
		sheet: { page: "a4l", margin: 0, axes: false, layers: [layer({ kind: "h", step: 10 }), layer({ kind: "v", step: 10 })] },
	},
	{
		id: "lined", name: "Линовка",
		sheet: { page: "a4p", margin: 30, axes: false, layers: [layer({ kind: "h", step: 9, color: "#7ea6d8", opacity: 55 })] },
	},
	{
		/* Двойная линовка (тетрадь «в две линии»): строка 8 мм зажата между
		   двумя СПЛОШНЫМИ, между строками — такой же промежуток. Обе системы
		   с шагом 16 мм, вторая сдвинута на 8: сдвиг здесь и делает пару. */
		id: "double", name: "Двойная линовка",
		sheet: {
			page: "a4p", margin: 30, axes: false,
			layers: [
				layer({ kind: "h", step: 16, offset: 16, color: "#7ea6d8", opacity: 70 }),
				layer({ kind: "h", step: 16, offset: 8, color: "#7ea6d8", opacity: 70 }),
			],
		},
	},
	{
		/* Косая линейка первого класса: строки через 9 мм, ровно посередине
		   пунктирная (по ней держат высоту строчных букв), и наклонные под
		   65° — этот угол и задаёт наклон почерка в прописях. */
		id: "slanted", name: "Косая линейка",
		sheet: {
			page: "a4p", margin: 30, axes: false,
			layers: [
				layer({ kind: "h", step: 9, offset: 9, color: "#7ea6d8", opacity: 65 }),
				layer({ kind: "h", step: 9, offset: 4.5, color: "#7ea6d8", style: "dashed", opacity: 35 }),
				layer({ kind: "slant", step: 12, angle: 65, color: "#7ea6d8", opacity: 30 }),
			],
		},
	},
	{
		id: "coords", name: "Координатная плоскость",
		sheet: { page: "a4l", margin: 0, axes: true, layers: [layer({ kind: "h", step: 10, opacity: 30 }), layer({ kind: "v", step: 10, opacity: 30 })] },
	},
	{
		/* Миллиметровка: три системы, каждая заметнее предыдущей. */
		id: "graph", name: "Миллиметровка",
		sheet: {
			page: "a4l", margin: 0, axes: false,
			layers: [
				layer({ kind: "h", step: 1, color: "#d9a1b3", opacity: 25 }),
				layer({ kind: "v", step: 1, color: "#d9a1b3", opacity: 25 }),
				layer({ kind: "h", step: 5, color: "#d9a1b3", opacity: 55 }),
				layer({ kind: "v", step: 5, color: "#d9a1b3", opacity: 55 }),
				layer({ kind: "h", step: 10, color: "#d9a1b3", opacity: 85, width: 2 }),
				layer({ kind: "v", step: 10, color: "#d9a1b3", opacity: 85, width: 2 }),
			],
		},
	},
	{
		id: "iso", name: "Изометрия",
		sheet: {
			page: "a4l", margin: 0, axes: false,
			layers: [
				layer({ kind: "v", step: 10, opacity: 35 }),
				layer({ kind: "slant", step: 10, angle: 30, opacity: 35 }),
				layer({ kind: "slant", step: 10, angle: 150, opacity: 35 }),
			],
		},
	},
	{ id: "blank", name: "Чистый лист", sheet: { page: "a4l", margin: 0, axes: false, layers: [] } },
];

export const newLayer = layer;
export const presetSheet = (id) => clone((PRESETS.find((p) => p.id === id) || PRESETS[0]).sheet);
export const clone = (sheet) => JSON.parse(JSON.stringify(sheet));

/* ── Геометрия ───────────────────────────────────────────────────────────── */

/**
 * Обрезка прямой по прямоугольнику листа.
 *
 * Наклонная линия задана точкой и направлением и почти всегда выходит за лист;
 * рисовать её целиком нельзя — получится клякса за краем страницы. Считаем два
 * параметра пересечения с полосами x∈[0,w] и y∈[0,h] и берём их перекрытие.
 */
function clip(px, py, dx, dy, w, h) {
	let t0 = -Infinity, t1 = Infinity;
	const slab = (p, d, min, max) => {
		if (Math.abs(d) < 1e-9) { return p >= min && p <= max; }
		const a = (min - p) / d, b = (max - p) / d;
		t0 = Math.max(t0, Math.min(a, b));
		t1 = Math.min(t1, Math.max(a, b));
		return true;
	};
	if (!slab(px, dx, 0, w) || !slab(py, dy, 0, h) || t0 >= t1) { return null; }
	return [px + dx * t0, py + dy * t0, px + dx * t1, py + dy * t1];
}

/**
 * Все линии разлиновки в миллиметрах: [{x1,y1,x2,y2,layer}].
 *
 * Одна функция и для листа, и для предпросмотра в панели — иначе предпросмотр
 * рано или поздно начнёт врать, а он ровно для того и нужен, чтобы не врал.
 */
export function rulingLines(sheet, limit) {
	const page = PAGES[sheet.page] || PAGES.a4l;
	const { w, h } = page;
	const out = [];
	const cap = limit || MAX_LINES;

	for (const L of sheet.layers) {
		if (!L.on || !(L.step > 0)) { continue; }
		const step = Math.max(0.5, L.step);
		const offset = ((L.offset % step) + step) % step;

		if ("h" === L.kind) {
			for (let y = offset; y <= h + 1e-6; y += step) {
				out.push({ x1: 0, y1: y, x2: w, y2: y, layer: L });
				if (out.length >= cap) { return out; }
			}
		} else if ("v" === L.kind) {
			for (let x = offset; x <= w + 1e-6; x += step) {
				out.push({ x1: x, y1: 0, x2: x, y2: h, layer: L });
				if (out.length >= cap) { return out; }
			}
		} else {
			/* Наклонные: шаг задан ПО ГОРИЗОНТАЛИ — именно так меряют
			   расстояние между косыми в тетради. Начинаем левее листа на
			   столько, сколько наклонная «съедает» по горизонтали на его
			   высоте, иначе левый нижний угол останется пустым. */
			const rad = (L.angle * Math.PI) / 180;
			const dx = Math.cos(rad), dy = -Math.sin(rad);
			const shift = Math.abs(dy) > 1e-6 ? Math.abs((h * dx) / dy) : 0;
			for (let x = offset - shift; x <= w + shift + 1e-6; x += step) {
				const seg = clip(x, h, dx, dy, w, h);
				if (seg) {
					out.push({ x1: seg[0], y1: seg[1], x2: seg[2], y2: seg[3], layer: L });
					if (out.length >= cap) { return out; }
				}
			}
		}
	}
	return out;
}

/** Сколько линий выйдет — для предупреждения в панели. */
export function countLines(sheet) {
	return rulingLines(sheet, MAX_LINES + 1).length;
}

/* ── Оси координат ───────────────────────────────────────────────────────── */

function axesSkeletons(page) {
	const w = page.w * MM, h = page.h * MM;
	const unit = 10 * MM;                       /* деление — сантиметр */
	const cx = Math.round(w / 2 / unit) * unit;
	const cy = Math.round(h / 2 / unit) * unit;
	const AXIS = "#1e1e1e";
	const out = [
		{ ...poly(0, cy, [[0, 0], [w, 0]], { strokeColor: AXIS, strokeWidth: 2 }), type: "arrow" },
		{ ...poly(cx, h, [[0, 0], [0, -h]], { strokeColor: AXIS, strokeWidth: 2 }), type: "arrow" },
		label(w - 26, cy + 8, "x", { fontSize: 16 }),
		label(cx + 10, 4, "y", { fontSize: 16 }),
		label(cx - 14, cy + 6, "0", { fontSize: 14 }),
	];
	const tick = (x, y, dx, dy) => out.push(poly(x, y, [[0, 0], [dx, dy]], { strokeColor: AXIS }));
	/* Засечки на каждой единице, подписи через одну: подписи на каждой
	   сливаются в кашу уже при двух пальцах масштаба. */
	for (let x = cx + unit, n = 1; x < w - 20; x += unit, n++) {
		tick(x, cy - 4, 0, 8);
		if (0 === n % 2) { out.push(label(x - 4, cy + 7, String(n))); }
	}
	for (let x = cx - unit, n = 1; x > 20; x -= unit, n++) {
		tick(x, cy - 4, 0, 8);
		if (0 === n % 2) { out.push(label(x - 8, cy + 7, "−" + n)); }
	}
	for (let y = cy - unit, n = 1; y > 20; y -= unit, n++) {
		tick(cx - 4, y, 8, 0);
		if (0 === n % 2) { out.push(label(cx + 8, y - 7, String(n))); }
	}
	for (let y = cy + unit, n = 1; y < h - 20; y += unit, n++) {
		tick(cx - 4, y, 8, 0);
		if (0 === n % 2) { out.push(label(cx + 8, y - 7, "−" + n)); }
	}
	return out;
}

/* ── Сборка листа ────────────────────────────────────────────────────────── */

export function buildRulingSheet(sheet, center) {
	const page = PAGES[sheet.page] || PAGES.a4l;
	const w = page.w * MM, h = page.h * MM;

	const parts = [{
		type: "rectangle",
		x: 0, y: 0, width: w, height: h,
		backgroundColor: "#ffffff",
		fillStyle: "solid",
		strokeColor: "#cbd5e1",
		...EXACT,
	}];

	for (const line of rulingLines(sheet)) {
		parts.push(poly(line.x1 * MM, line.y1 * MM,
			[[0, 0], [(line.x2 - line.x1) * MM, (line.y2 - line.y1) * MM]], {
				strokeColor: line.layer.color,
				strokeWidth: line.layer.width,
				strokeStyle: line.layer.style,
				opacity: line.layer.opacity,
			}));
	}

	if (sheet.margin > 0) {
		parts.push(poly(sheet.margin * MM, 0, [[0, 0], [0, h]], {
			strokeColor: "#e03131", opacity: 55,
		}));
	}

	if (sheet.axes) {
		parts.push(...axesSkeletons(page));
	}

	const skeletons = parts.map((p) => ({ ...p, x: p.x + center.x - w / 2, y: p.y + center.y - h / 2 }));
	return assemble(skeletons, { group: SHEET_GROUP + "-" + Math.random().toString(36).slice(2, 10), locked: true });
}
