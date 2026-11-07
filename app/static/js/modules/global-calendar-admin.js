/**
 * BormoClass Cross-Cutting Module (Zero-PII, Material Design 3.0)
 * Includes:
 *  - Teacher "To-review" screen (tabs: To-review / Reviewed, course filter, stats, mark-reviewed)
 *  - Student "To-do" screen (tabs: Assigned / Missing / Done with weekly buckets)
 *  - Calendar (week / month grid, course color chips, WebCal .ics copy & download)
 *  - Notification Center Bell (unread badge, feed, read-all, per-course mute prefs)
 *  - Domain Admin Console (org_units tree, verified_teacher toggle, OneRoster CSV import, audit logs, Takeout zip)
 */

import { openSpeedGrader } from "./speedgrader.js";

// =============================================================================
// 1. TEACHER SCREEN: TO-REVIEW (НА ПРОВЕРКУ)
// =============================================================================

export class ToReviewView {
  constructor(options = {}) {
    this.container = options.container || document.getElementById("appMain");
    this.activeTab = "to_review"; // 'to_review' | 'reviewed'
    this.selectedCourseId = "";
    this.items = [];
    this.courses = [];
  }

  async render() {
    if (!this.container) return;
    this.container.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 16px; padding: 4px;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
          <h2 style="margin: 0; font-size: 1.4rem;">На проверку</h2>
          <div style="display: flex; align-items: center; gap: 12px;">
            <div class="nav-rail" style="display: inline-flex; border-radius: 8px; background: var(--md-sys-color-surface-container-high, #e3e8ef); padding: 2px;">
              <button id="trTabToReview" class="nav-tab-btn ${this.activeTab === "to_review" ? "active" : ""}" style="
                padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.85rem;
                background: ${this.activeTab === "to_review" ? "var(--md-sys-color-surface, #ffffff)" : "transparent"};
              ">На проверку</button>
              <button id="trTabReviewed" class="nav-tab-btn ${this.activeTab === "reviewed" ? "active" : ""}" style="
                padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.85rem;
                background: ${this.activeTab === "reviewed" ? "var(--md-sys-color-surface, #ffffff)" : "transparent"};
              ">Проверено</button>
            </div>
            <select id="trCourseFilter" style="
              padding: 6px 12px; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
              background: var(--md-sys-color-surface, #ffffff); font-size: 0.85rem; cursor: pointer;
            ">
              <option value="">Все курсы</option>
            </select>
          </div>
        </div>
        <div id="trItemsContainer" style="display: flex; flex-direction: column; gap: 10px;">
          <div style="padding: 30px; text-align: center; color: #888;">Загрузка списка заданий...</div>
        </div>
      </div>
    `;

    this.bindEvents();
    await this.loadData();
  }

  bindEvents() {
    const tabToReview = document.getElementById("trTabToReview");
    const tabReviewed = document.getElementById("trTabReviewed");
    const courseFilter = document.getElementById("trCourseFilter");

    if (tabToReview) {
      tabToReview.onclick = () => {
        this.activeTab = "to_review";
        this.render();
      };
    }
    if (tabReviewed) {
      tabReviewed.onclick = () => {
        this.activeTab = "reviewed";
        this.render();
      };
    }
    if (courseFilter) {
      courseFilter.onchange = (e) => {
        this.selectedCourseId = e.target.value;
        this.loadData();
      };
    }
  }

  async loadData() {
    const listContainer = document.getElementById("trItemsContainer");
    if (!listContainer) return;

    try {
      const tabParam = this.activeTab === "reviewed" ? "reviewed" : "work_to_review";
      let url = `/api/classroom/global/to-review?tab=${tabParam}`;
      if (this.selectedCourseId) url += `&course_id=${this.selectedCourseId}`;

      const res = await fetch(url);
      if (!res.ok) {
        listContainer.innerHTML = `<div style="padding: 30px; text-align: center; color: #d32f2f;">Не удалось загрузить данные.</div>`;
        return;
      }
      this.items = await res.json();
      this.renderItems(this.items);
    } catch (e) {
      listContainer.innerHTML = `<div style="padding: 30px; text-align: center; color: #d32f2f;">Ошибка сети.</div>`;
    }
  }

  renderItems(items) {
    const container = document.getElementById("trItemsContainer");
    if (!container) return;

    if (!items || items.length === 0) {
      const emptyMsg = this.activeTab === "to_review"
        ? "Все сданные работы проверены! Отличный результат."
        : "Нет проверенных работ.";
      container.innerHTML = `
        <div style="text-align: center; padding: 48px; background: var(--md-sys-color-surface-container-low, #f7f9fc); border-radius: 16px; color: #666;">
          ${emptyMsg}
        </div>
      `;
      return;
    }

    container.innerHTML = items.map((it) => `
      <div class="tr-card" style="
        background: var(--md-sys-color-surface, #ffffff); border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
        border-radius: 14px; padding: 14px 18px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
      ">
        <div style="flex: 1; min-width: 240px;">
          <div style="font-weight: 700; font-size: 1.05rem; color: var(--md-sys-color-on-surface, #1f1f1f);">
            ${this.escapeHtml(it.coursework_title || it.title || "Задание")}
          </div>
          <div style="font-size: 0.85rem; color: var(--md-sys-color-on-surface-variant, #444746); margin-top: 2px;">
            Курс: ${this.escapeHtml(it.class_title || "Курс")} • Срок: ${it.due_at ? new Date(it.due_at * 1000).toLocaleDateString() : "Без срока"}
          </div>
          <div style="display: flex; gap: 14px; margin-top: 8px; font-size: 0.8rem; font-weight: 600;">
            <span style="color: #2e7d32;">Сдано: ${it.turned_in_count ?? 0}</span>
            <span style="color: #666;">Назначено: ${it.assigned_count ?? 0}</span>
            <span style="color: #005ac1;">Оценено: ${it.graded_count ?? 0}</span>
          </div>
        </div>

        <div style="display: flex; align-items: center; gap: 10px;">
          <button class="btn btn-primary tr-btn-open-sg" data-cid="${it.class_id}" data-cwid="${it.coursework_id || it.id}" data-sid="${it.student_id || ""}" style="
            padding: 8px 16px; border-radius: 8px; font-weight: 600; font-size: 0.85rem; cursor: pointer;
            background: var(--md-sys-color-primary, #005ac1); color: #fff; border: none;
          ">
            Проверить в SpeedGrader
          </button>

          <button class="btn btn-secondary tr-btn-mark-reviewed" data-cwid="${it.coursework_id || it.id}" data-reviewed="${it.reviewed_by_teacher ? "false" : "true"}" title="${it.reviewed_by_teacher ? "Вернуть в «На проверку»" : "Пометить как проверенное"}" style="
            padding: 8px 12px; border-radius: 8px; font-size: 0.85rem; cursor: pointer;
            border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5); background: var(--md-sys-color-surface-container-high, #e3e8ef);
          ">
            ${it.reviewed_by_teacher ? "↩ Вернуть" : "✓ Проверено"}
          </button>
        </div>
      </div>
    `).join("");

    container.querySelectorAll(".tr-btn-open-sg").forEach((btn) => {
      btn.onclick = () => {
        openSpeedGrader({
          classId: Number(btn.dataset.cid),
          courseworkId: Number(btn.dataset.cwid),
          studentId: btn.dataset.sid ? Number(btn.dataset.sid) : null,
          onClose: () => this.loadData(),
        });
      };
    });

    container.querySelectorAll(".tr-btn-mark-reviewed").forEach((btn) => {
      btn.onclick = async () => {
        const cwid = btn.dataset.cwid;
        const reviewed = btn.dataset.reviewed === "true";
        await fetch(`/api/classroom/coursework/${cwid}/mark-reviewed`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reviewed }),
        });
        this.loadData();
      };
    });
  }

  escapeHtml(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
}

// =============================================================================
// 2. STUDENT SCREEN: TO-DO (СПИСОК ДЕЛ)
// =============================================================================

export class ToDoView {
  constructor(options = {}) {
    this.container = options.container || document.getElementById("appMain");
    this.activeTab = "assigned"; // 'assigned' | 'missing' | 'done'
    this.data = { assigned: [], missing: [], done: [], buckets: {} };
  }

  async render() {
    if (!this.container) return;
    this.container.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 16px; padding: 4px;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
          <h2 style="margin: 0; font-size: 1.4rem;">Список дел</h2>
          <div class="nav-rail" style="display: inline-flex; border-radius: 8px; background: var(--md-sys-color-surface-container-high, #e3e8ef); padding: 2px;">
            <button id="tdTabAssigned" class="nav-tab-btn ${this.activeTab === "assigned" ? "active" : ""}" style="
              padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.85rem;
              background: ${this.activeTab === "assigned" ? "var(--md-sys-color-surface, #ffffff)" : "transparent"};
            ">Назначено</button>
            <button id="tdTabMissing" class="nav-tab-btn ${this.activeTab === "missing" ? "active" : ""}" style="
              padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.85rem;
              background: ${this.activeTab === "missing" ? "var(--md-sys-color-surface, #ffffff)" : "transparent"};
            ">Пропущено</button>
            <button id="tdTabDone" class="nav-tab-btn ${this.activeTab === "done" ? "active" : ""}" style="
              padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.85rem;
              background: ${this.activeTab === "done" ? "var(--md-sys-color-surface, #ffffff)" : "transparent"};
            ">Выполнено</button>
          </div>
        </div>
        <div id="tdBucketsContainer" style="display: flex; flex-direction: column; gap: 14px;">
          <div style="padding: 30px; text-align: center; color: #888;">Загрузка списка дел...</div>
        </div>
      </div>
    `;

    this.bindEvents();
    await this.loadData();
  }

  bindEvents() {
    const tAssigned = document.getElementById("tdTabAssigned");
    const tMissing = document.getElementById("tdTabMissing");
    const tDone = document.getElementById("tdTabDone");

    if (tAssigned) {
      tAssigned.onclick = () => {
        this.activeTab = "assigned";
        this.render();
      };
    }
    if (tMissing) {
      tMissing.onclick = () => {
        this.activeTab = "missing";
        this.render();
      };
    }
    if (tDone) {
      tDone.onclick = () => {
        this.activeTab = "done";
        this.render();
      };
    }
  }

  async loadData() {
    const container = document.getElementById("tdBucketsContainer");
    if (!container) return;

    try {
      const res = await fetch("/api/classroom/global/to-do");
      if (!res.ok) {
        container.innerHTML = `<div style="padding: 30px; text-align: center; color: #d32f2f;">Не удалось загрузить задачи.</div>`;
        return;
      }
      this.data = await res.json();
      this.renderBuckets();
    } catch (e) {
      container.innerHTML = `<div style="padding: 30px; text-align: center; color: #d32f2f;">Ошибка сети.</div>`;
    }
  }

  renderBuckets() {
    const container = document.getElementById("tdBucketsContainer");
    if (!container) return;

    const list = this.data[this.activeTab] || [];
    if (list.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; padding: 48px; background: var(--md-sys-color-surface-container-low, #f7f9fc); border-radius: 16px; color: #666;">
          В этой вкладке нет заданий.
        </div>
      `;
      return;
    }

    // Bucket labels
    const bucketTitles = {
      no_due_date: "Без срока сдачи",
      this_week: "На этой неделе",
      next_week: "На следующей неделе",
      later: "Позже",
      earlier: "Ранее",
    };

    // Group items by bucket
    const groups = {};
    list.forEach((item) => {
      const b = item.bucket || "no_due_date";
      if (!groups[b]) groups[b] = [];
      groups[b].push(item);
    });

    container.innerHTML = Object.entries(groups).map(([bKey, items]) => `
      <div style="display: flex; flex-direction: column; gap: 8px;">
        <div style="font-weight: 700; font-size: 0.95rem; color: var(--md-sys-color-primary, #005ac1); margin-top: 6px;">
          ${bucketTitles[bKey] || bKey} (${items.length})
        </div>
        ${items.map((it) => `
          <div style="
            background: var(--md-sys-color-surface, #ffffff); border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
            border-radius: 12px; padding: 12px 16px; display: flex; justify-content: space-between; align-items: center;
          ">
            <div>
              <div style="font-weight: 600; font-size: 1rem;">${this.escapeHtml(it.coursework_title || it.title)}</div>
              <div style="font-size: 0.8rem; color: #666; margin-top: 2px;">
                ${this.escapeHtml(it.class_title)} • ${it.due_at ? `Срок: ${new Date(it.due_at * 1000).toLocaleString()}` : "Без срока"}
              </div>
            </div>
            <div>
              ${it.grade_points !== null && it.grade_points !== undefined ? `
                <span style="font-weight: 700; color: #2e7d32; font-size: 0.9rem;">Оценка: ${it.grade_points} б.</span>
              ` : `
                <span style="padding: 4px 10px; border-radius: 10px; font-size: 0.78rem; font-weight: 600; background: #e3e8ef;">${it.status || "Назначено"}</span>
              `}
            </div>
          </div>
        `).join("")}
      </div>
    `).join("");
  }

  escapeHtml(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
}

// =============================================================================
// 3. CALENDAR VIEW (.ICS WEBCAL EXPORT & MONTH/WEEK GRID)
// =============================================================================

export class CalendarView {
  constructor(options = {}) {
    this.container = options.container || document.getElementById("appMain");
    this.viewMode = "month"; // 'month' | 'week'
    this.events = [];
    this.currentDate = new Date();
  }

  async render() {
    if (!this.container) return;
    this.container.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 16px; padding: 4px;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
          <div style="display: flex; align-items: center; gap: 12px;">
            <h2 style="margin: 0; font-size: 1.4rem;" id="calMonthTitle">Календарь дедлайнов</h2>
            <div style="display: flex; gap: 4px;">
              <button id="calBtnPrev" class="btn btn-secondary" style="padding: 4px 10px; border-radius: 6px; cursor: pointer;">◀</button>
              <button id="calBtnToday" class="btn btn-secondary" style="padding: 4px 10px; border-radius: 6px; cursor: pointer; font-weight: 600;">Сегодня</button>
              <button id="calBtnNext" class="btn btn-secondary" style="padding: 4px 10px; border-radius: 6px; cursor: pointer;">▶</button>
            </div>
          </div>

          <div style="display: flex; align-items: center; gap: 8px;">
            <button id="calBtnCopyWebcal" class="btn btn-secondary" style="
              padding: 6px 12px; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
              background: var(--md-sys-color-surface, #ffffff); font-size: 0.82rem; cursor: pointer; font-weight: 600;
            ">🔗 Скопировать WebCal .ics ссылку</button>
            <a id="calBtnDownloadIcs" href="/api/classroom/calendar/user_1.ics" download="bormoclass.ics" class="btn btn-secondary" style="
              padding: 6px 12px; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
              background: var(--md-sys-color-surface, #ffffff); font-size: 0.82rem; cursor: pointer; font-weight: 600; text-decoration: none; color: inherit;
            ">📥 Скачать .ics</a>
          </div>
        </div>

        <!-- Month Grid Viewport -->
        <div id="calGridContainer" style="
          border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5); border-radius: 12px;
          overflow: hidden; background: #fff;
        ">
          <!-- Calendar Days Grid -->
        </div>
      </div>
    `;

    this.bindEvents();
    await this.loadEvents();
  }

  bindEvents() {
    const btnPrev = document.getElementById("calBtnPrev");
    const btnNext = document.getElementById("calBtnNext");
    const btnToday = document.getElementById("calBtnToday");
    const btnWebcal = document.getElementById("calBtnCopyWebcal");

    if (btnPrev) {
      btnPrev.onclick = () => {
        this.currentDate.setMonth(this.currentDate.getMonth() - 1);
        this.renderCalendarGrid();
      };
    }
    if (btnNext) {
      btnNext.onclick = () => {
        this.currentDate.setMonth(this.currentDate.getMonth() + 1);
        this.renderCalendarGrid();
      };
    }
    if (btnToday) {
      btnToday.onclick = () => {
        this.currentDate = new Date();
        this.renderCalendarGrid();
      };
    }
    if (btnWebcal) {
      btnWebcal.onclick = () => {
        const url = `${window.location.origin}/api/classroom/calendar/user_1.ics`;
        navigator.clipboard.writeText(url).then(() => {
          alert("WebCal ссылка скопирована в буфер обмена!");
        });
      };
    }
  }

  async loadEvents() {
    try {
      const res = await fetch("/api/classroom/global/calendar");
      this.events = res.ok ? await res.json() : [];
      this.renderCalendarGrid();
    } catch {
      this.renderCalendarGrid();
    }
  }

  renderCalendarGrid() {
    const grid = document.getElementById("calGridContainer");
    const title = document.getElementById("calMonthTitle");
    if (!grid) return;

    const year = this.currentDate.getFullYear();
    const month = this.currentDate.getMonth();
    const monthNames = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
    if (title) title.textContent = `${monthNames[month]} ${year}`;

    const firstDayIndex = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    // Monday as 0
    const startOffset = (firstDayIndex + 6) % 7;

    const dayHeaders = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

    let html = `
      <div style="display: grid; grid-template-columns: repeat(7, 1fr); background: #f0f4f9; border-bottom: 1px solid #ddd; text-align: center; font-weight: 700; font-size: 0.85rem; padding: 8px 0;">
        ${dayHeaders.map((d) => `<div>${d}</div>`).join("")}
      </div>
      <div style="display: grid; grid-template-columns: repeat(7, 1fr); auto-rows: minmax(90px, auto); gap: 1px; background: #ddd;">
    `;

    // Blank cells before month start
    for (let i = 0; i < startOffset; i++) {
      html += `<div style="background: #fafafa; padding: 6px; min-height: 80px;"></div>`;
    }

    // Days cells
    for (let day = 1; day <= daysInMonth; day++) {
      const curDayTs = new Date(year, month, day).getTime() / 1000;
      const nextDayTs = curDayTs + 86400;

      const dayEvents = this.events.filter((ev) => ev.due_at >= curDayTs && ev.due_at < nextDayTs);

      html += `
        <div style="background: #ffffff; padding: 6px; min-height: 80px; display: flex; flex-direction: column; gap: 4px;">
          <div style="font-size: 0.8rem; font-weight: 700; color: #444;">${day}</div>
          <div style="display: flex; flex-direction: column; gap: 2px;">
            ${dayEvents.map((ev) => `
              <div style="
                background: #e3f2fd; color: #0d47a1; border-radius: 4px; padding: 2px 4px; font-size: 0.72rem;
                font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer;
              " title="${this.escapeHtml(ev.title)}">
                • ${this.escapeHtml(ev.title)}
              </div>
            `).join("")}
          </div>
        </div>
      `;
    }

    html += `</div>`;
    grid.innerHTML = html;
  }

  escapeHtml(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
}

// =============================================================================
// 4. NOTIFICATION CENTER BELL & PREFERENCES
// =============================================================================

export class NotificationCenter {
  constructor(options = {}) {
    this.bellElement = options.bellElement || document.getElementById("notifBellBtn");
    this.badgeElement = options.badgeElement || document.getElementById("notifBadge");
    this.unreadCount = 0;
    this.notifications = [];
  }

  init() {
    if (this.bellElement) {
      this.bellElement.onclick = (e) => {
        e.stopPropagation();
        this.toggleDropdown();
      };
    }
    this.pollNotifications();
  }

  async pollNotifications() {
    try {
      const res = await fetch("/api/classroom/notifications");
      if (res.ok) {
        this.notifications = await res.json();
        this.unreadCount = this.notifications.filter((n) => !n.is_read).length;
        if (this.badgeElement) {
          this.badgeElement.textContent = this.unreadCount;
          this.badgeElement.style.display = this.unreadCount > 0 ? "inline-block" : "none";
        }
      }
    } catch (e) {
      // offline silent
    }
  }

  toggleDropdown() {
    let dd = document.getElementById("notifDropdown");
    if (dd) {
      dd.remove();
      return;
    }

    dd = document.createElement("div");
    dd.id = "notifDropdown";
    dd.style.cssText = `
      position: absolute; top: 56px; right: 16px; width: 340px; background: #fff;
      border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5); border-radius: 12px;
      box-shadow: 0 6px 20px rgba(0,0,0,0.15); z-index: 10000; display: flex; flex-direction: column;
      max-height: 440px; overflow: hidden;
    `;

    dd.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid #eee;">
        <span style="font-weight: 700; font-size: 0.95rem;">Уведомления</span>
        <div style="display: flex; gap: 8px;">
          <button id="notifBtnReadAll" style="border:none;background:transparent;color:#005ac1;cursor:pointer;font-size:0.78rem;font-weight:600;">Прочитать все</button>
          <button id="notifBtnPrefs" style="border:none;background:transparent;cursor:pointer;font-size:0.85rem;" title="Настройки">⚙</button>
        </div>
      </div>
      <div id="notifList" style="flex:1; overflow-y:auto; display:flex; flex-direction:column;">
        ${this.notifications.length === 0 ? `<div style="padding: 24px; text-align: center; color: #888; font-size: 0.85rem;">Нет новых уведомлений</div>` : ""}
      </div>
    `;

    document.body.appendChild(dd);

    const list = document.getElementById("notifList");
    if (list && this.notifications.length > 0) {
      list.innerHTML = this.notifications.map((n) => `
        <div style="padding: 10px 14px; border-bottom: 1px solid #f5f5f5; background: ${n.is_read ? "#fff" : "#f0f7ff"}; font-size: 0.83rem;">
          <div style="font-weight: 700;">${this.escapeHtml(n.title)}</div>
          <div style="color: #444; margin-top: 2px;">${this.escapeHtml(n.body_text || "")}</div>
          <div style="font-size: 0.72rem; color: #888; margin-top: 4px;">${new Date(n.created_at * 1000).toLocaleString()}</div>
        </div>
      `).join("");
    }

    document.getElementById("notifBtnReadAll").onclick = async () => {
      await fetch("/api/classroom/notifications/read-all", { method: "POST" });
      this.pollNotifications();
      dd.remove();
    };

    document.getElementById("notifBtnPrefs").onclick = () => {
      dd.remove();
      this.openPrefsModal();
    };

    const closeHandler = (e) => {
      if (!dd.contains(e.target) && e.target !== this.bellElement) {
        dd.remove();
        document.removeEventListener("click", closeHandler);
      }
    };
    setTimeout(() => document.addEventListener("click", closeHandler), 10);
  }

  async openPrefsModal() {
    let modal = document.getElementById("notifPrefsModal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "notifPrefsModal";
      modal.style.cssText = `
        position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 10001;
        display: flex; align-items: center; justify-content: center;
      `;
      document.body.appendChild(modal);
    }

    modal.innerHTML = `
      <div style="background: #fff; width: 440px; border-radius: 14px; padding: 20px; box-shadow: 0 8px 24px rgba(0,0,0,0.2); display: flex; flex-direction: column; gap: 14px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <h3 style="margin: 0;">Настройки уведомлений</h3>
          <button id="npBtnClose" style="border:none;background:transparent;cursor:pointer;font-size:1.2rem;">✕</button>
        </div>
        <div style="display: flex; flex-direction: column; gap: 10px; font-size: 0.88rem;">
          <label style="display: flex; align-items: center; gap: 8px;">
            <input type="checkbox" id="npGlobalPush" checked>
            <span>Включить Push-уведомления</span>
          </label>
          <label style="display: flex; align-items: center; gap: 8px;">
            <input type="checkbox" id="npCommentsPush" checked>
            <span>Уведомлять о новых комментариях и @упоминаниях</span>
          </label>
          <label style="display: flex; align-items: center; gap: 8px;">
            <input type="checkbox" id="npGradePush" checked>
            <span>Уведомлять о выставлении и возврате оценок</span>
          </label>
        </div>
        <button id="npBtnSave" class="btn btn-primary" style="
          align-self: flex-end; padding: 8px 18px; border-radius: 8px; background: #005ac1; color: #fff; border: none; font-weight: 600; cursor: pointer;
        ">Сохранить</button>
      </div>
    `;

    document.getElementById("npBtnClose").onclick = () => modal.remove();
    document.getElementById("npBtnSave").onclick = async () => {
      await fetch("/api/classroom/notification-prefs", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          global_enabled: document.getElementById("npGlobalPush").checked,
          prefs: {
            comments: document.getElementById("npCommentsPush").checked,
            grades: document.getElementById("npGradePush").checked,
          },
        }),
      });
      modal.remove();
    };
  }

  escapeHtml(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
}

// =============================================================================
// 5. DOMAIN ADMIN CONSOLE (ORG UNITS, VERIFIED TEACHER, ONEROSTER, AUDIT, TAKEOUT)
// =============================================================================

export class DomainAdminConsole {
  constructor(options = {}) {
    this.container = options.container || document.getElementById("appMain");
    this.activeSection = "org_units"; // 'org_units' | 'teachers' | 'oneroster' | 'audit'
    this.orgUnits = [];
    this.users = [];
    this.auditLogs = [];
  }

  async render() {
    if (!this.container) return;
    this.container.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 16px; padding: 4px;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
          <div>
            <h2 style="margin: 0; font-size: 1.4rem;">Админ-консоль домена</h2>
            <div style="font-size: 0.82rem; color: #666;">Управление структурой, пользователями, импортом и аудитом школы</div>
          </div>
          <div style="display: flex; align-items: center; gap: 10px;">
            <a href="/api/classroom/admin/takeout.zip" download="bormoclass-takeout.zip" class="btn btn-secondary" style="
              display: flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 8px;
              border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5); background: var(--md-sys-color-surface, #ffffff);
              font-weight: 600; font-size: 0.85rem; cursor: pointer; text-decoration: none; color: inherit;
            ">
              📦 Выгрузка архива Takeout (.zip / .imscc)
            </a>
          </div>
        </div>

        <!-- Admin Navigation Tabs -->
        <div class="nav-rail" style="display: flex; gap: 4px; border-bottom: 2px solid #e3e8ef; padding-bottom: 4px;">
          <button id="admTabUnits" class="nav-tab-btn ${this.activeSection === "org_units" ? "active" : ""}" style="padding: 8px 16px; border:none; background:transparent; font-weight:600; cursor:pointer;">
            🏢 Подразделения (Org Units)
          </button>
          <button id="admTabTeachers" class="nav-tab-btn ${this.activeSection === "teachers" ? "active" : ""}" style="padding: 8px 16px; border:none; background:transparent; font-weight:600; cursor:pointer;">
            🎓 Верификация учителей
          </button>
          <button id="admTabOneRoster" class="nav-tab-btn ${this.activeSection === "oneroster" ? "active" : ""}" style="padding: 8px 16px; border:none; background:transparent; font-weight:600; cursor:pointer;">
            📥 Импорт OneRoster CSV
          </button>
          <button id="admTabAudit" class="nav-tab-btn ${this.activeSection === "audit" ? "active" : ""}" style="padding: 8px 16px; border:none; background:transparent; font-weight:600; cursor:pointer;">
            📜 Журнал аудита
          </button>
        </div>

        <!-- Dynamic Content Section -->
        <div id="admContent" style="background: #fff; border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5); border-radius: 12px; padding: 20px;">
          Загрузка раздела...
        </div>
      </div>
    `;

    this.bindEvents();
    await this.loadSection();
  }

  bindEvents() {
    const tabUnits = document.getElementById("admTabUnits");
    const tabTeachers = document.getElementById("admTabTeachers");
    const tabOneRoster = document.getElementById("admTabOneRoster");
    const tabAudit = document.getElementById("admTabAudit");

    if (tabUnits) tabUnits.onclick = () => { this.activeSection = "org_units"; this.render(); };
    if (tabTeachers) tabTeachers.onclick = () => { this.activeSection = "teachers"; this.render(); };
    if (tabOneRoster) tabOneRoster.onclick = () => { this.activeSection = "oneroster"; this.render(); };
    if (tabAudit) tabAudit.onclick = () => { this.activeSection = "audit"; this.render(); };
  }

  async loadSection() {
    const content = document.getElementById("admContent");
    if (!content) return;

    if (this.activeSection === "org_units") {
      await this.renderOrgUnitsSection(content);
    } else if (this.activeSection === "teachers") {
      await this.renderTeachersSection(content);
    } else if (this.activeSection === "oneroster") {
      this.renderOneRosterSection(content);
    } else if (this.activeSection === "audit") {
      await this.renderAuditSection(content);
    }
  }

  async renderOrgUnitsSection(content) {
    const res = await fetch("/api/classroom/admin/org-units");
    this.orgUnits = res.ok ? await res.json() : [];

    content.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
        <h3 style="margin: 0;">Дерево подразделений школы</h3>
        <button id="admBtnNewUnit" class="btn btn-primary" style="padding: 6px 14px; border-radius: 8px; background: #005ac1; color:#fff; border:none; cursor:pointer; font-weight:600;">
          + Создать подразделение
        </button>
      </div>
      <div style="display: flex; flex-direction: column; gap: 8px;">
        ${this.orgUnits.length === 0 ? `<div style="color: #888;">Подразделения еще не созданы.</div>` : ""}
        ${this.orgUnits.map((u) => `
          <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; border: 1px solid #eee; border-radius: 8px;">
            <div>
              <div style="font-weight: 700;">${this.escapeHtml(u.unit_title)}</div>
              <div style="font-size: 0.78rem; color: #666;">ID: ${u.id} • Учебный год: ${this.escapeHtml(u.academic_year || "2026-2027")}</div>
            </div>
            <button class="adm-btn-del-unit" data-id="${u.id}" style="border:none;background:transparent;color:#d32f2f;cursor:pointer;">Удалить</button>
          </div>
        `).join("")}
      </div>
    `;

    document.getElementById("admBtnNewUnit").onclick = async () => {
      const title = prompt("Название подразделения (например, «Старшая школа»):");
      if (title) {
        await fetch("/api/classroom/admin/org-units", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ unit_title: title }),
        });
        this.loadSection();
      }
    };

    content.querySelectorAll(".adm-btn-del-unit").forEach((btn) => {
      btn.onclick = async () => {
        if (confirm("Удалить подразделение?")) {
          await fetch(`/api/classroom/admin/org-units/${btn.dataset.id}`, { method: "DELETE" });
          this.loadSection();
        }
      };
    });
  }

  async renderTeachersSection(content) {
    const res = await fetch("/api/classroom/admin/users?role=teacher");
    this.users = res.ok ? await res.json() : [];

    content.innerHTML = `
      <h3 style="margin-top: 0;">Верификация учителей</h3>
      <p style="font-size: 0.85rem; color: #666;">Верифицированные учителя получают право создавать курсы и выставлять оценки.</p>
      <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 14px;">
        ${this.users.map((u) => `
          <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; border: 1px solid #eee; border-radius: 8px;">
            <div>
              <div style="font-weight: 700;">${this.escapeHtml(u.handle)}</div>
              <div style="font-size: 0.78rem; color: #666;">ID: ${u.id} • Роль: ${u.role}</div>
            </div>
            <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 0.85rem;">
              <input type="checkbox" class="adm-chk-verified" data-uid="${u.id}" ${u.verified_teacher ? "checked" : ""}>
              <span>Верифицирован</span>
            </label>
          </div>
        `).join("")}
      </div>
    `;

    content.querySelectorAll(".adm-chk-verified").forEach((chk) => {
      chk.onchange = async (e) => {
        await fetch(`/api/classroom/admin/users/${chk.dataset.uid}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ verified_teacher: e.target.checked }),
        });
      };
    });
  }

  renderOneRosterSection(content) {
    content.innerHTML = `
      <h3 style="margin-top: 0;">Импорт расписания OneRoster CSV</h3>
      <p style="font-size: 0.85rem; color: #666;">
        Перетащите CSV-файлы стандартов OneRoster (classes.csv, users.csv, enrollments.csv) или вставьте текст ниже:
      </p>
      <div id="admDropZone" style="
        border: 2px dashed #005ac1; border-radius: 12px; padding: 32px; text-align: center;
        background: #f0f7ff; cursor: pointer; margin: 16px 0;
      ">
        <div style="font-size: 1.8rem; margin-bottom: 6px;">📂</div>
        <div style="font-weight: 600;">Перетащите OneRoster CSV сюда или нажмите для выбора</div>
        <input type="file" id="admFileInput" accept=".csv" style="display: none;">
      </div>
      <textarea id="admCsvTextarea" rows="6" placeholder="Или вставьте CSV текст здесь (title, grade, subjectCode)..." style="
        width: 100%; box-sizing: border-box; padding: 10px; border-radius: 8px; border: 1px solid #ccc; font-family: monospace; font-size: 0.85rem;
      "></textarea>
      <button id="admBtnSubmitCsv" class="btn btn-primary" style="
        margin-top: 12px; padding: 8px 18px; border-radius: 8px; background: #005ac1; color: #fff; border: none; font-weight: 600; cursor: pointer;
      ">Импортировать в домен</button>
    `;

    const dropZone = document.getElementById("admDropZone");
    const fileInput = document.getElementById("admFileInput");
    dropZone.onclick = () => fileInput.click();

    fileInput.onchange = (e) => {
      const file = e.target.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (re) => {
          document.getElementById("admCsvTextarea").value = re.target.result;
        };
        reader.readAsText(file);
      }
    };

    document.getElementById("admBtnSubmitCsv").onclick = async () => {
      const text = document.getElementById("admCsvTextarea").value.trim();
      if (!text) {
        alert("Вставьте CSV данные для импорта");
        return;
      }
      const res = await fetch("/api/classroom/admin/import-oneroster", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ csv_text: text }),
      });
      if (res.ok) {
        const data = await res.json();
        alert(`Импортировано: ${data.imported_classes} классов, ${data.imported_users} пользователей!`);
      } else {
        alert("Ошибка импорта OneRoster CSV");
      }
    };
  }

  async renderAuditSection(content) {
    const res = await fetch("/api/classroom/admin/audit-logs");
    this.auditLogs = res.ok ? await res.json() : [];

    content.innerHTML = `
      <h3 style="margin-top: 0;">Журнал аудита действий</h3>
      <table style="width: 100%; border-collapse: collapse; font-size: 0.85rem; margin-top: 12px;">
        <thead>
          <tr style="background: #f0f4f9; text-align: left;">
            <th style="padding: 8px 12px; border: 1px solid #ddd;">Время</th>
            <th style="padding: 8px 12px; border: 1px solid #ddd;">Действие</th>
            <th style="padding: 8px 12px; border: 1px solid #ddd;">Объект</th>
            <th style="padding: 8px 12px; border: 1px solid #ddd;">Детали</th>
          </tr>
        </thead>
        <tbody>
          ${this.auditLogs.map((log) => `
            <tr>
              <td style="padding: 8px 12px; border: 1px solid #ddd; white-space: nowrap;">${new Date(log.created_at * 1000).toLocaleString()}</td>
              <td style="padding: 8px 12px; border: 1px solid #ddd; font-weight: 600;">${this.escapeHtml(log.action_code)}</td>
              <td style="padding: 8px 12px; border: 1px solid #ddd;">${this.escapeHtml(log.target_kind)} #${log.target_id}</td>
              <td style="padding: 8px 12px; border: 1px solid #ddd; font-family: monospace; font-size: 0.78rem;">${this.escapeHtml(JSON.stringify(log.details))}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  }

  escapeHtml(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
}
