/*
 * Дополняет русский словарь апстрима строками, которых в нём нет.
 *
 * Зачем. В словаре ru-RU версии 0.18.1 не хватает 56 строк из 424, и на их
 * месте редактор молча показывает английский — без ошибки, без пустого места.
 * Так на снимке для лендинга оказалась подсказка «Нажмите Enter для добавления
 * текста. Hold Ctrl and Arrow key to create a flowchart»: первая половина
 * переведена, вторая нет. Кроме подсказок это виды стрелок, «Очистить холст»,
 * «Вписать всё в экран», палитра команд, поиск по холсту и весь список
 * названий фигур.
 *
 * Как. Правим не исходник, а СОБРАННЫЙ апстримом чанк словаря
 * (node_modules/…/dist/prod/locales/ru-RU-*.js) — до сборки нашего бандла,
 * чтобы Vite взял уже дополненный. Чанк устроен так:
 *
 *     import"../chunk-….js";var r={…},a={…},…,f={labels:r,hints:s,…};
 *     export{i as alerts,…,f as default,…};
 *
 * Секции здесь — те же объекты, на которые ссылается композит `f`, поэтому
 * достаточно слить наши строки в него: и default, и именованные экспорты
 * увидят добавленное, потому что это одни и те же объекты.
 *
 * ⚠️ Скрипт ОБЯЗАН падать, а не молчать: если апстрим переименует экспорт или
 * сменит форму чанка, перевод молча исчезнет — как исчезали строки, ради
 * которых он написан. Поэтому проверяется всё: и файл, и экспорт, и то, что
 * после вставки текст на месте.
 */

import { readdirSync, readFileSync, writeFileSync } from "node:fs";

const LOCALES = "node_modules/@excalidraw/excalidraw/dist/prod/locales";

const extra = JSON.parse(readFileSync(new URL("./ru-extra.json", import.meta.url), "utf8"));
delete extra._comment;

const file = readdirSync(LOCALES).find((n) => n.startsWith("ru-RU-") && n.endsWith(".js"));
if (!file) {
  console.error(`перевод: в ${LOCALES} нет файла ru-RU-*.js — апстрим сменил раскладку локалей`);
  process.exit(1);
}

const path = `${LOCALES}/${file}`;
const source = readFileSync(path, "utf8");

const exportAt = source.lastIndexOf("export{");
if (exportAt < 0) {
  console.error("перевод: в чанке словаря нет export{…}");
  process.exit(1);
}

const defaultVar = /([A-Za-z_$][\w$]*) as default/.exec(source.slice(exportAt));
if (!defaultVar) {
  console.error("перевод: в export{…} нет «X as default» — некуда сливать");
  process.exit(1);
}

/* Слияние вглубь: наши строки не заменяют секцию целиком, а дописываются в
   неё. Заменять целиком нельзя — в секции labels апстрима 200 строк, и все
   они переведены. */
/*
 * ⚠️ Разделов, которых в словаре НЕТ ЦЕЛИКОМ, мало добавить в композит.
 * Редактор читает словарь как пространство имён модуля, то есть по ИМЕНОВАННЫМ
 * экспортам: `search`, `commandPalette` и прочие новые разделы, дописанные
 * только в объект default, оставались невидимыми — в главном меню так и висели
 * «Find on canvas» и «Command palette». Поэтому для отсутствующих разделов
 * заводим переменные и дописываем их в список экспорта.
 */
const exportBody = source.slice(exportAt);
const exported = new Set([...exportBody.matchAll(/([A-Za-z_$][\w$]*) as ([A-Za-z_$][\w$]*)/g)].map((m) => m[2]));
const missing = Object.keys(extra).filter((section) => !exported.has(section));

const merge =
  `;var pbExtra=${JSON.stringify(extra)};` +
  `(function deep(target,source){for(var key in source){` +
  `if(source[key]&&typeof source[key]==="object"&&target[key]&&typeof target[key]==="object"){deep(target[key],source[key]);}` +
  `else{target[key]=source[key];}}})(${defaultVar[1]},pbExtra);` +
  missing.map((section, i) => `var pbX${i}=pbExtra[${JSON.stringify(section)}];`).join("");

const closing = source.indexOf("}", exportAt);
const patched =
  source.slice(0, exportAt) + merge +
  source.slice(exportAt, closing) +
  missing.map((section, i) => `,pbX${i} as ${section}`).join("") +
  source.slice(closing);
writeFileSync(path, patched);
if (missing.length) {
  console.log(`перевод: дописаны целые разделы (${missing.join(", ")})`);
}

const added = Object.values(extra).reduce((n, section) => n + Object.keys(section).length, 0);
if (!readFileSync(path, "utf8").includes("Вписать всё в экран")) {
  console.error("перевод: вставка не доехала до файла");
  process.exit(1);
}
console.log(`перевод: ${added} строк дописано в ${file}`);
