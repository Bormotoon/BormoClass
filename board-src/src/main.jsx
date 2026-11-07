// Интерактивная доска app.педобраз.рф/board/.
//
// Это ТОНКАЯ ОБЁРТКА вокруг пакета @excalidraw/excalidraw (MIT), а не форк
// приложения excalidraw.com. Разница принципиальная, и выбор сделан осознанно:
// в готовом приложении апстрима зашиты Firebase, Sentry, аналитика, реклама
// Excalidraw+ и их сервер совместной работы — всё это пришлось бы вырезать
// патчами по минифицированному коду (как в соседнем mindmap, где apply.sh
// разросся до 37 КБ). Пакет же не содержит ничего из этого по построению:
// холст, панели и словари — и всё. Взамен хост-приложение обязано само
// сделать три вещи, которые в готовом приложении уже есть:
//   1) сохранение рисунка между заходами  → IndexedDB ниже;
//   2) сохранение личной библиотеки фигур → тот же IndexedDB, адаптер;
//   3) состав меню                        → <MainMenu> ниже.
//
// Бэкенда нет и не планируется: рисунок никуда не отправляется, всё считает и
// хранит браузер. Единственное исключение — кнопка учителя «☁ Заготовки» (Пульт
// в Паспорте): по явному нажатию сцена уходит в Паспорт через window.pbBoard ниже. Совместный режим (если он когда-нибудь появится) — это
// отдельный ретранслятор, и его включение будет отдельным, видимым решением.

import { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Excalidraw,
  MainMenu,
  WelcomeScreen,
  getNonDeletedElements,
  getSceneVersion,
  useHandleLibrary,
} from "@excalidraw/excalidraw";
import "@excalidraw/excalidraw/index.css";
import TeacherPanel, { MeasureBar } from "./teacher/Panel.jsx";
import SnapLayer from "./teacher/SnapLayer.jsx";
import { measure } from "./teacher/measure.js";
import { selectedInstrument } from "./teacher/elements.js";

// ── Хранилище ────────────────────────────────────────────────────────────────
// IndexedDB, а не localStorage (как у mindmap): на доску вставляют фотографии,
// а Excalidraw хранит их прямо в сцене строками data:. localStorage упёрся бы
// в свои ~5 МБ на первой же паре снимков с телефона — и упал бы молча, посреди
// урока. У IndexedDB такого потолка нет, а бинарные данные она хранит как есть.
const DB_NAME = "pb-board";
const STORES = ["scene", "files", "library"];

let connection = null;

function db() {
  if (!connection) {
    connection = new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, 1);
      request.onupgradeneeded = () => {
        for (const name of STORES) {
          if (!request.result.objectStoreNames.contains(name)) {
            request.result.createObjectStore(name);
          }
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
      request.onblocked = () => reject(new Error("база занята другой вкладкой"));
    });
  }
  return connection;
}

async function read(store) {
  const request = (await db()).transaction(store).objectStore(store).get("current");
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result ?? null);
    request.onerror = () => reject(request.error);
  });
}

async function write(store, value) {
  const transaction = (await db()).transaction(store, "readwrite");
  transaction.objectStore(store).put(value, "current");
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
}

// Хранилище может быть недоступно целиком: режим инкогнито, запрет сайту
// хранить данные, переполненный диск. Доска обязана в этом случае просто
// работать без автосохранения, а не падать белым экраном.
const warn = (what) => (error) => console.warn(`Доска: не удалось ${what}`, error);

