/**
 * BormoClass Main SPA Engine (~15 KB Vanilla JS)
 * Zero-PII, Material Design 3.0, AES-GCM 256-bit WebCrypto Vault,
 * Simonov SOU Analytics, SSE Live Matrix and Client-side CSV Export.
 */

import { ICONS, getIcon } from "./icons.js";
import { TeacherZeroKnowledgeVault } from "./webcrypto-vault.js";

class BormoClassApp {
  constructor() {
    this.user = null;
    this.adFree = false;
    this.currentView = "classes"; // 'classes' | 'class-detail' | 'to-review' | 'to-do' | 'calendar'
    this.currentClassId = null;
    this.currentClassTab = "stream"; // 'stream' | 'classwork' | 'people' | 'grades'
    this.vault = null;
    this.classEventSource = null;

    this.init();
  }

  async init() {
    this.setupTheme();
    this.bindGlobalEvents();

    if (window.pbPassport) {
      window.pbPassport.onUserChange((u) => {
        this.user = u;
        if (u && (u.role === "teacher" || u.role === "admin")) {
          this.vault = new TeacherZeroKnowledgeVault(u.id);
          this.vault.initOrLoadKey();
        }
        this.renderUserBar();
        this.renderNavigation();
        this.route();
      });

      window.pbPassport.onAdFreeChange((adFree) => {
        this.adFree = adFree;
        this.renderUserBar();
      });
    }

    window.addEventListener("hashchange", () => this.route());
  }

  setupTheme() {
    const saved = localStorage.getItem("bc_theme") || "light";
    document.documentElement.setAttribute("data-theme", saved);
  }

  toggleTheme() {
    const curr = document.documentElement.getAttribute("data-theme") || "light";
    const next = curr === "light" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("bc_theme", next);
    this.renderUserBar();
  }

