"""Логика «Пульта учителя» без Flask и без БД: колесо вызова, команды, рассадка, дежурства.

Вынесено из app.py, чтобы алгоритмы проверялись тестами на чистых данных, а маршруты
оставались тонкими. Везде только числовые id учеников: имён здесь нет и быть не может
(152-ФЗ) — расшифрованные подписи видит лишь браузер учителя.
"""
import math
import re
import secrets

# Награды, которые ученик получить сам не может. Первые десять — «сундук» из плана 5.1;
# quiz_champion выдаёт табло командной битвы (2.4).
BADGES = {
    "lesson_saver": "Спаситель урока",
    "code_of_week": "Лучший код недели",
    "logic_genius": "Гений логики",
    "kumir_master": "Мастер КуМира",
    "perfect_test": "Сотка на контрольной",
    "order_keeper": "Хранитель порядка",
    "class_soul": "Душа класса",
    "quarter_breakthrough": "Прорыв четверти",
    "teacher_helper": "Помощник учителя",
    "quarter_five": "Пятёрка за четверть",
    "quiz_champion": "Чемпион викторины",
}

# Сколько секунд перемены даёт каждая награда класса. Сумма задана на сервере, а не
# приходит от браузера: иначе кнопка «+999» была бы подделкой в одну строку консоли.
REWARD_SECONDS = {"silence": 300, "quiz": 300, "duty": 300, "answer": 180}
# Пауза между повторами одной награды в классе. «Тишину» нельзя заработать чаще раза в 10 минут
# (таймер самостоятельной работы короче не бывает), ответ у доски выдаётся по одному — паузы почти нет.
REWARD_COOLDOWN = {"silence": 600, "quiz": 30, "duty": 30, "answer": 5}

SUBJECTS = ("general", "informatics", "math", "russian", "history", "physics", "biology", "homeroom")

SLOT_RE = re.compile(r"^R([1-9])-C([1-9])-([LR])$")
STATE_KEYS = ("absent_today", "called_this_week", "do_not_pair", "duty_queue", "duty_history",
              "quarter_goal", "show_labels", "seating", "last_reward")


class ClassroomError(ValueError):
    """Условия невыполнимы (конфликты, мало мест): вызывающий отвечает 409, а не 500."""


def _ids(raw, allowed, limit=100):
    out = []
    for x in raw if isinstance(raw, list) else []:
        if isinstance(x, int) and not isinstance(x, bool) and x in allowed and x not in out:
            out.append(x)
    return out[:limit]


def sanitize_state(raw, member_ids, current=None):
    """Патч от браузера → только известные ключи нужной формы и только про учеников класса.

    Состояние лежит в одном JSON-поле, поэтому форму приходится держать здесь: иначе
    через PUT туда можно было бы положить что угодно, включая имена.
    """
    members = set(member_ids)
    out = dict(current or {})
    raw = raw if isinstance(raw, dict) else {}
    for key in ("absent_today", "called_this_week"):
        if key in raw and isinstance(raw[key], dict):
            stamp = "day" if key == "absent_today" else "week"
            label = str(raw[key].get(stamp, ""))[:10]
            if re.fullmatch(r"\d{4}-(\d{2}-\d{2}|W\d{2})", label):
                out[key] = {stamp: label, "ids": _ids(raw[key].get("ids"), members)}
    if "do_not_pair" in raw and isinstance(raw["do_not_pair"], list):
        pairs = []
        for p in raw["do_not_pair"][:200]:
            ids = _ids(p, members, 2)
            if len(ids) == 2 and sorted(ids) not in pairs:
                pairs.append(sorted(ids))
        out["do_not_pair"] = pairs
    if "duty_queue" in raw:
        out["duty_queue"] = _ids(raw["duty_queue"], members)
    if "duty_history" in raw and isinstance(raw["duty_history"], list):
        out["duty_history"] = [{"day": str(h.get("day", ""))[:10], "ids": _ids(h.get("ids"), members, 4)}
                               for h in raw["duty_history"][-30:] if isinstance(h, dict)]
    if "quarter_goal" in raw:
        g = raw["quarter_goal"]
        if g is None:
            out.pop("quarter_goal", None)
        elif isinstance(g, dict) and isinstance(g.get("target"), int) and 1 <= g["target"] <= 100000 \
                and isinstance(g.get("since"), int) and g["since"] > 0:
            out["quarter_goal"] = {"title": str(g.get("title", "")).strip()[:80], "target": g["target"], "since": g["since"]}
    if isinstance(raw.get("show_labels"), bool):
        out["show_labels"] = raw["show_labels"]
    if isinstance(raw.get("seating"), dict) and raw["seating"].get("variant") in (1, 2):
        out["seating"] = {"variant": raw["seating"]["variant"]}
    if isinstance(raw.get("last_reward"), dict):
        out["last_reward"] = {k: v for k, v in raw["last_reward"].items() if k in REWARD_SECONDS and isinstance(v, int)}
    return {k: out[k] for k in STATE_KEYS if k in out}


