/**
 * BormoClass Drawer Navigation & Courses Showcase
 * Hamburger drawer navigation, Course cards showcase, DND reordering,
 * Provisioned & Invitation states, and Add Course / Join modal dialogs.
 * Zero external CDN dependencies. Zero-PII compliant.
 */

import { v1Fetch, escapeHtml } from "./api-v1.js";

/**
 * Deterministic color palette for course banners
 */
export const THEME_PALETTE = [
  "#1a73e8", "#188038", "#d93025", "#e37400", "#a142f4",
  "#007b83", "#e52592", "#f29900", "#5f6368", "#0d652d"
];

/**
 * Generates an inline SVG pattern for course banner
 * @param {string} themeColor
 * @param {number} presetIndex
 * @returns {string} SVG string
 */
export function getCourseBannerSvg(themeColor = "#1a73e8", presetIndex = 0) {
  const safeColor = themeColor || "#1a73e8";
  const presets = [
    // 0: Geometric isometric cubes
    `<svg width="100%" height="100%" viewBox="0 0 400 120" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="g0" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="${safeColor}" stop-opacity="1"/>
          <stop offset="100%" stop-color="#111827" stop-opacity="0.9"/>
        </linearGradient>
      </defs>
      <rect width="100%" height="100%" fill="url(#g0)"/>
      <circle cx="360" cy="20" r="80" fill="white" fill-opacity="0.06"/>
      <polygon points="320,10 370,40 370,90 320,60" fill="white" fill-opacity="0.08"/>
      <polygon points="320,10 270,40 270,90 320,60" fill="white" fill-opacity="0.12"/>
      <polygon points="320,60 370,90 320,120 270,90" fill="white" fill-opacity="0.05"/>
    </svg>`,

    // 1: Waves & Curvature
    `<svg width="100%" height="100%" viewBox="0 0 400 120" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="g1" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="${safeColor}" stop-opacity="1"/>
          <stop offset="100%" stop-color="#0f172a" stop-opacity="0.85"/>
        </linearGradient>
      </defs>
      <rect width="100%" height="100%" fill="url(#g1)"/>
      <path d="M0,80 Q100,40 200,70 T400,50 L400,120 L0,120 Z" fill="white" fill-opacity="0.08"/>
      <path d="M0,95 Q150,60 300,90 T400,70 L400,120 L0,120 Z" fill="white" fill-opacity="0.06"/>
    </svg>`,

    // 2: Micro dots & intersecting circuits
    `<svg width="100%" height="100%" viewBox="0 0 400 120" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="g2" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="${safeColor}" stop-opacity="1"/>
          <stop offset="100%" stop-color="#1e1b4b" stop-opacity="0.9"/>
        </linearGradient>
      </defs>
      <rect width="100%" height="100%" fill="url(#g2)"/>
      <line x1="280" y1="0" x2="400" y2="120" stroke="white" stroke-width="2" stroke-opacity="0.1"/>
      <line x1="220" y1="0" x2="340" y2="120" stroke="white" stroke-width="1.5" stroke-opacity="0.08"/>
      <circle cx="340" cy="60" r="14" fill="none" stroke="white" stroke-width="2" stroke-opacity="0.15"/>
      <circle cx="340" cy="60" r="4" fill="white" fill-opacity="0.2"/>
    </svg>`,

    // 3: Diagonal dynamic stripes
    `<svg width="100%" height="100%" viewBox="0 0 400 120" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="g3" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="${safeColor}" stop-opacity="1"/>
          <stop offset="100%" stop-color="#18181b" stop-opacity="0.9"/>
        </linearGradient>
      </defs>
      <rect width="100%" height="100%" fill="url(#g3)"/>
      <polygon points="260,0 300,0 200,120 160,120" fill="white" fill-opacity="0.06"/>
      <polygon points="340,0 380,0 280,120 240,120" fill="white" fill-opacity="0.08"/>
      <polygon points="420,0 460,0 360,120 320,120" fill="white" fill-opacity="0.04"/>
    </svg>`
  ];

  const idx = Math.abs(Number(presetIndex) || 0) % presets.length;
  return presets[idx];
}

/**
 * Creates a deterministic SVG identicon for an anonymous handle
 * @param {string} handle
 * @param {number} size
 * @returns {string} SVG HTML string
 */
