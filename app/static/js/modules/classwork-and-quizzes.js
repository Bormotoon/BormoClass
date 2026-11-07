/**
 * BormoClass Classwork, Quizzes, Practice Sets & Standards
 * Assignment constructor (VIEW, EDIT, STUDENT_COPY), Rubric builder,
 * 7 Question Types Quiz Player with tab-focus lock, Practice Sets with scratchpad canvas.
 * Zero external CDN dependencies. Zero-PII compliant.
 */

import { v1Fetch, escapeHtml } from "./api-v1.js";

/**
 * Renders the complete Classwork tab view
 */
export function renderClassworkTab(container, courseId, user, options = {}) {
  const isTeacher = user && (user.role === "teacher" || user.role === "admin");
  const topics = options.topics || [];
  const items = options.items || [];

  container.innerHTML = `
    <div class="classwork-container">
      <!-- Top Action Bar -->
      <div class="classwork-top-bar">
        ${isTeacher ? `
          <div class="create-menu-dropdown-wrapper">
            <button class="btn btn-primary btn-create-classwork" id="createClassworkBtn">
              <span class="btn-icon">+</span> Создать
            </button>
            <div class="create-dropdown-menu" id="createDropdownMenu" style="display: none;">
              <button class="create-menu-item" data-type="ASSIGNMENT">📝 Задание</button>
              <button class="create-menu-item" data-type="QUIZ_ASSIGNMENT">📋 Задание с тестом</button>
              <button class="create-menu-item" data-type="PRACTICE_SET">💡 Интерактивный практикум</button>
              <button class="create-menu-item" data-type="QUESTION">❓ Вопрос</button>
              <button class="create-menu-item" data-type="MATERIAL">📁 Материал</button>
              <hr class="dropdown-divider" />
              <button class="create-menu-item" data-type="REUSE">🔁 Использовать повторно</button>
              <button class="create-menu-item" data-type="TOPIC">🏷️ Тема</button>
            </div>
          </div>
        ` : `<div></div>`}

        <div class="classwork-quick-links">
          <a href="#class/${courseId}/grades" class="btn btn-secondary btn-sm">📊 Журнал оценок</a>
          <a href="/board/${courseId}" target="_blank" class="btn btn-secondary btn-sm">🎨 Доска курса</a>
        </div>
      </div>

      <!-- Main Layout: Topics Sidebar + Items List -->
      <div class="classwork-layout">
        <!-- Sidebar Topics Filter -->
        <aside class="topics-sidebar" id="topicsSidebar">
          <div class="topics-sidebar-title">Темы</div>
          <ul class="topics-filter-list" id="topicsFilterList">
            <li class="topic-filter-item active" data-topic-id="ALL">Все темы</li>
            ${topics.map(t => `
              <li class="topic-filter-item" data-topic-id="${t.id}" title="${t.name}">
                ${t.name}
              </li>
            `).join("")}
          </ul>
        </aside>

        <!-- Items Content Area -->
        <main class="classwork-items-area" id="classworkItemsArea">
          <!-- Rendered dynamically -->
        </main>
      </div>
    </div>
  `;

  // Bind dropdown
  const createBtn = document.getElementById("createClassworkBtn");
  const createMenu = document.getElementById("createDropdownMenu");
  createBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    createMenu.style.display = createMenu.style.display === "block" ? "none" : "block";
  });

  document.addEventListener("click", () => {
    if (createMenu) createMenu.style.display = "none";
  });

  createMenu?.querySelectorAll(".create-menu-item").forEach(item => {
    item.addEventListener("click", () => {
      const type = item.dataset.type;
      if (type === "TOPIC") {
        openCreateTopicModal(courseId, options.onReload);
      } else if (type === "REUSE") {
        if (options.onReuse) options.onReuse();
      } else if (type === "PRACTICE_SET") {
        openPracticeSetCreator(courseId, options.onReload);
      } else {
        renderCourseWorkDialog(courseId, { workType: type }, options);
      }
    });
  });

  // Filter topics
  const itemsArea = document.getElementById("classworkItemsArea");
  renderItemsList(itemsArea, courseId, items, topics, "ALL", user, options);

  document.querySelectorAll(".topic-filter-item").forEach(tEl => {
    tEl.addEventListener("click", () => {
      document.querySelectorAll(".topic-filter-item").forEach(x => x.classList.remove("active"));
      tEl.classList.add("active");
      const filterId = tEl.dataset.topicId;
      renderItemsList(itemsArea, courseId, items, topics, filterId, user, options);
    });
  });
}

/**
 * Topic Creator Modal
 */
export function openCreateTopicModal(courseId, onSuccess) {
  const name = prompt("Введите название новой темы:");
  if (!name || !name.trim()) return;

  v1Fetch(`/v1/courses/${courseId}/topics`, {
    method: "POST",
    body: { name: name.trim() }
  }).then(() => {
    if (onSuccess) onSuccess();
  }).catch(err => alert("Ошибка создания темы: " + err.message));
}

/**
 * Items List grouping by Topic with Drag & Drop
 */
function renderItemsList(container, courseId, items, topics, filterTopicId, user, options = {}) {
  const isTeacher = user && (user.role === "teacher" || user.role === "admin");
  container.innerHTML = "";

  // Group items by topic
  let filteredTopics = topics;
  if (filterTopicId !== "ALL") {
    filteredTopics = topics.filter(t => String(t.id) === String(filterTopicId));
  }

  const itemsWithoutTopic = items.filter(it => !it.topicId && !it.topic_id);

  if (items.length === 0) {
    container.innerHTML = `
      <div class="empty-classwork-placeholder">
        <div class="placeholder-icon">📋</div>
        <p>Здесь пока нет заданий и материалов.</p>
        ${isTeacher ? `<p>Нажмите <strong>«+ Создать»</strong>, чтобы опубликовать первое задание.</p>` : ""}
      </div>
    `;
    return;
  }

  // 1. Items without topic (if filter is ALL)
  if (filterTopicId === "ALL" && itemsWithoutTopic.length > 0) {
    const groupEl = createTopicSection(courseId, null, itemsWithoutTopic, user, options);
    container.appendChild(groupEl);
  }

  // 2. Sections per topic
  filteredTopics.forEach(topic => {
    const topicItems = items.filter(it => String(it.topicId || it.topic_id) === String(topic.id));
    const sectionEl = createTopicSection(courseId, topic, topicItems, user, options);
    container.appendChild(sectionEl);
  });
}

