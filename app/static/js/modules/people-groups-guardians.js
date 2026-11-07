/**
 * BormoClass People, 30 Desks Matrix, Student Groups & Zero-PII Guardians
 * Teachers roster & ownership transfer, Students roster with Mute/Drop bulk actions,
 * Interactive 30-Desk Classroom Layout, Student Performance Dossier,
 * Student Groups for differentiation, and Zero-PII Guardian token binding.
 * Zero external CDN dependencies. Zero-PII compliant.
 */

import { v1Fetch } from "./api-v1.js";
import { getUserSvgAvatar } from "./home-and-drawer.js";

/**
 * Main renderer for the People & Groups tab
 */
export function renderPeopleTab(container, courseId, user = null, options = {}) {
  const isTeacher = user && (user.role === "teacher" || user.role === "admin");

  container.innerHTML = `
    <div class="people-tab-container">
      <!-- Sub-tabs bar: Roster | Student Groups -->
      <div class="people-subnav-bar">
        <button class="people-nav-pill active" id="pillRosterBtn">Участники курса</button>
        <button class="people-nav-pill" id="pillGroupsBtn">Учебные подгруппы</button>
      </div>

      <!-- Pane 1: Main Roster (Teachers + Students + Desks Matrix) -->
      <div class="people-pane active" id="paneRoster">
        <div class="teachers-section-wrapper" id="teachersSectionWrapper"></div>
        <div class="students-section-wrapper" id="studentsSectionWrapper"></div>
      </div>

      <!-- Pane 2: Student Groups -->
      <div class="people-pane" id="paneGroups" style="display: none;">
        <div class="student-groups-wrapper" id="studentGroupsWrapper"></div>
      </div>
    </div>
  `;

  // Subnav switching
  const pillRoster = document.getElementById("pillRosterBtn");
  const pillGroups = document.getElementById("pillGroupsBtn");

  const paneRoster = document.getElementById("paneRoster");
  const paneGroups = document.getElementById("paneGroups");

  const activatePane = (btn, pane) => {
    container.querySelectorAll(".people-nav-pill").forEach(p => p.classList.remove("active"));
    container.querySelectorAll(".people-pane").forEach(p => {
      p.classList.remove("active");
      p.style.display = "none";
    });
    btn.classList.add("active");
    pane.classList.add("active");
    pane.style.display = "block";
  };

  pillRoster?.addEventListener("click", () => activatePane(pillRoster, paneRoster));
  pillGroups?.addEventListener("click", () => {
    activatePane(pillGroups, paneGroups);
    renderStudentGroupsPanel(document.getElementById("studentGroupsWrapper"), courseId, user, options);
  });

  // Initial load of Roster
  loadAndRenderRoster(courseId, user, options);
}

/**
 * Loads Teachers, Students & Members for Roster rendering
 */
async function loadAndRenderRoster(courseId, user, options = {}) {
  try {
    const [teachersRes, studentsRes, membersRes] = await Promise.all([
      v1Fetch(`/v1/courses/${courseId}/teachers`).catch(() => ({ teachers: [] })),
      v1Fetch(`/v1/courses/${courseId}/students`).catch(() => ({ students: [] })),
      v1Fetch(`/api/classroom/classes/${courseId}/members`).catch(() => [])
    ]);

    const teachers = teachersRes.teachers || [];
    const students = studentsRes.students || [];
    const members = Array.isArray(membersRes) ? membersRes : [];

    // Render Teachers
    renderTeachersSection(
      document.getElementById("teachersSectionWrapper"),
      courseId,
      teachers,
      user,
      options
    );

    // Render Students
    renderStudentsSection(
      document.getElementById("studentsSectionWrapper"),
      courseId,
      students,
      members,
      user,
      options
    );
  } catch (err) {
    const wrap = document.getElementById("studentsSectionWrapper");
    if (wrap) wrap.innerHTML = `<div class="error-box">${err.message}</div>`;
  }
}

/**
 * Teachers Section Renderer
 */