export function getUserSvgAvatar(handle = "User", size = 36) {
  let hash = 0;
  for (let i = 0; i < handle.length; i++) {
    hash = (hash << 5) - hash + handle.charCodeAt(i);
    hash |= 0;
  }
  const color = THEME_PALETTE[Math.abs(hash) % THEME_PALETTE.length];
  const initial = (handle || "U").trim().charAt(0).toUpperCase();

  return `
    <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" xmlns="http://www.w3.org/2000/svg" style="border-radius: 50%; vertical-align: middle; flex-shrink: 0;">
      <circle cx="${size / 2}" cy="${size / 2}" r="${size / 2}" fill="${color}" />
      <text x="50%" y="54%" text-anchor="middle" dominant-baseline="middle" fill="#ffffff" font-size="${Math.round(size * 0.48)}" font-family="system-ui, -apple-system, sans-serif" font-weight="700">
        ${initial}
      </text>
    </svg>
  `;
}

/**
 * Global Drawer controller
 */
export class DrawerNav {
  constructor(options = {}) {
    this.isOpen = false;
    this.options = options;
    this.container = null;
    this.backdrop = null;
  }

  init(containerId = "appDrawerContainer") {
    let container = document.getElementById(containerId);
    if (!container) {
      container = document.createElement("div");
      container.id = containerId;
      document.body.appendChild(container);
    }
    this.container = container;
  }

  toggle() {
    if (this.isOpen) {
      this.close();
    } else {
      this.open();
    }
  }

  open() {
    this.isOpen = true;
    const drawerEl = document.getElementById("mainAppDrawer");
    const backdropEl = document.getElementById("drawerBackdrop");
    if (drawerEl) drawerEl.classList.add("drawer-open");
    if (backdropEl) backdropEl.classList.add("backdrop-open");
    document.body.style.overflow = "hidden";
  }

  close() {
    this.isOpen = false;
    const drawerEl = document.getElementById("mainAppDrawer");
    const backdropEl = document.getElementById("drawerBackdrop");
    if (drawerEl) drawerEl.classList.remove("drawer-open");
    if (backdropEl) backdropEl.classList.remove("backdrop-open");
    document.body.style.overflow = "";
  }

