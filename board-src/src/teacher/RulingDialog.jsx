/*
 * Конструктор листа: слои разлиновки, предпросмотр, размер страницы.
 *
 * Отдельным окном, а не строчкой в боковой панели: у слоя восемь свойств, а
 * слоёв бывает шесть (миллиметровка) — в колонке шириной 330 px это
 * превратилось бы в лестницу, по которой невозможно попасть пальцем.
 *
 * Предпросмотр считает ТУ ЖЕ функцию rulingLines, что и настоящий лист. Иначе
 * он рано или поздно начнёт врать — а он ровно для того и нужен, чтобы не врал.
 */

import { useMemo, useState } from "react";
import {
	clone,
	countLines,
	LAYER_COLORS,
	LAYER_KINDS,
	MAX_LINES,
	newLayer,
	PAGES,
	PRESETS,
	presetSheet,
	rulingLines,
} from "./ruling.js";

const WIDTHS = [{ v: 1, name: "Тонкая" }, { v: 2, name: "Средняя" }, { v: 4, name: "Жирная" }];
const STYLES = [{ v: "solid", name: "Сплошная" }, { v: "dashed", name: "Пунктир" }, { v: "dotted", name: "Точки" }];

/** Предпросмотр: кусок листа целиком, вписанный в отведённое место. */
function Preview({ sheet }) {
	const page = PAGES[sheet.page] || PAGES.a4l;
	const lines = useMemo(() => rulingLines(sheet), [sheet]);
	return (
		<svg className="pbr__preview" viewBox={`0 0 ${page.w} ${page.h}`} role="img"
			aria-label={`Предпросмотр листа ${page.name}, линий: ${lines.length}`}>
			<rect x="0" y="0" width={page.w} height={page.h} fill="#fff" stroke="#cbd5e1" strokeWidth="0.4" />
			{lines.map((l, i) => (
				<line key={i} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2}
					stroke={l.layer.color}
					strokeWidth={l.layer.width * 0.25}
					strokeOpacity={l.layer.opacity / 100}
					strokeDasharray={"dashed" === l.layer.style ? "2 1.4" : "dotted" === l.layer.style ? "0.4 1.2" : undefined}
					strokeLinecap={"dotted" === l.layer.style ? "round" : undefined} />
			))}
			{sheet.margin > 0 && (
				<line x1={sheet.margin} y1="0" x2={sheet.margin} y2={page.h} stroke="#e03131" strokeWidth="0.4" strokeOpacity="0.55" />
			)}
			{sheet.axes && (
				<g stroke="#1e1e1e" strokeWidth="0.5">
					<line x1="0" y1={page.h / 2} x2={page.w} y2={page.h / 2} />
					<line x1={page.w / 2} y1="0" x2={page.w / 2} y2={page.h} />
				</g>
			)}
		</svg>
	);
}