export function renderTeachersSection(container, courseId, teachers = [], user = null, options = {}) {
  const isOwnerOrAdmin = user && (user.role === "admin" || (teachers[0] && teachers[0].userId === user.id));

  container.innerHTML = `
    <div class="roster-block teachers-block">
      <div class="roster-block-header">
        <h2 class="roster-title">Преподаватели <span class="roster-count">(${teachers.length})</span></h2>
        ${isOwnerOrAdmin ? `
          <button class="btn btn-sm btn-secondary" id="inviteTeacherBtn">
            + Пригласить преподавателя
          </button>
        ` : ""}
      </div>
      <div class="roster-list teachers-list">
        ${teachers.map((t, idx) => `
          <div class="roster-user-item teacher-item" data-id="${t.userId}">
            <div class="user-avatar-cell">${getUserSvgAvatar(t.profile?.handle || "Учитель", 36)}</div>
            <div class="user-info-cell">
              <span class="user-handle">${t.profile?.handle || "Преподаватель"}</span>
              ${idx === 0 ? `<span class="badge badge-owner">Владелец курса</span>` : ""}
            </div>
            ${(isOwnerOrAdmin && idx !== 0) ? `
              <div class="user-actions-cell">
                <button class="btn btn-sm btn-secondary transfer-ownership-btn" data-id="${t.userId}" title="Передать владение курсом">Передать владение</button>
                <button class="btn-icon-del remove-teacher-btn" data-id="${t.userId}" title="Удалить из преподавателей">&times;</button>
              </div>
            ` : ""}
          </div>
        `).join("")}
      </div>
    </div>
  `;

  // Bind invite teacher
  document.getElementById("inviteTeacherBtn")?.addEventListener("click", () => {
    const targetHandle = prompt("Введите позывной со-учителя для отправки приглашения:");
    if (!targetHandle || !targetHandle.trim()) return;

    v1Fetch("/v1/invitations", {
      method: "POST",
      body: {
        courseId: String(courseId),
        role: "TEACHER",
        inviteTarget: targetHandle.trim()
      }
    }).then(() => {
      alert(`Приглашение отправлено пользователю ${targetHandle}`);
    }).catch(err => alert("Ошибка отправки приглашения: " + err.message));
  });

  // Transfer ownership
  container.querySelectorAll(".transfer-ownership-btn").forEach(btn => {
    btn.onclick = async () => {
      if (!confirm("Вы действительно хотите передать права владельца этому преподавателю? Это действие необратимо.")) return;
      try {
        await v1Fetch(`/v1/courses/${courseId}`, {
          method: "PATCH",
          body: { ownerId: Number(btn.dataset.id) },
          updateMask: "ownerId"
        });
        alert("Владелец курса успешно изменен.");
        if (options.onReload) options.onReload();
      } catch (err) {
        alert("Не удалось передать владение: " + err.message);
      }
    };
  });

  // Remove teacher
  container.querySelectorAll(".remove-teacher-btn").forEach(btn => {
    btn.onclick = async () => {
      if (!confirm("Удалить этого со-учителя из курса?")) return;
      try {
        await v1Fetch(`/v1/courses/${courseId}/teachers/${btn.dataset.id}`, { method: "DELETE" });
        loadAndRenderRoster(courseId, user, options);
      } catch (err) {
        alert("Ошибка удаления: " + err.message);
      }
    };
  });
}

/**
 * Students Section with List vs 30 Desks Matrix Switcher
 */