  render(state = {}, onNavigate = () => {}) {
    if (!this.container) this.init();

    const {
      user = null,
      teachingCourses = [],
      enrolledCourses = [],
      toReviewCount = 0,
      toDoCount = 0,
      currentHash = window.location.hash || "#classes"
    } = state;

    const isTeacher = user && (user.role === "teacher" || user.role === "admin");
    const isAdmin = user && user.role === "admin";

    this.container.innerHTML = `
      <div id="drawerBackdrop" class="drawer-backdrop"></div>
      <aside id="mainAppDrawer" class="main-drawer" role="navigation" aria-label="Главная навигация">
        <div class="drawer-header">
          <div class="drawer-brand">
            <span class="drawer-logo-icon">🏫</span>
            <span class="drawer-brand-name">BormoClass</span>
          </div>
          <button id="closeDrawerBtn" class="drawer-close-btn" aria-label="Закрыть меню">&times;</button>
        </div>

        <div class="drawer-body">
          <div class="drawer-nav-group">
            <a href="#classes" class="drawer-item ${currentHash === "#classes" ? "active" : ""}" data-route="classes">
              <span class="drawer-item-icon">📚</span>
              <span class="drawer-item-label">Курсы</span>
            </a>
            <a href="#calendar" class="drawer-item ${currentHash === "#calendar" ? "active" : ""}" data-route="calendar">
              <span class="drawer-item-icon">📅</span>
              <span class="drawer-item-label">Календарь</span>
            </a>
          </div>

          <hr class="drawer-divider" />

          ${isTeacher ? `
            <div class="drawer-section">
              <div class="drawer-section-title">Преподаю</div>
              <a href="#to-review" class="drawer-item ${currentHash === "#to-review" ? "active" : ""}" data-route="to-review">
                <span class="drawer-item-icon">📋</span>
                <span class="drawer-item-label">На проверку</span>
                ${toReviewCount > 0 ? `<span class="drawer-badge">${toReviewCount}</span>` : ""}
              </a>
              <div class="drawer-course-list">
                ${teachingCourses.map(c => `
                  <a href="#class/${c.id}" class="drawer-course-item ${currentHash === `#class/${c.id}` ? "active" : ""}" data-route="class/${c.id}">
                    <span class="drawer-course-dot" style="background: ${c.theme_color || '#1a73e8'};"></span>
                    <span class="drawer-course-name" title="${escapeHtml(c.name)}">${escapeHtml(c.name)}</span>
                  </a>
                `).join("")}
                ${teachingCourses.length === 0 ? `<div class="drawer-empty-hint">Нет активных курсов</div>` : ""}
              </div>
            </div>
            <hr class="drawer-divider" />
          ` : ""}

          ${user ? `
            <div class="drawer-section">
              <div class="drawer-section-title">Учусь</div>
              <a href="#to-do" class="drawer-item ${currentHash === "#to-do" ? "active" : ""}" data-route="to-do">
                <span class="drawer-item-icon">✅</span>
                <span class="drawer-item-label">Список дел</span>
                ${toDoCount > 0 ? `<span class="drawer-badge">${toDoCount}</span>` : ""}
              </a>
              <div class="drawer-course-list">
                ${enrolledCourses.map(c => `
                  <a href="#class/${c.id}" class="drawer-course-item ${currentHash === `#class/${c.id}` ? "active" : ""}" data-route="class/${c.id}">
                    <span class="drawer-course-dot" style="background: ${c.theme_color || '#188038'};"></span>
                    <span class="drawer-course-name" title="${escapeHtml(c.name)}">${escapeHtml(c.name)}</span>
                  </a>
                `).join("")}
                ${enrolledCourses.length === 0 ? `<div class="drawer-empty-hint">Вы еще не записаны на курсы</div>` : ""}
              </div>
            </div>
            <hr class="drawer-divider" />
          ` : ""}

          <div class="drawer-nav-group">
            <a href="#archived-classes" class="drawer-item ${currentHash === "#archived-classes" ? "active" : ""}" data-route="archived-classes">
              <span class="drawer-item-icon">📦</span>
              <span class="drawer-item-label">Архив курсов</span>
            </a>

            ${isAdmin ? `
              <a href="#admin" class="drawer-item ${currentHash === "#admin" ? "active" : ""}" data-route="admin">
                <span class="drawer-item-icon">🛡️</span>
                <span class="drawer-item-label">Админ-консоль</span>
              </a>
            ` : ""}

            <a href="#notification-settings" class="drawer-item ${currentHash === "#notification-settings" ? "active" : ""}" data-route="notification-settings">
              <span class="drawer-item-icon">⚙️</span>
              <span class="drawer-item-label">Настройки уведомлений</span>
            </a>
          </div>
        </div>
      </aside>
    `;

    // Bind drawer events
    document.getElementById("closeDrawerBtn")?.addEventListener("click", () => this.close());
    document.getElementById("drawerBackdrop")?.addEventListener("click", () => this.close());

    this.container.querySelectorAll(".drawer-item, .drawer-course-item").forEach(item => {
      item.addEventListener("click", (e) => {
        const route = item.getAttribute("data-route");
        this.close();
        if (typeof onNavigate === "function") {
          onNavigate(route, e);
        }
      });
    });
  }
}

export const drawerNav = new DrawerNav();

/**
 * Renders the Courses Showcase grid
 *
 * @param {HTMLElement} container
 * @param {Array<Object>} courses
 * @param {Object} options
 */
export function renderCoursesShowcase(container, courses = [], options = {}) {
  const {
    user = null,
    invitations = [],
    onAcceptCourse = () => {},
    onDeclineCourse = () => {},
    onAcceptInvitation = () => {},
    onDeclineInvitation = () => {},
    onReorder = () => {},
    onOpenClass = () => {},
    onActionMenu = () => {}
  } = options;

  container.innerHTML = "";

  const showcaseWrapper = document.createElement("div");
  showcaseWrapper.className = "showcase-wrapper";

  // 1. Invitations section (if any)
  if (invitations && invitations.length > 0) {
    const invBlock = document.createElement("div");
    invBlock.className = "invitations-banner-block";
    invBlock.innerHTML = `
      <div class="invitations-heading">
        <span class="inv-badge-icon">📩</span>
        <span>Входящие приглашения (${invitations.length})</span>
      </div>
      <div class="invitations-grid">
        ${invitations.map(inv => `
          <div class="invitation-card" data-inv-id="${inv.id}">
            <div class="inv-card-info">
              <div class="inv-course-name">${escapeHtml(inv.course_name || "Курс #" + inv.course_id)}</div>
              <div class="inv-role-text">Роль: ${inv.role === "TEACHER" ? "Преподаватель" : "Учащийся"}</div>
            </div>
            <div class="inv-card-actions">
              <button class="btn btn-sm btn-primary accept-inv-btn" data-id="${inv.id}">Принять</button>
              <button class="btn btn-sm btn-secondary decline-inv-btn" data-id="${inv.id}">Отклонить</button>
            </div>
          </div>
        `).join("")}
      </div>
    `;

    invBlock.querySelectorAll(".accept-inv-btn").forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        onAcceptInvitation(btn.dataset.id);
      };
    });
    invBlock.querySelectorAll(".decline-inv-btn").forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        onDeclineInvitation(btn.dataset.id);
      };
    });

    showcaseWrapper.appendChild(invBlock);
  }

  // 2. Courses Grid
  const grid = document.createElement("div");
  grid.className = "courses-grid";
  grid.id = "coursesGrid";

  if (courses.length === 0 && invitations.length === 0) {
    grid.innerHTML = `
      <div class="empty-showcase-placeholder">
        <div class="placeholder-icon">📖</div>
        <h3>У вас пока нет курсов</h3>
        <p>Создайте новый курс или присоединитесь к существующему с помощью кнопки [+] вверху.</p>
      </div>
    `;
    showcaseWrapper.appendChild(grid);
    container.appendChild(showcaseWrapper);
    return;
  }

  courses.forEach((c, index) => {
    const isProvisioned = c.course_state === "PROVISIONED" || c.courseState === "PROVISIONED";
    const isArchived = c.course_state === "ARCHIVED" || c.courseState === "ARCHIVED";
    const themeColor = c.theme_color || THEME_PALETTE[index % THEME_PALETTE.length];
    const bannerSvg = getCourseBannerSvg(themeColor, c.banner_preset || index);
    const ownerAvatarSvg = getUserSvgAvatar(c.owner_handle || "Учитель", 40);

    const deadlines = Array.isArray(c.upcoming_deadlines) ? c.upcoming_deadlines.slice(0, 2) : [];

    const card = document.createElement("div");
    card.className = `course-card ${isProvisioned ? "card-provisioned" : ""} ${isArchived ? "card-archived" : ""}`;
    card.draggable = !isProvisioned && !isArchived;
    card.dataset.courseId = c.id;
    card.dataset.index = index;

    card.innerHTML = `
      <div class="course-card-header" style="background-color: ${themeColor};">
        <div class="banner-svg-container">${bannerSvg}</div>
        <div class="course-header-content">
          <div class="course-title-row">
            <h3 class="course-title" title="${escapeHtml(c.name || 'Курс')}">${escapeHtml(c.name || 'Без названия')}</h3>
            <button class="card-menu-btn" data-id="${c.id}" aria-label="Меню курса">⋮</button>
          </div>
          <div class="course-section-row">${escapeHtml(c.section || c.subject || "")} ${c.room ? `· Каб. ${escapeHtml(c.room)}` : ""}</div>
          <div class="course-owner-row">${escapeHtml(c.owner_handle || "Преподаватель")}</div>
        </div>
        <div class="course-owner-avatar">${ownerAvatarSvg}</div>
      </div>

      ${isProvisioned ? `
        <div class="provisioned-bar">
          <div class="provisioned-text">⚡ Администратор подготовил курс</div>
          <div class="provisioned-actions">
            <button class="btn btn-sm btn-primary accept-course-btn" data-id="${c.id}">Принять</button>
            <button class="btn btn-sm btn-secondary decline-course-btn" data-id="${c.id}">Отклонить</button>
          </div>
        </div>
      ` : ""}

      <div class="course-card-body">
        <div class="course-deadlines-section">
          ${deadlines.length > 0 ? `
            <div class="deadlines-title">Срок сдачи:</div>
            ${deadlines.map(d => `
              <div class="deadline-item" title="${escapeHtml(d.title)}">
                <span class="deadline-bullet">⏰</span>
                <span class="deadline-due">${escapeHtml(d.due_label || 'Скоро')}:</span>
                <span class="deadline-name">${escapeHtml(d.title)}</span>
              </div>
            `).join("")}
          ` : `
            <div class="no-deadlines-hint">Дедлайнов на ближайшие дни нет</div>
          `}
        </div>
      </div>

      <div class="course-card-footer">
        <button class="card-footer-action-btn gradebook-btn" data-id="${c.id}" title="Журнал оценок">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
        </button>
        <button class="card-footer-action-btn folder-btn" data-id="${c.id}" title="Папка заданий">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
        </button>
      </div>
    `;

    // Click on card opens class
    card.addEventListener("click", (e) => {
      if (e.target.closest(".card-menu-btn") ||
          e.target.closest(".accept-course-btn") ||
          e.target.closest(".decline-course-btn") ||
          e.target.closest(".gradebook-btn") ||
          e.target.closest(".folder-btn")) {
        return;
      }
      onOpenClass(c.id);
    });

    // Sub-buttons
    card.querySelector(".accept-course-btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      onAcceptCourse(c.id);
    });
    card.querySelector(".decline-course-btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      onDeclineCourse(c.id);
    });
    card.querySelector(".gradebook-btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      window.location.hash = `#class/${c.id}/grades`;
    });
    card.querySelector(".folder-btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      window.location.hash = `#class/${c.id}/classwork`;
    });
    card.querySelector(".card-menu-btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      onActionMenu(c, e);
    });

    // Drag and drop sorting
    card.addEventListener("dragstart", (e) => {
      card.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", String(c.id));
    });

    card.addEventListener("dragend", () => {
      card.classList.remove("dragging");
      grid.querySelectorAll(".course-card").forEach(cEl => cEl.classList.remove("drag-over"));
    });

    card.addEventListener("dragover", (e) => {
      e.preventDefault();
      card.classList.add("drag-over");
    });

    card.addEventListener("dragleave", () => {
      card.classList.remove("drag-over");
    });

    card.addEventListener("drop", (e) => {
      e.preventDefault();
      card.classList.remove("drag-over");
      const draggedCourseId = e.dataTransfer.getData("text/plain");
      if (draggedCourseId && draggedCourseId !== String(c.id)) {
        const fromIdx = courses.findIndex(x => String(x.id) === draggedCourseId);
        const toIdx = courses.findIndex(x => String(x.id) === String(c.id));
        if (fromIdx >= 0 && toIdx >= 0) {
          const reordered = [...courses];
          const [moved] = reordered.splice(fromIdx, 1);
          reordered.splice(toIdx, 0, moved);
          onReorder(reordered);
        }
      }
    });

    grid.appendChild(card);
  });

  showcaseWrapper.appendChild(grid);
  container.appendChild(showcaseWrapper);
}

