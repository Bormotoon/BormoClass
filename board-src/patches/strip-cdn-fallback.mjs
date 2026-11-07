// Вырезает из СОБРАННОГО бандла запасной адрес шрифтов на чужом CDN.
//
// Зачем. Шрифты рисунка библиотека грузит через fetch, и список адресов
// собирает так (excalidraw/fonts, метод createUrls):
//
//     …свой путь из window.EXCALIDRAW_ASSET_PATH…
//     return r.push(new URL(n, X.ASSETS_FALLBACK_URL)), r
//
// Запасной адрес (https://esm.sh/@excalidraw/excalidraw@версия/dist/prod/)
// добавляется ВСЕГДА, даже когда свой путь задан и файлы на месте, — и запросы
// уходят по обоим адресам сразу, а не по очереди. Замерено браузером
// (23.08.2026): на один текстовый блок 2 запроса к себе и 230 к esm.sh.
//
// CSP в nginx.conf их блокирует, наружу они не уходят — но остаются 230
// сообщений об ошибке в консоли при каждом открытии доски. Консоль, забитая
// штатным мусором, — это консоль, в которой не видно настоящей ошибки.
// Поэтому режем сам вызов: остаётся только свой путь.
//
// ⚠️ Правка по минифицированному коду, поэтому она ОБЯЗАНА падать, а не
// молчать: если апстрим переписал это место, замена не найдётся и сборка
// остановится здесь. Имена переменных минификатор меняет от сборки к сборке,
// поэтому зацеплено имя свойства ASSETS_FALLBACK_URL — оно строковое и
// переживает минификацию.

import { readdirSync, readFileSync, writeFileSync } from "node:fs";

const dir = "dist/assets";
const pattern = /return\s+(\w+)\.push\(new URL\((\w+),\s*(\w+)\.ASSETS_FALLBACK_URL\)\),\s*\1/g;

let patched = 0;
for (const name of readdirSync(dir).filter((n) => n.endsWith(".js"))) {
  const path = `${dir}/${name}`;
  const source = readFileSync(path, "utf8");
  const result = source.replace(pattern, (_match, list) => {
    patched += 1;
    return `return ${list}`;
  });
  if (result !== source) {
    writeFileSync(path, result);
    console.log(`патч: запасной CDN вырезан из ${name}`);
  }
}

if (patched !== 1) {
  console.error(
    `патч: ожидали ровно одно место с ASSETS_FALLBACK_URL, нашли ${patched}. ` +
      `Апстрим переписал загрузчик шрифтов — проверить руками и поправить регулярку.`,
  );
  process.exit(1);
}