export default function RulingDialog({ initial, onApply, onClose, onSnap }) {
	const [sheet, setSheet] = useState(() => clone(initial));

	const total = countLines(sheet);
	const tooMany = total > MAX_LINES;

	const patch = (id, change) =>
		setSheet((s) => ({ ...s, layers: s.layers.map((l) => (l.id === id ? { ...l, ...change } : l)) }));
	const remove = (id) => setSheet((s) => ({ ...s, layers: s.layers.filter((l) => l.id !== id) }));
	const add = () => setSheet((s) => ({ ...s, layers: [...s.layers, newLayer({})] }));
	const move = (index, delta) =>
		setSheet((s) => {
			const layers = s.layers.slice();
			const to = index + delta;
			if (to < 0 || to >= layers.length) { return s; }
			[layers[index], layers[to]] = [layers[to], layers[index]];
			return { ...s, layers };
		});

	return (
		<div className="pbr__backdrop" role="dialog" aria-modal="true" aria-label="Конструктор листа">
			<div className="pbr">
				<header className="pbr__head">
					<b>Конструктор листа</b>
					<button type="button" className="pbt__close" onClick={onClose} aria-label="Закрыть">×</button>
				</header>

				<div className="pbr__body">
					<div className="pbr__left">
						<Preview sheet={sheet} />

						<label className="pbr__field">Размер листа
							<select value={sheet.page} onChange={(e) => setSheet({ ...sheet, page: e.target.value })}>
								{Object.entries(PAGES).map(([id, p]) => (
									<option key={id} value={id}>{p.name} — {p.w}×{p.h} мм</option>
								))}
							</select>
						</label>

						<label className="pbr__check">
							<input type="checkbox" checked={sheet.margin > 0}
								onChange={(e) => setSheet({ ...sheet, margin: e.target.checked ? 30 : 0 })} />
							Поле слева
						</label>
						{sheet.margin > 0 && (
							<label className="pbr__field">Отступ поля, мм
								<input type="number" min="5" max="80" step="5" value={sheet.margin}
									onChange={(e) => setSheet({ ...sheet, margin: +e.target.value })} />
							</label>
						)}

						<label className="pbr__check">
							<input type="checkbox" checked={!!sheet.axes}
								onChange={(e) => setSheet({ ...sheet, axes: e.target.checked })} />
							Оси координат с подписями
						</label>

						<p className={"pbr__count" + (tooMany ? " is-warn" : "")}>
							{tooMany
								? `Линий больше ${MAX_LINES} — лист станет тяжёлым, лишние обрежутся. Увеличьте шаг или возьмите лист меньше.`
								: `Линий на листе: ${total}`}
						</p>
					</div>

					<div className="pbr__right">
						<div className="pbr__presets">
							{PRESETS.map((p) => (
								<button type="button" key={p.id} className="pbt__btn pbt__btn--small"
									onClick={() => setSheet(presetSheet(p.id))}>
									{p.name}
								</button>
							))}
						</div>

						<div className="pbr__layers">
							{sheet.layers.map((L, index) => (
								<div className={"pbr__layer" + (L.on ? "" : " is-off")} key={L.id}>
									<div className="pbr__layer-row">
										<label className="pbr__check pbr__check--tight" title="Показывать слой">
											<input type="checkbox" checked={L.on} onChange={(e) => patch(L.id, { on: e.target.checked })} />
										</label>

										<select value={L.kind} onChange={(e) => patch(L.id, { kind: e.target.value })} aria-label="Тип слоя">
											{LAYER_KINDS.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
										</select>

										<label className="pbr__num">шаг
											<input type="number" min="0.5" step="0.5" value={L.step}
												onChange={(e) => patch(L.id, { step: +e.target.value })} />
										</label>
										<label className="pbr__num">сдвиг
											<input type="number" step="0.5" value={L.offset}
												onChange={(e) => patch(L.id, { offset: +e.target.value })} />
										</label>
										{"slant" === L.kind && (
											<label className="pbr__num">угол
												<input type="number" min="1" max="179" step="1" value={L.angle}
													onChange={(e) => patch(L.id, { angle: +e.target.value })} />
											</label>
										)}

										<span className="pbr__spacer" />
										<button type="button" className="pbr__icon" title="Выше" onClick={() => move(index, -1)}>↑</button>
										<button type="button" className="pbr__icon" title="Ниже" onClick={() => move(index, 1)}>↓</button>
										<button type="button" className="pbr__icon pbr__icon--del" title="Удалить слой" onClick={() => remove(L.id)}>×</button>
									</div>

									<div className="pbr__layer-row pbr__layer-row--look">
										<span className="pbr__colors">
											{LAYER_COLORS.map((c) => (
												<button type="button" key={c} className={"pbr__color" + (L.color === c ? " is-on" : "")}
													style={{ background: c }} title={c} aria-label={"Цвет " + c}
													onClick={() => patch(L.id, { color: c })} />
											))}
										</span>

										<select value={L.width} onChange={(e) => patch(L.id, { width: +e.target.value })} aria-label="Толщина">
											{WIDTHS.map((w) => <option key={w.v} value={w.v}>{w.name}</option>)}
										</select>

										<select value={L.style} onChange={(e) => patch(L.id, { style: e.target.value })} aria-label="Начертание">
											{STYLES.map((s) => <option key={s.v} value={s.v}>{s.name}</option>)}
										</select>

										<label className="pbr__num pbr__num--wide">видимость
											<input type="range" min="10" max="100" step="5" value={L.opacity}
												onChange={(e) => patch(L.id, { opacity: +e.target.value })} />
										</label>

										{/* Прилипание у Excalidraw одно на холст, поэтому это не свойство
										    слоя, а действие: «пусть фигуры липнут к ЭТОМУ шагу». */}
										<button type="button" className="pbt__btn pbt__btn--small" title="Сделать шаг этого слоя шагом привязки"
											onClick={() => onSnap(L.step)}>
											Привязка
										</button>
									</div>
								</div>
							))}
						</div>

						<button type="button" className="pbt__btn pbt__btn--quiet" onClick={add}>Добавить слой</button>
					</div>
				</div>

				<footer className="pbr__foot">
					<span className="pbr__hint">Лист встанет по центру экрана и будет заперт, чтобы не мешать чертежу.</span>
					<button type="button" className="pbt__btn" onClick={onClose}>Отмена</button>
					<button type="button" className="pbt__btn pbr__apply" onClick={() => onApply(sheet)}>Поставить лист</button>
				</footer>
			</div>
		</div>
	);
}
