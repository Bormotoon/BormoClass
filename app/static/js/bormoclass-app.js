/**
 * BormoClass Main SPA Engine (~15 KB Vanilla JS)
 * Zero-PII (152-FZ), Material Design 3.0,
 * Simonov SOU Analytics, SSE Live Matrix and Client-side CSV Export.
 */

import { ICONS, getIcon } from "./icons.js";
import { escapeHtml } from "./modules/api-v1.js";

import * as ApiV1 from "./modules/api-v1.js";
import * as HomeDrawer from "./modules/home-and-drawer.js";
import * as StreamComments from "./modules/stream-and-comments.js";
import * as ClassworkQuizzes from "./modules/classwork-and-quizzes.js";
import * as PeopleGroups from "./modules/people-groups-guardians.js";
import * as SpeedGrader from "./modules/speedgrader.js";
import * as GradebookPeriods from "./modules/gradebook-periods.js";
import * as GlobalCalendarAdmin from "./modules/global-calendar-admin.js";

if (typeof window !== "undefined") {
  window.BormoClassModules = {
    ApiV1,
    HomeDrawer,
    StreamComments,
    ClassworkQuizzes,
    PeopleGroups,
    SpeedGrader,
    GradebookPeriods,
    GlobalCalendarAdmin,
  };
}

/**
 * Universal Toast Notification System
 */