/**
 * Universal Modal for the [+] action: Join class or Create course
 *
 * @param {Object} options
 */
export function openPlusActionModal(options = {}) {
  const {
    user = null,
    onCourseCreated = () => {},
    onJoined = () => {}
  } = options;

  let modalOverlay = document.getElementById("plusActionModalOverlay");
  if (!modalOverlay) {
    modalOverlay = document.createElement("div");
    modalOverlay.id = "plusActionModalOverlay";
    modalOverlay.className = "modal-overlay";
    document.body.appendChild(modalOverlay);
  }

  const isTeacher = user && (user.role === "teacher" || user.role === "admin");

  modalOverlay.innerHTML = `
    <div class="modal-card plus-modal-card">
      <div class="modal-header">
        <div class="plus-modal-tabs">
          <button class="plus-tab-btn active" id="tabJoinBtn">Присоединиться</button>
          ${isTeacher ? `<button class="plus-tab-btn" id="tabCreateBtn">Создать курс</button>` : ""}
        </div>
        <button class="modal-close-btn" id="closePlusModalBtn">&times;</button>
      </div>

      <div class="modal-body">
        <!-- Join Tab Content -->
        <div id="joinTabContent" class="plus-tab-pane active">
          <form id="joinForm">
            <p class="modal-hint-text">
              Введите код курса, выданный преподавателем, или 5-значный пин-код парты.
            </p>
            <div class="form-group">
              <label for="enrollmentCodeInput">Код курса (или ПИН)</label>
              <input type="text" id="enrollmentCodeInput" class="form-control" placeholder="Например, abc1234 или 42819" required />
            </div>

            <div class="form-group" id="seatNumberGroup">
              <label for="seatNumberInput">Номер парты (для учеников, от 1 до 30)</label>
              <input type="number" id="seatNumberInput" class="form-control" min="1" max="30" placeholder="1-30" />
            </div>

            <div class="modal-actions">
              <button type="button" class="btn btn-secondary" id="cancelJoinBtn">Отмена</button>
              <button type="submit" class="btn btn-primary" id="submitJoinBtn">Присоединиться</button>
            </div>
          </form>
        </div>

        <!-- Create Tab Content -->
        ${isTeacher ? `
          <div id="createTabContent" class="plus-tab-pane" style="display: none;">
            <form id="createCourseForm">
              <div class="form-group">
                <label for="courseNameInput">Название курса <span class="required">*</span></label>
                <input type="text" id="courseNameInput" class="form-control" placeholder="Например, Алгебра и геометрия" required maxlength="100" />
              </div>

              <div class="form-group">
                <label for="courseSectionInput">Раздел / Класс</label>
                <input type="text" id="courseSectionInput" class="form-control" placeholder="Например, 8-А" maxlength="50" />
              </div>

              <div class="form-row">
                <div class="form-group col">
                  <label for="courseSubjectInput">Предмет</label>
                  <input type="text" id="courseSubjectInput" class="form-control" placeholder="Математика" maxlength="50" />
                </div>
                <div class="form-group col">
                  <label for="courseRoomInput">Аудитория</label>
                  <input type="text" id="courseRoomInput" class="form-control" placeholder="Каб. 302" maxlength="20" />
                </div>
              </div>

              <div class="form-group">
                <label for="courseDescInput">Описание / Силлабус</label>
                <textarea id="courseDescInput" class="form-control" rows="3" placeholder="Краткое описание требований и целей курса"></textarea>
              </div>

              <div class="modal-actions">
                <button type="button" class="btn btn-secondary" id="cancelCreateBtn">Отмена</button>
                <button type="submit" class="btn btn-primary" id="submitCreateBtn">Создать</button>
              </div>
            </form>
          </div>
        ` : ""}
      </div>
    </div>
  `;

  const close = () => {
    modalOverlay.style.display = "none";
    modalOverlay.innerHTML = "";
  };

  modalOverlay.style.display = "flex";

  document.getElementById("closePlusModalBtn")?.addEventListener("click", close);
  document.getElementById("cancelJoinBtn")?.addEventListener("click", close);
  document.getElementById("cancelCreateBtn")?.addEventListener("click", close);

  // Tabs switching
  const tabJoinBtn = document.getElementById("tabJoinBtn");
  const tabCreateBtn = document.getElementById("tabCreateBtn");
  const joinPane = document.getElementById("joinTabContent");
  const createPane = document.getElementById("createTabContent");

  tabJoinBtn?.addEventListener("click", () => {
    tabJoinBtn.classList.add("active");
    tabCreateBtn?.classList.remove("active");
    if (joinPane) joinPane.style.display = "block";
    if (createPane) createPane.style.display = "none";
  });

  tabCreateBtn?.addEventListener("click", () => {
    tabCreateBtn.classList.add("active");
    tabJoinBtn?.classList.remove("active");
    if (createPane) createPane.style.display = "block";
    if (joinPane) joinPane.style.display = "none";
  });

  // Join submit
  document.getElementById("joinForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const code = document.getElementById("enrollmentCodeInput")?.value.trim();
    const seat = document.getElementById("seatNumberInput")?.value;
    if (!code) return;

    try {
      // First try /api/classroom/classes/join (pin or code)
      let res;
      if (code.length === 5 && !isNaN(code)) {
        res = await v1Fetch("/api/classroom/classes/join", {
          method: "POST",
          body: { join_pin: code, seat_number: seat ? Number(seat) : 1 }
        });
      } else {
        // v1 courses enrollment
        res = await v1Fetch("/api/classroom/classes/join", {
          method: "POST",
          body: { enrollment_code: code, seat_number: seat ? Number(seat) : 1 }
        });
      }
      close();
      onJoined(res);
    } catch (err) {
      alert(err.message || "Не удалось присоединиться к курсу.");
    }
  });

  // Create course submit
  document.getElementById("createCourseForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("courseNameInput")?.value.trim();
    const section = document.getElementById("courseSectionInput")?.value.trim();
    const subject = document.getElementById("courseSubjectInput")?.value.trim();
    const room = document.getElementById("courseRoomInput")?.value.trim();
    const desc = document.getElementById("courseDescInput")?.value.trim();

    if (!name) return;

    try {
      const payload = {
        name,
        section,
        subject,
        room,
        descriptionHeading: desc
      };
      const newCourse = await v1Fetch("/v1/courses", {
        method: "POST",
        body: payload
      });
      close();
      onCourseCreated(newCourse);
    } catch (err) {
      alert(err.message || "Не удалось создать курс.");
    }
  });
}