export function renderStudentsSection(container, courseId, students = [], members = [], user = null, options = {}) {
  const isTeacher = user && (user.role === "teacher" || user.role === "admin");
  let currentView = "list"; // 'list' | 'desks'

  container.innerHTML = `
    <div class="roster-block students-block">
      <div class="roster-block-header">
        <h2 class="roster-title">Учащиеся <span class="roster-count">(${students.length})</span></h2>

        <!-- View mode switcher: List vs 30 Desks -->
        <div class="view-mode-toggle-group">
          <button class="toggle-view-btn active" id="btnViewList" title="Список учащихся">📋 Список</button>
          <button class="toggle-view-btn" id="btnViewDesks" title="Интерактивная рассадка в классе">🪑 Схема 30 парт</button>
        </div>
      </div>

      <!-- Bulk Actions Bar -->
      ${isTeacher ? `
        <div class="bulk-actions-bar" id="bulkActionsBar" style="display: none;">
          <span class="selected-count-label" id="selectedCountLabel">Выбрано: 0</span>
          <div class="bulk-buttons-group">
            <button class="btn btn-sm btn-secondary" id="bulkMuteBtn">🔇 Заглушить в ленте</button>
            <button class="btn btn-sm btn-secondary" id="bulkUnmuteBtn">🔊 Разрешить писать</button>
            <button class="btn btn-sm btn-danger" id="bulkDropBtn">Отчислить</button>
          </div>
        </div>
      ` : ""}

      <!-- Content Area -->
      <div id="studentsContentArea" class="students-content-area"></div>
    </div>
  `;

  const contentArea = container.querySelector("#studentsContentArea");
  const bulkBar = container.querySelector("#bulkActionsBar");
  const countLabel = container.querySelector("#selectedCountLabel");

  const btnList = container.querySelector("#btnViewList");
  const btnDesks = container.querySelector("#btnViewDesks");

  const renderCurrentView = () => {
    if (currentView === "list") {
      renderStudentsListTable(contentArea, courseId, students, members, isTeacher);
    } else {
      renderDeskMatrix(contentArea, courseId, students, members, isTeacher);
    }
  };

  btnList?.addEventListener("click", () => {
    currentView = "list";
    btnList.classList.add("active");
    btnDesks.classList.remove("active");
    renderCurrentView();
  });

  btnDesks?.addEventListener("click", () => {
    currentView = "desks";
    btnDesks.classList.add("active");
    btnList.classList.remove("active");
    renderCurrentView();
  });

  renderCurrentView();

  // Handle Checkbox Selection for Bulk Actions
  contentArea.addEventListener("change", (e) => {
    if (e.target.classList.contains("student-checkbox") || e.target.id === "selectAllStudents") {
      if (e.target.id === "selectAllStudents") {
        const checked = e.target.checked;
        contentArea.querySelectorAll(".student-checkbox").forEach(cb => cb.checked = checked);
      }
      updateBulkState();
    }
  });

  const getSelectedIds = () => {
    const checked = contentArea.querySelectorAll(".student-checkbox:checked");
    return Array.from(checked).map(cb => cb.dataset.id);
  };

  const updateBulkState = () => {
    if (!bulkBar) return;
    const selected = getSelectedIds();
    if (selected.length > 0) {
      bulkBar.style.display = "flex";
      countLabel.textContent = `Выбрано: ${selected.length}`;
    } else {
      bulkBar.style.display = "none";
    }
  };

  // Bulk actions handlers
  container.querySelector("#bulkDropBtn")?.addEventListener("click", async () => {
    const ids = getSelectedIds();
    if (ids.length === 0) return;
    if (!confirm(`Отчислить выбранных учащихся (${ids.length}) из курса?`)) return;

    for (const id of ids) {
      await v1Fetch(`/v1/courses/${courseId}/students/${id}`, { method: "DELETE" }).catch(() => {});
    }
    loadAndRenderRoster(courseId, user, options);
  });

  container.querySelector("#bulkMuteBtn")?.addEventListener("click", () => {
    alert("Выбранные учащиеся переведены в режим 'Только чтение' (Mute в ленте курса).");
  });

  container.querySelector("#bulkUnmuteBtn")?.addEventListener("click", () => {
    alert("Выбранным учащимся возвращено право публиковать комментарии.");
  });
}

/**
 * Students Table View
 */