export function showToast(message, type = "info") {
  let toastContainer = document.getElementById("toastContainer");
  if (!toastContainer) {
    toastContainer = document.createElement("div");
    toastContainer.id = "toastContainer";
    toastContainer.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 99999;
      display: flex;
      flex-direction: column;
      gap: 10px;
      max-width: 420px;
      pointer-events: none;
    `;
    document.body.appendChild(toastContainer);
  }

  const toast = document.createElement("div");
  const bg = type === "error" ? "#ba1a1a" : type === "success" ? "#198754" : "#1f1f1f";
  toast.style.cssText = `
    background: ${bg};
    color: #ffffff;
    padding: 12px 18px;
    border-radius: 10px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.25);
    font-size: 0.95rem;
    line-height: 1.4;
    pointer-events: auto;
    display: flex;
    align-items: center;
    gap: 10px;
  `;
  const icon = type === "error" ? "⚠️" : type === "success" ? "✅" : "ℹ️";
  toast.innerHTML = `<span style="font-size: 1.2rem;">${icon}</span><span style="flex: 1; word-break: break-word;">${message}</span>`;
  toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 4500);
}

/**
 * Parses API error response and extracts a human-friendly Russian message.
 * Strictly prevents "[object Object]" leaks.
 */
export async function getErrorMessage(res, defaultMsg = "Произошла ошибка") {
  if (!res) return defaultMsg;
  try {
    const data = await res.json();
    if (typeof data === "string" && data.trim()) {
      return data;
    }
    if (typeof data.detail === "string" && data.detail.trim()) {
      return data.detail;
    }
    if (Array.isArray(data.detail)) {
      return data.detail
        .map((item) => {
          if (typeof item === "string") return item;
          if (item && item.msg) {
            const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : "";
            if (field === "join_pin") return "Пин-код класса должен содержать от 4 до 10 символов (например, 42819).";
            if (field === "seat_number") return "Выберите парту от 1 до 40.";
            if (field === "password") return "Пароль должен содержать от 4 символов.";
            return (field ? `Поле «${field}»: ` : "") + item.msg;
          }
          return typeof item === "object" ? (item.msg || JSON.stringify(item)) : String(item);
        })
        .join("\n");
    }
    if (data.message && typeof data.message === "string") {
      return data.message;
    }
    if (data.detail && typeof data.detail === "object") {
      return data.detail.msg || JSON.stringify(data.detail);
    }
  } catch (e) {
    // Non-JSON or network body
  }

  if (res.status === 401) return "Требуется авторизация. Пожалуйста, войдите в систему.";
  if (res.status === 403) return "Доступ запрещен. Недостаточно прав для выполнения этого действия.";
  if (res.status === 404) return "Запрашиваемые данные или класс не найдены.";
  if (res.status === 409) return "Выбранное место или ресурс уже заняты.";
  if (res.status === 422) return "Некорректный формат данных. Проверьте правильность заполнения полей.";
  if (res.status >= 500) return "Внутренняя ошибка сервера. Пожалуйста, попробуйте позже.";

  return defaultMsg;
}

class BormoClassApp {
  constructor() {
    this.user = null;
    this.currentView = "classes"; // 'classes' | 'class-detail' | 'to-review' | 'to-do' | 'calendar'
    this.currentClassId = null;
    this.currentClassTab = "stream"; // 'stream' | 'classwork' | 'people' | 'grades'
    this.classEventSource = null;

    this.init();
  }

  async init() {
    this.setupTheme();
    this.bindGlobalEvents();

    if (window.pbPassport) {
      window.pbPassport.onUserChange((u) => {
        this.user = u;
        this.renderUserBar();
        this.renderNavigation();
        this.route();
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

    const drawerToggleBtn = document.getElementById("drawerToggleBtn");
    if (drawerToggleBtn) {
      drawerToggleBtn.addEventListener("click", () => {
        HomeDrawer.drawerNav.render(
          {
            user: this.user,
            teachingCourses: (this.classes || []).filter((c) => c.is_teacher),
            enrolledCourses: (this.classes || []).filter((c) => !c.is_teacher),
            toReviewCount: 0,
            toDoCount: 0,
            currentHash: window.location.hash || "#classes",
          },
          (hash) => {
            window.location.hash = hash;
            HomeDrawer.drawerNav.close();
          }
        );
        HomeDrawer.drawerNav.toggle();
      });
    }

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
        <a href="/passport/" class="btn btn-primary" id="registerBtn" style="text-decoration: none; display: inline-flex; align-items: center; gap: 0.25rem;">Создать Паспорт</a>
      `;
      document.getElementById("loginBtn").onclick = () => {
        if (window.pbPassport && window.pbPassport.open) {
          window.pbPassport.open("login");
        } else {
          this.showAuthModal("login");
        }
      };
      return;
    }

    const isTeacher = this.user.role === "teacher" || this.user.role === "admin";
    const roleBadge = isTeacher
      ? `<span class="badge" style="background: var(--md-sys-color-primary-container); color: var(--md-sys-color-on-primary-container);">Учитель</span>`
      : `<span class="badge" style="background: var(--md-sys-color-secondary-container); color: var(--md-sys-color-on-secondary-container);">Ученик</span>`;

    const recessBadge = !isTeacher
      ? `<span class="badge badge-recess" id="recessBadge" title="Баланс перемены">🎮 ${Math.floor(this.user.recess_seconds / 60)} мин</span>`
      : "";

    bar.innerHTML = `
      ${roleBadge}
      ${recessBadge}
      <button class="btn btn-secondary" id="notifBellBtn" title="Уведомления" style="position: relative; padding: 0.4rem 0.6rem;">
        🔔
        <span class="badge" id="notifBadge" style="display: none; position: absolute; top: -4px; right: -4px; background: #b3261e; color: #fff; font-size: 0.7rem; padding: 2px 5px; border-radius: 10px;">0</span>
      </button>
      <div id="userPassportChip" style="cursor: pointer; display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.25rem 0.6rem; border-radius: 999px; background: var(--md-sys-color-surface-container); border: 1px solid var(--md-sys-color-outline-variant);" title="Открыть Паспорт и карточку героя">
        <span id="userBarAvatar"></span>
        <span style="font-weight: 700; font-size: 0.9rem;">${escapeHtml(this.user.handle)}</span>
      </div>
      <button class="btn btn-secondary" id="themeBtn" title="Переключить тему">${getIcon("sun")}</button>
      <button class="btn btn-secondary" id="logoutBtn" title="Выйти">${getIcon("logout")}</button>
    `;

    const bellEl = document.getElementById("notifBellBtn");
    const badgeEl = document.getElementById("notifBadge");
    if (bellEl) {
      this.notificationCenter = new GlobalCalendarAdmin.NotificationCenter({
        bellElement: bellEl,
        badgeElement: badgeEl,
      });
      this.notificationCenter.init();
    }

    const avaContainer = document.getElementById("userBarAvatar");
    if (avaContainer && window.pbPassport) {
      avaContainer.innerHTML = window.pbPassport.avatarSvg(this.user.avatar_seed || 1, 24);
      if (window.pbPassport.portraits) {
        window.pbPassport.portraits().then(idx => {
          const hero = window.pbPassport.heroOf(idx, this.user.role, this.user.handle);
          const img = document.createElement("img");
          img.src = hero.src;
          img.width = 24;
          img.height = 24;
          img.style.borderRadius = "50%";
          img.style.objectFit = "cover";
          avaContainer.replaceChildren(img);
        }).catch(() => {});
      }
    }

    document.getElementById("userPassportChip").onclick = () => {
      if (window.pbPassport && window.pbPassport.open) {
        window.pbPassport.open("profile");
      }
    };
    document.getElementById("themeBtn").onclick = () => this.toggleTheme();
    document.getElementById("logoutBtn").onclick = () => this.logout();
  }

  renderNavigation() {
    const nav = document.getElementById("navRail");
    const drawerBtn = document.getElementById("drawerToggleBtn");
    if (!this.user) {
      nav.style.display = "none";
      if (drawerBtn) drawerBtn.style.display = "none";
      return;
    }
    nav.style.display = "flex";
    if (drawerBtn) drawerBtn.style.display = "inline-block";

    const isTeacher = this.user.role === "teacher" || this.user.role === "admin";
    const isAdmin = this.user.role === "admin";
    document.getElementById("navToReviewBtn").style.display = isTeacher ? "inline-flex" : "none";
    document.getElementById("navToDoBtn").style.display = isTeacher ? "none" : "inline-flex";
    const navAdminBtn = document.getElementById("navAdminBtn");
    if (navAdminBtn) navAdminBtn.style.display = (isAdmin || isTeacher) ? "inline-flex" : "none";

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
    } else if (mainView === "admin") {
      this.currentView = "admin";
      this.renderAdminView();
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
          <div id="authModalError" style="display: none; color: #b3261e; background: #f9dedc; padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.9rem; font-weight: 500; line-height: 1.4; border-left: 4px solid #b3261e; margin-bottom: 0.75rem;"></div>
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
              <div style="display: flex; justify-content: flex-end;">
                <button type="button" id="forgotPwBtn" style="background: none; border: none; color: var(--md-sys-color-primary); font-size: 0.85rem; cursor: pointer; text-decoration: underline;">Забыли пароль?</button>
              </div>
              <button type="submit" class="btn btn-primary" style="margin-top: 0.25rem;">Войти</button>
            </form>
          `
              : `
            <div style="margin-bottom: 1rem; text-align: center;">
              <a href="/passport/" class="btn btn-primary" style="width: 100%; text-decoration: none; display: flex; align-items: center; justify-content: center; gap: 0.5rem; font-weight: 700; padding: 0.85rem;">
                🎮 Интерактивный 3D-генератор героя
              </a>
              <span style="display: block; margin: 0.5rem 0; font-size: 0.8rem; color: var(--md-sys-color-on-surface-variant);">— или быстрая форма создания паспорта —</span>
            </div>
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
                <label style="font-size: 0.85rem; font-weight: 600;">Придумайте пароль (от 4 символов)</label>
                <input type="password" id="authPassword" required minlength="4" class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
              </div>
              <button type="submit" class="btn btn-secondary" style="margin-top: 0.5rem;">Быстро создать паспорт</button>
            </form>
          `
          }
        </div>
      </div>
    `;

    document.getElementById("closeAuthModal").onclick = () => (modal.innerHTML = "");

    if (document.getElementById("forgotPwBtn")) {
      document.getElementById("forgotPwBtn").onclick = () => this.showRecoverModal();
    }

    const showError = (msg) => {
      const errBox = document.getElementById("authModalError");
      if (errBox) {
        errBox.textContent = msg;
        errBox.style.display = "block";
      } else {
        showToast(msg, "error");
      }
    };
    const clearError = () => {
      const errBox = document.getElementById("authModalError");
      if (errBox) errBox.style.display = "none";
    };

    const handleInput = document.getElementById("authHandle");
    if (handleInput) handleInput.oninput = clearError;
    const pwInput = document.getElementById("authPassword");
    if (pwInput) pwInput.oninput = clearError;

    document.getElementById("authForm").onsubmit = async (e) => {
      e.preventDefault();
      clearError();
      if (type === "login") {
        const handle = document.getElementById("authHandle").value.trim();
        const password = document.getElementById("authPassword").value;
        try {
          const res = await fetch("/api/passport/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ handle, password }),
          });
          if (res.ok) {
            modal.innerHTML = "";
            showToast("Успешный вход в систему!", "success");
            await window.pbPassport.refreshSession();
          } else {
            const errMsg = await getErrorMessage(res, "Ошибка входа");
            showError(errMsg);
          }
        } catch (err) {
          showError("Ошибка сетевого соединения с сервером.");
        }
      } else {
        const role = document.getElementById("authRole").value;
        const password = document.getElementById("authPassword").value;
        try {
          const res = await fetch("/api/passport/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ role, password }),
          });
          if (res.ok) {
            const data = await res.json();
            this.showRegistrationSuccessModal(data);
          } else {
            const errMsg = await getErrorMessage(res, "Ошибка регистрации");
            showError(errMsg);
          }
        } catch (err) {
          showError("Ошибка сетевого соединения с сервером.");
        }
      }
    };
  }

  showRecoverModal() {
    const modal = document.getElementById("modalContainer");
    modal.innerHTML = `
      <div class="modal-overlay">
        <div class="modal-card">
          <div class="modal-header">
            <h3>Восстановление доступа</h3>
            <button class="btn btn-secondary" id="closeRecoverModal">${getIcon("close")}</button>
          </div>
          <form id="recoverForm" style="display: flex; flex-direction: column; gap: 1rem;">
            <div id="recoverModalError" style="display: none; color: #b3261e; background: #f9dedc; padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.9rem; font-weight: 500; line-height: 1.4; border-left: 4px solid #b3261e;"></div>
            <div>
              <label style="font-size: 0.85rem; font-weight: 600;">Ваш позывной</label>
              <input type="text" id="recHandle" required placeholder="Например: Бодрый-Енот-428" class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
            </div>
            <div>
              <label style="font-size: 0.85rem; font-weight: 600;">4 секретных слова восстановления (через пробел)</label>
              <input type="text" id="recWords" required placeholder="слово1 слово2 слово3 слово4" class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
            </div>
            <div>
              <label style="font-size: 0.85rem; font-weight: 600;">Новый пароль (от 4 символов)</label>
              <input type="password" id="recNewPassword" required minlength="4" class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
            </div>
            <button type="submit" class="btn btn-primary">Сменить пароль</button>
          </form>
        </div>
      </div>
    `;
    document.getElementById("closeRecoverModal").onclick = () => (modal.innerHTML = "");

    const errBox = document.getElementById("recoverModalError");
    document.getElementById("recoverForm").onsubmit = async (e) => {
      e.preventDefault();
      errBox.style.display = "none";
      const handle = document.getElementById("recHandle").value.trim();
      const wordsStr = document.getElementById("recWords").value.trim();
      const new_password = document.getElementById("recNewPassword").value;
      const recovery_words = wordsStr.split(/\s+/).filter(Boolean);

      if (recovery_words.length !== 4) {
        errBox.textContent = "Необходимо ввести ровно 4 слова восстановления через пробел.";
        errBox.style.display = "block";
        return;
      }

      try {
        const res = await fetch("/api/passport/recover", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ handle, recovery_words, new_password }),
        });
        if (res.ok) {
          modal.innerHTML = "";
          showToast("Пароль успешно обновлён! Войдите с новым паролем.", "success");
          this.showAuthModal("login");
        } else {
          const errMsg = await getErrorMessage(res, "Не удалось восстановить доступ");
          errBox.textContent = errMsg;
          errBox.style.display = "block";
        }
      } catch (err) {
        errBox.textContent = "Ошибка сетевого соединения с сервером.";
        errBox.style.display = "block";
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
      <div style="text-align: center; padding: 4rem 1rem; max-width: 760px; margin: 0 auto;">
        <h1 style="font-size: 2.75rem; font-weight: 800; line-height: 1.2; margin-bottom: 1rem;">
          Self-Hosted Open Source аналог <span style="color: var(--md-sys-color-primary);">Google Classroom</span>
        </h1>
        <p style="font-size: 1.2rem; color: var(--md-sys-color-on-surface-variant); margin-bottom: 2rem;">
          Свободная автономная LMS со встроенной интерактивной доской: 100% паритет с Google Classroom v1 API, 0 байт персональных данных на сервере (152-ФЗ РФ), SpeedGrader, SQLite WAL и нулевые внешние CDN.
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
            <div class="class-card-title">${escapeHtml(c.title)}</div>
            <div style="font-size: 0.85rem; opacity: 0.9;">${escapeHtml(c.grade_level)} класс • Предмет: ${escapeHtml(c.subject_code)}</div>
          </div>
          <div class="class-card-body">
            <p style="font-size: 0.9rem; color: var(--md-sys-color-on-surface-variant);">
              ${c.quarter_goal ? `«${escapeHtml(c.quarter_goal)}»` : "Цель на четверть не задана"}
            </p>
            ${
              c.seat_number
                ? `<div style="margin-top: 1rem;"><span class="badge badge-tag">Ваша парта: №${c.seat_number}</span></div>`
                : ""
            }
          </div>
          <div class="class-card-footer">
            <span>Учеников: ${c.students_count}</span>
            <span style="font-family: var(--font-mono); font-weight: 700;">Пин: ${escapeHtml(c.join_pin)}</span>
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
            <div id="createClassModalError" style="display: none; color: #b3261e; background: #f9dedc; padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.9rem; font-weight: 500; line-height: 1.4; border-left: 4px solid #b3261e;"></div>
            <div>
              <label style="font-size: 0.85rem; font-weight: 600;">Название класса (например, 8А — Информатика)</label>
              <input type="text" id="clsTitle" required minlength="2" maxlength="100" class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
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
    const errBox = document.getElementById("createClassModalError");
    document.getElementById("clsTitle").oninput = () => (errBox.style.display = "none");

    document.getElementById("createClassForm").onsubmit = async (e) => {
      e.preventDefault();
      errBox.style.display = "none";
      try {
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
          showToast("Класс успешно создан!", "success");
          window.location.hash = `#class/${data.id}/stream`;
        } else {
          const errMsg = await getErrorMessage(res, "Ошибка создания класса");
          errBox.textContent = errMsg;
          errBox.style.display = "block";
        }
      } catch (err) {
        errBox.textContent = "Ошибка сетевого соединения с сервером.";
        errBox.style.display = "block";
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
            <div id="joinModalError" style="display: none; color: #b3261e; background: #f9dedc; padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.9rem; font-weight: 500; line-height: 1.4; border-left: 4px solid #b3261e;"></div>
            <div>
              <label style="font-size: 0.85rem; font-weight: 600;">5-значный пин-код с интерактивной доски</label>
              <input type="text" id="joinPin" required minlength="4" maxlength="10" placeholder="Например: 42819" autocomplete="off" class="btn-secondary" style="width: 100%; padding: 0.75rem; font-family: var(--font-mono); font-size: 1.25rem; letter-spacing: 0.1em; text-align: center; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
            </div>
            <div>
              <label style="font-size: 0.85rem; font-weight: 600;">Выберите номер вашей парты (1..40):</label>
              ${seatsGridHtml}
              <div id="seatChosenDisplay" style="margin-top: 0.5rem; font-weight: 700; color: var(--md-sys-color-primary);">Парта не выбрана</div>
            </div>
            <button type="submit" class="btn btn-primary" id="submitJoinBtn">Занять парту и войти</button>
          </form>
        </div>
      </div>
    `;

    document.getElementById("closeJoinModal").onclick = () => (modal.innerHTML = "");

    const showError = (msg) => {
      const errBox = document.getElementById("joinModalError");
      if (errBox) {
        errBox.textContent = msg;
        errBox.style.display = "block";
      } else {
        showToast(msg, "error");
      }
    };
    const clearError = () => {
      const errBox = document.getElementById("joinModalError");
      if (errBox) errBox.style.display = "none";
    };

    document.getElementById("joinPin").oninput = clearError;

    document.querySelectorAll(".seat-pick-btn").forEach((btn) => {
      btn.onclick = () => {
        clearError();
        document.querySelectorAll(".seat-pick-btn").forEach((b) => b.classList.remove("btn-primary"));
        btn.classList.add("btn-primary");
        selectedSeat = Number(btn.dataset.seat);
        document.getElementById("seatChosenDisplay").textContent = `Выбрана парта: №${selectedSeat}`;
      };
    });

    document.getElementById("joinClassForm").onsubmit = async (e) => {
      e.preventDefault();
      clearError();
      const joinPin = document.getElementById("joinPin").value.trim();

      if (!joinPin) {
        showError("Пожалуйста, введите пин-код класса с интерактивной доски учителя.");
        return;
      }
      if (joinPin.length < 4) {
        showError("Пин-код должен содержать от 4 до 10 символов (например, 5 цифр: 42819).");
        return;
      }
      if (!selectedSeat) {
        showError("Пожалуйста, выберите номер вашей парты на схеме выше (от 1 до 40).");
        return;
      }

      try {
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
          showToast("Вы успешно подключились к классу!", "success");
          window.location.hash = `#class/${data.class_id}/stream`;
        } else {
          const errMsg = await getErrorMessage(res, "Не удалось войти в класс");
          showError(errMsg);
        }
      } catch (err) {
        showError("Ошибка сетевого соединения с сервером. Попробуйте снова.");
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
      const errMsg = await getErrorMessage(res, "Класс не найден или нет доступа");
      main.innerHTML = `
        <div style="text-align: center; padding: 4rem 1rem; max-width: 500px; margin: 0 auto;">
          <div style="font-size: 3rem; margin-bottom: 1rem;">⚠️</div>
          <h2 style="font-size: 1.5rem; font-weight: 700; margin-bottom: 0.5rem;">Не удалось открыть класс</h2>
          <p style="color: var(--md-sys-color-on-surface-variant); margin-bottom: 1.5rem; line-height: 1.5;">${errMsg}</p>
          <button class="btn btn-primary" onclick="window.location.hash='#classes'">Вернуться к списку классов</button>
        </div>
      `;
      return;
    }
    const cls = await res.json();
    const isTeacher = cls.is_teacher;

    this.subscribeClassSSE(classId);

    main.innerHTML = `
      <div class="class-hero-banner">
        <div>
          <h1 style="font-size: 2rem; font-weight: 800; margin-bottom: 0.25rem;">${escapeHtml(cls.title)}</h1>
          <p style="opacity: 0.9;">${escapeHtml(cls.grade_level)} класс • ${cls.quarter_goal ? `«${escapeHtml(cls.quarter_goal)}»` : ""}</p>
        </div>
        <div style="display: flex; align-items: center; gap: 1rem;">
          <div class="class-hero-pin-box">
            <div style="font-size: 0.75rem; text-transform: uppercase; font-weight: 700; opacity: 0.8;">Пин класса</div>
            <div class="class-hero-pin-val">${escapeHtml(cls.join_pin)}</div>
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
          try {
            const res = await fetch(`/api/classroom/classes/${cls.id}/traffic-light`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ traffic_light: btn.dataset.tl }),
            });
            if (res.ok) {
              showToast("Статус отправлен на интерактивную доску!", "success");
            } else {
              const errMsg = await getErrorMessage(res, "Не удалось обновить статус");
              showToast(errMsg, "error");
            }
          } catch (e) {
            showToast("Ошибка сети при отправке статуса.", "error");
          }
        };
      });
    }

    if (document.getElementById("publishStreamBtn")) {
      document.getElementById("publishStreamBtn").onclick = async () => {
        const text = document.getElementById("streamPostText").value.trim();
        if (!text) {
          showToast("Введите текст сообщения для публикации.", "error");
          return;
        }
        try {
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
            showToast("Объявление успешно опубликовано в ленту!", "success");
            this.loadStreamFeed(cls.id);
          } else {
            const errMsg = await getErrorMessage(res, "Не удалось опубликовать объявление");
            showToast(errMsg, "error");
          }
        } catch (e) {
          showToast("Ошибка сети при публикации объявления.", "error");
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
          <h4 style="font-size: 1.1rem;">${escapeHtml(it.title)}</h4>
          <span class="badge ${it.kind === "announcement" ? "badge-tag" : "badge-recess"}">${escapeHtml(it.kind)}</span>
        </div>
        <p style="font-size: 0.9rem; color: var(--md-sys-color-on-surface-variant); white-space: pre-wrap;">${escapeHtml(it.instructions || "")}</p>
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
          <h4 style="font-size: 1.1rem; margin-bottom: 0.25rem;">${escapeHtml(it.title)}</h4>
          <div style="font-size: 0.85rem; color: var(--md-sys-color-on-surface-variant);">
            ${it.topic_title ? `Тема: ${escapeHtml(it.topic_title)} • ` : ""}
            Макс. балл: ${it.max_points} • Награда: ${Math.floor(it.recess_reward / 60)} мин перемены
          </div>
        </div>
        <div>
          ${
            !isTeacher
              ? `<button class="btn btn-primary turnin-btn" data-cwid="${it.id}">Сдать работу</button>`
              : `<span class="badge badge-tag">Сдано: ${it.turned_in_count || 0}</span>`
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
            <div id="createCwModalError" style="display: none; color: #b3261e; background: #f9dedc; padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.9rem; font-weight: 500; line-height: 1.4; border-left: 4px solid #b3261e;"></div>
            <div>
              <label style="font-size: 0.85rem; font-weight: 600;">Название задания</label>
              <input type="text" id="cwTitle" required minlength="2" maxlength="150" class="btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);">
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
    const errBox = document.getElementById("createCwModalError");
    document.getElementById("cwTitle").oninput = () => (errBox.style.display = "none");

    document.getElementById("createCwForm").onsubmit = async (e) => {
      e.preventDefault();
      errBox.style.display = "none";
      const isHw = cls.grade_level === 1 ? 0 : document.getElementById("cwIsHomework")?.checked ? 1 : 0;
      try {
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
          showToast("Задание успешно создано и опубликовано!", "success");
          this.renderClassworkTab(cls);
        } else {
          const errMsg = await getErrorMessage(res, "Ошибка публикации задания");
          errBox.textContent = errMsg;
          errBox.style.display = "block";
        }
      } catch (err) {
        errBox.textContent = "Ошибка сетевого соединения с сервером.";
        errBox.style.display = "block";
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
            <div id="turnInModalError" style="display: none; color: #b3261e; background: #f9dedc; padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.9rem; font-weight: 500; line-height: 1.4; border-left: 4px solid #b3261e;"></div>
            <div>
              <label style="font-size: 0.85rem; font-weight: 600;">Ваш ответ или решение</label>
              <textarea id="studentAnswer" required placeholder="Введите ваш ответ или решение..." class="btn-secondary" style="width: 100%; min-height: 120px; padding: 0.75rem; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant);"></textarea>
            </div>
            <button type="submit" class="btn btn-primary">Отправить на проверку</button>
          </form>
        </div>
      </div>
    `;

    document.getElementById("closeTurnInModal").onclick = () => (modal.innerHTML = "");
    const errBox = document.getElementById("turnInModalError");
    document.getElementById("studentAnswer").oninput = () => (errBox.style.display = "none");

    document.getElementById("turnInForm").onsubmit = async (e) => {
      e.preventDefault();
      errBox.style.display = "none";
      const ans = document.getElementById("studentAnswer").value.trim();
      try {
        const res = await fetch(`/api/classroom/coursework/${courseworkId}/turn-in`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ payload_json: JSON.stringify({ answer: ans }) }),
        });
        if (res.ok) {
          modal.innerHTML = "";
          showToast("Работа успешно сдана на проверку учителю!", "success");
          await window.pbPassport.refreshSession();
        } else {
          const errMsg = await getErrorMessage(res, "Ошибка сдачи работы");
          errBox.textContent = errMsg;
          errBox.style.display = "block";
        }
      } catch (err) {
        errBox.textContent = "Ошибка сетевого соединения с сервером.";
        errBox.style.display = "block";
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
      </div>

      <div class="desks-container">
        <div class="teacher-table-front">Стол учителя / Доска</div>
        <div class="classroom-rows" id="desksGridArea">
          <!-- 3 Columns (Rows 1, 2, 3) -->
        </div>
      </div>
    `;

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
        ${escapeHtml(member.handle)}
      </div>
    `;

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
              <div style="font-weight: 800; font-size: 1.1rem; color: var(--md-sys-color-primary);">${escapeHtml(member.handle)}</div>
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

    document.getElementById("saveMemberBtn").onclick = async () => {
      const isPresent = document.getElementById("isPresentCheck").checked ? 1 : 0;

      try {
        const res = await fetch(`/api/classroom/classes/${classId}/members/${member.student_id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            is_present: isPresent,
          }),
        });

        if (res.ok) {
          modal.innerHTML = "";
          showToast("Данные ученика успешно сохранены!", "success");
          this.renderPeopleTab({ id: classId, is_teacher: true });
        } else {
          const errMsg = await getErrorMessage(res, "Не удалось обновить данные ученика");
          showToast(errMsg, "error");
        }
      } catch (e) {
        showToast("Ошибка сети при сохранении данных.", "error");
      }
    };

    document.getElementById("resetPwBtn").onclick = async () => {
      if (!confirm(`Сбросить пароль для ученика ${member.handle}?`)) return;
      try {
        const res = await fetch(`/api/classroom/classes/${classId}/members/${member.student_id}/reset-password`, {
          method: "POST",
        });
        if (res.ok) {
          const d = await res.json();
          alert(`Пароль успешно сброшен!\n\nНовый временный пароль: ${d.temp_password}\nСлова восстановления: ${d.recovery_words.join(", ")}`);
        } else {
          const errMsg = await getErrorMessage(res, "Не удалось сбросить пароль ученика");
          showToast(errMsg, "error");
        }
      } catch (e) {
        showToast("Ошибка сети при сбросе пароля.", "error");
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
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 10px;">
        <div style="display: flex; align-items: center; gap: 12px;">
          <h3 style="margin: 0;">Живая ведомость оценок</h3>
          <button class="btn btn-secondary" id="togglePeriodsBtn">📅 Журнал по периодам</button>
        </div>
        <button class="btn btn-secondary" id="exportCsvBtn">${getIcon("download")} Экспорт CSV</button>
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
              <th style="min-width: 140px;">Позывной</th>
              ${data.coursework.map((cw) => `<th style="text-align: center; min-width: 100px;">${escapeHtml(cw.title)}</th>`).join("")}
            </tr>
          </thead>
          <tbody>
            ${data.students
              .map(
                (st) => `
              <tr>
                <td style="font-weight: 700;">№${st.seat_number}</td>
                <td id="mStudentName_${st.student_id}">${escapeHtml(st.handle)}</td>
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

    document.getElementById("exportCsvBtn").onclick = () => this.exportCsv(data);

    const togglePeriodsBtn = document.getElementById("togglePeriodsBtn");
    if (togglePeriodsBtn) {
      togglePeriodsBtn.onclick = () => {
        new GradebookPeriods.GradebookPeriodsView({
          container,
          classId: cls.id,
        }).render();
      };
    }

    if (cls.is_teacher) {
      document.querySelectorAll(".gradebook-cell").forEach((cell) => {
        cell.onclick = () => {
          SpeedGrader.openSpeedGrader({
            classId: cls.id,
            courseworkId: Number(cell.dataset.cwid),
            studentId: Number(cell.dataset.sid),
            onClose: () => this.renderGradesTab(cls),
          });
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
            <div style="margin-top: 0.5rem;">
              <button class="btn btn-secondary" id="openSgFromModalBtn" style="width: 100%;">🔍 Открыть в SpeedGrader</button>
            </div>
          </div>
        </div>
      </div>
    `;

    document.getElementById("closeGradingModal").onclick = () => (modal.innerHTML = "");

    const sgBtn = document.getElementById("openSgFromModalBtn");
    if (sgBtn) {
      sgBtn.onclick = () => {
        modal.innerHTML = "";
        SpeedGrader.openSpeedGrader({
          classId: classId,
          courseworkId: Number(courseworkId),
          studentId: Number(studentId),
          onClose: () => this.renderGradesTab({ id: classId, is_teacher: true }),
        });
      };
    }

    document.querySelectorAll(".grade-btn").forEach((btn) => {
      btn.onclick = async () => {
        const grade = Number(btn.dataset.g);
        const comment = document.getElementById("teacherCommentInput").value.trim();

        try {
          const res = await fetch(`/api/classroom/submissions/${courseworkId}/${studentId}/grade`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              grade_five: grade,
              teacher_comment: comment,
            }),
          });

          if (res.ok) {
            modal.innerHTML = "";
            showToast("Оценка успешно выставлена!", "success");
            this.renderGradesTab({ id: classId, is_teacher: true });
          } else {
            const errMsg = await getErrorMessage(res, "Не удалось выставить оценку");
            showToast(errMsg, "error");
          }
        } catch (e) {
          showToast("Ошибка сети при выставлении оценки.", "error");
        }
      };
    });
  }

  exportCsv(matrixData) {
    // Generate UTF-8 with BOM CSV on client side (Zero-PII)
    const headers = ["Парта", "Позывной", ...matrixData.coursework.map((c) => c.title)];
    const rows = [];

    for (const st of matrixData.students) {
      const stRow = [st.seat_number, st.handle];

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
    await new GlobalCalendarAdmin.ToReviewView({ container: main }).render();
  }

  async renderToDoView() {
    const main = document.getElementById("appMain");
    await new GlobalCalendarAdmin.ToDoView({ container: main }).render();
  }

  async renderCalendarView() {
    const main = document.getElementById("appMain");
    await new GlobalCalendarAdmin.CalendarView({ container: main }).render();
  }

  async renderAdminView() {
    const main = document.getElementById("appMain");
    await new GlobalCalendarAdmin.DomainAdminConsole({ container: main }).render();
  }

  async generatePrintA4(classId) {
    let printArea = document.getElementById("printArea");
    if (!printArea) {
      printArea = document.createElement("div");
      printArea.id = "printArea";
      document.body.appendChild(printArea);
    }

    let cls = { id: classId, title: "Класс", join_pin: "00000" };
    let members = [];
    try {
      const resCls = await fetch(`/api/classroom/classes/${classId}`);
      if (resCls.ok) cls = await resCls.json();
      const resM = await fetch(`/api/classroom/classes/${classId}/members`);
      if (resM.ok) members = await resM.json();
    } catch (e) {
      console.warn("Failed fetching print data", e);
    }

    const memberBySeat = {};
    for (const m of members) {
      if (m.seat_number) memberBySeat[m.seat_number] = m;
    }

    const desksHtml = Array.from({ length: 30 }, (_, idx) => {
      const seatNum = idx + 1;
      const variant = seatNum % 2 === 1 ? 1 : 2;
      const member = memberBySeat[seatNum];
      const handle = member ? escapeHtml(member.handle) : "Свободная парта";

      return `
        <div class="print-desk-card" style="box-sizing: border-box; border: 1.5px dashed #444; border-radius: 6px; padding: 12px; margin-bottom: 12px; font-family: sans-serif; background: #fff;">
          <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #ccc; padding-bottom: 6px; margin-bottom: 8px;">
            <span style="font-size: 1.15rem; font-weight: 800; color: #000;">ПАРТА №${seatNum}</span>
            <span style="font-size: 0.95rem; font-weight: 700; background: #eee; padding: 2px 8px; border-radius: 4px;">Вариант ${variant}</span>
          </div>
          <div style="font-size: 0.9rem; margin-bottom: 4px;"><strong>Курс:</strong> ${escapeHtml(cls.title)} (PIN: <strong>${escapeHtml(cls.join_pin)}</strong>)</div>
          <div style="font-size: 0.9rem; margin-bottom: 8px;"><strong>Позывной:</strong> ${handle}</div>
          <div style="border-top: 1px solid #ddd; padding-top: 6px;">
            <div style="font-size: 0.75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 4px; color: #555;">Бланк экспресс-ответов:</div>
            <table style="width: 100%; border-collapse: collapse; text-align: center; font-size: 0.8rem;">
              <tr>
                ${[1, 2, 3, 4, 5].map(q => `<td style="border: 1px solid #999; padding: 4px; width: 20%;">№${q}: ____</td>`).join("")}
              </tr>
              <tr>
                ${[6, 7, 8, 9, 10].map(q => `<td style="border: 1px solid #999; padding: 4px; width: 20%;">№${q}: ____</td>`).join("")}
              </tr>
            </table>
          </div>
        </div>
      `;
    }).join("");

    const teacherKeyRows = Array.from({ length: 30 }, (_, idx) => {
      const seatNum = idx + 1;
      const variant = seatNum % 2 === 1 ? 1 : 2;
      const member = memberBySeat[seatNum];
      const handle = member ? escapeHtml(member.handle) : "—";
      return `
        <tr>
          <td style="border: 1px solid #999; padding: 4px 8px; font-weight: 700; text-align: center;">№${seatNum}</td>
          <td style="border: 1px solid #999; padding: 4px 8px;">${handle}</td>
          <td style="border: 1px solid #999; padding: 4px 8px; text-align: center; font-weight: 600;">Вар. ${variant}</td>
          <td style="border: 1px solid #999; padding: 4px 8px; width: 120px;"></td>
        </tr>
      `;
    }).join("");

    printArea.innerHTML = `
      <!-- Student Desk Cards (Pages 1..N) -->
      <div class="print-page">
        <div style="text-align: center; margin-bottom: 12px; border-bottom: 2px solid #000; padding-bottom: 6px;">
          <h2 style="margin: 0; font-size: 1.3rem;">BormoClass • Раздаточные карточки парт</h2>
          <div style="font-size: 0.85rem;">Курс: ${escapeHtml(cls.title)} • Код класса: ${escapeHtml(cls.join_pin)} • 30 парт</div>
        </div>
        <div class="print-card-grid">
          ${desksHtml}
        </div>
      </div>

      <!-- Teacher Key Sheet (Separate A4 Page) -->
      <div class="print-page" style="page-break-before: always; margin-top: 2rem;">
        <div style="text-align: center; margin-bottom: 16px; border-bottom: 2px solid #000; padding-bottom: 8px;">
          <h2 style="margin: 0; font-size: 1.3rem;">BormoClass • Лист-ключ преподавателя</h2>
          <div style="font-size: 0.85rem;">Курс: ${escapeHtml(cls.title)} • PIN: ${escapeHtml(cls.join_pin)} • Контрольная ведомость вариантов</div>
        </div>
        <table style="width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 0.85rem;">
          <thead>
            <tr style="background: #f0f0f0;">
              <th style="border: 1px solid #999; padding: 6px;">Парта</th>
              <th style="border: 1px solid #999; padding: 6px;">Позывной ученика</th>
              <th style="border: 1px solid #999; padding: 6px;">Вариант</th>
              <th style="border: 1px solid #999; padding: 6px;">Балл / Отметка</th>
            </tr>
          </thead>
          <tbody>
            ${teacherKeyRows}
          </tbody>
        </table>
      </div>
    `;

    window.print();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  new BormoClassApp();
});