// ── Что именно сохраняем из appState ─────────────────────────────────────────
// Список закрытый, а не «весь appState минус лишнее», и это важно: в appState
// живёт вся временная жизнь интерфейса (какое окно открыто, что выделено, где
// курсоры соавторов). Восстанавливать это при следующем заходе не нужно и
// местами вредно. Здесь только то, что учитель заметит: положение и масштаб
// холста, фон, тема, сетка и текущие настройки пера.
const PERSISTED_APP_STATE = [
  "viewBackgroundColor", "theme", "gridSize", "gridModeEnabled", "objectsSnapModeEnabled",
  "zoom", "scrollX", "scrollY", "name",
  "currentItemStrokeColor", "currentItemBackgroundColor", "currentItemFillStyle",
  "currentItemStrokeWidth", "currentItemStrokeStyle", "currentItemRoughness",
  "currentItemOpacity", "currentItemFontFamily", "currentItemFontSize",
  "currentItemTextAlign", "currentItemStartArrowhead", "currentItemEndArrowhead",
  "currentItemRoundness", "currentItemArrowType",
];

const cleanAppState = (appState) =>
  Object.fromEntries(
    PERSISTED_APP_STATE.filter((key) => appState[key] !== undefined).map((key) => [key, appState[key]]),
  );

// ⚠️ Чтение обязано когда-нибудь закончиться. Excalidraw держит заставку
// «Загрузка сцены…» РОВНО до того, как разрешится этот промис, а IndexedDB умеет
// не отвечать вовсе: открытая в соседней вкладке база другой версии переводит
// запрос в onblocked, и ни onsuccess, ни onerror уже не придут. Без ограничения
// по времени доска в такой вкладке не открылась бы никогда. Пять секунд — и
// работаем с чистого листа: пустая доска лучше вечной заставки.
const withTimeout = (promise, ms) =>
  Promise.race([promise, new Promise((resolve) => setTimeout(() => resolve(null), ms))]);

async function loadInitialData() {
  try {
    const [scene, files] = await withTimeout(
      Promise.all([read("scene"), read("files")]),
      5000,
    ) ?? [];
    if (!scene) {
      return null;
    }
    return {
      elements: scene.elements ?? [],
      appState: scene.appState ?? {},
      files: files ?? undefined,
      // Прокрутку не трогаем: своё положение холста мы восстановили из appState,
      // и подгонка «по содержимому» поверх этого сбросила бы её.
      scrollToContent: false,
    };
  } catch (error) {
    warn("прочитать сохранённый рисунок")(error);
    return null;
  }
}

const libraryAdapter = {
  load: () => read("library").catch(() => null),
  save: (data) => write("library", data),
};