def fresh_state(state, today, week):
    """Отметки «сегодня» и «на этой неделе» сами протухают: вчерашние отсутствующие не должны
    навсегда выпадать из колеса, а круг вызова — переноситься на следующую неделю."""
    state = dict(state)
    if state.get("absent_today", {}).get("day") != today:
        state.pop("absent_today", None)
    if state.get("called_this_week", {}).get("week") != week:
        state.pop("called_this_week", None)
    return state


# ── колесо вызова ─────────────────────────────────────────────────────────────
def spin_wheel(member_ids, absent, called, choose=secrets.choice):
    """→ (выпавший | None, новый список «уже отвечали», круг начат заново?)."""
    pool = [i for i in member_ids if i not in set(absent)]
    if not pool:
        return None, list(called), False
    fresh = [i for i in pool if i not in set(called)]
    restarted = not fresh
    if restarted:
        # Круг пройден: все присутствующие уже отвечали на этой неделе — начинаем сначала,
        # иначе колесо замолчало бы до понедельника.
        called, fresh = [], pool
    picked = choose(sorted(fresh))
    return picked, [i for i in called if i in pool] + [picked], restarted


# ── команды и пары ────────────────────────────────────────────────────────────
def _caps(total, n):
    base, extra = divmod(total, n)
    return [base + 1 if i < extra else base for i in range(n)]