function createTopicSection(courseId, topic, items, user, options = {}) {
  const isTeacher = user && (user.role === "teacher" || user.role === "admin");
  const section = document.createElement("div");
  section.className = "topic-section";
  if (topic) section.dataset.topicId = topic.id;

  const topicTitle = topic ? topic.name : "Без темы";
  section.innerHTML = `
    <div class="topic-section-header">
      <h2 class="topic-title">${topicTitle}</h2>
      ${(topic && isTeacher) ? `
        <button class="topic-menu-btn" data-topic-id="${topic.id}">⋮</button>
      ` : ""}
    </div>
    <div class="topic-items-list" id="topicList_${topic ? topic.id : 'none'}"></div>
  `;

  const listEl = section.querySelector(".topic-items-list");

  items.forEach(item => {
    const itemCard = document.createElement("div");
    itemCard.className = "classwork-item-card";
    itemCard.draggable = isTeacher;
    itemCard.dataset.itemId = item.id;

    const icon = item.workType === "MATERIAL" ? "📁"
               : item.workType === "QUESTION" ? "❓"
               : item.workType === "QUIZ_ASSIGNMENT" ? "📋"
               : "📝";

    const dueText = item.dueDate ? `Срок сдачи: ${formatDueDate(item.dueDate, item.dueTime)}` : "Без срока";

    itemCard.innerHTML = `
      <div class="cw-card-row">
        <span class="cw-icon">${icon}</span>
        <div class="cw-info">
          <div class="cw-title">${item.title || "Без названия"}</div>
          <div class="cw-due">${dueText}</div>
        </div>
        <div class="cw-actions">
          ${item.maxPoints !== undefined ? `<span class="cw-points-badge">${item.maxPoints} б.</span>` : ""}
          ${isTeacher ? `<button class="cw-menu-btn" data-id="${item.id}">⋮</button>` : ""}
        </div>
      </div>
      <div class="cw-card-details" style="display: none;">
        <div class="cw-instructions">${item.description || "Инструкций нет."}</div>
        ${item.materials && item.materials.length > 0 ? `
          <div class="cw-materials-chips">
            ${item.materials.map(m => {
              const file = m.localFile || m.driveFile || m.link || {};
              const title = file.localFile?.title || file.driveFile?.title || file.title || "Вложение";
              const mode = file.shareMode || "VIEW";
              const modeLabel = mode === "STUDENT_COPY" ? "Копия для каждого" : mode === "EDIT" ? "Редактирование" : "Просмотр";
              return `<span class="mat-chip" title="Режим: ${modeLabel}">📎 ${title} <small>(${modeLabel})</small></span>`;
            }).join("")}
          </div>
        ` : ""}
        <div class="cw-footer-actions">
          ${item.workType === "QUIZ_ASSIGNMENT" ? `
            <button class="btn btn-sm btn-primary play-quiz-btn" data-id="${item.id}">Пройти тест</button>
          ` : ""}
          ${item.workType === "PRACTICE_SET" ? `
            <button class="btn btn-sm btn-primary play-set-btn" data-id="${item.id}">Открыть практикум</button>
          ` : ""}
          <a href="#class/${courseId}/submission/${item.id}" class="btn btn-sm btn-secondary">Подробнее</a>
        </div>
      </div>
    `;

    // Click expands item
    itemCard.querySelector(".cw-card-row").addEventListener("click", () => {
      const details = itemCard.querySelector(".cw-card-details");
      details.style.display = details.style.display === "none" ? "block" : "none";
    });

    itemCard.querySelector(".play-quiz-btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      openQuizPlayerModal(item.id);
    });

    itemCard.querySelector(".play-set-btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      openPracticeSetModal(item.id);
    });

    // DND
    if (isTeacher) {
      itemCard.addEventListener("dragstart", (e) => {
        e.dataTransfer.setData("text/plain", String(item.id));
      });
    }

    listEl.appendChild(itemCard);
  });

  return section;
}

function formatDueDate(dueDate, dueTime) {
  if (!dueDate) return "";
  const d = `${dueDate.year}-${String(dueDate.month).padStart(2, "0")}-${String(dueDate.day).padStart(2, "0")}`;
  if (dueTime) {
    const t = `${String(dueTime.hours || 0).padStart(2, "0")}:${String(dueTime.minutes || 0).padStart(2, "0")}`;
    return `${d} ${t}`;
  }
  return d;
}

/**
 * Universal Dialog for CourseWork / Quiz Creation & Editing
 */
