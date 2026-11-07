/*
 * Измерения по выделенному: длина, угол, периметр, площадь.
 *
 * Это и есть транспортир с линейкой в честном виде. Настоящий транспортир на
 * экране можно только прикладывать на глаз (и он тоже есть — как объект,
 * который двигают и поворачивают), а здесь величина считается по самим
 * элементам сцены и показывается цифрой. Для «измерьте угол» на уроке цифра
 * полезнее картинки: по ней сразу видно, сошёлся ответ или нет.
 *
 * Считаем из публичных данных элемента, ничего не зная о внутренностях
 * редактора: координаты, точки ломаной и угол поворота — часть формата сцены.
 */

import { CELL, CM } from "./elements.js";

const rus = (n, digits) => n.toFixed(digits == null ? 1 : digits).replace(".", ",");

/** Длина в сантиметрах и клетках: у школьника на листе — клетки, у линейки — см. */
const len = (px) => `${rus(px / CM)} см · ${rus(px / CELL)} кл`;
const area = (px2) => `${rus(px2 / (CM * CM))} см² · ${rus(px2 / (CELL * CELL))} кл²`;
const deg = (d) => `${rus(d)}°`;

/** Поворот вектора на угол элемента: у повёрнутой линии направление другое. */
function rotate([x, y], angle) {
	if (!angle) { return [x, y]; }
	const c = Math.cos(angle), s = Math.sin(angle);
	return [x * c - y * s, x * s + y * c];
}

function polyPoints(element) {
	return (element.points || []).map((p) => rotate(p, element.angle || 0));
}

/** Направление отрезка в градусах от горизонтали, 0…180. */
function direction(element) {
	const pts = polyPoints(element);
	if (pts.length < 2) { return null; }
	const dx = pts[pts.length - 1][0] - pts[0][0];
	const dy = pts[pts.length - 1][1] - pts[0][1];
	let a = (Math.atan2(-dy, dx) * 180) / Math.PI;
	if (a < 0) { a += 180; }
	return a % 180;
}

function pathLength(pts) {
	let total = 0;
	for (let i = 1; i < pts.length; i++) {
		total += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
	}
	return total;
}

/** Площадь замкнутой ломаной по формуле шнурков. */
function shoelace(pts) {
	let sum = 0;
	for (let i = 0; i < pts.length - 1; i++) {
		sum += pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1];
	}
	return Math.abs(sum) / 2;
}

const isClosed = (pts) =>
	pts.length > 3 && Math.hypot(pts[0][0] - pts[pts.length - 1][0], pts[0][1] - pts[pts.length - 1][1]) < 6;

const centerOf = (el) => ({ x: el.x + (el.width || 0) / 2, y: el.y + (el.height || 0) / 2 });

/** Габарит элемента: для фигур это рамка, для ломаной — рамка её точек. */
const span = (el) => Math.hypot(Math.abs(el.width || 0), Math.abs(el.height || 0));

/**
 * Что в выделении считать самой фигурой.
 *
 * Наши вставки — группы: у окружности есть точка центра, у угла — два луча,
 * дуга и подпись. Без отбора выделение такой группы уходило бы в ветку «две
 * фигуры» и показывало расстояние между центрами вместо радиуса. Поэтому у
 * ОДНОЙ группы отбрасываем подписи и всё, что заметно мельче главного: у
 * окружности останется окружность, у угла — два луча (и тогда покажется угол
 * между ними, что и требовалось).
 */
function significant(items) {
	const first = (items[0].groupIds || [])[0];
	const oneGroup = items.length > 1 && first && items.every((el) => (el.groupIds || [])[0] === first);
	if (!oneGroup) { return items; }
	const sized = items.filter((el) => "text" !== el.type);
	if (!sized.length) { return items; }
	const max = Math.max(...sized.map(span));
	return max > 0 ? sized.filter((el) => span(el) >= max * 0.4) : sized;
}

/**
 * @param {Array} selected  выделенные элементы сцены
 * @returns {{title: string, rows: Array<[string,string]>}|null}
 */