def split_teams(ids, n, mode="random", score=None, conflicts=(), shuffle=None):
    """Разбить ids на n команд размером поровну (±1).

    random — честный перемешанный раздатчик; balanced — «змейка» по числу решённых
    задач, чтобы в каждой команде был сильный капитан; conflict_free — как random, но пары
    из `conflicts` гарантированно в разных командах (иначе ClassroomError).
    """
    ids = list(ids)
    if not 2 <= n <= len(ids):
        raise ClassroomError("Команд должно быть от 2 и не больше, чем учеников.")
    shuffle = shuffle or secrets.SystemRandom().shuffle
    bad = {frozenset(p) for p in conflicts}
    shuffle(ids)
    teams = [[] for _ in range(n)]
    caps = _caps(len(ids), n)
    if mode == "balanced":
        score = score or {}
        # сортировка устойчива, а ids уже перемешаны: равные по силе не склеиваются по номеру
        ordered = sorted(ids, key=lambda i: -score.get(i, 0))
        for i, sid in enumerate(ordered):
            # «змейка»: сильные раздаются туда-обратно, поэтому суммарная сила команд близка
            k = i % n
            teams[k if (i // n) % 2 == 0 else n - 1 - k].append(sid)
        return teams
    if mode == "random":
        for sid in ids:
            i = next(k for k in range(n) if len(teams[k]) < caps[k])
            teams[i].append(sid)
        return teams
    if mode != "conflict_free":
        raise ClassroomError("mode: random | balanced | conflict_free.")
    # Сначала самых конфликтных: у них меньше всего вариантов, так отказ случится рано.
    degree = {i: sum(1 for p in bad if i in p) for i in ids}
    ids.sort(key=lambda i: -degree[i])
    budget = [20000]

    def place(pos):
        budget[0] -= 1
        if budget[0] < 0:
            return False
        if pos == len(ids):
            return True
        sid = ids[pos]
        # пробуем команды от наименее заполненной: распределение выходит ровнее
        for k in sorted(range(n), key=lambda k: len(teams[k])):
            if len(teams[k]) < caps[k] and not any(frozenset((sid, m)) in bad for m in teams[k]):
                teams[k].append(sid)
                if place(pos + 1):
                    return True
                teams[k].pop()
        return False

    if not place(0):
        raise ClassroomError("Не получается развести конфликтующих учеников по таким командам. "
                             "Уменьшите число запретных пар или команд.")
    return teams


# ── рассадка ──────────────────────────────────────────────────────────────────
def parse_slot(slot):
    m = SLOT_RE.match(slot or "")
    return (int(m[1]), int(m[2]), m[3]) if m else None


def layout(variant):
    """Вариант 1 — 3 ряда по 5 двухместных парт (30 мест), вариант 2 — по 6 (36 мест)."""
    return 3, 5 if variant == 1 else 6


def _near(a, b):
    """Одна парта или соседние в ряду: болтающих и конфликтующих держим подальше."""
    return a[0] == b[0] and abs(a[1] - b[1]) <= 1


def auto_seat(students, conflicts, rows, desks, tries=300, rng=None):
    """students: [{'id', 'front': bool, 'tall': bool}] → {id: 'R1-C2-L'}.

    front_row_vision — строго первые два ряда; tall — последний ряд (если высоких больше,
    чем мест в нём, берутся следующие с конца); остальные — куда сядут без конфликтов.
    Случайные перезапуски вместо полного перебора: учителю нужна разумная рассадка за
    секунду, а не оптимум; невыполнимое честно сообщается.
    """
    rng = rng or secrets.SystemRandom()
    if len(students) > rows * desks * 2:
        raise ClassroomError(f"Мест в кабинете {rows * desks * 2}, учеников {len(students)}.")
    bad = {frozenset(p) for p in conflicts}
    slots = [(r, c, s) for r in range(1, rows + 1) for c in range(1, desks + 1) for s in "LR"]
    front = [s for s in students if s["front"]]
    tall = [s for s in students if s["tall"] and not s["front"]]
    rest = [s for s in students if not s["front"] and not s["tall"]]
    front_rows = {1, 2} if rows >= 2 else {1}
    if len(front) > len(front_rows) * desks * 2:
        raise ClassroomError("Слишком много учеников с пометкой «плохо видит» для первых двух рядов.")
    tall_rows, cap = set(), 0
    for r in range(rows, 0, -1):
        if cap >= len(tall):
            break
        tall_rows.add(r)
        cap += desks * 2
    if len(tall) > cap or (tall_rows & front_rows and tall):
        raise ClassroomError("Высоких учеников больше, чем мест на последних партах.")
    def ok(taken, sid, slot):
        return all(not (frozenset((sid, other)) in bad and _near(slot, s2)) for s2, other in taken.items())

    for _ in range(tries):
        taken = {}
        done = True
        for group, rows_allowed in ((front, front_rows), (tall, tall_rows), (rest, None)):
            for st in group:
                options = [s for s in slots if s not in taken and (rows_allowed is None or s[0] in rows_allowed)
                           and ok(taken, st["id"], s)]
                if rows_allowed is None:
                    # свободных усаживаем вперёд, оставляя «хвост» высоким и пустые места сзади
                    options.sort(key=lambda s: (s[0], rng.random()))
                    options = [o for o in options if o[0] == options[0][0]] if options else options
                if not options:
                    done = False
                    break
                taken[rng.choice(options)] = st["id"]
            if not done:
                break
        if done:
            return {sid: f"R{r}-C{c}-{side}" for (r, c, side), sid in taken.items()}
    raise ClassroomError("Не удалось рассадить с учётом пометок и запретных пар. Уберите часть ограничений.")


# ── дежурства ─────────────────────────────────────────────────────────────────
def duty_today(queue, absent, k=2):
    return [i for i in queue if i not in set(absent)][:k]


def duty_rotate(queue, served):
    """Отдежурившие уходят в конец очереди: порядок честный, без споров «опять я»."""
    served = set(served)
    return [i for i in queue if i not in served] + [i for i in queue if i in served]


# ── контрольные ───────────────────────────────────────────────────────────────
def assessment_stats(grades):
    """grades: {sid: оценка 2–5} → качество знаний %, успеваемость %, СОУ %.

    СОУ — степень обученности: (100·n5 + 64·n4 + 36·n3 + 14·n2) / N, стандартная методика
    с весами по уровню обученности.
    """
    marks = [g for g in grades.values() if g in (2, 3, 4, 5)]
    n = len(marks)
    if not n:
        return {"n": 0, "quality": 0.0, "success": 0.0, "sou": 0.0}
    c = {m: marks.count(m) for m in (2, 3, 4, 5)}
    return {"n": n, "quality": round(100 * (c[4] + c[5]) / n, 1), "success": round(100 * (n - c[2]) / n, 1),
            "sou": round((100 * c[5] + 64 * c[4] + 36 * c[3] + 14 * c[2]) / n, 1)}


# ── мини-тесты («пятиминутки») ────────────────────────────────────────────────
BLITZ_TYPES = ("choice", "number", "fill", "match")


def validate_blitz_items(items):
    """Карточки пятиминутки от учителя или модели → очищенный список либо ClassroomError.

    Проверяем структуру жёстко: ответы потом сверяет сервер, и вопрос без однозначного
    ответа сделал бы оценку произвольной.
    """
    if not isinstance(items, list) or not 1 <= len(items) <= 20:
        raise ClassroomError("В пятиминутке от 1 до 20 вопросов.")
    out = []
    for it in items:
        if not isinstance(it, dict) or it.get("type") not in BLITZ_TYPES:
            raise ClassroomError("Тип вопроса: choice | number | fill | match.")
        q = str(it.get("q", "")).strip()[:300]
        if not q:
            raise ClassroomError("У вопроса нет текста.")
        t = it["type"]
        if t == "choice":
            opts = [str(o).strip()[:120] for o in it.get("options", []) if str(o).strip()]
            ans = it.get("answer")
            if not 2 <= len(opts) <= 6 or not isinstance(ans, int) or isinstance(ans, bool) or not 0 <= ans < len(opts):
                raise ClassroomError("choice: 2–6 вариантов и номер верного.")
            out.append({"type": t, "q": q, "options": opts, "answer": ans})
        elif t == "number":
            try:
                ans = float(it.get("answer"))
            except (TypeError, ValueError):
                raise ClassroomError("number: ответ должен быть числом.") from None
            if not math.isfinite(ans):
                raise ClassroomError("number: ответ должен быть конечным числом.")
            out.append({"type": t, "q": q, "answer": ans})
        elif t == "fill":
            acc = [_norm_text(a) for a in it.get("answer", []) if _norm_text(a)] if isinstance(it.get("answer"), list) \
                else [_norm_text(it.get("answer"))]
            if not acc or not acc[0]:
                raise ClassroomError("fill: нужен хотя бы один допустимый ответ.")
            out.append({"type": t, "q": q, "answer": acc[:5]})
        else:
            pairs = [[str(a).strip()[:80], str(b).strip()[:80]] for a, b in
                     (p for p in it.get("pairs", []) if isinstance(p, (list, tuple)) and len(p) == 2)]
            if not 2 <= len(pairs) <= 6 or any(not a or not b for a, b in pairs):
                raise ClassroomError("match: 2–6 пар.")
            out.append({"type": t, "q": q, "pairs": pairs})
    return out


def _norm_text(v):
    return re.sub(r"\s+", " ", str(v or "").strip().lower().replace("ё", "е"))


def public_blitz(items, rng=None):
    """Карточки без ответов — то, что получает ученик. Для match правая колонка перемешана."""
    rng = rng or secrets.SystemRandom()
    out = []
    for it in items:
        pub = {"type": it["type"], "q": it["q"]}
        if it["type"] == "choice":
            pub["options"] = it["options"]
        elif it["type"] == "match":
            pub["left"] = [a for a, _ in it["pairs"]]
            right = [b for _, b in it["pairs"]]
            rng.shuffle(right)
            pub["right"] = right
        out.append(pub)
    return out


def grade_blitz(items, answers):
    """→ (верных, всего). answers — список в порядке вопросов; всё нераспознанное — неверно."""
    answers = answers if isinstance(answers, list) else []
    right = 0
    for it, a in zip(items, answers + [None] * len(items)):
        t = it["type"]
        try:
            if t == "choice":
                right += a == it["answer"]
            elif t == "number":
                right += abs(float(str(a).replace(",", ".")) - it["answer"]) < 1e-6
            elif t == "fill":
                right += _norm_text(a) in it["answer"]
            else:
                # match: ученик присылает для каждой левой подписи текст правой
                right += isinstance(a, list) and [_norm_text(x) for x in a] == [_norm_text(b) for _, b in it["pairs"]]
        except (TypeError, ValueError):
            pass
    return right, len(items)


def blitz_grade(right, total):
    ratio = right / total if total else 0
    return 5 if ratio >= 0.85 else 4 if ratio >= 0.65 else 3 if ratio >= 0.4 else 2


def personal_tasks(required, seat):
    """Задачи задания для ученика за партой `seat` (п. 3.4, «уникальный вариант каждому»).

    У задачи с `variants` = n есть n вариантов `<task_id>.v1…vn` (pythontutor/scripts/mutate_tasks_llm.py)
    плюс исходная. Номер берётся по месту со сдвигом на номер задачи: у соседей по парте (места s и s+1)
    при n ≥ 1 различается каждая задача, а не только первая. Без вариантов — исходные задачи всем.
    """
    out = []
    for i, t in enumerate(required):
        k = (seat + i) % (t.get("variants", 0) + 1) if t.get("variants") else 0
        titles = t.get("variant_titles") or []
        out.append({**t, "base_id": t["task_id"], "variant": k, "task_id": f"{t['task_id']}.v{k}" if k else t["task_id"],
                    "title": titles[k - 1] if 0 < k <= len(titles) else t.get("title")})
    return out