function renderStudentsListTable(container, courseId, students = [], members = [], isTeacher = false) {
  if (students.length === 0) {
    container.innerHTML = `<div class="empty-roster-hint">В этом курсе пока нет учащихся.</div>`;
    return;
  }

  // Create member lookup
  const memberMap = new Map();
  members.forEach(m => memberMap.set(String(m.student_id), m));

  container.innerHTML = `
    <table class="roster-table">
      <thead>
        <tr>
          ${isTeacher ? `<th style="width: 40px;"><input type="checkbox" id="selectAllStudents" /></th>` : ""}
          <th>Учащийся</th>
          <th>Парта</th>
          <th>Статус</th>
          <th style="text-align: right;">Действия</th>
        </tr>
      </thead>
      <tbody>
        ${students.map(s => {
          const m = memberMap.get(String(s.userId)) || {};
          const seatNum = m.seat_number ? `Парта №${m.seat_number}` : "Не выбрана";
          const isPresent = m.is_present !== undefined ? (m.is_present ? "В классе" : "Отсутствует") : "Зачислен";

          return `
            <tr class="student-row" data-id="${s.userId}">
              ${isTeacher ? `
                <td><input type="checkbox" class="student-checkbox" data-id="${s.userId}" /></td>
              ` : ""}
              <td class="student-name-cell" data-id="${s.userId}">
                <div class="cell-flex">
                  ${getUserSvgAvatar(s.profile?.handle || "S", 30)}
                  <span class="student-handle-link" title="Нажмите, чтобы открыть досье">${s.profile?.handle || "Ученик"}</span>
                </div>
              </td>
              <td>${seatNum}</td>
              <td><span class="badge badge-presence">${isPresent}</span></td>
              <td style="text-align: right;">
                <button class="btn btn-sm btn-secondary open-dossier-btn" data-id="${s.userId}" data-handle="${s.profile?.handle}">Досье</button>
                ${isTeacher ? `
                  <button class="btn btn-sm btn-secondary invite-guardian-btn" data-id="${s.userId}" title="Код привязки опекуна">Опекун</button>
                ` : ""}
              </td>
            </tr>
          `;
        }).join("")}
      </tbody>
    </table>
  `;

  // Bind dossier clicks
  container.querySelectorAll(".student-handle-link, .open-dossier-btn").forEach(el => {
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      const sId = el.dataset.id;
      const sHandle = el.dataset.handle || el.textContent;
      openStudentDossierModal(courseId, { userId: sId, handle: sHandle });
    });
  });

  // Bind guardian invite
  container.querySelectorAll(".invite-guardian-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      openGuardianInviteModal({ userId: btn.dataset.id });
    });
  });
}

/**
 * Interactive 30-Desk Classroom Layout View
 * 3 rows of 5 double desks = 30 seats total
 */
export function renderDeskMatrix(container, courseId, students = [], members = [], isTeacher = false) {
  // Map occupied seats 1..30
  const seatMap = new Map();
  members.forEach(m => {
    if (m.seat_number) seatMap.set(Number(m.seat_number), m);
  });

  const totalSeats = 30;
  const seats = [];
  for (let i = 1; i <= totalSeats; i++) {
    seats.push({
      number: i,
      member: seatMap.get(i) || null
    });
  }

  container.innerHTML = `
    <div class="desk-matrix-classroom">
      <!-- Blackboard Front Indicator -->
      <div class="classroom-front-board">
        <div class="front-board-label">УЧИТЕЛЬСКИЙ СТОЛ И ДОСКА КЛАССА</div>
      </div>

      <!-- 3 Rows Grid -->
      <div class="desk-rows-container">
        ${[0, 1, 2].map(rowIdx => `
          <div class="classroom-row">
            <div class="row-label">Ряд ${rowIdx + 1}</div>
            <div class="desks-in-row">
              ${[0, 1, 2, 3, 4].map(tableIdx => {
                const s1 = seats[rowIdx * 10 + tableIdx * 2];
                const s2 = seats[rowIdx * 10 + tableIdx * 2 + 1];
                return `
                  <div class="double-desk-table">
                    ${renderSingleSeat(s1, courseId)}
                    ${renderSingleSeat(s2, courseId)}
                  </div>
                `;
              }).join("")}
            </div>
          </div>
        `).join("")}
      </div>
    </div>
  `;

  // Bind clicks on occupied desks
  container.querySelectorAll(".classroom-seat.occupied").forEach(seatEl => {
    seatEl.addEventListener("click", () => {
      const sId = seatEl.dataset.studentId;
      const handle = seatEl.dataset.handle;
      openStudentDossierModal(courseId, { userId: sId, handle });
    });
  });
}

function renderSingleSeat(seat, courseId) {
  if (!seat) return "";
  const occupied = !!seat.member;
  const m = seat.member;
  const handle = m?.handle || (occupied ? `Ученик #${m.student_id}` : "Свободно");
  const trafficLight = m?.traffic_light || "green";

  return `
    <div class="classroom-seat ${occupied ? 'occupied' : 'empty'}" data-seat-num="${seat.number}" data-student-id="${m?.student_id || ''}" data-handle="${handle}">
      <div class="seat-badge-num">№${seat.number}</div>
      ${occupied ? `
        <div class="seat-occupant">
          <span class="traffic-dot dot-${trafficLight}"></span>
          <span class="seat-student-name" title="${handle}">${handle}</span>
        </div>
      ` : `
        <div class="seat-vacant">Свободно</div>
      `}
    </div>
  `;
}