export function measure(selected) {
	const all = (selected || []).filter((el) => el && !el.isDeleted);
	if (!all.length) { return null; }

	/* Линейку и транспортир не меряем: это инструменты, а не чертёж. Строка
	   мер про них выдавала бы «выделено фигур: 63» и только мешала. */
	if (all.every((el) => (el.groupIds || []).some((g) => 0 === String(g).indexOf("pb-tool-")))) {
		return null;
	}

	const items = significant(all);
	if (!items.length) { return null; }

	if (1 === items.length) {
		const el = items[0];

		if ("line" === el.type || "arrow" === el.type) {
			const pts = polyPoints(el);
			if (pts.length <= 2) {
				return {
					title: "arrow" === el.type ? "Стрелка" : "Отрезок",
					rows: [["Длина", len(pathLength(pts))], ["Угол к горизонтали", deg(direction(el))]],
				};
			}
			const closed = isClosed(pts);
			const rows = [[closed ? "Периметр" : "Длина", len(pathLength(pts))], ["Вершин", String(pts.length - (closed ? 1 : 0))]];
			if (closed) { rows.push(["Площадь", area(shoelace(pts))]); }
			return { title: closed ? "Многоугольник" : "Ломаная", rows };
		}

		if ("rectangle" === el.type || "diamond" === el.type) {
			const w = Math.abs(el.width), h = Math.abs(el.height);
			const isDiamond = "diamond" === el.type;
			return {
				title: isDiamond ? "Ромб" : (Math.abs(w - h) < 1 ? "Квадрат" : "Прямоугольник"),
				rows: [
					["Стороны", `${rus(w / CM)} × ${rus(h / CM)} см`],
					["Периметр", len(isDiamond ? 4 * Math.hypot(w / 2, h / 2) : 2 * (w + h))],
					["Площадь", area(isDiamond ? (w * h) / 2 : w * h)],
				],
			};
		}

		if ("ellipse" === el.type) {
			const a = Math.abs(el.width) / 2, b = Math.abs(el.height) / 2;
			if (Math.abs(a - b) < 1) {
				return {
					title: "Окружность",
					rows: [
						["Радиус", len(a)],
						["Диаметр", len(2 * a)],
						["Длина окружности", len(2 * Math.PI * a)],
						["Площадь круга", area(Math.PI * a * a)],
					],
				};
			}
			return {
				title: "Эллипс",
				rows: [["Полуоси", `${rus(a / CM)} и ${rus(b / CM)} см`], ["Площадь", area(Math.PI * a * b)]],
			};
		}

		if ("freedraw" === el.type) {
			return { title: "Линия от руки", rows: [["Длина следа", len(pathLength(polyPoints(el)))]] };
		}

		return null;
	}

	if (2 === items.length) {
		const [a, b] = items;
		const linear = items.filter((el) => ("line" === el.type || "arrow" === el.type) && (el.points || []).length >= 2);
		if (2 === linear.length) {
			let angle = Math.abs(direction(linear[0]) - direction(linear[1]));
			if (angle > 90) { angle = 180 - angle; }
			return {
				title: "Две прямые",
				rows: [
					["Угол между ними", `${deg(angle)} и ${deg(180 - angle)}`],
					["Длины", `${rus(pathLength(polyPoints(linear[0])) / CM)} и ${rus(pathLength(polyPoints(linear[1])) / CM)} см`],
				],
			};
		}
		const ca = centerOf(a), cb = centerOf(b);
		return {
			title: "Две фигуры",
			rows: [["Между центрами", len(Math.hypot(cb.x - ca.x, cb.y - ca.y))]],
		};
	}

	const xs = items.map((el) => [el.x, el.x + (el.width || 0)]).flat();
	const ys = items.map((el) => [el.y, el.y + (el.height || 0)]).flat();
	return {
		title: `Выделено фигур: ${items.length}`,
		rows: [["Габарит", `${rus((Math.max(...xs) - Math.min(...xs)) / CM)} × ${rus((Math.max(...ys) - Math.min(...ys)) / CM)} см`]],
	};
}