export function renderCourseWorkDialog(courseId, initialData = {}, options = {}) {
  let modal = document.getElementById("courseWorkDialogOverlay");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "courseWorkDialogOverlay";
    modal.className = "modal-overlay full-screen-modal-overlay";
    document.body.appendChild(modal);
  }

  const workType = initialData.workType || "ASSIGNMENT";
  const topics = options.topics || [];
  const gradeCategories = options.gradeCategories || [];
  const gradingPeriods = options.gradingPeriods || [];
  const standardsList = options.standards || [];

  modal.innerHTML = `
    <div class="modal-card dialog-fullscreen-card">
      <div class="modal-header">
        <div class="dialog-title-wrapper">
          <span class="dialog-icon">📝</span>
          <h3>${initialData.id ? "Редактировать задание" : "Новое задание"}</h3>
        </div>
        <div class="dialog-top-actions">
          <button type="button" class="btn btn-secondary" id="closeCwDialogBtn">Закрыть</button>
          <button type="button" class="btn btn-primary" id="saveCwBtn">Создать задание</button>
        </div>
      </div>

      <div class="modal-body dialog-two-columns">
        <!-- Left Column: Content & Materials -->
        <div class="dialog-left-col">
          <div class="form-group">
            <input type="text" id="cwTitleInput" class="form-control form-control-lg" placeholder="Название задания" required value="${initialData.title || ''}" />
          </div>

          <div class="form-group">
            <label class="form-label">Инструкции (необязательно)</label>
            <textarea id="cwInstructionsInput" class="form-control" rows="6" placeholder="Опишите требования, шаги выполнения и критерии сдачи...">${initialData.description || ''}</textarea>
          </div>

          <!-- Attachments List with Modes (VIEW / EDIT / STUDENT_COPY) -->
          <div class="dialog-attachments-section">
            <div class="attachments-header">
              <span class="sec-title">Вложения и файлы</span>
              <div class="attach-btn-row">
                <label class="btn btn-sm btn-secondary">
                  📎 Загрузить файл
                  <input type="file" id="cwFileInput" style="display: none;" multiple />
                </label>
                <button type="button" class="btn btn-sm btn-secondary" id="cwAddLinkBtn">🔗 Ссылка</button>
                <button type="button" class="btn btn-sm btn-secondary" id="cwAddBoardBtn">🎨 Доска</button>
              </div>
            </div>

            <div id="cwAttachmentsContainer" class="cw-attachments-container"></div>
          </div>

          ${workType === "QUIZ_ASSIGNMENT" ? `
            <div class="quiz-embed-config-box">
              <div class="quiz-embed-title">📋 Встроенный тест (Quiz Assignment)</div>
              <p class="quiz-embed-desc">К заданию прикреплен интерактивный тест с автоматической проверкой.</p>
              <button type="button" class="btn btn-secondary" id="configureQuizQuestionsBtn">Настроить вопросы теста</button>
            </div>
          ` : ""}
        </div>

        <!-- Right Column: Settings & Criteria -->
        <div class="dialog-right-col">
          <div class="sidebar-setting-card">
            <div class="form-group">
              <label class="form-label">Баллы</label>
              <div class="points-input-row">
                <input type="number" id="cwPointsInput" class="form-control" min="0" max="1000" value="${initialData.maxPoints !== undefined ? initialData.maxPoints : 100}" />
                <label class="checkbox-inline">
                  <input type="checkbox" id="cwNoPointsCheck" ${initialData.maxPoints === 0 ? "checked" : ""} />
                  <span>Без оценки</span>
                </label>
              </div>
            </div>

            <div class="form-group">
              <label class="form-label">Срок сдачи</label>
              <input type="date" id="cwDueDateInput" class="form-control" />
              <input type="time" id="cwDueTimeInput" class="form-control" style="margin-top: 6px;" />
              <label class="checkbox-block" style="margin-top: 8px;">
                <input type="checkbox" id="cwCloseAfterDueCheck" />
                <span>Запретить сдачу после срока (close_after_due)</span>
              </label>
            </div>

            <div class="form-group">
              <label class="form-label">Тема</label>
              <select id="cwTopicSelect" class="form-control">
                <option value="">Без темы</option>
                ${topics.map(t => `<option value="${t.id}">${t.name}</option>`).join("")}
              </select>
            </div>

            <div class="form-group">
              <label class="form-label">Категория оценки</label>
              <select id="cwGradeCategorySelect" class="form-control">
                <option value="">Без категории</option>
                ${gradeCategories.map(c => `<option value="${c.id}">${c.name || c.title} (${c.weight || 100}%)</option>`).join("")}
              </select>
            </div>

            <div class="form-group">
              <label class="form-label">Учебный период</label>
              <select id="cwGradingPeriodSelect" class="form-control">
                <option value="">Текущий период</option>
                ${gradingPeriods.map(p => `<option value="${p.id}">${p.title || p.name}</option>`).join("")}
              </select>
            </div>

            <!-- Rubrics section -->
            <div class="form-group">
              <label class="form-label">Критерии оценки (Рубрика)</label>
              <button type="button" class="btn btn-sm btn-secondary w-100" id="cwOpenRubricBuilderBtn">+ Рубрика</button>
              <div id="cwRubricBadge" style="display: none; font-size: 0.85rem; color: #198754; margin-top: 6px;">✓ Рубрика прикреплена</div>
            </div>

            <!-- Originality check toggle -->
            <div class="form-group">
              <label class="checkbox-block">
                <input type="checkbox" id="cwOriginalityCheck" />
                <span>Проверка на уникальность (Антиплагиат)</span>
              </label>
            </div>

            <!-- Learning standards picker -->
            <div class="form-group">
              <label class="form-label">Образовательные стандарты (ФГОС / CASE)</label>
              <select id="cwStandardsSelect" class="form-control" multiple size="3">
                ${standardsList.map(s => `<option value="${s.id}">[${s.code || s.standard_code}] ${s.description || s.title}</option>`).join("")}
              </select>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;

  modal.style.display = "flex";

  const closeDialog = () => {
    modal.style.display = "none";
    modal.innerHTML = "";
  };

  document.getElementById("closeCwDialogBtn")?.addEventListener("click", closeDialog);

  // Attachments state
  const attachments = [...(initialData.materials || [])];
  const attachContainer = document.getElementById("cwAttachmentsContainer");

  const renderAttachmentsList = () => {
    attachContainer.innerHTML = attachments.map((att, idx) => `
      <div class="dialog-att-item">
        <span class="att-title">📎 ${att.title || "Вложение"}</span>
        <div class="att-mode-selector">
          <select class="form-select-sm att-mode-select" data-index="${idx}">
            <option value="VIEW" ${att.shareMode === "VIEW" ? "selected" : ""}>Учащиеся могут просматривать</option>
            <option value="EDIT" ${att.shareMode === "EDIT" ? "selected" : ""}>Учащиеся могут редактировать общий файл</option>
            <option value="STUDENT_COPY" ${att.shareMode === "STUDENT_COPY" ? "selected" : ""}>Копия для каждого учащегося</option>
          </select>
        </div>
        <button type="button" class="btn-att-remove" data-index="${idx}">&times;</button>
      </div>
    `).join("");

    attachContainer.querySelectorAll(".att-mode-select").forEach(sel => {
      sel.onchange = (e) => {
        attachments[Number(e.target.dataset.index)].shareMode = e.target.value;
      };
    });

    attachContainer.querySelectorAll(".btn-att-remove").forEach(btn => {
      btn.onclick = (e) => {
        attachments.splice(Number(e.target.dataset.index), 1);
        renderAttachmentsList();
      };
    });
  };

  renderAttachmentsList();

  // File upload
  document.getElementById("cwFileInput")?.addEventListener("change", async (e) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f);
      try {
        const res = await fetch("/api/storage/upload", { method: "POST", body: fd });
        const json = await res.json();
        attachments.push({
          type: "localFile",
          title: json.title || json.file_title || "Вложение",
          url: json.download_url || json.url || `/api/storage/download/${json.file_id || json.id}`,
          shareMode: "STUDENT_COPY" // Default: copy for each student
        });
        renderAttachmentsList();
      } catch (err) {
        alert("Ошибка загрузки файла: " + err.message);
      }
    }
  });

  // Link: разрешены только внутренние относительные пути портала, начинающиеся с /
  document.getElementById("cwAddLinkBtn")?.addEventListener("click", () => {
    const url = prompt("Введите внутренний путь ссылки (начиная с /):");
    if (!url) return;
    if (!url.startsWith("/")) {
      alert("Разрешены только внутренние относительные пути (начинающиеся с '/'). Внешние ссылки запрещены политикой 100% автономности.");
      return;
    }
    const title = prompt("Заголовок ссылки:", url) || url;
    attachments.push({ type: "link", title, url, shareMode: "VIEW" });
    renderAttachmentsList();
  });

  // Board
  document.getElementById("cwAddBoardBtn")?.addEventListener("click", () => {
    attachments.push({
      type: "board",
      title: "Интерактивная доска к заданию",
      url: `/board/${courseId}`,
      shareMode: "STUDENT_COPY"
    });
    renderAttachmentsList();
  });

  // Rubric state
  let currentRubric = null;
  document.getElementById("cwOpenRubricBuilderBtn")?.addEventListener("click", () => {
    openRubricBuilderModal((rubricData) => {
      currentRubric = rubricData;
      document.getElementById("cwRubricBadge").style.display = "block";
    });
  });

  // Save Coursework
  document.getElementById("saveCwBtn")?.addEventListener("click", async () => {
    const title = document.getElementById("cwTitleInput")?.value.trim();
    if (!title) {
      alert("Укажите название задания.");
      return;
    }

    const description = document.getElementById("cwInstructionsInput")?.value.trim();
    const noPoints = document.getElementById("cwNoPointsCheck")?.checked;
    const maxPoints = noPoints ? 0 : Number(document.getElementById("cwPointsInput")?.value || 100);
    const topicId = document.getElementById("cwTopicSelect")?.value || null;
    const closeAfterDue = document.getElementById("cwCloseAfterDueCheck")?.checked ? 1 : 0;
    const dateVal = document.getElementById("cwDueDateInput")?.value;
    const timeVal = document.getElementById("cwDueTimeInput")?.value;

    let dueDate = null;
    let dueTime = null;
    if (dateVal) {
      const parts = dateVal.split("-");
      dueDate = { year: Number(parts[0]), month: Number(parts[1]), day: Number(parts[2]) };
    }
    if (timeVal) {
      const parts = timeVal.split(":");
      dueTime = { hours: Number(parts[0]), minutes: Number(parts[1]) };
    }

    // Format materials payload
    const materials = attachments.map(a => {
      if (a.type === "localFile" || a.type === "driveFile") {
        return {
          localFile: {
            localFile: { title: a.title, alternateLink: a.url },
            shareMode: a.shareMode || "STUDENT_COPY"
          }
        };
      }
      return {
        link: { title: a.title, url: a.url },
        shareMode: a.shareMode || "VIEW"
      };
    });

    const payload = {
      title,
      description,
      workType,
      state: "PUBLISHED",
      maxPoints,
      materials,
      topicId: topicId ? Number(topicId) : undefined,
      dueDate,
      dueTime,
      closeAfterDue: closeAfterDue === 1
    };

    try {
      const cw = await v1Fetch(`/v1/courses/${courseId}/courseWork`, {
        method: "POST",
        body: payload
      });

      // Save Rubric if configured
      if (currentRubric && cw && cw.id) {
        await v1Fetch(`/v1/courses/${courseId}/courseWork/${cw.id}/rubric`, {
          method: "POST",
          body: currentRubric
        });
      }

      closeDialog();
      if (options.onReload) options.onReload();
    } catch (err) {
      alert("Не удалось создать задание: " + err.message);
    }
  });
}

/**
 * Visual Rubric Builder Modal
 */
export function openRubricBuilderModal(onSave) {
  let modal = document.getElementById("rubricBuilderModalOverlay");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "rubricBuilderModalOverlay";
    modal.className = "modal-overlay";
    document.body.appendChild(modal);
  }

  const criteria = [
    {
      title: "Понимание темы",
      description: "Глубина освоения теоретического материала",
      levels: [
        { points: 5, title: "Отлично", description: "Полное и безошибочное понимание" },
        { points: 4, title: "Хорошо", description: "Незначительные неточности" },
        { points: 3, title: "Удовлетворительно", description: "Фрагментарные знания" }
      ]
    }
  ];

  modal.innerHTML = `
    <div class="modal-card rubric-modal-card">
      <div class="modal-header">
        <h3>Конструктор рубрики оценки</h3>
        <button class="modal-close-btn" id="closeRubricModal">&times;</button>
      </div>
      <div class="modal-body">
        <div id="criteriaListContainer"></div>
        <button type="button" class="btn btn-secondary btn-sm" id="addCriterionBtn">+ Добавить критерий</button>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" id="cancelRubricBtn">Отмена</button>
        <button type="button" class="btn btn-primary" id="saveRubricBtn">Сохранить рубрику</button>
      </div>
    </div>
  `;

  modal.style.display = "flex";

  const close = () => {
    modal.style.display = "none";
  };

  document.getElementById("closeRubricModal")?.addEventListener("click", close);
  document.getElementById("cancelRubricBtn")?.addEventListener("click", close);

  const container = document.getElementById("criteriaListContainer");

  const renderCriteria = () => {
    container.innerHTML = criteria.map((crit, cIdx) => `
      <div class="rubric-criterion-box">
        <div class="criterion-header">
          <input type="text" class="form-control crit-title-input" value="${crit.title}" placeholder="Название критерия" data-idx="${cIdx}" />
          <button type="button" class="btn-crit-del" data-idx="${cIdx}">&times;</button>
        </div>
        <div class="criterion-levels-grid">
          ${crit.levels.map((lvl, lIdx) => `
            <div class="rubric-level-card">
              <div class="lvl-points-row">
                <input type="number" class="lvl-points-input" value="${lvl.points}" data-c="${cIdx}" data-l="${lIdx}" />
                <span class="lvl-points-label">баллов</span>
              </div>
              <input type="text" class="lvl-title-input" value="${lvl.title}" placeholder="Уровень" data-c="${cIdx}" data-l="${lIdx}" />
              <textarea class="lvl-desc-input" placeholder="Описание требований..." data-c="${cIdx}" data-l="${lIdx}">${lvl.description}</textarea>
            </div>
          `).join("")}
        </div>
      </div>
    `).join("");
  };

  renderCriteria();

  document.getElementById("addCriterionBtn")?.addEventListener("click", () => {
    criteria.push({
      title: "Новый критерий",
      description: "",
      levels: [
        { points: 5, title: "Отлично", description: "" },
        { points: 3, title: "Удовлетворительно", description: "" }
      ]
    });
    renderCriteria();
  });

  document.getElementById("saveRubricBtn")?.addEventListener("click", () => {
    close();
    if (onSave) onSave({ criteria });
  });
}

/**
 * Quiz Player with Countdown Timer, Tab-Focus Lock & Instant Auto-grading
 */
export function openQuizPlayerModal(quizId) {
  let modal = document.getElementById("quizPlayerModalOverlay");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "quizPlayerModalOverlay";
    modal.className = "modal-overlay full-screen-modal-overlay";
    document.body.appendChild(modal);
  }

  modal.innerHTML = `
    <div class="modal-card quiz-player-card">
      <div class="quiz-player-header">
        <div class="quiz-player-title-box">
          <span class="quiz-icon">📋</span>
          <h3 id="quizPlayerTitle">Загрузка теста...</h3>
        </div>
        <div class="quiz-player-status-box">
          <div class="quiz-timer-badge" id="quizCountdownTimer">--:--</div>
          <div class="tab-focus-badge" id="tabFocusBadge" style="display: none;">⚠️ Потеря фокуса вкладки!</div>
        </div>
      </div>

      <div class="modal-body quiz-player-body" id="quizPlayerBody">
        <p>Инициализация вопросов...</p>
      </div>

      <div class="modal-footer quiz-player-footer">
        <button type="button" class="btn btn-secondary" id="exitQuizBtn">Выйти</button>
        <button type="button" class="btn btn-primary" id="submitQuizBtn">Сдать тест</button>
      </div>
    </div>
  `;

  modal.style.display = "flex";

  // Load Quiz data
  v1Fetch(`/api/classroom/quizzes/${quizId}`).then(quiz => {
    initQuizPlayer(quiz, modal);
  }).catch(err => {
    document.getElementById("quizPlayerBody").innerHTML = `<div class="error-box">${err.message}</div>`;
  });
}

function initQuizPlayer(quiz, modalEl) {
  const titleEl = document.getElementById("quizPlayerTitle");
  const bodyEl = document.getElementById("quizPlayerBody");
  const timerEl = document.getElementById("quizCountdownTimer");
  const focusBadge = document.getElementById("tabFocusBadge");
  const submitBtn = document.getElementById("submitQuizBtn");
  const exitBtn = document.getElementById("exitQuizBtn");

  titleEl.textContent = quiz.quiz_title || "Тест";

  let questions = [];
  try {
    questions = typeof quiz.questions_json === "string" ? JSON.parse(quiz.questions_json) : (quiz.questions_json || []);
  } catch {
    questions = [];
  }

  // Timer
  let timeLeft = quiz.time_limit_sec || 0;
  let timerInterval = null;

  if (timeLeft > 0) {
    const updateTimer = () => {
      const mins = Math.floor(timeLeft / 60);
      const secs = timeLeft % 60;
      timerEl.textContent = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
      if (timeLeft <= 60) {
        timerEl.classList.add("timer-warning");
      }
      if (timeLeft <= 0) {
        clearInterval(timerInterval);
        alert("Время тестирования вышло! Ответы будут автоматически отправлены.");
        submitAnswers();
      }
      timeLeft--;
    };
    updateTimer();
    timerInterval = setInterval(updateTimer, 1000);
  } else {
    timerEl.textContent = "Без ограничения времени";
  }

  // Tab focus detection
  let tabSwitchViolations = 0;
  const onVisibilityChange = () => {
    if (document.hidden && quiz.lock_tab_focus) {
      tabSwitchViolations++;
      focusBadge.style.display = "inline-flex";
      focusBadge.textContent = `⚠️ Зафиксирован уход из вкладки (${tabSwitchViolations})`;
    }
  };
  document.addEventListener("visibilitychange", onVisibilityChange);

  // Render 7 Question Types
  bodyEl.innerHTML = questions.map((q, idx) => `
    <div class="quiz-question-card" data-q-index="${idx}">
      <div class="q-header">
        <span class="q-number">Вопрос ${idx + 1}</span>
        <span class="q-points">${q.points || 1} б.</span>
      </div>
      <div class="q-prompt">${q.prompt || ""}</div>
      <div class="q-answers-area">
        ${renderQuestionAnswerInput(q, idx)}
      </div>
    </div>
  `).join("");

  // Setup interactive drag & drop reordering for ORDERING questions
  bodyEl.querySelectorAll(".ordering-list").forEach(list => {
    let dragged = null;
    list.querySelectorAll(".ordering-item").forEach(item => {
      item.addEventListener("dragstart", () => {
        dragged = item;
        item.style.opacity = "0.5";
      });
      item.addEventListener("dragend", () => {
        item.style.opacity = "1";
        dragged = null;
      });
      item.addEventListener("dragover", (e) => {
        e.preventDefault();
      });
      item.addEventListener("drop", (e) => {
        e.preventDefault();
        if (dragged && dragged !== item) {
          const allItems = Array.from(list.children);
          const draggedIdx = allItems.indexOf(dragged);
          const targetIdx = allItems.indexOf(item);
          if (draggedIdx < targetIdx) {
            item.after(dragged);
          } else {
            item.before(dragged);
          }
        }
      });
    });
  });

  const close = () => {
    clearInterval(timerInterval);
    document.removeEventListener("visibilitychange", onVisibilityChange);
    modalEl.style.display = "none";
    modalEl.innerHTML = "";
  };

  exitBtn?.addEventListener("click", () => {
    if (confirm("Вы действительно хотите покинуть тест? Несохраненные ответы будут потеряны.")) {
      close();
    }
  });

  const submitAnswers = async () => {
    clearInterval(timerInterval);
    const answers = collectQuizAnswers(questions, bodyEl);

    try {
      const res = await v1Fetch(`/api/classroom/quizzes/${quiz.id}/submit`, {
        method: "POST",
        body: {
          answers_json: answers,
          focus_lost_count: tabSwitchViolations
        }
      });

      const score = res.auto_score ?? res.score ?? 0;
      const maxScore = res.max_score ?? 0;
      const percent = maxScore > 0 ? Math.round((score / maxScore) * 100) : 100;

      // Show result screen
      bodyEl.innerHTML = `
        <div class="quiz-result-view">
          <div class="result-badge-icon">🎉</div>
          <h3>Тест завершен!</h3>
          <div class="result-score">Ваш результат: <strong>${score}</strong> из ${maxScore} баллов (${percent}%)</div>
          ${tabSwitchViolations > 0 ? `<div class="violations-alert">Вниманию учителя: зафиксировано выходов из вкладки: ${tabSwitchViolations}</div>` : ""}
        </div>
      `;
      submitBtn.style.display = "none";
      exitBtn.textContent = "Закрыть";
    } catch (err) {
      alert("Ошибка при отправке ответов: " + err.message);
    }
  };

  submitBtn?.addEventListener("click", () => {
    if (confirm("Сдать тест на проверку?")) {
      submitAnswers();
    }
  });
}

function renderQuestionAnswerInput(q, qIdx) {
  const rawType = (q.type || "single_choice").toLowerCase();
  let type = rawType;
  if (type === "short_text") type = "short_answer";
  if (type === "numeric_tolerance") type = "numeric";

  switch (type) {
    case "single_choice":
      return (q.options || []).map((opt, i) => `
        <label class="q-option-label">
          <input type="radio" name="q_${qIdx}" value="${i}" />
          <span>${escapeHtml(opt)}</span>
        </label>
      `).join("");

    case "multiple_choice":
      return (q.options || []).map((opt, i) => `
        <label class="q-option-label">
          <input type="checkbox" name="q_${qIdx}" value="${i}" />
          <span>${escapeHtml(opt)}</span>
        </label>
      `).join("");

    case "short_answer":
      return `<input type="text" class="form-control" name="q_${qIdx}" placeholder="Ваш краткий ответ..." />`;

    case "numeric":
      return `<input type="number" step="any" class="form-control" name="q_${qIdx}" placeholder="Числовой ответ..." />`;

    case "matching": {
      const pairs = Array.isArray(q.pairs)
        ? q.pairs
        : Object.entries(q.pairs || {}).map(([k, v]) => ({ left: k, right: v }));
      return `
        <div class="matching-grid">
          ${pairs.map((pair, i) => `
            <div class="matching-row">
              <span class="match-left">${escapeHtml(pair.left)}</span>
              <span class="match-arrow">→</span>
              <input type="text" class="form-control match-right-input" name="q_${qIdx}_match_${i}" data-left="${escapeHtml(pair.left)}" placeholder="Соответствие" />
            </div>
          `).join("")}
        </div>
      `;
    }

    case "ordering": {
      const items = q.items || q.correct_order || [];
      return `
        <div class="ordering-list" id="orderList_${qIdx}">
          ${items.map((item) => `
            <div class="ordering-item" draggable="true" data-item="${escapeHtml(item)}" style="display:flex;align-items:center;gap:8px;padding:6px;border:1px solid #ccc;margin-bottom:4px;border-radius:4px;cursor:grab;">
              <span class="order-handle">☰</span>
              <span class="order-text">${escapeHtml(item)}</span>
            </div>
          `).join("")}
        </div>
      `;
    }

    default:
      return `<input type="text" class="form-control" name="q_${qIdx}" />`;
  }
}

function collectQuizAnswers(questions, container) {
  const answers = {};
  questions.forEach((q, idx) => {
    const rawType = (q.type || "single_choice").toLowerCase();
    let type = rawType;
    if (type === "short_text") type = "short_answer";
    if (type === "numeric_tolerance") type = "numeric";

    const qKey = String(q.id ?? idx);

    if (type === "single_choice") {
      const checked = container.querySelector(`input[name="q_${idx}"]:checked`);
      answers[qKey] = checked ? (isNaN(checked.value) ? checked.value : Number(checked.value)) : null;
    } else if (type === "multiple_choice") {
      const checked = container.querySelectorAll(`input[name="q_${idx}"]:checked`);
      answers[qKey] = Array.from(checked).map(c => isNaN(c.value) ? c.value : Number(c.value));
    } else if (type === "short_answer") {
      const el = container.querySelector(`[name="q_${idx}"]`);
      answers[qKey] = el ? el.value.trim() : "";
    } else if (type === "numeric") {
      const el = container.querySelector(`[name="q_${idx}"]`);
      answers[qKey] = el && el.value.trim() !== "" ? Number(el.value.trim()) : 0;
    } else if (type === "matching") {
      const matchMap = {};
      const inputs = container.querySelectorAll(`[name^="q_${idx}_match_"]`);
      inputs.forEach(inp => {
        const leftKey = inp.dataset.left || inp.getAttribute("data-left");
        if (leftKey) {
          matchMap[leftKey] = inp.value.trim();
        }
      });
      answers[qKey] = matchMap;
    } else if (type === "ordering") {
      const items = container.querySelectorAll(`#orderList_${idx} .ordering-item`);
      answers[qKey] = Array.from(items).map(el => el.dataset.item);
    } else {
      const el = container.querySelector(`[name="q_${idx}"]`);
      answers[qKey] = el ? el.value.trim() : "";
    }
  });
  return answers;
}

