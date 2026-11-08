// Вырезает из СОБРАННОГО бандла запасной адрес шрифтов на чужом CDN
// и вырезает upstream demo API-ключи Firebase.

import { readdirSync, readFileSync, writeFileSync } from "node:fs";

const dir = "dist/assets";
const pattern = /return\s+(\w+)\.push\(new URL\((\w+),\s*(\w+)\.ASSETS_FALLBACK_URL\)\),\s*\1/g;
const secretPattern = new RegExp("AIza" + "Sy[A-Za-z0-9_-]{33}", "g");

let patched = 0;
let secretsStripped = 0;
for (const name of readdirSync(dir).filter((n) => n.endsWith(".js"))) {
  const path = `${dir}/${name}`;
  const source = readFileSync(path, "utf8");
  let result = source.replace(pattern, (_match, list) => {
    patched += 1;
    return `return ${list}`;
  });

  result = result.replace(secretPattern, () => {
    secretsStripped += 1;
    return "";
  });

  if (result !== source) {
    writeFileSync(path, result);
    console.log(`патч: обработан файл ${name}`);
  }
}

if (patched !== 1) {
  console.error(
    `патч: ожидали ровно одно место с ASSETS_FALLBACK_URL, нашли ${patched}. ` +
      `Апстрим переписал загрузчик шрифтов — проверить руками и поправить регулярку.`,
  );
  process.exit(1);
}

console.log(`патч: успешно применён (CDN вырезан: ${patched}, секретов очищено: ${secretsStripped})`);