// ── Доска ────────────────────────────────────────────────────────────────────
function Board() {
  const [api, setApi] = useState(null);
  const [teacherOpen, setTeacherOpen] = useState(false);
  /* Что показывает строка измерений и в каком состоянии сетка — читаем из
     appState в onChange, а не держим свою копию: источник истины один. */
  const [measurement, setMeasurement] = useState(null);
  const [grid, setGrid] = useState({ on: false, size: 20 });
  /* Какой инструмент выделен: панель показывает его размеры числами. */
  const [tool, setTool] = useState(null);
  const stage = useRef(null);
  // Промис, а не значение: Excalidraw принимает initialData промисом и сам
  // показывает загрузку. Создаётся ровно один раз — иначе каждый перерендер
  // начинал бы чтение заново и затирал бы уже нарисованное.
  const [initialData] = useState(loadInitialData);

  useHandleLibrary({ excalidrawAPI: api, adapter: libraryAdapter });

  // Мост для «Заготовок» Пульта учителя (deploy_theme/assets/js/pb-teacher.js, tabBoards):
  // учитель сохраняет доску в Паспорт дома и открывает в школе. Сам Пульт приходит с
  // /pb-passport.js (nginx/passport.conf); без него мост просто никто не вызывает.
  useEffect(() => {
    if (!api) {
      return undefined;
    }
    window.pbBoard = {
      get: () => ({
        elements: getNonDeletedElements(api.getSceneElements()),
        appState: cleanAppState(api.getAppState()),
        files: api.getFiles(),
      }),
      set: ({ elements = [], appState = {}, files = {} }) => {
        api.addFiles(Object.values(files));
        api.updateScene({ elements, appState });
        api.scrollToContent();
      },
    };
    return () => {
      delete window.pbBoard;
    };
  }, [api]);

  const pending = useRef(null);
  const timer = useRef(0);
  const savedVersion = useRef(-1);
  const savedState = useRef("");
  const savedFileIds = useRef("");

  const flush = useCallback(() => {
    const snapshot = pending.current;
    if (!snapshot) {
      return;
    }
    const { elements, appState, files } = snapshot;

    // Сравниваем ДО записи, а не пишем всё подряд: onChange срабатывает и на
    // движение указателя над холстом, и на выделение — записывать сцену на
    // каждое такое событие значило бы дёргать диск во время рисования.
    const version = getSceneVersion(elements);
    const state = JSON.stringify(cleanAppState(appState));
    if (version !== savedVersion.current || state !== savedState.current) {
      savedVersion.current = version;
      savedState.current = state;
      write("scene", {
        // Удалённые фигуры Excalidraw держит в сцене ради отмены действия;
        // между заходами отмена всё равно не переживает, а вес растёт.
        elements: getNonDeletedElements(elements),
        appState: JSON.parse(state),
      }).catch(warn("сохранить рисунок"));
    }

    // Картинки лежат отдельным хранилищем и переписываются, только когда
    // изменился их состав: строка data: на фотографию с телефона весит
    // мегабайты, и таскать её при каждом штрихе незачем.
    const ids = Object.keys(files ?? {}).sort().join(",");
    if (ids !== savedFileIds.current) {
      savedFileIds.current = ids;
      write("files", files ?? {}).catch(warn("сохранить картинки"));
    }
  }, []);

  const onChange = useCallback(
    (elements, appState, files) => {
      pending.current = { elements, appState, files };
      clearTimeout(timer.current);
      timer.current = setTimeout(flush, 800);

      /* onChange срабатывает и на движение указателя, поэтому состояние
         обновляем ТОЛЬКО когда оно и правда изменилось: иначе каждый мазок
         пером перерисовывал бы панель и строку измерений. */
      const selected = elements.filter(
        (element) => appState.selectedElementIds[element.id] && !element.isDeleted,
      );
      const next = measure(selected);
      setMeasurement((prev) =>
        JSON.stringify(prev) === JSON.stringify(next) ? prev : next,
      );
      setGrid((prev) =>
        prev.on === !!appState.gridModeEnabled && prev.size === appState.gridSize
          ? prev
          : { on: !!appState.gridModeEnabled, size: appState.gridSize },
      );
      const picked = selectedInstrument(elements, appState.selectedElementIds);
      setTool((prev) =>
        JSON.stringify(prev) === JSON.stringify(picked) ? prev : picked,
      );
    },
    [flush],
  );

  // Вкладку закрывают и сворачивают чаще, чем ждут 800 мс тишины: на скрытие
  // страницы дописываем немедленно. pagehide, а не beforeunload — на мобильных
  // браузерах beforeunload не срабатывает вовсе.
  useEffect(() => {
    const saveNow = () => {
      if (document.visibilityState === "hidden") {
        clearTimeout(timer.current);
        flush();
      }
    };
    document.addEventListener("visibilitychange", saveNow);
    window.addEventListener("pagehide", saveNow);
    return () => {
      document.removeEventListener("visibilitychange", saveNow);
      window.removeEventListener("pagehide", saveNow);
    };
  }, [flush]);

  return (
    <>
    {/* Обёртка нужна слою прилипания: он ловит указатель на ней в фазе
        перехвата, до того как до события доберётся холст. */}
    <div className="pb-stage" ref={stage}>
    <Excalidraw
      excalidrawAPI={setApi}
      // Кнопка панели — в штатной верхней полосе рядом с «Библиотекой»:
      // единственное место интерфейса, куда библиотека пускает хозяина.
      renderTopRightUI={() => (
        <button
          type="button"
          className={"pbt-trigger" + (teacherOpen ? " is-on" : "")}
          onClick={() => setTeacherOpen((open) => !open)}
          title="Лист в клетку, фон, линейка, транспортир и точные фигуры"
          aria-pressed={teacherOpen}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M3 9.5 9.5 3 21 14.5 14.5 21z" />
            <path d="M7 8.5 8.5 10M9.5 6 12 8.5M12 3.5 14.5 6M6 12l1.5 1.5M8.5 14.5 11 17" />
          </svg>
          <span>Учителю</span>
        </button>
      )}
      initialData={initialData}
      onChange={onChange}
      langCode="ru-RU"
      name="Доска"
      // Никаких «умных» функций апстрима: они ходят на их сервер (oss-ai).
      aiEnabled={false}
      // Встраивание чужих страниц (YouTube, Figma, Giphy) выключено: на уроке
      // это лишний способ увести класс наружу, а нам — лишний внешний адрес.
      validateEmbeddable={false}
      // Библиотека фигур апстрима открывается по кнопке в панели библиотеки;
      // возвращаться она должна к нам, а не на excalidraw.com.
      libraryReturnUrl={window.location.href.split("#")[0]}
    >
      <MainMenu>
        <MainMenu.DefaultItems.LoadScene />
        <MainMenu.DefaultItems.SaveToActiveFile />
        {/* «Сохранить в...» — именно тем пунктом, который кладёт .excalidraw на
            диск. SaveToActiveFile сам по себе появляется ТОЛЬКО когда файл уже
            открыт, поэтому без Export сохранить доску в файл было нечем — и
            обещание «открыть завтра и продолжить» не выполнялось. */}
        <MainMenu.DefaultItems.Export />
        <MainMenu.DefaultItems.SaveAsImage />
        <MainMenu.Separator />
        <MainMenu.DefaultItems.SearchMenu />
        <MainMenu.DefaultItems.CommandPalette />
        <MainMenu.Separator />
        <MainMenu.DefaultItems.ClearCanvas />
        <MainMenu.Separator />
        <MainMenu.DefaultItems.ToggleTheme />
        <MainMenu.DefaultItems.ChangeCanvasBackground />
      </MainMenu>

      {/* Свой экран приветствия, а не стандартный: у стандартного в середине
          логотип Excalidraw и ссылки апстрима, а это наша страница портала. */}
      <WelcomeScreen>
        <WelcomeScreen.Center>
          <WelcomeScreen.Center.Heading>
            Доска для урока. Рисуйте прямо здесь — всё сохранится в браузере.
          </WelcomeScreen.Center.Heading>
          <WelcomeScreen.Center.Menu>
            <WelcomeScreen.Center.MenuItemLoadScene />
            <WelcomeScreen.Center.MenuItemHelp />
          </WelcomeScreen.Center.Menu>
        </WelcomeScreen.Center>
        <WelcomeScreen.Hints.ToolbarHint>
          <p>Инструменты. Клавиши 1—9 переключают их без мыши</p>
        </WelcomeScreen.Hints.ToolbarHint>
        <WelcomeScreen.Hints.MenuHint>
          <p>Открыть, сохранить в файл, выгрузить картинкой</p>
        </WelcomeScreen.Hints.MenuHint>
        <WelcomeScreen.Hints.HelpHint>
          <p>Все горячие клавиши — здесь</p>
        </WelcomeScreen.Hints.HelpHint>
      </WelcomeScreen>
    </Excalidraw>
    </div>

    {api && <SnapLayer api={api} stage={stage} />}

    {teacherOpen && api && (
      <TeacherPanel
        api={api}
        onClose={() => setTeacherOpen(false)}
        gridOn={grid.on}
        gridSize={grid.size}
        tool={tool}
      />
    )}
    {measurement && <MeasureBar data={measurement} />}
    </>
  );
}

createRoot(document.getElementById("app")).render(<Board />);
