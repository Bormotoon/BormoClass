import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // base: "./" — адреса ассетов в index.html относительные. Обязательно:
  // приложение живёт под префиксом (app.педобраз.рф/board/), а Caddy этот
  // префикс срезает (handle_path), то есть контейнер видит запросы от корня.
  // С абсолютным base браузер просил бы /assets/… мимо префикса и получал 404.
  base: "./",
  plugins: [react()],
  build: {
    target: "es2022",
    // Чанки здесь большие по природе (холст, mermaid, katex), дробить нечего:
    // всё, кроме основного, и так грузится лениво. Предупреждение только шумит.
    chunkSizeWarningLimit: 2048,
  },
});