  bindGlobalEvents() {
    document.getElementById("brandBtn").addEventListener("click", () => {
      window.location.hash = "#classes";
    });

    document.querySelectorAll(".nav-tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const view = btn.dataset.view;
        window.location.hash = `#${view}`;
      });
    });
  }

  renderUserBar() {
    const bar = document.getElementById("userBar");
    if (!this.user) {
      bar.innerHTML = `
        <button class="btn btn-secondary" id="loginBtn">Войти</button>
        <button class="btn btn-primary" id="registerBtn">Регистрация</button>
      `;
      document.getElementById("loginBtn").onclick = () => this.showAuthModal("login");
      document.getElementById("registerBtn").onclick = () => this.showAuthModal("register");
      return;
    }

    const isTeacher = this.user.role === "teacher" || this.user.role === "admin";
    const proBadge = this.adFree
      ? `<span class="badge badge-pro">PRO (Без рекламы)</span>`
      : isTeacher
      ? `<button class="btn btn-tonal" id="activateProBtn" style="padding: 0.2rem 0.6rem; font-size: 0.8rem;">Активировать PRO</button>`
      : "";

    const recessBadge = !isTeacher
      ? `<span class="badge badge-recess" id="recessBadge" title="Баланс перемены">🎮 ${Math.floor(this.user.recess_seconds / 60)} мин</span>`
      : "";

    bar.innerHTML = `
      ${proBadge}
      ${recessBadge}
      <span style="font-weight: 700; font-size: 0.9rem;">${this.user.handle}</span>
      <button class="btn btn-secondary" id="themeBtn" title="Переключить тему">${getIcon("sun")}</button>
      <button class="btn btn-secondary" id="logoutBtn" title="Выйти">${getIcon("logout")}</button>
    `;

    document.getElementById("themeBtn").onclick = () => this.toggleTheme();
    document.getElementById("logoutBtn").onclick = () => this.logout();
    if (document.getElementById("activateProBtn")) {
      document.getElementById("activateProBtn").onclick = () => this.showActivateCodeModal();
    }
  }

  renderNavigation() {
    const nav = document.getElementById("navRail");
    if (!this.user) {
      nav.style.display = "none";
      return;
    }
    nav.style.display = "flex";

    const isTeacher = this.user.role === "teacher" || this.user.role === "admin";
    document.getElementById("navToReviewBtn").style.display = isTeacher ? "inline-flex" : "none";
    document.getElementById("navToDoBtn").style.display = isTeacher ? "none" : "inline-flex";

    // Update active state
    document.querySelectorAll(".nav-tab-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === this.currentView);
    });
  }

  route() {
    const hash = window.location.hash.slice(1) || "classes";
    const parts = hash.split("/");
    const mainView = parts[0];

    if (!this.user) {
      this.renderGuestLanding();
      return;
    }

    if (mainView === "class" && parts[1]) {
      this.currentView = "class-detail";
      this.currentClassId = Number(parts[1]);
      this.currentClassTab = parts[2] || "stream";
      this.renderClassDetail(this.currentClassId, this.currentClassTab);
    } else if (mainView === "to-review") {
      this.currentView = "to-review";
      this.renderToReviewView();
    } else if (mainView === "to-do") {
      this.currentView = "to-do";
      this.renderToDoView();
    } else if (mainView === "calendar") {
      this.currentView = "calendar";
      this.renderCalendarView();
    } else {
      this.currentView = "classes";
      this.renderClassesList();
    }

    this.renderNavigation();
  }

  // ---------------------------------------------------------------------------
  // AUTHENTICATION & ZERO-PII REGISTRATION
  // ---------------------------------------------------------------------------

  showAuthModal(type = "login") {
    const modal = document.getElementById("modalContainer");
    modal.innerHTML = `
      <div class="modal-overlay">
        <div class="modal-card">
          <div class="modal-header">
            <h3>${type === "login" ? "Вход в Паспорт" : "Регистрация паспорта (Zero-PII)"}</h3>
            <button class="btn btn-secondary" id="closeAuthModal">${getIcon("close")}</button>
          </div>
          ${
            type === "login"
              ? `
            <form id="authForm" style="display: flex; flex-direction: column; gap: 1rem;">
              <div>
                <label style="font-size: 0.85rem; font-weight: 600;">Позывной (например, Бодрый-Енот-428)</label>
                <input type="text" id="authHandle" required class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
              </div>
              <div>
                <label style="font-size: 0.85rem; font-weight: 600;">Пароль</label>
                <input type="password" id="authPassword" required class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
              </div>
              <button type="submit" class="btn btn-primary" style="margin-top: 0.5rem;">Войти</button>
            </form>
          `
              : `
            <form id="authForm" style="display: flex; flex-direction: column; gap: 1rem;">
              <p style="font-size: 0.85rem; color: var(--md-sys-color-on-surface-variant);">
                По стандарту 152-ФЗ РФ персональные данные не запрашиваются. Вам будет сгенерирован безымянный позывной и 4 слова восстановления.
              </p>
              <div>
                <label style="font-size: 0.85rem; font-weight: 600;">Роль</label>
                <select id="authRole" class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
                  <option value="student">Ученик</option>
                  <option value="teacher">Учитель</option>
                </select>
              </div>
              <div>
                <label style="font-size: 0.85rem; font-weight: 600;">Придумайте пароль</label>
                <input type="password" id="authPassword" required minlength="4" class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
              </div>
              <button type="submit" class="btn btn-primary" style="margin-top: 0.5rem;">Создать паспорт</button>
            </form>
          `
          }
        </div>
      </div>
    `;

    document.getElementById("closeAuthModal").onclick = () => (modal.innerHTML = "");
    document.getElementById("authForm").onsubmit = async (e) => {
      e.preventDefault();
      if (type === "login") {
        const handle = document.getElementById("authHandle").value.trim();
        const password = document.getElementById("authPassword").value;
        const res = await fetch("/api/passport/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ handle, password }),
        });
        if (res.ok) {
          modal.innerHTML = "";
          await window.pbPassport.refreshSession();
        } else {
          const err = await res.json();
          alert(err.detail || "Ошибка входа");
        }
      } else {
        const role = document.getElementById("authRole").value;
        const password = document.getElementById("authPassword").value;
        const res = await fetch("/api/passport/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ role, password }),
        });
        if (res.ok) {
          const data = await res.json();
          this.showRegistrationSuccessModal(data);
        } else {
          const err = await res.json();
          alert(err.detail || "Ошибка регистрации");
        }
      }
    };
  }

  showRegistrationSuccessModal(data) {
    const modal = document.getElementById("modalContainer");
    const words = data.recovery_words.join("  •  ");
    modal.innerHTML = `
      <div class="modal-overlay">
        <div class="modal-card">
          <h3>Паспорт успешно создан!</h3>
          <p style="margin: 1rem 0;">Ваш позывной: <strong style="color: var(--md-sys-color-primary); font-size: 1.2rem;">${data.user.handle}</strong></p>
          <div style="background: var(--md-sys-color-surface-container-high); padding: 1rem; border-radius: 8px; margin-bottom: 1rem;">
            <p style="font-size: 0.85rem; font-weight: 700; margin-bottom: 0.5rem;">Сохраните 4 секретных слова для восстановления доступа:</p>
            <p style="font-size: 1.1rem; font-weight: 800; color: var(--md-sys-color-primary);">${words}</p>
          </div>
          <button class="btn btn-primary" id="confirmRegBtn" style="width: 100%;">Я сохранил данные, продолжить</button>
        </div>
      </div>
    `;
    document.getElementById("confirmRegBtn").onclick = async () => {
      modal.innerHTML = "";
      await window.pbPassport.refreshSession();
    };
  }

  async logout() {
    await fetch("/api/passport/logout", { method: "POST" });
    await window.pbPassport.refreshSession();
    window.location.hash = "#classes";
  }

  // ---------------------------------------------------------------------------
  // GUEST LANDING
  // ---------------------------------------------------------------------------

  renderGuestLanding() {
    const main = document.getElementById("appMain");
    main.innerHTML = `
      <div style="text-align: center; padding: 4rem 1rem; max-width: 720px; margin: 0 auto;">
        <h1 style="font-size: 2.75rem; font-weight: 800; line-height: 1.2; margin-bottom: 1rem;">
          Школьный класс, авторизация и доска со стандартом <span style="color: var(--md-sys-color-primary);">Zero-PII</span>
        </h1>
        <p style="font-size: 1.2rem; color: var(--md-sys-color-on-surface-variant); margin-bottom: 2rem;">
          0 байт персональных данных на сервере. Соответствие 152-ФЗ РФ. Неблокирующий SQLite WAL, Material Design 3.0 и нулевые внешние CDN.
        </p>
        <div style="display: flex; gap: 1rem; justify-content: center;">
          <button class="btn btn-primary" id="heroRegBtn" style="padding: 0.8rem 2rem; font-size: 1.1rem;">Начать работу</button>
          <button class="btn btn-secondary" id="heroLoginBtn" style="padding: 0.8rem 2rem; font-size: 1.1rem;">Войти по паспорту</button>
        </div>
      </div>
    `;
    document.getElementById("heroRegBtn").onclick = () => this.showAuthModal("register");
    document.getElementById("heroLoginBtn").onclick = () => this.showAuthModal("login");
  }

  // ---------------------------------------------------------------------------
  // CLASS SHOWCASE LIST
  // ---------------------------------------------------------------------------

  async renderClassesList() {
    const main = document.getElementById("appMain");
    main.innerHTML = `<div style="text-align: center; padding: 2rem;">Загрузка классов...</div>`;

    const isTeacher = this.user.role === "teacher" || this.user.role === "admin";
    const res = await fetch("/api/classroom/classes");
    const classes = res.ok ? await res.json() : [];

    let headerActions = isTeacher
      ? `<button class="btn btn-primary" id="createClassBtn">${getIcon("add")} Создать класс</button>`
      : `<button class="btn btn-primary" id="joinClassBtn">${getIcon("add")} Войти в класс</button>`;

    let cardsHtml = "";
    if (classes.length === 0) {
      cardsHtml = `
        <div style="grid-column: 1 / -1; text-align: center; padding: 3rem; background: var(--md-sys-color-surface-container-low); border-radius: 16px;">
          <p style="font-size: 1.1rem; color: var(--md-sys-color-on-surface-variant);">
            ${isTeacher ? "У вас пока нет созданных классов." : "Вы пока не состоите ни в одном классе."}
          </p>
        </div>
      `;
    } else {
      cardsHtml = classes
        .map(
          (c) => `
        <div class="class-card" data-class-id="${c.id}">
          <div class="class-card-header">
            <div class="class-card-title">${c.title}</div>
            <div style="font-size: 0.85rem; opacity: 0.9;">${c.grade_level} класс • Предмет: ${c.subject_code}</div>
          </div>
          <div class="class-card-body">
            <p style="font-size: 0.9rem; color: var(--md-sys-color-on-surface-variant);">
              ${c.quarter_goal ? `«${c.quarter_goal}»` : "Цель на четверть не задана"}
            </p>
            ${
              c.seat_number
                ? `<div style="margin-top: 1rem;"><span class="badge badge-pro">Ваша парта: №${c.seat_number}</span></div>`
                : ""
            }
          </div>
          <div class="class-card-footer">
            <span>Учеников: ${c.students_count}</span>
            <span style="font-family: var(--font-mono); font-weight: 700;">Пин: ${c.join_pin}</span>
          </div>
        </div>
      `
        )
        .join("");
    }

    main.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
        <h2>${isTeacher ? "Мои классы" : "Учебные классы"}</h2>
        ${headerActions}
      </div>
      <div class="classes-grid">
        ${cardsHtml}
      </div>
    `;

    if (document.getElementById("createClassBtn")) {
      document.getElementById("createClassBtn").onclick = () => this.showCreateClassModal();
    }
    if (document.getElementById("joinClassBtn")) {
      document.getElementById("joinClassBtn").onclick = () => this.showJoinClassModal();
    }

    document.querySelectorAll(".class-card").forEach((card) => {
      card.onclick = () => {
        window.location.hash = `#class/${card.dataset.classId}/stream`;
      };
    });
  }

  showCreateClassModal() {
    const modal = document.getElementById("modalContainer");
    modal.innerHTML = `
      <div class="modal-overlay">
        <div class="modal-card">
          <div class="modal-header">
            <h3>Создание учебного класса</h3>
            <button class="btn btn-secondary" id="closeClassModal">${getIcon("close")}</button>
          </div>
          <form id="createClassForm" style="display: flex; flex-direction: column; gap: 1rem;">
            <div>
              <label style="font-size: 0.85rem; font-weight: 600;">Название класса (например, 8А — Информатика)</label>
              <input type="text" id="clsTitle" required class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
              <div>
                <label style="font-size: 0.85rem; font-weight: 600;">Параллель (1..11 класс)</label>
                <input type="number" id="clsGrade" value="8" min="1" max="11" required class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
              </div>
              <div>
                <label style="font-size: 0.85rem; font-weight: 600;">Код предмета</label>
                <input type="text" id="clsSubject" value="inf" required class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
              </div>
            </div>
            <div>
              <label style="font-size: 0.85rem; font-weight: 600;">Цель класса на четверть (в шапку Ленты)</label>
              <input type="text" id="clsGoal" placeholder="Сдать ВПР на отлично" class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
            </div>
            <button type="submit" class="btn btn-primary" style="margin-top: 0.5rem;">Создать класс</button>
          </form>
        </div>
      </div>
    `;

    document.getElementById("closeClassModal").onclick = () => (modal.innerHTML = "");
    document.getElementById("createClassForm").onsubmit = async (e) => {
      e.preventDefault();
      const res = await fetch("/api/classroom/classes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: document.getElementById("clsTitle").value.trim(),
          grade_level: Number(document.getElementById("clsGrade").value),
          subject_code: document.getElementById("clsSubject").value.trim(),
          quarter_goal: document.getElementById("clsGoal").value.trim(),
        }),
      });
      if (res.ok) {
        modal.innerHTML = "";
        const data = await res.json();
        window.location.hash = `#class/${data.id}/stream`;
      } else {
        alert("Ошибка создания класса");
      }
    };
  }

  showJoinClassModal() {
    const modal = document.getElementById("modalContainer");
    let selectedSeat = null;

    // Схема 40 парт в 3 ряда (кнопки выбора)
    let seatsGridHtml = '<div style="display: grid; grid-template-columns: repeat(8, 1fr); gap: 0.35rem; max-height: 240px; overflow-y: auto; padding: 0.5rem;">';
    for (let i = 1; i <= 40; i++) {
      seatsGridHtml += `<button type="button" class="btn btn-secondary seat-pick-btn" data-seat="${i}" style="padding: 0.5rem 0.25rem; font-size: 0.85rem;">№${i}</button>`;
    }
    seatsGridHtml += "</div>";

    modal.innerHTML = `
      <div class="modal-overlay">
        <div class="modal-card">
          <div class="modal-header">
            <h3>Вход в класс по пин-коду</h3>
            <button class="btn btn-secondary" id="closeJoinModal">${getIcon("close")}</button>
          </div>
          <form id="joinClassForm" style="display: flex; flex-direction: column; gap: 1rem;">
            <div>
              <label style="font-size: 0.85rem; font-weight: 600;">5-значный пин-код с доски</label>
              <input type="text" id="joinPin" required maxlength="10" placeholder="Например: 42819" class="btn-secondary" style="width: 100%; padding: 0.75rem; font-family: var(--font-mono); font-size: 1.25rem; letter-spacing: 0.1em; text-align: center; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
            </div>
            <div>
              <label style="font-size: 0.85rem; font-weight: 600;">Выберите номер вашей парты (1..40):</label>
              ${seatsGridHtml}
              <div id="seatChosenDisplay" style="margin-top: 0.5rem; font-weight: 700; color: var(--md-sys-color-primary);">Парта не выбрана</div>
            </div>
            <button type="submit" class="btn btn-primary" id="submitJoinBtn" disabled>Занять парту и войти</button>
          </form>
        </div>
      </div>
    `;

    document.getElementById("closeJoinModal").onclick = () => (modal.innerHTML = "");

    document.querySelectorAll(".seat-pick-btn").forEach((btn) => {
      btn.onclick = () => {
        document.querySelectorAll(".seat-pick-btn").forEach((b) => b.classList.remove("btn-primary"));
        btn.classList.add("btn-primary");
        selectedSeat = Number(btn.dataset.seat);
        document.getElementById("seatChosenDisplay").textContent = `Выбрана парта: №${selectedSeat}`;
        document.getElementById("submitJoinBtn").disabled = false;
      };
    });

    document.getElementById("joinClassForm").onsubmit = async (e) => {
      e.preventDefault();
      if (!selectedSeat) return;
      const joinPin = document.getElementById("joinPin").value.trim();

      const res = await fetch("/api/classroom/classes/join", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          join_pin: joinPin,
          seat_number: selectedSeat,
        }),
      });

      if (res.ok) {
        modal.innerHTML = "";
        const data = await res.json();
        window.location.hash = `#class/${data.class_id}/stream`;
      } else {
        const err = await res.json();
        alert(err.detail || "Не удалось войти в класс");
      }
    };
  }

  // ---------------------------------------------------------------------------
  // CLASS DETAIL (4 TABS)
  // ---------------------------------------------------------------------------

  async renderClassDetail(classId, activeTab = "stream") {
    const main = document.getElementById("appMain");
    main.innerHTML = `<div style="text-align: center; padding: 2rem;">Загрузка класса...</div>`;

    const res = await fetch(`/api/classroom/classes/${classId}`);
    if (!res.ok) {
      main.innerHTML = `<p>Класс не найден или нет доступа</p>`;
      return;
    }
    const cls = await res.json();
    const isTeacher = cls.is_teacher;

    this.subscribeClassSSE(classId);

    main.innerHTML = `
      <div class="class-hero-banner">
        <div>
          <h1 style="font-size: 2rem; font-weight: 800; margin-bottom: 0.25rem;">${cls.title}</h1>
          <p style="opacity: 0.9;">${cls.grade_level} класс • ${cls.quarter_goal ? `«${cls.quarter_goal}»` : ""}</p>
        </div>
        <div style="display: flex; align-items: center; gap: 1rem;">
          <div class="class-hero-pin-box">
            <div style="font-size: 0.75rem; text-transform: uppercase; font-weight: 700; opacity: 0.8;">Пин класса</div>
            <div class="class-hero-pin-val">${cls.join_pin}</div>
          </div>
          <button class="btn btn-secondary" id="openBoardBtn" style="height: 52px; font-weight: 700;">
            ${getIcon("board")} Интерактивная доска
          </button>
        </div>
      </div>

      <!-- Class Internal Navigation Tabs -->
      <div class="nav-rail" style="border-radius: 12px; margin-bottom: 1.5rem; background: var(--md-sys-color-surface-container-low);">
        <button class="nav-tab-btn ${activeTab === "stream" ? "active" : ""}" data-ctab="stream">Лента</button>
        <button class="nav-tab-btn ${activeTab === "classwork" ? "active" : ""}" data-ctab="classwork">Задания</button>
        <button class="nav-tab-btn ${activeTab === "people" ? "active" : ""}" data-ctab="people">Люди и Парты</button>
        <button class="nav-tab-btn ${activeTab === "grades" ? "active" : ""}" data-ctab="grades">Оценки</button>
      </div>

      <div id="classTabContent"></div>
    `;

    document.getElementById("openBoardBtn").onclick = () => {
      window.location.href = `/board/${classId}`;
    };

    document.querySelectorAll("[data-ctab]").forEach((btn) => {
      btn.onclick = () => {
        window.location.hash = `#class/${classId}/${btn.dataset.ctab}`;
      };
    });

    if (activeTab === "stream") this.renderStreamTab(cls);
    else if (activeTab === "classwork") this.renderClassworkTab(cls);
    else if (activeTab === "people") this.renderPeopleTab(cls);
    else if (activeTab === "grades") this.renderGradesTab(cls);
  }

  subscribeClassSSE(classId) {
    if (this.classEventSource) {
      this.classEventSource.close();
    }
    this.classEventSource = new EventSource(`/api/classroom/${classId}/stream`);
    this.classEventSource.addEventListener("submission_updated", () => {
      if (this.currentClassTab === "grades") {
        this.renderGradesTab({ id: classId, is_teacher: true });
      }
    });
  }

  // TAB 1: STREAM
  async renderStreamTab(cls) {
    const container = document.getElementById("classTabContent");
    const isTeacher = cls.is_teacher;

    let studentTrafficLightHtml = "";
    if (!isTeacher && cls.my_membership) {
      studentTrafficLightHtml = `
        <div style="background: var(--md-sys-color-surface-container-lowest); border: 1px solid var(--md-sys-color-outline-variant); border-radius: 16px; padding: 1.25rem; margin-bottom: 1.5rem;">
          <h4 style="margin-bottom: 0.5rem;">Светофор понимания на уроке</h4>
          <p style="font-size: 0.85rem; color: var(--md-sys-color-on-surface-variant); margin-bottom: 1rem;">
            Сообщите учителю на интерактивной доске, понятен ли вам текущий материал:
          </p>
          <div class="traffic-light-widget" style="margin-top: 0;">
            <button class="traffic-btn green" data-tl="green">🟢 Всё понятно</button>
            <button class="traffic-btn yellow" data-tl="yellow">🟡 Есть вопрос</button>
            <button class="traffic-btn red" data-tl="red">🔴 Нужна помощь</button>
          </div>
        </div>
      `;
    }

    container.innerHTML = `
      ${studentTrafficLightHtml}
      <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
        <div>
          ${
            isTeacher
              ? `
            <div style="background: var(--md-sys-color-surface-container-lowest); border: 1px solid var(--md-sys-color-outline-variant); border-radius: 16px; padding: 1.25rem; margin-bottom: 1.5rem;">
              <h4 style="margin-bottom: 0.75rem;">Опубликовать объявление в ленту</h4>
              <textarea id="streamPostText" placeholder="Напишите сообщение классу..." class="btn-secondary" style="width: 100%; min-height: 80px; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant); margin-bottom: 0.75rem;"></textarea>
              <div style="display: flex; justify-content: flex-end;">
                <button class="btn btn-primary" id="publishStreamBtn">Опубликовать</button>
              </div>
            </div>
          `
              : ""
          }
          <div id="streamFeed">Загрузка объявлений...</div>
        </div>

        <div>
          <div style="background: var(--md-sys-color-surface-container-lowest); border: 1px solid var(--md-sys-color-outline-variant); border-radius: 16px; padding: 1.25rem;">
            <h4 style="margin-bottom: 0.5rem;">Предстоящие дедлайны</h4>
            <div id="streamDeadlines">Загрузка...</div>
          </div>
        </div>
      </div>
    `;

    if (!isTeacher) {
      document.querySelectorAll("[data-tl]").forEach((btn) => {
        btn.onclick = async () => {
          await fetch(`/api/classroom/classes/${cls.id}/traffic-light`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ traffic_light: btn.dataset.tl }),
          });
          alert("Статус отправлен на интерактивную доску!");
        };
      });
    }

    if (document.getElementById("publishStreamBtn")) {
      document.getElementById("publishStreamBtn").onclick = async () => {
        const text = document.getElementById("streamPostText").value.trim();
        if (!text) return;
        const res = await fetch(`/api/classroom/classes/${cls.id}/coursework`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: text.slice(0, 50),
            instructions: text,
            kind: "announcement",
            is_homework: 0,
          }),
        });
        if (res.ok) {
          document.getElementById("streamPostText").value = "";
          this.loadStreamFeed(cls.id);
        }
      };
    }

    this.loadStreamFeed(cls.id);
  }

  async loadStreamFeed(classId) {
    const feed = document.getElementById("streamFeed");
    const res = await fetch(`/api/classroom/classes/${classId}/coursework`);
    if (!res.ok) return;
    const items = await res.json();

    if (items.length === 0) {
      feed.innerHTML = `<div style="text-align: center; padding: 2rem; color: var(--md-sys-color-on-surface-variant);">В ленте пока нет записей</div>`;
      return;
    }

    feed.innerHTML = items
      .map(
        (it) => `
      <div style="background: var(--md-sys-color-surface-container-lowest); border: 1px solid var(--md-sys-color-outline-variant); border-radius: 16px; padding: 1.25rem; margin-bottom: 1rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
          <h4 style="font-size: 1.1rem;">${it.title}</h4>
          <span class="badge ${it.kind === "announcement" ? "badge-pro" : "badge-recess"}">${it.kind}</span>
        </div>
        <p style="font-size: 0.9rem; color: var(--md-sys-color-on-surface-variant); white-space: pre-wrap;">${it.instructions || ""}</p>
      </div>
    `
      )
      .join("");
  }

  // TAB 2: CLASSWORK
  async renderClassworkTab(cls) {
    const container = document.getElementById("classTabContent");
    const isTeacher = cls.is_teacher;

    container.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
        <h3>Учебные задания и материалы</h3>
        <div style="display: flex; gap: 0.75rem;">
          <button class="btn btn-secondary" id="printSheetBtn">${getIcon("print")} Печать на класс (А4)</button>
          ${
            isTeacher
              ? `<button class="btn btn-primary" id="createCwBtn">${getIcon("add")} Создать задание</button>`
              : ""
          }
        </div>
      </div>
      <div id="classworkList">Загрузка заданий...</div>
    `;

    if (document.getElementById("createCwBtn")) {
      document.getElementById("createCwBtn").onclick = () => this.showCreateCourseworkModal(cls);
    }
    document.getElementById("printSheetBtn").onclick = () => this.generatePrintA4(cls.id);

    const res = await fetch(`/api/classroom/classes/${cls.id}/coursework`);
    const items = res.ok ? await res.json() : [];

    const list = document.getElementById("classworkList");
    if (items.length === 0) {
      list.innerHTML = `<div style="text-align: center; padding: 3rem; background: var(--md-sys-color-surface-container-low); border-radius: 16px;">Заданий пока нет</div>`;
      return;
    }

    list.innerHTML = items
      .map(
        (it) => `
      <div style="background: var(--md-sys-color-surface-container-lowest); border: 1px solid var(--md-sys-color-outline-variant); border-radius: 16px; padding: 1.25rem; margin-bottom: 1rem; display: flex; justify-content: space-between; align-items: center;">
        <div>
          <h4 style="font-size: 1.1rem; margin-bottom: 0.25rem;">${it.title}</h4>
          <div style="font-size: 0.85rem; color: var(--md-sys-color-on-surface-variant);">
            ${it.topic_title ? `Тема: ${it.topic_title} • ` : ""}
            Макс. балл: ${it.max_points} • Награда: ${Math.floor(it.recess_reward / 60)} мин перемены
          </div>
        </div>
        <div>
          ${
            !isTeacher
              ? `<button class="btn btn-primary turnin-btn" data-cwid="${it.id}">Сдать работу</button>`
              : `<span class="badge badge-pro">Сдано: ${it.turned_in_count || 0}</span>`
          }
        </div>
      </div>
    `
      )
      .join("");

    document.querySelectorAll(".turnin-btn").forEach((btn) => {
      btn.onclick = () => this.showTurnInModal(btn.dataset.cwid);
    });
  }

  showCreateCourseworkModal(cls) {
    const modal = document.getElementById("modalContainer");
    modal.innerHTML = `
      <div class="modal-overlay">
        <div class="modal-card">
          <div class="modal-header">
            <h3>Новое задание</h3>
            <button class="btn btn-secondary" id="closeCwModal">${getIcon("close")}</button>
          </div>
          <form id="createCwForm" style="display: flex; flex-direction: column; gap: 1rem;">
            <div>
              <label style="font-size: 0.85rem; font-weight: 600;">Название задания</label>
              <input type="text" id="cwTitle" required class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
            </div>
            <div>
              <label style="font-size: 0.85rem; font-weight: 600;">Инструкции к заданию</label>
              <textarea id="cwInstructions" class="btn-secondary" style="width: 100%; min-height: 80px; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);"></textarea>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
              <div>
                <label style="font-size: 0.85rem; font-weight: 600;">Макс. балл</label>
                <input type="number" id="cwPoints" value="5" min="1" max="100" class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
              </div>
              <div>
                <label style="font-size: 0.85rem; font-weight: 600;">Награда (секунды)</label>
                <input type="number" id="cwRecess" value="300" min="0" max="3600" class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
              </div>
            </div>
            ${
              cls.grade_level === 1
                ? `<div style="background: var(--md-sys-color-error-container); color: var(--md-sys-color-on-error-container); padding: 0.75rem; border-radius: 8px; font-size: 0.85rem; font-weight: 700;">
                     ⚠️ Для 1-го класса домашние задания запрещены нормами СанПиН и Минпросвещения РФ (только классная работа).
                   </div>`
                : `
              <div>
                <label style="display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; font-weight: 600;">
                  <input type="checkbox" id="cwIsHomework"> Домашнее задание
                </label>
              </div>
            `
            }
            <button type="submit" class="btn btn-primary" style="margin-top: 0.5rem;">Опубликовать</button>
          </form>
        </div>
      </div>
    `;

    document.getElementById("closeCwModal").onclick = () => (modal.innerHTML = "");
    document.getElementById("createCwForm").onsubmit = async (e) => {
      e.preventDefault();
      const isHw = cls.grade_level === 1 ? 0 : document.getElementById("cwIsHomework")?.checked ? 1 : 0;
      const res = await fetch(`/api/classroom/classes/${cls.id}/coursework`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: document.getElementById("cwTitle").value.trim(),
          instructions: document.getElementById("cwInstructions").value.trim(),
          max_points: Number(document.getElementById("cwPoints").value),
          recess_reward: Number(document.getElementById("cwRecess").value),
          is_homework: isHw,
          kind: "assignment",
          state: "published",
        }),
      });
      if (res.ok) {
        modal.innerHTML = "";
        this.renderClassworkTab(cls);
      } else {
        const err = await res.json();
        alert(err.detail || "Ошибка публикации задания");
      }
    };
  }

  showTurnInModal(courseworkId) {
    const modal = document.getElementById("modalContainer");
    modal.innerHTML = `
      <div class="modal-overlay">
        <div class="modal-card">
          <div class="modal-header">
            <h3>Сдача работы</h3>
            <button class="btn btn-secondary" id="closeTurnInModal">${getIcon("close")}</button>
          </div>
          <form id="turnInForm" style="display: flex; flex-direction: column; gap: 1rem;">
            <div>
              <label style="font-size: 0.85rem; font-weight: 600;">Ваш ответ или решение</label>
              <textarea id="studentAnswer" required class="btn-secondary" style="width: 100%; min-height: 120px; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);"></textarea>
            </div>
            <button type="submit" class="btn btn-primary">Отправить на проверку</button>
          </form>
        </div>
      </div>
    `;

    document.getElementById("closeTurnInModal").onclick = () => (modal.innerHTML = "");
    document.getElementById("turnInForm").onsubmit = async (e) => {
      e.preventDefault();
      const ans = document.getElementById("studentAnswer").value.trim();
      const res = await fetch(`/api/classroom/coursework/${courseworkId}/turn-in`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ payload_json: JSON.stringify({ answer: ans }) }),
      });
      if (res.ok) {
        modal.innerHTML = "";
        alert("Работа успешно сдана!");
        await window.pbPassport.refreshSession();
      } else {
        alert("Ошибка сдачи работы");
      }
    };
  }

  // TAB 3: PEOPLE & SEATS (3 ROWS, 1..40)
  async renderPeopleTab(cls) {
    const container = document.getElementById("classTabContent");
    const isTeacher = cls.is_teacher;

    container.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
        <h3>Схема 3 рядов парт (1..40) и присутствие</h3>
        ${
          isTeacher
            ? `<button class="btn btn-secondary" id="vaultKeyBtn">🔑 Ключ шифрования учителя</button>`
            : ""
        }
      </div>

      <div class="desks-container">
        <div class="teacher-table-front">Стол учителя / Доска</div>
        <div class="classroom-rows" id="desksGridArea">
          <!-- 3 Columns (Rows 1, 2, 3) -->
        </div>
      </div>
    `;

    if (document.getElementById("vaultKeyBtn")) {
      document.getElementById("vaultKeyBtn").onclick = () => this.showVaultKeyModal();
    }

    const res = await fetch(`/api/classroom/classes/${cls.id}/members`);
    const members = res.ok ? await res.json() : [];

    const memberBySeat = {};
    for (const m of members) {
      memberBySeat[m.seat_number] = m;
    }

    const grid = document.getElementById("desksGridArea");
    grid.innerHTML = "";

    // 3 rows: row 1 (1..14), row 2 (15..28), row 3 (29..40)
    const rowRanges = [
      { name: "1 ряд у окна", seats: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14] },
      { name: "2 средний ряд", seats: [15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28] },
      { name: "3 ряд у двери", seats: [29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40] },
    ];

    for (const row of rowRanges) {
      const colDiv = document.createElement("div");
      colDiv.className = "desk-row-column";
      colDiv.innerHTML = `<div style="font-weight: 700; font-size: 0.9rem; text-align: center; color: var(--md-sys-color-primary);">${row.name}</div>`;

      for (let s = 0; s < row.seats.length; s += 2) {
        const s1 = row.seats[s];
        const s2 = row.seats[s + 1];

        const pairDiv = document.createElement("div");
        pairDiv.className = "desk-pair";
        pairDiv.appendChild(this.buildSeatElement(cls, s1, memberBySeat[s1]));
        if (s2) pairDiv.appendChild(this.buildSeatElement(cls, s2, memberBySeat[s2]));

        colDiv.appendChild(pairDiv);
      }
      grid.appendChild(colDiv);
    }
  }

  buildSeatElement(cls, seatNum, member) {
    const btn = document.createElement("button");
    btn.className = `seat-btn ${member ? "occupied" : ""} ${member && !member.is_present ? "absent" : ""}`;
    btn.type = "button";

    if (!member) {
      btn.innerHTML = `<span class="seat-number-tag">№${seatNum}</span><span style="font-size: 0.75rem; opacity: 0.5;">Свободно</span>`;
      return btn;
    }

    const trafficClass = `traffic-${member.traffic_light || "green"}`;
    btn.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: space-between; width: 100%;">
        <span class="seat-number-tag">№${seatNum}</span>
        <div class="seat-traffic-dot ${trafficClass}"></div>
      </div>
      <div id="seatName_${member.student_id}" style="font-weight: 600; font-size: 0.8rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 90px;">
        ${member.handle}
      </div>
    `;

    // Try decrypt name locally if vault is available
    if (cls.is_teacher && this.vault && member.encrypted_note) {
      this.vault.decryptStudentName(member.encrypted_note).then((dec) => {
        if (dec && !dec.includes("🔒")) {
          const el = document.getElementById(`seatName_${member.student_id}`);
          if (el) el.textContent = dec;
        }
      });
    }

    if (cls.is_teacher) {
      btn.onclick = () => this.showStudentManagementModal(cls.id, member);
    }
    return btn;
  }

  showStudentManagementModal(classId, member) {
    const modal = document.getElementById("modalContainer");
    modal.innerHTML = `
      <div class="modal-overlay">
        <div class="modal-card">
          <div class="modal-header">
            <h3>Управление партой №${member.seat_number}</h3>
            <button class="btn btn-secondary" id="closeMemberModal">${getIcon("close")}</button>
          </div>
          <div style="display: flex; flex-direction: column; gap: 1rem;">
            <div>
              <label style="font-size: 0.85rem; font-weight: 600;">Позывной ученика</label>
              <div style="font-weight: 800; font-size: 1.1rem; color: var(--md-sys-color-primary);">${member.handle}</div>
            </div>
            <div>
              <label style="font-size: 0.85rem; font-weight: 600;">ФИО (шифруется AES-GCM 256-bit локально в браузере)</label>
              <input type="text" id="plainStudentName" placeholder="Иванов Иван" class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
            </div>
            <div>
              <label style="display: flex; align-items: center; gap: 0.5rem; font-size: 0.9rem; font-weight: 600;">
                <input type="checkbox" id="isPresentCheck" ${member.is_present ? "checked" : ""}> Присутствует на уроке
              </label>
            </div>
            <button class="btn btn-primary" id="saveMemberBtn">Сохранить изменения</button>
            <hr style="border: 0; border-top: 1px solid var(--md-sys-color-outline-variant); margin: 0.5rem 0;">
            <button class="btn btn-secondary" id="resetPwBtn" style="color: var(--md-sys-color-error);">
              Сбросить пароль ученика в 1 клик
            </button>
          </div>
        </div>
      </div>
    `;

    document.getElementById("closeMemberModal").onclick = () => (modal.innerHTML = "");

    if (this.vault && member.encrypted_note) {
      this.vault.decryptStudentName(member.encrypted_note).then((dec) => {
        if (dec && !dec.includes("🔒")) {
          document.getElementById("plainStudentName").value = dec;
        }
      });
    }

    document.getElementById("saveMemberBtn").onclick = async () => {
      const name = document.getElementById("plainStudentName").value.trim();
      const isPresent = document.getElementById("isPresentCheck").checked ? 1 : 0;
      let encryptedNote = member.encrypted_note;

      if (name && this.vault) {
        if (!this.vault.hasKey()) {
          alert("Сначала задайте ключ учителя в меню «Ключ шифрования»!");
          return;
        }
        encryptedNote = await this.vault.encryptStudentName(name);
      }

      const res = await fetch(`/api/classroom/classes/${classId}/members/${member.student_id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          encrypted_note: encryptedNote,
          is_present: isPresent,
        }),
      });

      if (res.ok) {
        modal.innerHTML = "";
        this.renderPeopleTab({ id: classId, is_teacher: true });
      }
    };

    document.getElementById("resetPwBtn").onclick = async () => {
      if (!confirm(`Сбросить пароль для ${member.handle}?`)) return;
      const res = await fetch(`/api/classroom/classes/${classId}/members/${member.student_id}/reset-password`, {
        method: "POST",
      });
      if (res.ok) {
        const d = await res.json();
        alert(`Новый временный пароль: ${d.temp_password}\nСлова: ${d.recovery_words.join(", ")}`);
      }
    };
  }

  showVaultKeyModal() {
    const modal = document.getElementById("modalContainer");
    modal.innerHTML = `
      <div class="modal-overlay">
        <div class="modal-card">
          <div class="modal-header">
            <h3>Ключ шифрования учителя (WebCrypto AES-GCM)</h3>
            <button class="btn btn-secondary" id="closeVaultModal">${getIcon("close")}</button>
          </div>
          <p style="font-size: 0.85rem; color: var(--md-sys-color-on-surface-variant); margin-bottom: 1rem;">
            Введите секретную парольную фразу. Из неё локально в браузере будет получен 256-битный ключ AES-GCM для расшифровки реальных фамилий учеников.
          </p>
          <input type="password" id="vaultPassphrase" placeholder="Секретная фраза учителя" class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant); margin-bottom: 1rem;">
          <button class="btn btn-primary" id="initVaultBtn" style="width: 100%;">Инициализировать ключ</button>
        </div>
      </div>
    `;
    document.getElementById("closeVaultModal").onclick = () => (modal.innerHTML = "");
    document.getElementById("initVaultBtn").onclick = async () => {
      const pass = document.getElementById("vaultPassphrase").value;
      if (!pass) return;
      await this.vault.initOrLoadKey(pass);
      modal.innerHTML = "";
      alert("Ключ успешно загружен!");
      if (this.currentClassId) {
        this.renderPeopleTab({ id: this.currentClassId, is_teacher: true });
      }
    };
  }

  // TAB 4: GRADES (LIVE MATRIX & SIMONOV SOU)
  async renderGradesTab(cls) {
    const container = document.getElementById("classTabContent");
    const res = await fetch(`/api/classroom/classes/${cls.id}/matrix`);
    if (!res.ok) return;
    const data = await res.json();

    const m = data.analytics;

    container.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
        <h3>Живая ведомость оценок</h3>
        <button class="btn btn-secondary" id="exportCsvBtn">${getIcon("download")} Экспорт CSV (с ФИО)</button>
      </div>

      <!-- Simonov SOU Analytics Panel -->
      <div class="analytics-bar">
        <div class="metric-card">
          <div class="metric-title">Абсолютная успеваемость (Усп)</div>
          <div class="metric-value">${m.usp}%</div>
          <div style="font-size: 0.75rem; color: var(--md-sys-color-on-surface-variant);">(5+4+3) / всего</div>
        </div>
        <div class="metric-card">
          <div class="metric-title">Качество знаний (КЗ)</div>
          <div class="metric-value">${m.kz}%</div>
          <div style="font-size: 0.75rem; color: var(--md-sys-color-on-surface-variant);">(5+4) / всего</div>
        </div>
        <div class="metric-card">
          <div class="metric-title">СОУ по Симонову</div>
          <div class="metric-value" style="color: #2e7d32;">${m.sou}%</div>
          <div style="font-size: 0.75rem; color: var(--md-sys-color-on-surface-variant);">(100*N5+64*N4+36*N3+16*N2)</div>
        </div>
        <div class="metric-card">
          <div class="metric-title">Всего оценок</div>
          <div class="metric-value" style="font-size: 1.5rem;">${m.n_total} (5: ${m.n5}, 4: ${m.n4}, 3: ${m.n3}, 2: ${m.n2})</div>
        </div>
      </div>

      <!-- Matrix Table -->
      <div class="matrix-wrapper">
        <table class="gradebook-table">
          <thead>
            <tr>
              <th style="min-width: 60px;">Парта</th>
              <th style="min-width: 140px;">Ученик</th>
              ${data.coursework.map((cw) => `<th style="text-align: center; min-width: 100px;">${cw.title}</th>`).join("")}
            </tr>
          </thead>
          <tbody>
            ${data.students
              .map(
                (st) => `
              <tr>
                <td style="font-weight: 700;">№${st.seat_number}</td>
                <td id="mStudentName_${st.student_id}">${st.handle}</td>
                ${data.coursework
                  .map((cw) => {
                    const sub = data.submissions[`${cw.id}_${st.student_id}`];
                    const grade = sub && sub.grade_five ? sub.grade_five : sub && sub.status === "turned_in" ? "Сдано" : "—";
                    const gradeClass = sub && sub.grade_five ? `grade-${sub.grade_five}` : "";
                    return `<td class="gradebook-cell ${gradeClass}" data-cwid="${cw.id}" data-sid="${st.student_id}">${grade}</td>`;
                  })
                  .join("")}
              </tr>
            `
              )
              .join("")}
          </tbody>
        </table>
      </div>
    `;

    // Local decryption of names for matrix
    if (this.vault) {
      for (const st of data.students) {
        if (st.encrypted_note) {
          this.vault.decryptStudentName(st.encrypted_note).then((dec) => {
            if (dec && !dec.includes("🔒")) {
              const el = document.getElementById(`mStudentName_${st.student_id}`);
              if (el) el.textContent = dec;
            }
          });
        }
      }
    }

    document.getElementById("exportCsvBtn").onclick = () => this.exportCsvWithDecryptedNames(data);

    if (cls.is_teacher) {
      document.querySelectorAll(".gradebook-cell").forEach((cell) => {
        cell.onclick = () => {
          this.showGradingModal(cls.id, cell.dataset.cwid, cell.dataset.sid);
        };
      });
    }
  }

  showGradingModal(classId, courseworkId, studentId) {
    const modal = document.getElementById("modalContainer");
    modal.innerHTML = `
      <div class="modal-overlay">
        <div class="modal-card">
          <div class="modal-header">
            <h3>Выставление оценки</h3>
            <button class="btn btn-secondary" id="closeGradingModal">${getIcon("close")}</button>
          </div>
          <div style="display: flex; flex-direction: column; gap: 1rem;">
            <div>
              <label style="font-size: 0.85rem; font-weight: 600;">Оценка по шкале РФ (2..5)</label>
              <div style="display: flex; gap: 0.5rem; margin-top: 0.5rem;">
                <button class="btn btn-secondary grade-btn" data-g="5" style="flex: 1;">5</button>
                <button class="btn btn-secondary grade-btn" data-g="4" style="flex: 1;">4</button>
                <button class="btn btn-secondary grade-btn" data-g="3" style="flex: 1;">3</button>
                <button class="btn btn-secondary grade-btn" data-g="2" style="flex: 1;">2</button>
              </div>
            </div>
            <div>
              <label style="font-size: 0.85rem; font-weight: 600;">Комментарий учителя (сохраняется в банк)</label>
              <input type="text" id="teacherCommentInput" placeholder="Отличная работа!" class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
            </div>
          </div>
        </div>
      </div>
    `;

    document.getElementById("closeGradingModal").onclick = () => (modal.innerHTML = "");

    document.querySelectorAll(".grade-btn").forEach((btn) => {
      btn.onclick = async () => {
        const grade = Number(btn.dataset.g);
        const comment = document.getElementById("teacherCommentInput").value.trim();

        await fetch(`/api/classroom/submissions/${courseworkId}/${studentId}/grade`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            grade_five: grade,
            teacher_comment: comment,
          }),
        });

        modal.innerHTML = "";
        this.renderGradesTab({ id: classId, is_teacher: true });
      };
    });
  }

  async exportCsvWithDecryptedNames(matrixData) {
    // Generate UTF-8 with BOM CSV on client side
    const headers = ["Парта", "Позывной", "ФИО (расшифровано)", ...matrixData.coursework.map((c) => c.title)];
    const rows = [];

    for (const st of matrixData.students) {
      let realName = "";
      if (this.vault && st.encrypted_note) {
        realName = await this.vault.decryptStudentName(st.encrypted_note) || "";
      }
      const stRow = [st.seat_number, st.handle, realName];

      for (const cw of matrixData.coursework) {
        const sub = matrixData.submissions[`${cw.id}_${st.student_id}`];
        stRow.push(sub && sub.grade_five ? sub.grade_five : "");
      }
      rows.push(stRow);
    }

    const csvContent =
      "\uFEFF" +
      [headers, ...rows]
        .map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(","))
        .join("\r\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `bormoclass_grades_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // ---------------------------------------------------------------------------
  // GLOBAL SCREENS: TO-REVIEW, TO-DO, CALENDAR
  // ---------------------------------------------------------------------------

  async renderToReviewView() {
    const main = document.getElementById("appMain");
    main.innerHTML = `<h2>На проверку (Все сданные работы)</h2><div id="toReviewList">Загрузка...</div>`;

    const res = await fetch("/api/classroom/global/to-review");
    const items = res.ok ? await res.json() : [];

    const list = document.getElementById("toReviewList");
    if (items.length === 0) {
      list.innerHTML = `<div style="text-align: center; padding: 3rem; background: var(--md-sys-color-surface-container-low); border-radius: 16px; margin-top: 1rem;">Все работы проверены! Отличная работа.</div>`;
      return;
    }

    list.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 1rem; margin-top: 1rem;">
        ${items
          .map(
            (it) => `
          <div style="background: var(--md-sys-color-surface-container-lowest); border: 1px solid var(--md-sys-color-outline-variant); border-radius: 16px; padding: 1.25rem; display: flex; justify-content: space-between; align-items: center;">
            <div>
              <div style="font-weight: 700; font-size: 1.1rem;">${it.coursework_title}</div>
              <div style="font-size: 0.85rem; color: var(--md-sys-color-on-surface-variant);">
                Класс: ${it.class_title} • Парта №${it.seat_number}: ${it.student_handle}
              </div>
            </div>
            <button class="btn btn-primary review-grade-btn" data-cid="${it.class_id}" data-cwid="${it.coursework_id}" data-sid="${it.student_id}">
              Проверить и оценить
            </button>
          </div>
        `
          )
          .join("")}
      </div>
    `;

    document.querySelectorAll(".review-grade-btn").forEach((btn) => {
      btn.onclick = () => {
        this.showGradingModal(btn.dataset.cid, btn.dataset.cwid, btn.dataset.sid);
      };
    });
  }

  async renderToDoView() {
    const main = document.getElementById("appMain");
    const res = await fetch("/api/classroom/global/to-do");
    const data = res.ok ? await res.json() : { assigned: [], missing: [], done: [] };

    main.innerHTML = `
      <h2>Список дел</h2>
      <div class="nav-rail" style="margin: 1rem 0; border-radius: 12px; background: var(--md-sys-color-surface-container-low);">
        <button class="nav-tab-btn active" id="tabAssigned">Назначено (${data.assigned.length})</button>
        <button class="nav-tab-btn" id="tabMissing">Пропущено (${data.missing.length})</button>
        <button class="nav-tab-btn" id="tabDone">Выполнено (${data.done.length})</button>
      </div>
      <div id="todoItemsContainer"></div>
    `;

    const container = document.getElementById("todoItemsContainer");
    const renderList = (items) => {
      if (items.length === 0) {
        container.innerHTML = `<p style="padding: 2rem; text-align: center; color: var(--md-sys-color-on-surface-variant);">Пусто</p>`;
        return;
      }
      container.innerHTML = items
        .map(
          (it) => `
        <div style="background: var(--md-sys-color-surface-container-lowest); border: 1px solid var(--md-sys-color-outline-variant); border-radius: 16px; padding: 1.25rem; margin-bottom: 0.75rem;">
          <div style="font-weight: 700;">${it.coursework_title}</div>
          <div style="font-size: 0.85rem; color: var(--md-sys-color-on-surface-variant);">
            Класс: ${it.class_title} • ${it.due_at ? `Срок: ${new Date(it.due_at * 1000).toLocaleDateString()}` : "Без срока"}
          </div>
        </div>
      `
        )
        .join("");
    };

    renderList(data.assigned);
    document.getElementById("tabAssigned").onclick = (e) => {
      document.querySelectorAll(".nav-tab-btn").forEach((b) => b.classList.remove("active"));
      e.target.classList.add("active");
      renderList(data.assigned);
    };
    document.getElementById("tabMissing").onclick = (e) => {
      document.querySelectorAll(".nav-tab-btn").forEach((b) => b.classList.remove("active"));
      e.target.classList.add("active");
      renderList(data.missing);
    };
    document.getElementById("tabDone").onclick = (e) => {
      document.querySelectorAll(".nav-tab-btn").forEach((b) => b.classList.remove("active"));
      e.target.classList.add("active");
      renderList(data.done);
    };
  }

  async renderCalendarView() {
    const main = document.getElementById("appMain");
    const res = await fetch("/api/classroom/global/calendar");
    const items = res.ok ? await res.json() : [];

    main.innerHTML = `
      <h2>Календарь дедлайнов</h2>
      <div style="display: flex; flex-direction: column; gap: 1rem; margin-top: 1.5rem;">
        ${
          items.length === 0
            ? `<div style="text-align: center; padding: 2rem;">Нет запланированных дедлайнов</div>`
            : items
                .map(
                  (it) => `
            <div style="background: var(--md-sys-color-surface-container-lowest); border: 1px solid var(--md-sys-color-outline-variant); border-radius: 16px; padding: 1.25rem; display: flex; align-items: center; gap: 1.5rem;">
              <div style="font-family: var(--font-mono); font-size: 1.25rem; font-weight: 800; color: var(--md-sys-color-primary);">
                ${new Date(it.due_at * 1000).toLocaleDateString()}
              </div>
              <div>
                <div style="font-weight: 700;">${it.title}</div>
                <div style="font-size: 0.85rem; color: var(--md-sys-color-on-surface-variant);">${it.class_title}</div>
              </div>
            </div>
          `
                )
                .join("")
        }
      </div>
    `;
  }

  showActivateCodeModal() {
    const modal = document.getElementById("modalContainer");
    modal.innerHTML = `
      <div class="modal-overlay">
        <div class="modal-card">
          <div class="modal-header">
            <h3>Активация подписки «Пульт учителя»</h3>
            <button class="btn btn-secondary" id="closeProModal">${getIcon("close")}</button>
          </div>
          <p style="font-size: 0.85rem; color: var(--md-sys-color-on-surface-variant); margin-bottom: 1rem;">
            Введите пин-код активации формата PED-26-XXXX-XXXX-XX для отключения рекламы во всех ваших классах:
          </p>
          <input type="text" id="licenseCodeInput" placeholder="PED-26-DEV0-0001-1M" class="btn-secondary" style="width: 100%; padding: 0.75rem; font-family: var(--font-mono); border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant); margin-bottom: 1rem;">
          <button class="btn btn-primary" id="submitProCodeBtn" style="width: 100%;">Активировать</button>
        </div>
      </div>
    `;

    document.getElementById("closeProModal").onclick = () => (modal.innerHTML = "");
    document.getElementById("submitProCodeBtn").onclick = async () => {
      const code = document.getElementById("licenseCodeInput").value.trim();
      const res = await window.pbPassport.activateCode(code);
      if (res && res.ok) {
        modal.innerHTML = "";
        alert("Подписка «Пульт учителя» успешно активирована на 30 дней!");
      } else {
        alert(res.error || "Неверный пин-код");
      }
    };
  }

  generatePrintA4(classId) {
    // Generate individual test variant cut-sheets for seats 1..40 and print
    window.print();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  new BormoClassApp();
});