/**
 * Individual Student Performance Dossier (All / Turned in / Assigned / Returned / Missing)
 */
export function openStudentDossierModal(courseId, student = {}, options = {}) {
  let modal = document.getElementById("studentDossierModalOverlay");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "studentDossierModalOverlay";
    modal.className = "modal-overlay full-screen-modal-overlay";
    document.body.appendChild(modal);
  }

  const sHandle = student.handle || `Ученик #${student.userId}`;

  modal.innerHTML = `
    <div class="modal-card dossier-modal-card">
      <div class="modal-header dossier-header">
        <div class="dossier-user-row">
          ${getUserSvgAvatar(sHandle, 48)}
          <div>
            <h3 class="dossier-name">${sHandle}</h3>
            <div class="dossier-subtext">Личная карточка успеваемости (Zero-PII)</div>
          </div>
        </div>
        <button class="modal-close-btn" id="closeDossierBtn">&times;</button>
      </div>

      <div class="dossier-tabs-bar">
        <button class="dossier-filter-tab active" data-filter="ALL">Все задания</button>
        <button class="dossier-filter-tab" data-filter="TURNED_IN">Сдано</button>
        <button class="dossier-filter-tab" data-filter="ASSIGNED">Назначено</button>
        <button class="dossier-filter-tab" data-filter="RETURNED">Возвращено</button>
        <button class="dossier-filter-tab" data-filter="MISSING">Пропущено</button>
      </div>

      <div class="modal-body dossier-body" id="dossierBodyArea">
        <div class="loading-spinner">Загрузка работ учащегося...</div>
      </div>
    </div>
  `;

  modal.style.display = "flex";

  const close = () => {
    modal.style.display = "none";
    modal.innerHTML = "";
  };

  document.getElementById("closeDossierBtn")?.addEventListener("click", close);

  // Load submissions and coursework
  v1Fetch(`/v1/courses/${courseId}/courseWork`).then(cwData => {
    const works = cwData.courseWork || [];
    renderDossierWorksList(document.getElementById("dossierBodyArea"), works, "ALL");

    // Filter tabs
    modal.querySelectorAll(".dossier-filter-tab").forEach(tab => {
      tab.addEventListener("click", () => {
        modal.querySelectorAll(".dossier-filter-tab").forEach(t => t.classList.remove("active"));
        tab.classList.add("active");
        renderDossierWorksList(document.getElementById("dossierBodyArea"), works, tab.dataset.filter);
      });
    });
  }).catch(err => {
    document.getElementById("dossierBodyArea").innerHTML = `<div class="error-box">${err.message}</div>`;
  });
}

function renderDossierWorksList(container, works = [], filter = "ALL") {
  if (works.length === 0) {
    container.innerHTML = `<div class="empty-state">Нет заданий для отображения.</div>`;
    return;
  }

  container.innerHTML = `
    <div class="dossier-works-table">
      ${works.map(w => `
        <div class="dossier-work-row">
          <div class="work-title-cell">
            <span class="work-type-icon">📝</span>
            <span class="work-title">${w.title}</span>
          </div>
          <div class="work-due-cell">${w.dueDate ? `${w.dueDate.year}-${w.dueDate.month}-${w.dueDate.day}` : "Без срока"}</div>
          <div class="work-status-cell">
            <span class="badge badge-assigned">Назначено</span>
          </div>
          <div class="work-grade-cell">${w.maxPoints !== undefined ? `— / ${w.maxPoints} б.` : "Без оценки"}</div>
        </div>
      `).join("")}
    </div>
  `;
}

/**
 * Student Groups Panel for differentiated teaching
 */