/**
 * Practice Sets Interactive Player with Hints & Scratchpad Canvas
 */
export async function openPracticeSetModal(setId) {
  let modal = document.getElementById("practiceSetModalOverlay");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "practiceSetModalOverlay";
    modal.className = "modal-overlay full-screen-modal-overlay";
    document.body.appendChild(modal);
  }

  modal.innerHTML = `
    <div class="modal-card practice-set-card" style="max-width:850px; width:95%; max-height:90vh; overflow-y:auto; padding:20px; background:#fff; border-radius:12px;">
      <div class="practice-header" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
        <div class="practice-title-box" style="display:flex; align-items:center; gap:8px;">
          <span class="practice-icon" style="font-size:1.4rem;">💡</span>
          <h3 id="psModalTitle" style="margin:0;">Интерактивный практикум</h3>
        </div>
        <button class="modal-close-btn" id="closePracticeSetBtn">&times;</button>
      </div>
      <div id="psModalLoading" style="text-align:center; padding:30px;">Загрузка практикума...</div>
      <div id="psModalContent" style="display:none;" class="practice-body">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
          <div class="task-number-badge" id="psCardBadge" style="font-weight:700; background:#e8f0fe; color:#1967d2; padding:4px 10px; border-radius:12px; font-size:0.85rem;">Задача 1</div>
          <div id="psCardCounter" style="font-size:0.85rem; color:#666;"></div>
        </div>
        <div class="practice-task-card" style="margin-bottom:16px; border:1px solid #e0e0e0; border-radius:8px; padding:16px; background:#fafafa;">
          <div class="task-prompt" id="taskPrompt" style="font-size:1.05rem; margin-bottom:16px; line-height:1.5;"></div>

          <div class="task-answer-row" style="display:flex; gap:8px; margin-bottom:12px;">
            <input type="text" id="practiceAnswerInput" class="form-control" placeholder="Введите ответ..." />
            <button type="button" class="btn btn-primary" id="checkCardBtn">Проверить шаг</button>
          </div>

          <div id="psFeedbackArea" style="margin-bottom:12px; font-weight:600; display:none;"></div>

          <div class="practice-hints-box">
            <button type="button" class="btn btn-sm btn-secondary" id="revealHintBtn">💡 Получить подсказку</button>
            <div id="hintContentArea" class="hint-content-area" style="display: none; margin-top:8px;"></div>
          </div>
        </div>

        <!-- Scratchpad Canvas Area -->
        <div class="scratchpad-box" style="border:1px solid #e0e0e0; border-radius:8px; padding:12px; background:#fff;">
          <div class="scratchpad-toolbar" style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
            <span class="scratchpad-title" style="font-weight:600; font-size:0.85rem;">Черновик решения (холст):</span>
            <button type="button" class="btn btn-sm btn-secondary" id="scratchPenBtn">✏️ Карандаш</button>
            <button type="button" class="btn btn-sm btn-secondary" id="scratchEraserBtn">🧹 Ластик</button>
            <button type="button" class="btn btn-sm btn-secondary" id="scratchClearBtn">Очистить</button>
          </div>
          <canvas id="scratchpadCanvas" width="800" height="260" class="scratchpad-canvas" style="border:1px dashed #ccc; width:100%; max-width:800px; display:block; cursor:crosshair;"></canvas>
        </div>

        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:16px;">
          <button type="button" class="btn btn-secondary" id="psPrevBtn">← Предыдущая</button>
          <button type="button" class="btn btn-secondary" id="psNextBtn">Следующая →</button>
        </div>
      </div>
    </div>
  `;

  modal.style.display = "flex";

  const close = () => {
    modal.style.display = "none";
    modal.innerHTML = "";
  };
  document.getElementById("closePracticeSetBtn")?.addEventListener("click", close);

  let setData = null;
  try {
    setData = await v1Fetch(`/api/classroom/practice-sets/${setId}`);
  } catch (err) {
    document.getElementById("psModalLoading").innerHTML = `<div style="color:red;">Ошибка загрузки: ${escapeHtml(err.message)}</div>`;
    return;
  }

  document.getElementById("psModalLoading").style.display = "none";
  document.getElementById("psModalContent").style.display = "block";
  document.getElementById("psModalTitle").textContent = setData.set_title || "Интерактивный практикум";

  let cards = setData.cards || [];
  if (typeof setData.cards_json === "string" && cards.length === 0) {
    try { cards = JSON.parse(setData.cards_json); } catch {}
  }
  if (!Array.isArray(cards) || cards.length === 0) {
    document.getElementById("psModalContent").innerHTML = `<div style="padding:20px; text-align:center;">В этом практикуме пока нет карточек с заданиями.</div>`;
    return;
  }

  let currentIdx = 0;
  let hintIdx = 0;
  const canvas = document.getElementById("scratchpadCanvas");
  setupScratchpad(canvas);

  const renderCurrentCard = () => {
    hintIdx = 0;
    const card = cards[currentIdx];
    document.getElementById("psCardBadge").textContent = `Задача ${currentIdx + 1}`;
    document.getElementById("psCardCounter").textContent = `${currentIdx + 1} из ${cards.length}`;
    document.getElementById("taskPrompt").innerHTML = escapeHtml(card.prompt || "Без текста задания");
    document.getElementById("practiceAnswerInput").value = "";
    
    const feedbackArea = document.getElementById("psFeedbackArea");
    feedbackArea.style.display = "none";
    feedbackArea.innerHTML = "";

    const hintBtn = document.getElementById("revealHintBtn");
    const hintArea = document.getElementById("hintContentArea");
    hintArea.innerHTML = "";
    hintArea.style.display = "none";
    const hints = Array.isArray(card.hints) ? card.hints : [];
    if (hints.length === 0) {
      hintBtn.style.display = "none";
    } else {
      hintBtn.style.display = "inline-block";
      hintBtn.disabled = false;
      hintBtn.textContent = `💡 Получить подсказку (${hints.length})`;
    }

    document.getElementById("psPrevBtn").disabled = (currentIdx === 0);
    document.getElementById("psNextBtn").disabled = (currentIdx === cards.length - 1);
  };

  document.getElementById("revealHintBtn")?.addEventListener("click", () => {
    const card = cards[currentIdx];
    const hints = Array.isArray(card.hints) ? card.hints : [];
    const hintBtn = document.getElementById("revealHintBtn");
    const hintArea = document.getElementById("hintContentArea");
    if (hintIdx < hints.length) {
      hintArea.style.display = "block";
      const p = document.createElement("div");
      p.style.padding = "6px 10px";
      p.style.marginBottom = "4px";
      p.style.background = "#fff8e1";
      p.style.borderRadius = "4px";
      p.style.fontSize = "0.9rem";
      p.textContent = `💡 Подсказка ${hintIdx + 1}: ${hints[hintIdx++]}`;
      hintArea.appendChild(p);
      if (hintIdx >= hints.length) {
        hintBtn.disabled = true;
        hintBtn.textContent = "Все подсказки открыты";
      } else {
        hintBtn.textContent = `💡 Ещё подсказка (${hints.length - hintIdx} ост.)`;
      }
    }
  });

  document.getElementById("checkCardBtn")?.addEventListener("click", async () => {
    const card = cards[currentIdx];
    const val = document.getElementById("practiceAnswerInput")?.value.trim();
    if (!val) {
      alert("Введите ваш ответ");
      return;
    }
    const feedbackArea = document.getElementById("psFeedbackArea");
    try {
      const res = await v1Fetch(`/api/classroom/practice-sets/${setId}/check-card`, {
        method: "POST",
        body: {
          card_id: String(card.id || currentIdx),
          answer: val,
          used_hint: hintIdx > 0,
          scratchpad_json: null
        }
      });
      feedbackArea.style.display = "block";
      if (res.correct) {
        feedbackArea.style.color = "#2e7d32";
        feedbackArea.innerHTML = `✅ Верно! Отличная работа!` + (res.explanation ? `<div style="font-weight:normal; margin-top:4px;">${escapeHtml(res.explanation)}</div>` : "");
      } else {
        feedbackArea.style.color = "#c62828";
        feedbackArea.innerHTML = `❌ Ответ не совпадает. Попробуйте воспользоваться подсказкой или перепроверить в черновике.`;
      }
    } catch (e) {
      alert("Ошибка при проверке: " + e.message);
    }
  });

  document.getElementById("psPrevBtn")?.addEventListener("click", () => {
    if (currentIdx > 0) {
      currentIdx--;
      renderCurrentCard();
    }
  });

  document.getElementById("psNextBtn")?.addEventListener("click", () => {
    if (currentIdx < cards.length - 1) {
      currentIdx++;
      renderCurrentCard();
    }
  });

  renderCurrentCard();
}

