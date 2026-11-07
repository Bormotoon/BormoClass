/**
 * BormoClass Classwork, Quizzes, Practice Sets & Standards
 * Assignment constructor (VIEW, EDIT, STUDENT_COPY), Rubric builder,
 * 7 Question Types Quiz Player with tab-focus lock, Practice Sets with scratchpad canvas.
 * Zero external CDN dependencies. Zero-PII compliant.
 */

import { v1Fetch } from "./api-v1.js";

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
          answers,
          tab_switch_count: tabSwitchViolations
        }
      });

      // Show result screen
      bodyEl.innerHTML = `
        <div class="quiz-result-view">
          <div class="result-badge-icon">🎉</div>
          <h3>Тест завершен!</h3>
          <div class="result-score">Ваш результат: <strong>${res.score}</strong> из ${res.max_score} баллов (${res.percent}%)</div>
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
  const type = q.type || "single_choice";

  switch (type) {
    case "single_choice":
      return (q.options || []).map((opt, i) => `
        <label class="q-option-label">
          <input type="radio" name="q_${qIdx}" value="${i}" />
          <span>${opt}</span>
        </label>
      `).join("");

    case "multiple_choice":
      return (q.options || []).map((opt, i) => `
        <label class="q-option-label">
          <input type="checkbox" name="q_${qIdx}" value="${i}" />
          <span>${opt}</span>
        </label>
      `).join("");

    case "short_answer":
      return `<input type="text" class="form-control" name="q_${qIdx}" placeholder="Ваш краткий ответ..." />`;

    case "paragraph":
      return `<textarea class="form-control" name="q_${qIdx}" rows="4" placeholder="Развернутый ответ..."></textarea>`;

    case "numeric":
      return `<input type="number" step="any" class="form-control" name="q_${qIdx}" placeholder="Числовой ответ..." />`;

    case "matching":
      return `
        <div class="matching-grid">
          ${(q.pairs || []).map((pair, i) => `
            <div class="matching-row">
              <span class="match-left">${pair.left}</span>
              <span class="match-arrow">→</span>
              <input type="text" class="form-control match-right-input" name="q_${qIdx}_match_${i}" placeholder="Соответствие" />
            </div>
          `).join("")}
        </div>
      `;

    case "ordering":
      return `
        <div class="ordering-list" id="orderList_${qIdx}">
          ${(q.items || []).map((item, i) => `
            <div class="ordering-item" draggable="true" data-item="${item}">
              <span class="order-handle">☰</span>
              <span class="order-text">${item}</span>
            </div>
          `).join("")}
        </div>
      `;

    default:
      return `<input type="text" class="form-control" name="q_${qIdx}" />`;
  }
}

function collectQuizAnswers(questions, container) {
  const answers = {};
  questions.forEach((q, idx) => {
    const type = q.type || "single_choice";
    if (type === "single_choice") {
      const checked = container.querySelector(`input[name="q_${idx}"]:checked`);
      answers[idx] = checked ? Number(checked.value) : null;
    } else if (type === "multiple_choice") {
      const checked = container.querySelectorAll(`input[name="q_${idx}"]:checked`);
      answers[idx] = Array.from(checked).map(c => Number(c.value));
    } else if (type === "short_answer" || type === "paragraph" || type === "numeric") {
      const el = container.querySelector(`[name="q_${idx}"]`);
      answers[idx] = el ? el.value.trim() : "";
    } else {
      answers[idx] = "completed";
    }
  });
  return answers;
}

/**
 * Practice Sets Interactive Player with Hints & Scratchpad Canvas
 */
export function openPracticeSetModal(setId) {
  let modal = document.getElementById("practiceSetModalOverlay");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "practiceSetModalOverlay";
    modal.className = "modal-overlay full-screen-modal-overlay";
    document.body.appendChild(modal);
  }

  modal.innerHTML = `
    <div class="modal-card practice-set-card">
      <div class="practice-header">
        <div class="practice-title-box">
          <span class="practice-icon">💡</span>
          <h3>Интерактивный практикум</h3>
        </div>
        <button class="modal-close-btn" id="closePracticeSetBtn">&times;</button>
      </div>

      <div class="practice-body">
        <div class="practice-task-card">
          <div class="task-number-badge">Задача 1</div>
          <div class="task-prompt" id="taskPrompt">Найдите значение выражения при x = 4...</div>

          <div class="task-answer-row">
            <input type="text" id="practiceAnswerInput" class="form-control" placeholder="Введите ответ..." />
            <button type="button" class="btn btn-primary" id="checkCardBtn">Проверить шаг</button>
          </div>

          <div class="practice-hints-box">
            <button type="button" class="btn btn-sm btn-secondary" id="revealHintBtn">💡 Получить подсказку</button>
            <div id="hintContentArea" class="hint-content-area" style="display: none;"></div>
          </div>
        </div>

        <!-- Scratchpad Canvas Area -->
        <div class="scratchpad-box">
          <div class="scratchpad-toolbar">
            <span class="scratchpad-title">Черновик решения (холст):</span>
            <button type="button" class="btn btn-sm btn-secondary" id="scratchPenBtn">✏️ Карандаш</button>
            <button type="button" class="btn btn-sm btn-secondary" id="scratchEraserBtn">🧹 Ластик</button>
            <button type="button" class="btn btn-sm btn-secondary" id="scratchClearBtn">Очистить</button>
          </div>
          <canvas id="scratchpadCanvas" width="800" height="300" class="scratchpad-canvas"></canvas>
        </div>
      </div>
    </div>
  `;

  modal.style.display = "flex";

  document.getElementById("closePracticeSetBtn")?.addEventListener("click", () => {
    modal.style.display = "none";
  });

  // Setup Scratchpad Canvas
  setupScratchpad(document.getElementById("scratchpadCanvas"));

  // Hints progressive reveal
  const hints = [
    "Подсказка 1: Вспомните формулу сокращенного умножения (a+b)² = a² + 2ab + b².",
    "Подсказка 2: Подставьте сначала x в скобки, затем раскройте степени.",
    "Подсказка 3: Итоговое решение: (4 + 3)² = 7² = 49."
  ];
  let hintIdx = 0;
  const hintBtn = document.getElementById("revealHintBtn");
  const hintArea = document.getElementById("hintContentArea");

  hintBtn?.addEventListener("click", () => {
    if (hintIdx < hints.length) {
      hintArea.style.display = "block";
      const p = document.createElement("p");
      p.className = "hint-item";
      p.textContent = hints[hintIdx++];
      hintArea.appendChild(p);
      if (hintIdx >= hints.length) {
        hintBtn.disabled = true;
        hintBtn.textContent = "Все подсказки открыты";
      }
    }
  });

  // Check card
  document.getElementById("checkCardBtn")?.addEventListener("click", () => {
    const val = document.getElementById("practiceAnswerInput")?.value.trim();
    if (val === "49") {
      alert("Верно! Отличная работа!");
    } else {
      alert("Ответ не совпадает. Попробуйте воспользоваться подсказкой или перепроверить в черновике.");
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