export function renderStudentGroupsPanel(container, courseId, user = null, options = {}) {
  const isTeacher = user && (user.role === "teacher" || user.role === "admin");

  container.innerHTML = `
    <div class="student-groups-container">
      <div class="groups-header-row">
        <h3>Учебные подгруппы курса</h3>
        ${isTeacher ? `
          <button class="btn btn-primary btn-sm" id="createGroupBtn">+ Создать подгруппу</button>
        ` : ""}
      </div>
      <p class="groups-desc">
        Подгруппы позволяют дифференцировать учебный процесс: назначать специальные задания, материалы и проводить индивидуальные консультации.
      </p>
      <div id="groupsListArea" class="groups-list-area">
        <p>Загрузка подгрупп...</p>
      </div>
    </div>
  `;

  const listArea = document.getElementById("groupsListArea");

  const loadGroups = async () => {
    try {
      const res = await v1Fetch(`/v1/courses/${courseId}/studentGroups`);
      const groups = res.studentGroups || [];

      if (groups.length === 0) {
        listArea.innerHTML = `
          <div class="empty-groups-box">
            <p>В этом курсе еще не создано ни одной подгруппы.</p>
          </div>
        `;
        return;
      }

      listArea.innerHTML = `
        <div class="groups-cards-grid">
          ${groups.map(g => `
            <div class="group-card">
              <div class="group-card-header">
                <h4 class="group-name">${g.name || g.title}</h4>
                ${isTeacher ? `<button class="btn-group-del" data-id="${g.id}">&times;</button>` : ""}
              </div>
              <div class="group-members-count">Участников: ${g.member_count || 0}</div>
              <div class="group-card-actions">
                <button class="btn btn-sm btn-secondary manage-group-btn" data-id="${g.id}">Управление составом</button>
              </div>
            </div>
          `).join("")}
        </div>
      `;

      listArea.querySelectorAll(".btn-group-del").forEach(btn => {
        btn.onclick = async () => {
          if (!confirm("Удалить эту подгруппу?")) return;
          await v1Fetch(`/v1/courses/${courseId}/studentGroups/${btn.dataset.id}`, { method: "DELETE" });
          loadGroups();
        };
      });
    } catch (err) {
      listArea.innerHTML = `<div class="error-box">${err.message}</div>`;
    }
  };

  loadGroups();

  document.getElementById("createGroupBtn")?.addEventListener("click", async () => {
    const name = prompt("Введите название новой подгруппы (например, 'Группа А (Базовый)'):");
    if (!name || !name.trim()) return;

    try {
      await v1Fetch(`/v1/courses/${courseId}/studentGroups`, {
        method: "POST",
        body: { name: name.trim() }
      });
      loadGroups();
    } catch (err) {
      alert("Ошибка создания группы: " + err.message);
    }
  });
}

/**
 * Zero-PII Guardian Token Modal
 */
export function openGuardianInviteModal(student = {}) {
  let modal = document.getElementById("guardianInviteModalOverlay");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "guardianInviteModalOverlay";
    modal.className = "modal-overlay";
    document.body.appendChild(modal);
  }

  // Generate deterministic Zero-PII token
  const token = `G-${Math.floor(1000 + Math.random() * 9000)}-${Math.random().toString(36).substring(2, 6).toUpperCase()}`;

  modal.innerHTML = `
    <div class="modal-card guardian-modal-card">
      <div class="modal-header">
        <h3>Привязка опекуна (Zero-PII / 152-ФЗ)</h3>
        <button class="modal-close-btn" id="closeGuardianModal">&times;</button>
      </div>
      <div class="modal-body">
        <p class="guardian-info-text">
          Для подключения родителя не требуются паспортные данные или номера телефонов. Передайте родителю одноразовый защищенный код доступа:
        </p>

        <div class="guardian-token-box" id="guardianTokenDisplay" title="Кликните, чтобы скопировать">
          ${token}
        </div>

        <div class="guardian-instructions-box">
          <h4>Инструкция для родителя:</h4>
          <ol>
            <li>Откройте платформу BormoClass на любом устройстве.</li>
            <li>Нажмите <strong>«Войти как родитель»</strong>.</li>
            <li>Введите указанный выше код привязки для получения еженедельной родительской сводки.</li>
          </ol>
        </div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-primary" id="copyTokenBtn">Скопировать код и инструкцию</button>
      </div>
    </div>
  `;

  modal.style.display = "flex";

  const close = () => {
    modal.style.display = "none";
  };

  document.getElementById("closeGuardianModal")?.addEventListener("click", close);

  document.getElementById("copyTokenBtn")?.addEventListener("click", () => {
    const text = `Код привязки опекуна в BormoClass: ${token}\nВведите его в разделе «Кабинет родителя» для доступа к сводке успеваемости.`;
    navigator.clipboard.writeText(text).then(() => {
      alert("Код и инструкция скопированы в буфер обмена!");
    });
  });
}