/**
 * Practice Set Creator Modal
 */
export function openPracticeSetCreator(courseId, onReload) {
  let modal = document.getElementById("practiceSetCreatorOverlay");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "practiceSetCreatorOverlay";
    modal.className = "modal-overlay full-screen-modal-overlay";
    document.body.appendChild(modal);
  }

  let cards = [
    { id: "c1", prompt: "", answer: "", hints: [] }
  ];

  const renderCards = () => {
    const listEl = document.getElementById("pscCardsList");
    if (!listEl) return;
    listEl.innerHTML = cards.map((c, idx) => `
      <div class="psc-card-item" style="border:1px solid #ddd; border-radius:8px; padding:12px; margin-bottom:12px; background:#fff;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <strong>Карточка ${idx + 1}</strong>
          ${cards.length > 1 ? `<button type="button" class="btn btn-sm btn-danger psc-remove-card" data-idx="${idx}">Удалить</button>` : ""}
        </div>
        <div style="margin-bottom:8px;">
          <label style="display:block; font-size:0.85rem; font-weight:600; margin-bottom:4px;">Вопрос / Задание:</label>
          <textarea class="form-control psc-prompt" data-idx="${idx}" rows="2" placeholder="Условие задачи...">${escapeHtml(c.prompt || "")}</textarea>
        </div>
        <div style="margin-bottom:8px;">
          <label style="display:block; font-size:0.85rem; font-weight:600; margin-bottom:4px;">Правильный ответ:</label>
          <input type="text" class="form-control psc-answer" data-idx="${idx}" value="${escapeHtml(c.answer || "")}" placeholder="Ответ (число или точный текст)..." />
        </div>
        <div>
          <label style="display:block; font-size:0.85rem; font-weight:600; margin-bottom:4px;">Подсказки (через новую строку):</label>
          <textarea class="form-control psc-hints" data-idx="${idx}" rows="2" placeholder="Подсказка 1&#10;Подсказка 2">${escapeHtml((c.hints || []).join("\n"))}</textarea>
        </div>
      </div>
    `).join("");

    listEl.querySelectorAll(".psc-remove-card").forEach(btn => {
      btn.onclick = () => {
        const i = Number(btn.dataset.idx);
        cards.splice(i, 1);
        renderCards();
      };
    });

    listEl.querySelectorAll(".psc-prompt").forEach(ta => {
      ta.onchange = () => { cards[Number(ta.dataset.idx)].prompt = ta.value; };
    });
    listEl.querySelectorAll(".psc-answer").forEach(inp => {
      inp.onchange = () => { cards[Number(inp.dataset.idx)].answer = inp.value; };
    });
    listEl.querySelectorAll(".psc-hints").forEach(ta => {
      ta.onchange = () => {
        cards[Number(ta.dataset.idx)].hints = ta.value.split("\n").map(s => s.trim()).filter(Boolean);
      };
    });
  };

  modal.innerHTML = `
    <div class="modal-card" style="max-width:700px; max-height:90vh; overflow-y:auto; padding:24px; background:#fff; border-radius:12px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
        <h3 style="margin:0;">Создать интерактивный практикум (Practice Set)</h3>
        <button type="button" class="modal-close-btn" id="closePracticeSetCreatorBtn">&times;</button>
      </div>
      <div style="margin-bottom:16px;">
        <label style="display:block; font-weight:600; margin-bottom:4px;">Название практикума:</label>
        <input type="text" id="pscTitleInput" class="form-control" placeholder="Например: Квадратные уравнения. Базовый уровень" />
      </div>
      <div id="pscCardsList"></div>
      <div style="display:flex; gap:8px; margin-bottom:20px;">
        <button type="button" class="btn btn-secondary" id="pscAddCardBtn">+ Добавить карточку</button>
      </div>
      <div style="display:flex; justify-content:flex-end; gap:8px;">
        <button type="button" class="btn btn-secondary" id="pscCancelBtn">Отмена</button>
        <button type="button" class="btn btn-primary" id="pscSaveBtn">Сохранить практикум</button>
      </div>
    </div>
  `;

  modal.style.display = "flex";
  renderCards();

  const close = () => {
    modal.style.display = "none";
    modal.innerHTML = "";
  };

  document.getElementById("closePracticeSetCreatorBtn")?.addEventListener("click", close);
  document.getElementById("pscCancelBtn")?.addEventListener("click", close);

  document.getElementById("pscAddCardBtn")?.addEventListener("click", () => {
    cards.push({ id: "c" + (cards.length + 1), prompt: "", answer: "", hints: [] });
    renderCards();
  });

  document.getElementById("pscSaveBtn")?.addEventListener("click", async () => {
    const title = document.getElementById("pscTitleInput")?.value.trim();
    if (!title) {
      alert("Укажите название практикума");
      return;
    }
    // sync any current inputs
    document.querySelectorAll(".psc-prompt").forEach(ta => {
      cards[Number(ta.dataset.idx)].prompt = ta.value.trim();
    });
    document.querySelectorAll(".psc-answer").forEach(inp => {
      cards[Number(inp.dataset.idx)].answer = inp.value.trim();
    });
    document.querySelectorAll(".psc-hints").forEach(ta => {
      cards[Number(ta.dataset.idx)].hints = ta.value.split("\n").map(s => s.trim()).filter(Boolean);
    });

    try {
      await v1Fetch("/api/classroom/practice-sets", {
        method: "POST",
        body: {
          class_id: Number(courseId),
          set_title: title,
          cards_json: JSON.stringify(cards)
        }
      });
      close();
      if (typeof onReload === "function") onReload();
    } catch (e) {
      alert("Ошибка при сохранении практикума: " + e.message);
    }
  });
}

function setupScratchpad(canvas) {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let drawing = false;
  let mode = "pen"; // 'pen' | 'eraser'

  ctx.lineWidth = 2;
  ctx.lineCap = "round";
  ctx.strokeStyle = "#1a73e8";

  canvas.addEventListener("mousedown", (e) => {
    drawing = true;
    ctx.beginPath();
    ctx.moveTo(e.offsetX, e.offsetY);
  });

  canvas.addEventListener("mousemove", (e) => {
    if (!drawing) return;
    if (mode === "eraser") {
      ctx.clearRect(e.offsetX - 10, e.offsetY - 10, 20, 20);
    } else {
      ctx.lineTo(e.offsetX, e.offsetY);
      ctx.stroke();
    }
  });

  window.addEventListener("mouseup", () => {
    drawing = false;
  });

  document.getElementById("scratchPenBtn")?.addEventListener("click", () => {
    mode = "pen";
    ctx.strokeStyle = "#1a73e8";
    ctx.lineWidth = 2;
  });

  document.getElementById("scratchEraserBtn")?.addEventListener("click", () => {
    mode = "eraser";
  });

  document.getElementById("scratchClearBtn")?.addEventListener("click", () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  });
}
