/*
   «Паспорт ПедОбраза» — клиентская система пользователей BormoClass (Zero-PII).
   Вход без персональных данных, 3D-карточка героя, билет на перемену.
*/
(() => {
    'use strict';

    if (window.pbPassport && window.pbPassport.heroOf) { return; }

    const API = window.PB_PASSPORT_API ?? '';
    const COOKIE = 'pb_pass';
    const COOKIE_DOMAIN = '';
    const RECENT_KEY = 'pb_recent_tools_v1';
    const LOCAL_KEY = 'pb_local_solved_v1';
    const REFRESH_KEY = 'pb_pass_refreshed';
    const TASKS_FOR_RECESS = 3;
    const SOLVE_AWARD = 300;
    const PAID = false;
    const SALES = false;
    const PORTAL = '';
    const RECESS_OPEN = true;

    /* Словари никнеймов — копия dictionaries.py для подсказок при вводе ника */
    const ADJ = 'Бодрый Добрый Веселый Быстрый Умный Смелый Тихий Яркий Ловкий Храбрый Забавный Дружный Звонкий Солнечный Лунный Звездный Космический Морской Лесной Полярный Золотой Серебряный Бронзовый Медный Стальной Хрустальный Бархатный Шелковый Пушистый Мохнатый Румяный Резвый Спокойный Задумчивый Любопытный Сообразительный Терпеливый Внимательный Настойчивый Находчивый Аккуратный Благородный Вежливый Великодушный Верный Гостеприимный Изобретательный Мудрый Отважный Приветливый Радостный Рассудительный Светлый Славный Справедливый Улыбчивый Усердный Шустрый Щедрый Юный Альпийский Арктический Балтийский Байкальский Уральский Сибирский Таежный Степной Горный Речной Озерный Рассветный Закатный Утренний Вечерний Летний Зимний Весенний Осенний Снежный Ледяной Теплый Прохладный Свежий Ясный Чистый Прозрачный Лучистый Сияющий Искристый Мерцающий Танцующий Поющий Читающий Рисующий Мечтательный Творческий Научный Ученый Логичный Точный Меткий Прыгучий Летучий Плавучий Бегучий Парящий Скользящий Катящийся Вращающийся Магнитный Электрический Квантовый Атомный Лазерный Цифровой Двоичный Десятичный Бинарный Модульный Рекурсивный Линейный Круглый Квадратный Треугольный Овальный Полосатый Пятнистый Клетчатый Узорчатый Кудрявый Гладкий Мягкий Крепкий Прочный Легкий Звучный Певучий Задорный Озорной Игривый Проворный Расторопный Сноровистый Пытливый Смекалистый Дотошный Дальновидный Зоркий Чуткий Отзывчивый Сердечный Душевный Уютный Домашний Вольный Свободный Лихой Удалой Мирный Радужный Малиновый Лимонный Мятный Ванильный Медовый Карамельный Яблочный Клубничный Апельсиновый Арбузный Ягодный Грибной Ореховый Кедровый Дубовый Березовый Кленовый Сосновый Васильковый Ромашковый Подснежный Луговой Полевой Небесный Облачный Громкий Бирюзовый Изумрудный Сапфировый Янтарный Рубиновый Лазурный Багряный Алый Лиловый Сиреневый Персиковый Оранжевый Зеленый Голубой Синий Фиолетовый Розовый Белоснежный Перламутровый Гибкий Упругий Звенящий Шуршащий Журчащий Шумный Бойкий Живой Прыткий Увлеченный Целеустремленный Трудолюбивый Организованный Собранный Выносливый Неутомимый Неунывающий Беззаботный Безмятежный Невозмутимый Домовитый Хозяйственный Заботливый Нежный Ласковый Милый Крошечный Огромный Могучий Величавый Статный Стройный Подвижный Спортивный Танцевальный Музыкальный Книжный Шахматный Классный Школьный Отличный Образцовый Примерный Исправный'.split(' ');
    const NOUN = 'Енот Лис Медведь Заяц Бобр Ежик Барсук Хомяк Тигр Лев Слон Жираф Пингвин Тюлень Морж Кит Дельфин Осьминог Краб Окунь Карп Лосось Сом Орел Сокол Ястреб Филин Дятел Скворец Снегирь Воробей Журавль Лебедь Петух Попугай Кролик Олень Лось Кабан Бык Конь Пони Верблюд Кенгуру Коала Муравьед Тушканчик Суслик Бурундук Соболь Горностай Хорек Песец Шакал Гепард Леопард Ягуар Крокодил Геккон Хамелеон Тритон Дракон Единорог Гусь Утенок Котенок Щенок Медвежонок Лисенок Волчонок Зайчонок Жук Мотылек Шмель Сверчок Кузнечик Богомол Паук Муравей Светлячок Кот Пес Цыпленок Ослик Мишка Барашек Козленок Поросенок Теленок Жеребенок Спутник Астероид Метеорит Квазар Пульсар Зонд Ровер Телескоп Космонавт Астронавт Планетоход Шаттл Модуль Орбитер Марс Юпитер Сатурн Нептун Меркурий Уран Плутон Титан Горизонт Зенит Апогей Перигей Космос Звездолет Скафандр Иллюминатор Радар Маяк Пилот Штурман Экипаж Старт Полет Луч Протон Нейтрон Электрон Атом Ион Фотон Кварк Магнит Маятник Спектр Вектор Градус Кристалл Алмаз Рубин Изумруд Сапфир Топаз Янтарь Кварц Графит Гранит Базальт Мрамор Вулкан Гейзер Ледник Водопад Ручей Океан Залив Пролив Остров Архипелаг Каньон Утес Холм Перевал Компас Глобус Циркуль Микроскоп Барометр Термометр Секундомер Алгоритм Бит Байт Пиксель Процессор Компилятор Интерпретатор Цикл Массив Сервер Модем Кубик Робот Датчик Транзистор Конденсатор Резистор Диод Эксперимент Опыт Принцип Параграф Задачник Учебник Дневник Конспект Ластик Карандаш Пингвиненок Тукан Фламинго Бегемот Носорог Гиббон Мамонт Динозавр Трицератопс Птеродактиль Эхолот Градусник Гироскоп Сейсмограф Телеграф Телефон Принтер Монитор Курсор Скрипт Дебаггер Логотип Лабиринт Параллелепипед Многогранник Тетраэдр Октаэдр Конус Цилиндр Шар Куб Овал Ромб Квадрат Треугольник Радиус Диаметр Периметр Аккумулятор Бинокль Вездеход Метроном Нанобот Осциллограф Планетарий Реостат Секстант Термос Стеллаж'.split(' ');

    const nowSec = () => Math.floor(Date.now() / 1000);
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const safe = (fn, fallback) => { try { return fn(); } catch { return fallback; } };

    const b64uToBytes = (s) => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (s.length % 4)) % 4)), (c) => c.charCodeAt(0));
    const bytesToB64u = (b) => btoa(String.fromCharCode(...b)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

    const bridgeListeners = new Set();
    let cachedUser = null;

    function readPass() {
        const m = document.cookie.match(/(?:^|;\s*)pb_pass=([^;]*)/);
        if (!m) { return null; }
        return safe(() => {
            const p = JSON.parse(new TextDecoder().decode(b64uToBytes(decodeURIComponent(m[1]).split('.')[0])));
            return p && p.exp > nowSec() ? p : null;
        }, null);
    }

    const getUser = () => {
        const p = readPass();
        if (p) {
            return {
                id: p.uid || p.user_id,
                user_id: p.uid || p.user_id,
                handle: p.h || p.handle,
                role: p.role,
                avatar_seed: p.seed || p.avatar_seed || 1,
                avatarSeed: p.seed || p.avatar_seed || 1,
                recess_seconds: p.rec_bal ?? 0,
                proUntil: p.pro,
                classId: p.cid
            };
        }
        return cachedUser;
    };

    const isProTeacher = () => { const p = readPass(); return !!p && p.role === 'teacher' && p.pro > nowSec(); };
    const isAdFree = () => { const p = readPass(); return !!p && p.ad_free === true && (p.adf || 0) > nowSec(); };

    /* ── Сеть и талоны ──────────────────────────────────────────────────────── */
    async function call(path, body, retried) {
        const res = await fetch(API + '/api/passport' + path, body === undefined
            ? { credentials: 'include' }
            : { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            const errDetail = typeof data.detail === "string" ? data.detail : (data.message || 'Сервис недоступен.');
            throw Object.assign(new Error(errDetail), { code: data.error, data });
        }
        if (data.user) {
            cachedUser = data.user;
        }
        if (body !== undefined || path === '/me') {
            changed();
        }
        return data;
    }

    let ticketCache = null;
    async function ticket(fresh) {
        if (!ticketCache || fresh || Date.now() - ticketCache.at > 50 * 60e3) {
            ticketCache = { t: (await call('/ticket')).ticket, at: Date.now() };
        }
        const wait = 2100 - (Date.now() - ticketCache.at);
        if (wait > 0) { await sleep(wait); }
        return ticketCache.t;
    }

    function changed() {
        hydrate();
        const u = getUser();
        bridgeListeners.forEach(fn => {
            try { fn(u); } catch (e) { console.error(e); }
        });
        document.dispatchEvent(new CustomEvent('pbpassport:change', { detail: u }));
    }

    async function refreshSession() {
        try {
            const data = await call('/me');
            if (data && data.user) {
                cachedUser = data.user;
                changed();
                return data;
            }
        } catch (e) {
            cachedUser = null;
            changed();
        }
        return { user: null };
    }

    function logout() {
        call('/logout', {}).catch(() => {});
        document.cookie = `${COOKIE}=; Max-Age=0; Path=/`;
        cachedUser = null;
        changed();
    }

    /* ── Аватары и герои ────────────────────────────────────────────────────── */
    function avatarCells(seed) {
        let a = (seed || 1) >>> 0;
        const rnd = () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
        const hue = Math.floor(rnd() * 360);
        const cells = [];
        for (let y = 0; y < 5; y++) {
            const row = [rnd() < 0.55, rnd() < 0.55, rnd() < 0.55];
            cells.push([row[0], row[1], row[2], row[1], row[0]]);
        }
        if (!cells.flat().some(Boolean)) { cells[2][2] = true; }
        return { cells, color: `hsl(${hue} 70% 55%)`, bg: `hsl(${hue} 30% 16%)` };
    }

    function avatarSvg(seed, size = 40) {
        const { cells, color, bg } = avatarCells(seed);
        let rects = '';
        cells.forEach((row, y) => row.forEach((on, x) => { if (on) { rects += `<rect x="${x + 1}" y="${y + 1}" width="1" height="1"/>`; } }));
        return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 7 7" width="${size}" height="${size}" shape-rendering="crispEdges" aria-hidden="true"><rect width="7" height="7" rx="1" fill="${bg}"/><g fill="${color}">${rects}</g></svg>`;
    }

    const PORTRAITS = API + '/passport/portraits/';
    let portraitIndex = null;
    function portraits() {
        portraitIndex ??= fetch(PORTRAITS + 'index.json').then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status))))
            .catch((e) => { portraitIndex = null; throw e; });
        return portraitIndex;
    }

    function heroOf(index, role, handle) {
        let a = 2166136261;
        const key = `hero|${role}|${handle}`;
        for (let i = 0; i < key.length; i++) { a = Math.imul(a ^ key.charCodeAt(i), 16777619); }
        a >>>= 0;
        const rnd = () => { a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
        const pick = (arr) => arr[Math.floor(rnd() * arr.length)];
        const raceId = pick(Object.keys(index.races)), race = index.races[raceId];
        const classId = pick(Object.keys(race.classes)), klass = race.classes[classId];
        const body = rnd() < 0.5 ? 'male' : 'female';
        const n = Math.floor(rnd() * klass[body]);
        return { raceId, race, klass, body, src: `${PORTRAITS}${raceId}/${classId}/${body}/${String(n).padStart(2, '0')}.jpg` };
    }

    function heroInto(svg, p, size, caption) {
        if (!svg) { return; }
        portraits().then((idx) => {
            const hero = heroOf(idx, p.role, p.handle || p.h);
            const img = document.createElement('img');
            img.src = hero.src;
            img.width = size;
            img.height = size;
            img.className = 'pbp-hero';
            img.decoding = 'async';
            svg.replaceWith(img);
            if (caption) { caption.textContent = `${hero.race.name} • ${hero.klass.name}`; }
        }).catch(() => {});
    }

    /* ── Шифрование заметок учителя (PBKDF2 / AES-GCM) ────────────────────────── */
    const enc = new TextEncoder();
    const crypt = {
        async key(masterPassword, handle) {
            const base = await crypto.subtle.importKey('raw', enc.encode(masterPassword), 'PBKDF2', false, ['deriveKey']);
            return crypto.subtle.deriveKey(
                { name: 'PBKDF2', salt: enc.encode('pb-notes:' + handle), iterations: 250000, hash: 'SHA-256' },
                base, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
        },
        async encrypt(key, text) {
            const iv = crypto.getRandomValues(new Uint8Array(12));
            const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, enc.encode(text)));
            return bytesToB64u(iv) + ':' + bytesToB64u(ct);
        },
        async decrypt(key, packed) {
            const [iv, ct] = packed.split(':');
            return new TextDecoder().decode(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64uToBytes(iv) }, key, b64uToBytes(ct)));
        },
    };

    /* ── Ключ активации ─────────────────────────────────────────────────────── */
    const ALPHABET = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ';
    function codeChecksum(body) {
        let h = 0x811C9DC5;
        for (const ch of body) { h = Math.imul(h ^ ch.charCodeAt(0), 0x01000193) >>> 0; }
        const v = h & 1023;
        return ALPHABET[v >> 5] + ALPHABET[v & 31];
    }
    function checkCode(raw) {
        const flat = String(raw).toUpperCase().replace(/[^A-Z0-9]/g, '');
        if (!flat) { return 'empty'; }
        if (flat.length !== 15 || !flat.startsWith('PED26') || [...flat.slice(5)].some((c) => !ALPHABET.includes(c))) { return 'format'; }
        const body = flat.slice(5, 13);
        return codeChecksum(`PED-26-${body.slice(0, 4)}-${body.slice(4)}`) === flat.slice(13) ? 'ok' : 'typo';
    }

    function suggest(value) {
        const parts = value.replace(/ё/gi, 'е').split('-');
        const starts = (list, p) => list.filter((w) => w.toLowerCase().startsWith(p.toLowerCase())).slice(0, 8);
        if (parts.length === 1) { return starts(ADJ, parts[0]).map((a) => a + '-'); }
        if (parts.length === 2) { return starts(NOUN, parts[1]).map((n) => `${parts[0]}-${n}-`); }
        return [];
    }

    /* ── BormoClass Интеграция заданий и перемены ───────────────────────────── */
    async function solveTask(taskId, score, courseworkId = null) {
        try {
            const data = await call('/solve', {
                task_id: taskId,
                score: Math.max(0, Math.min(100, score)),
                coursework_id: courseworkId
            });
            if (cachedUser && data.recess_seconds !== undefined) {
                cachedUser.recess_seconds = data.recess_seconds;
                changed();
            }
            return data;
        } catch (err) {
            return { ok: false, error: err.message, message: err.message };
        }
    }

    async function spendRecess(seconds) {
        try {
            const data = await call('/recess/spend', { seconds });
            if (cachedUser && data.remaining_seconds !== undefined) {
                cachedUser.recess_seconds = data.remaining_seconds;
                changed();
            }
            return data;
        } catch (err) {
            return { ok: false, error: err.message, message: err.message };
        }
    }

    /* ── Диалог Паспорта ────────────────────────────────────────────────────── */
    const CSS = `
dialog.pbp{border:1px solid var(--md-sys-color-outline,#555);border-radius:16px;padding:0;max-width:min(30rem,calc(100vw - 2rem));width:100%;background:var(--md-sys-color-surface,#161616);color:var(--md-sys-color-on-surface,#eee);font:16px/1.45 system-ui,sans-serif;z-index:9999}
dialog.pbp::backdrop{background:rgba(0,0,0,.6)}
.pbp-in{padding:1.25rem 1.25rem 1.5rem;display:grid;gap:.9rem}
.pbp h2{margin:0;font-size:1.25rem}.pbp p{margin:0;color:var(--md-sys-color-on-surface-variant,#bbb)}
.pbp-tabs{display:flex;gap:.4rem;flex-wrap:wrap}
.pbp button,.pbp input,.pbp select{font:inherit;min-height:44px;border-radius:10px;border:1px solid var(--md-sys-color-outline,#666);background:var(--md-sys-color-surface-container,#222);color:inherit;padding:.4rem .8rem}
.pbp button{cursor:pointer}.pbp button:focus-visible,.pbp input:focus-visible,.pbp select:focus-visible{outline:2px solid var(--md-sys-color-primary,#f90);outline-offset:2px}
.pbp button.pri{background:var(--md-sys-color-primary,#f90);color:var(--md-sys-color-on-primary,#000);border-color:transparent;font-weight:600}
.pbp button[aria-selected=true]{background:var(--md-sys-color-primary-container,#431);color:var(--md-sys-color-on-primary-container,#fdb)}
.pbp button:disabled{opacity:.5;cursor:default}
.pbp label{display:grid;gap:.25rem;font-size:.9rem}
.pbp-err{color:var(--md-sys-color-error,#f66);min-height:1.2em}
.pbp-ok{color:#5c5}
.pbp-opts{display:grid;gap:.4rem}
.pbp-words{display:grid;grid-template-columns:1fr 1fr;gap:.5rem}.pbp-words b{padding:.6rem;border-radius:10px;background:var(--md-sys-color-surface-container-high,#2a2a2a);text-align:center;font-size:1.1rem}
.pbp-row{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center}
.pbp-x{position:absolute;right:.6rem;top:.6rem;min-width:44px}
.pbp-hero{display:block;flex:none;border-radius:12px;object-fit:cover}`;

    function h(tag, props, ...kids) {
        const el = document.createElement(tag);
        Object.entries(props || {}).forEach(([k, v]) => {
            if (k === 'class') { el.className = v; } else if (k.startsWith('on')) { el.addEventListener(k.slice(2), v); } else if (v !== false && v != null) { el.setAttribute(k, v === true ? '' : v); }
        });
        kids.flat().filter((c) => c != null && c !== false).forEach((c) => el.append(c instanceof Node ? c : document.createTextNode(String(c))));
        return el;
    }
    const field = (label, input) => h('label', null, label, input);

    let dlg = null;
    function openModal(tab) {
        if (!dlg) {
            const st = document.createElement('style');
            st.textContent = CSS;
            document.head.append(st);
            dlg = h('dialog', { class: 'pbp', 'aria-labelledby': 'pbp-title' });
            dlg.addEventListener('click', (e) => { if (e.target === dlg) { dlg.close(); } });
            document.body.append(dlg);
        }
        show(tab || (getUser() ? 'profile' : 'login'));
        if (!dlg.open) { dlg.showModal(); }
        ticket().catch(() => {});
    }

    function show(tab, notice) {
        const user = getUser();
        const tabs = user
            ? [['profile', 'Профиль']]
            : [['login', 'Войти'], ['register', 'Создать Паспорт'], ['recover', 'Забыл пароль']];
        const err = h('div', { class: 'pbp-err', role: 'alert' });
        let body;
        if (tab === 'profile' && user) {
            body = viewProfile(err);
        } else if (tab === 'recover') {
            body = viewRecover(err);
        } else if (tab === 'register') {
            body = viewRegister();
        } else {
            body = viewLogin(err);
        }
        dlg.replaceChildren(h('div', { class: 'pbp-in' },
            h('button', { class: 'pbp-x', type: 'button', 'aria-label': 'Закрыть', onclick: () => dlg.close() }, '✕'),
            h('h2', { id: 'pbp-title' }, 'Паспорт ПедОбраза'),
            h('div', { class: 'pbp-tabs', role: 'tablist' }, tabs.map(([id, label]) => h('button', { type: 'button', role: 'tab', 'aria-selected': String(id === tab), onclick: () => show(id) }, label))),
            notice ? h('p', { class: 'pbp-ok' }, notice) : null,
            body, err));
        dlg.querySelector('input,select,button.pri')?.focus();
    }

    const act = (err, btn, fn) => async (e) => {
        e?.preventDefault();
        err.textContent = '';
        btn.disabled = true;
        try { await fn(); } catch (x) { err.textContent = x.message; } finally { btn.disabled = false; }
    };

    function viewLogin(err) {
        const handle = h('input', { name: 'handle', autocomplete: 'username', list: 'pbp-names', placeholder: 'Бодрый-Енот-428', required: true });
        const list = h('datalist', { id: 'pbp-names' });
        handle.addEventListener('input', () => list.replaceChildren(...suggest(handle.value).map((v) => h('option', { value: v }))));
        const pw = h('input', { type: 'password', name: 'password', autocomplete: 'current-password', required: true });
        const go = h('button', { class: 'pri', type: 'submit' }, 'Войти');
        const form = h('form', { class: 'pbp-in', style: 'padding:0' }, field('Позывной', handle), list, field('Пароль', pw), h('div', { class: 'pbp-row' }, go));
        form.addEventListener('submit', act(err, go, async () => {
            const body = { ticket: await ticket(), handle: handle.value, password: pw.value };
            await call('/login', body);
            dlg.close();
            await refreshSession();
        }));
        return form;
    }

    function viewRecover(err) {
        const handle = h('input', { name: 'handle', list: 'pbp-names2', required: true, placeholder: 'Бодрый-Енот-428' });
        const list = h('datalist', { id: 'pbp-names2' });
        handle.addEventListener('input', () => list.replaceChildren(...suggest(handle.value).map((v) => h('option', { value: v }))));
        const words = [0, 1, 2, 3].map((i) => h('input', { name: 'w' + i, autocomplete: 'off', required: true, placeholder: `Слово ${i + 1}` }));
        const pw = h('input', { type: 'password', autocomplete: 'new-password', required: true, minlength: 4, placeholder: 'Новый пароль' });
        const go = h('button', { class: 'pri', type: 'submit' }, 'Сбросить пароль');
        const form = h('form', { class: 'pbp-in', style: 'padding:0' },
            h('p', null, 'Введите позывной и четыре секретных слова восстановления.'),
            field('Позывной', handle), list, h('div', { class: 'pbp-words' }, words), field('Новый пароль', pw), go);
        form.addEventListener('submit', act(err, go, async () => {
            await call('/recover', { ticket: await ticket(), handle: handle.value, recovery_words: words.map((w) => w.value.trim().toLowerCase()), new_password: pw.value });
            show('profile', 'Пароль успешно обновлён.');
            await refreshSession();
        }));
        return form;
    }

    function viewRegister() {
        return h('div', { class: 'pbp-in', style: 'padding:0' },
            h('p', null, 'Регистрация без персональных данных: барабан позывного, 3D-карточка с героем и выгрузка PNG-паспорта.'),
            h('button', { class: 'pri', type: 'button', onclick: () => { location.href = '/passport/'; } }, 'Открыть генератор карточек'));
    }

    function viewProfile(err) {
        const p = getUser();
        const av = h('span'); av.innerHTML = avatarSvg(p.avatar_seed || p.avatarSeed || 1, 96);
        const race = h('p');
        heroInto(av.firstElementChild, p, 96, race);
        const roleLabel = p.role === 'teacher' ? 'Учитель' : 'Ученик';
        const out = h('button', { type: 'button', onclick: () => { logout(); dlg.close(); } }, 'Выйти из системы');
        const toCard = h('button', { type: 'button', class: 'pri', onclick: () => { location.href = '/passport/'; } }, 'Карточка в полный экран');
        return h('div', { class: 'pbp-in', style: 'padding:0' },
            h('div', { class: 'pbp-row' }, av, h('div', null, h('b', { style: 'font-size:1.2rem' }, p.handle), h('br'), roleLabel, race)),
            p.recess_seconds !== undefined ? h('p', null, `Секунды перемены: ${p.recess_seconds} с`) : null,
            h('div', { class: 'pbp-row' }, toCard, out));
    }

    function hydrate() {
        const u = getUser();
        document.querySelectorAll('[data-pbp-handle]').forEach((el) => { el.textContent = u ? u.handle : ''; });
        document.querySelectorAll('[data-pbp-avatar]').forEach((el) => {
            if (u) {
                el.innerHTML = avatarSvg(u.avatar_seed || u.avatarSeed || 1, parseInt(el.getAttribute('data-pbp-size') || '32', 10));
            } else {
                el.innerHTML = '';
            }
        });
    }

    window.addEventListener("message", async (event) => {
        if (event.origin !== window.location.origin) return;
        const data = event.data;
        if (!data || typeof data !== "object") return;
        if (data.type === "PB_TASK_SOLVED" && data.task_id) {
            const score = typeof data.score === "number" ? data.score : 100;
            await solveTask(data.task_id, score, data.coursework_id || null);
        }
    });

    const pbPassport = {
        getUser,
        isProTeacher,
        isAdFree,
        logout,
        refresh: refreshSession,
        refreshSession,
        api: call,
        ticket,
        words: { adj: ADJ, noun: NOUN },
        portraits,
        heroOf,
        open: openModal,
        avatarSvg,
        avatarCells,
        checkCode,
        codeChecksum,
        suggest,
        crypto: crypt,
        solveTask,
        spendRecess,
        onUserChange: (cb) => {
            bridgeListeners.add(cb);
            const u = getUser();
            if (u) cb(u);
            return () => bridgeListeners.delete(cb);
        }
    };

    window.pbPassport = pbPassport;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', refreshSession, { once: true });
    } else {
        refreshSession();
    }
})();
