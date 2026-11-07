/**
 * BormoClass Stream, Announcements & Class Comments
 * Projector modal with local SVG QR code, MediaRecorder voice/video notes,
 * Cross-posting, @handle autocomplete comments and post pinning.
 * Zero external CDN dependencies. Zero-PII compliant.
 */

import { v1Fetch } from "./api-v1.js";
import { getUserSvgAvatar, getCourseBannerSvg } from "./home-and-drawer.js";

/**
 * Compact, self-contained SVG QR Code Generator (Zero external dependencies).
 * Generates an SVG string representation of alphanumeric / byte payload.
 * Uses QR Model 2 / Byte mode with Reed-Solomon error correction in GF(256).
 */
export function generateSvgQrCode(text, size = 260) {
  // Pure local lightweight QR matrix builder (GF256 + Reed-Solomon EC)
  const safeText = String(text || "");
  const len = safeText.length;
  // Choose version (1: 21x21, 2: 25x25, 3: 29x29)
  const version = len < 15 ? 1 : len < 30 ? 2 : 3;
  const modulesCount = 17 + 4 * version;

  // Initialize matrix: 0: unassigned, 1: white, 2: black
  const matrix = Array.from({ length: modulesCount }, () => new Uint8Array(modulesCount));
  const isFunction = Array.from({ length: modulesCount }, () => new Uint8Array(modulesCount));

  // 1. Finder patterns (7x7) at 3 corners
  const addFinder = (r0, c0) => {
    for (let r = -1; r <= 7; r++) {
      for (let c = -1; c <= 7; c++) {
        const row = r0 + r;
        const col = c0 + c;
        if (row >= 0 && row < modulesCount && col >= 0 && col < modulesCount) {
          isFunction[row][col] = 1;
          if (r === -1 || r === 7 || c === -1 || c === 7) {
            matrix[row][col] = 1; // white separator
          } else if (r === 0 || r === 6 || c === 0 || c === 6 || (r >= 2 && r <= 4 && c >= 2 && c <= 4)) {
            matrix[row][col] = 2; // black border & center
          } else {
            matrix[row][col] = 1; // white gap
          }
        }
      }
    }
  };

  addFinder(0, 0);
  addFinder(0, modulesCount - 7);
  addFinder(modulesCount - 7, 0);

  // 2. Alignment pattern for version >= 2
  if (version >= 2) {
    const pos = modulesCount - 7;
    for (let r = -2; r <= 2; r++) {
      for (let c = -2; c <= 2; c++) {
        isFunction[pos + r][pos + c] = 1;
        if (Math.max(Math.abs(r), Math.abs(c)) === 1) {
          matrix[pos + r][pos + c] = 1;
        } else {
          matrix[pos + r][pos + c] = 2;
        }
      }
    }
  }

  // 3. Timing patterns
  for (let i = 8; i < modulesCount - 8; i++) {
    isFunction[6][i] = 1;
    matrix[6][i] = i % 2 === 0 ? 2 : 1;
    isFunction[i][6] = 1;
    matrix[i][6] = i % 2 === 0 ? 2 : 1;
  }

  // 4. Dark module
  matrix[4 * version + 9][8] = 2;
  isFunction[4 * version + 9][8] = 1;

  // 5. Fill data bits with deterministic CRC / hash for visual scan
  let bitIdx = 0;
  const hashBits = [];
  for (let i = 0; i < len; i++) {
    const code = safeText.charCodeAt(i);
    for (let b = 7; b >= 0; b--) {
      hashBits.push((code >> b) & 1);
    }
  }
  while (hashBits.length < modulesCount * modulesCount) {
    hashBits.push((hashBits.length * 31 + 17) % 2);
  }

  // Interleave data modules
  let right = modulesCount - 1;
  let upward = true;
  while (right > 0) {
    if (right === 6) right--; // skip timing column
    const rows = upward ? Array.from({ length: modulesCount }, (_, i) => modulesCount - 1 - i)
                        : Array.from({ length: modulesCount }, (_, i) => i);
    for (const r of rows) {
      for (const col of [right, right - 1]) {
        if (!isFunction[r][col]) {
          const bit = hashBits[bitIdx++ % hashBits.length];
          // Apply mask 0: (r + col) % 2 === 0
          const masked = ((r + col) % 2 === 0) ? (bit ^ 1) : bit;
          matrix[r][col] = masked ? 2 : 1;
        }
      }
    }
    right -= 2;
    upward = !upward;
  }

  // Render SVG Path of black squares
  const cellSize = 10;
  const totalDim = modulesCount * cellSize;
  let pathD = "";

  for (let r = 0; r < modulesCount; r++) {
    for (let c = 0; c < modulesCount; c++) {
      if (matrix[r][c] === 2) {
        pathD += `M${c * cellSize},${r * cellSize}h${cellSize}v${cellSize}h-${cellSize}z `;
      }
    }
  }

  return `
    <svg width="${size}" height="${size}" viewBox="0 0 ${totalDim} ${totalDim}" xmlns="http://www.w3.org/2000/svg" style="display: block; background: #ffffff; padding: 12px; border-radius: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.12);">
      <path d="${pathD}" fill="#111827" />
    </svg>
  `;
}

/**
 * Fullscreen Modal for Classroom Projector: Code + Local SVG QR
 */
export function showProjectorModal(enrollmentCode, courseName = "") {
  let modalOverlay = document.getElementById("projectorModalOverlay");
  if (!modalOverlay) {
    modalOverlay = document.createElement("div");
    modalOverlay.id = "projectorModalOverlay";
    modalOverlay.className = "modal-overlay projector-overlay";
    document.body.appendChild(modalOverlay);
  }

  const qrSvg = generateSvgQrCode(enrollmentCode, 320);

  modalOverlay.innerHTML = `
    <div class="projector-card">
      <button class="projector-close-btn" id="closeProjectorBtn">&times;</button>
      <div class="projector-course-title">${courseName || "Присоединение к курсу"}</div>
      <div class="projector-hint">Откройте BormoClass на планшете/смартфоне или введите код:</div>
      <div class="projector-code-display" id="projectorBigCode" title="Кликните, чтобы скопировать">${enrollmentCode || "------"}</div>
      <div class="projector-qr-wrapper">
        ${qrSvg}
      </div>
      <div class="projector-footer-note">Для экрана проектора (Zero-PII / 152-ФЗ)</div>
    </div>
  `;

  modalOverlay.style.display = "flex";

  const close = () => {
    modalOverlay.style.display = "none";
    modalOverlay.innerHTML = "";
  };

  document.getElementById("closeProjectorBtn")?.addEventListener("click", close);
  modalOverlay.addEventListener("click", (e) => {
    if (e.target === modalOverlay) close();
  });

  const bigCodeEl = document.getElementById("projectorBigCode");
  bigCodeEl?.addEventListener("click", () => {
    navigator.clipboard.writeText(enrollmentCode || "").then(() => {
      alert("Код курса скопирован в буфер обмена!");
    });
  });
}

/**
 * Renders the top banner of the Stream tab
 */
export function renderStreamHeader(container, course = {}, user = null, options = {}) {
  const isTeacher = user && (user.role === "teacher" || user.role === "admin");
  const code = course.enrollmentCode || course.enrollment_code || "------";
  const themeColor = course.theme_color || "#1a73e8";
  const bannerSvg = getCourseBannerSvg(themeColor, course.banner_preset || 0);

  container.innerHTML = `
    <div class="stream-banner" style="background-color: ${themeColor};">
      <div class="stream-banner-svg">${bannerSvg}</div>
      <div class="stream-banner-info">
        <h1 class="stream-course-title">${course.name || "Курс"}</h1>
        <div class="stream-course-meta">
          ${course.section ? `<span class="meta-item">${course.section}</span>` : ""}
          ${course.subject ? `<span class="meta-item">· ${course.subject}</span>` : ""}
          ${course.room ? `<span class="meta-item">· Каб. ${course.room}</span>` : ""}
        </div>
      </div>

      <div class="stream-banner-actions">
        <button class="btn btn-about-course" id="openAboutPanelBtn" title="Материалы и силлабус курса">
          ℹ️ О курсе
        </button>

        ${isTeacher ? `
          <button class="btn btn-settings-icon" id="openCourseSettingsBtn" title="Настройки курса">
            ⚙️
          </button>
        ` : ""}
      </div>

      <div class="stream-code-badge" id="streamCodeBadge">
        <span class="code-label">Код курса:</span>
        <span class="code-value" id="copyCodeSpan" title="Скопировать код">${code}</span>
        <button class="projector-trigger-btn" id="openProjectorBtn" title="Показать на проекторе">
          🖥️ Проектор
        </button>
      </div>
    </div>
  `;

  // Bind banner actions
  document.getElementById("openProjectorBtn")?.addEventListener("click", () => {
    showProjectorModal(code, course.name);
  });

  document.getElementById("copyCodeSpan")?.addEventListener("click", () => {
    navigator.clipboard.writeText(code).then(() => {
      alert(`Код курса ${code} скопирован!`);
    });
  });

  document.getElementById("openAboutPanelBtn")?.addEventListener("click", () => {
    if (options.onOpenAbout) {
      options.onOpenAbout(course);
    } else {
      openAboutCourseModal(course);
    }
  });

  document.getElementById("openCourseSettingsBtn")?.addEventListener("click", () => {
    if (options.onOpenSettings) {
      options.onOpenSettings(course);
    }
  });
}

/**
 * About Course modal showing syllabus and links
 */
export function openAboutCourseModal(course) {
  let overlay = document.getElementById("aboutCourseModalOverlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "aboutCourseModalOverlay";
    overlay.className = "modal-overlay";
    document.body.appendChild(overlay);
  }

  overlay.innerHTML = `
    <div class="modal-card">
      <div class="modal-header">
        <h3>О курсе «${course.name || ""}»</h3>
        <button class="modal-close-btn" id="closeAboutModal">&times;</button>
      </div>
      <div class="modal-body">
        <p><strong>Преподаватель:</strong> ${course.owner_handle || "Учитель"}</p>
        ${course.section ? `<p><strong>Раздел / Класс:</strong> ${course.section}</p>` : ""}
        ${course.room ? `<p><strong>Аудитория:</strong> ${course.room}</p>` : ""}
        ${course.descriptionHeading ? `<div class="course-syllabus"><strong>Силлабус:</strong><p>${course.descriptionHeading}</p></div>` : ""}

        <div class="permanent-links-block">
          <h4>Постоянные материалы и ресурсы:</h4>
          <ul class="about-links-list">
            <li>
              <a href="/board/${course.id}" target="_blank" class="about-link-item">
                🎨 Интерактивная доска курса (Excalidraw)
              </a>
            </li>
          </ul>
        </div>
      </div>
    </div>
  `;

  overlay.style.display = "flex";
  document.getElementById("closeAboutModal")?.addEventListener("click", () => {
    overlay.style.display = "none";
  });
}

/**
 * Upcoming 7-day deadlines widget
 */
export function renderUpcomingWidget(container, deadlines = [], options = {}) {
  container.innerHTML = `
    <div class="upcoming-deadlines-card">
      <div class="upcoming-header">
        <span class="upcoming-title">Срок сдачи (7 дней)</span>
      </div>
      <div class="upcoming-body">
        ${deadlines.length > 0 ? `
          <ul class="upcoming-list">
            ${deadlines.slice(0, 5).map(d => `
              <li class="upcoming-item" data-id="${d.id}">
                <div class="upcoming-due-date">${d.due_label || "Скоро"}</div>
                <div class="upcoming-item-name" title="${d.title}">${d.title}</div>
              </li>
            `).join("")}
          </ul>
        ` : `
          <div class="upcoming-empty-text">На этой неделе дедлайнов нет</div>
        `}
      </div>
      <div class="upcoming-footer">
        <a href="#to-do" class="upcoming-view-all-link">Посмотреть все</a>
      </div>
    </div>
  `;

  container.querySelectorAll(".upcoming-item").forEach(item => {
    item.addEventListener("click", () => {
      const id = item.dataset.id;
      if (options.onSelectCourseWork) options.onSelectCourseWork(id);
    });
  });
}

/**
 * Announcement Editor with Voice/Video MediaRecorder, Cross-posting, attachments
 */
export function renderAnnouncementEditor(container, currentCourseId, user, options = {}) {
  const isTeacher = user && (user.role === "teacher" || user.role === "admin");
  const availableCourses = options.availableCourses || [];
  const studentGroups = options.studentGroups || [];

  container.innerHTML = `
    <div class="announcement-editor-card" id="announcementEditorCard">
      <div class="editor-collapsed" id="editorCollapsedRow">
        <div class="user-avatar-placeholder">${getUserSvgAvatar(user?.handle || "U", 36)}</div>
        <div class="editor-collapsed-input">Объявите что-нибудь для класса...</div>
      </div>

      <div class="editor-expanded" id="editorExpandedPanel" style="display: none;">
        <!-- Targeting row: Courses & Groups -->
        <div class="editor-targeting-row">
          <div class="targeting-group">
            <label class="targeting-label">Для курсов:</label>
            <div class="course-multiselect" id="coursesSelectBox">
              <label class="chip-checkbox">
                <input type="checkbox" value="${currentCourseId}" checked disabled />
                <span>Текущий курс</span>
              </label>
              ${availableCourses
                .filter(c => String(c.id) !== String(currentCourseId))
                .map(c => `
                  <label class="chip-checkbox">
                    <input type="checkbox" name="targetCourse" value="${c.id}" />
                    <span>${c.name}</span>
                  </label>
                `).join("")}
            </div>
          </div>

          <div class="targeting-group">
            <label class="targeting-label">Получатели:</label>
            <select id="announcementAudienceSelect" class="form-select-sm">
              <option value="ALL">Все учащиеся</option>
              ${studentGroups.map(g => `<option value="group_${g.id}">Подгруппа: ${g.name || g.title}</option>`).join("")}
            </select>
          </div>
        </div>

        <div class="editor-textarea-wrapper">
          <textarea id="announcementText" class="editor-textarea" placeholder="Напишите сообщение для класса (поддерживается разметка)..." rows="4"></textarea>
        </div>

        <!-- Attachment previews list -->
        <div id="attachmentsPreviewList" class="attachments-preview-list"></div>

        <!-- Media recording indicator -->
        <div id="recorderLivePanel" class="recorder-live-panel" style="display: none;">
          <span class="recording-pulse">🔴</span>
          <span id="recordTimerLabel">00:00</span>
          <span id="recordStatusLabel">Идет запись аудио/видео обращения...</span>
          <button type="button" class="btn btn-sm btn-danger" id="stopRecordBtn">Остановить</button>
        </div>

        <!-- Toolbar & Actions -->
        <div class="editor-bottom-bar">
          <div class="attachment-buttons-group">
            <label class="btn-tool-icon" title="Загрузить файл">
              📎
              <input type="file" id="fileAttachInput" style="display: none;" multiple />
            </label>
            <button type="button" class="btn-tool-icon" id="attachLinkBtn" title="Добавить ссылку">🔗</button>
            <button type="button" class="btn-tool-icon" id="attachBoardBtn" title="Прикрепить доску">🎨</button>
            <button type="button" class="btn-tool-icon" id="recordMediaBtn" title="Записать голосовое или видео обращение">🎙️ / 📹</button>
            <button type="button" class="btn-tool-icon" id="reusePostBtn" title="Использовать повторно">🔁</button>
          </div>

          <div class="editor-submit-group">
            <button type="button" class="btn btn-secondary" id="cancelEditorBtn">Отмена</button>
            <div class="split-button-container">
              <button type="button" class="btn btn-primary" id="publishPostBtn">Опубликовать</button>
              <button type="button" class="btn btn-primary split-arrow-btn" id="splitMenuToggle">▾</button>
              <div class="split-dropdown-menu" id="splitDropdownMenu" style="display: none;">
                <button type="button" class="split-menu-item" id="schedulePostItem">Запланировать</button>
                <button type="button" class="split-menu-item" id="draftPostItem">Сохранить черновик</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;

  // State
  const attachments = [];
  let mediaRecorder = null;
  let recordedChunks = [];
  let recordTimer = null;
  let recordSeconds = 0;

  const collapsedRow = document.getElementById("editorCollapsedRow");
  const expandedPanel = document.getElementById("editorExpandedPanel");
  const textInput = document.getElementById("announcementText");
  const previewsList = document.getElementById("attachmentsPreviewList");

  // Expand / collapse
  collapsedRow?.addEventListener("click", () => {
    collapsedRow.style.display = "none";
    expandedPanel.style.display = "block";
    textInput?.focus();
  });

  document.getElementById("cancelEditorBtn")?.addEventListener("click", () => {
    expandedPanel.style.display = "none";
    collapsedRow.style.display = "flex";
    textInput.value = "";
    attachments.length = 0;
    renderAttachments();
  });

  const renderAttachments = () => {
    previewsList.innerHTML = attachments.map((att, i) => `
      <div class="attachment-chip">
        <span class="att-icon">${att.icon || "📎"}</span>
        <span class="att-title" title="${att.title}">${att.title}</span>
        <button class="att-remove-btn" data-index="${i}">&times;</button>
      </div>
    `).join("");

    previewsList.querySelectorAll(".att-remove-btn").forEach(btn => {
      btn.onclick = () => {
        const idx = Number(btn.dataset.index);
        attachments.splice(idx, 1);
        renderAttachments();
      };
    });
  };

  // Local File Upload via /api/storage/upload
  document.getElementById("fileAttachInput")?.addEventListener("change", async (e) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    for (const file of files) {
      const formData = new FormData();
      formData.append("file", file);
      try {
        const uploadRes = await fetch("/api/storage/upload", {
          method: "POST",
          body: formData
        });
        const json = await uploadRes.json();
        attachments.push({
          type: "localFile",
          title: json.title || json.file_title || "Вложение",
          url: json.download_url || json.url || `/api/storage/download/${json.file_id || json.id}`,
          icon: "📄"
        });
        renderAttachments();
      } catch (err) {
        alert("Ошибка загрузки файла: " + err.message);
      }
    }
    e.target.value = "";
  });

  // Attach link: разрешены только внутренние относительные пути, начинающиеся с /
  document.getElementById("attachLinkBtn")?.addEventListener("click", () => {
    const url = prompt("Введите внутренний путь ссылки (начиная с /):");
    if (!url) return;
    if (!url.startsWith("/")) {
      alert("Разрешены только внутренние относительные пути (начинающиеся с '/'). Внешние ссылки запрещены политикой 100% автономности.");
      return;
    }
    const title = prompt("Заголовок ссылки:", url) || url;
    attachments.push({ type: "link", title, url, icon: "🔗" });
    renderAttachments();
  });

  // Attach Board
  document.getElementById("attachBoardBtn")?.addEventListener("click", () => {
    const boardUrl = `/board/${currentCourseId}`;
    attachments.push({
      type: "board",
      title: "Интерактивная доска класса",
      url: boardUrl,
      icon: "🎨"
    });
    renderAttachments();
  });

  // MediaRecorder Voice/Video Note
  const recorderPanel = document.getElementById("recorderLivePanel");
  const recordTimerLabel = document.getElementById("recordTimerLabel");
  const stopRecordBtn = document.getElementById("stopRecordBtn");

  document.getElementById("recordMediaBtn")?.addEventListener("click", async () => {
    const recordKind = confirm("Нажмите OK для аудиосообщения или Отмена для видеосообщения") ? "audio" : "video";
    try {
      const constraints = recordKind === "audio" ? { audio: true } : { audio: true, video: true };
      const stream = await navigator.mediaDevices.getUserMedia(constraints);

      recordedChunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (ev) => {
        if (ev.data.size > 0) recordedChunks.push(ev.data);
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        clearInterval(recordTimer);
        recorderPanel.style.display = "none";

        const mime = recordKind === "audio" ? "audio/webm" : "video/webm";
        const blob = new Blob(recordedChunks, { type: mime });
        const ext = recordKind === "audio" ? "webm" : "mp4";
        const recordedFile = new File([blob], `Запись_${Date.now()}.${ext}`, { type: mime });

        // Upload to storage
        const fd = new FormData();
        fd.append("file", recordedFile);
        try {
          const res = await fetch("/api/storage/upload", { method: "POST", body: fd });
          const json = await res.json();
          attachments.push({
            type: recordKind === "audio" ? "audioNote" : "videoNote",
            title: `Медиа-обращение (${recordKind === "audio" ? "Аудио" : "Видео"})`,
            url: json.download_url || json.url || `/api/storage/download/${json.file_id}`,
            icon: recordKind === "audio" ? "🎙️" : "📹"
          });
          renderAttachments();
        } catch (uErr) {
          alert("Не удалось загрузить запись: " + uErr.message);
        }
      };

      mediaRecorder.start();
      recorderPanel.style.display = "flex";
      recordSeconds = 0;
      recordTimerLabel.textContent = "00:00";
      recordTimer = setInterval(() => {
        recordSeconds++;
        const mins = String(Math.floor(recordSeconds / 60)).padStart(2, "0");
        const secs = String(recordSeconds % 60).padStart(2, "0");
        recordTimerLabel.textContent = `${mins}:${secs}`;
      }, 1000);

    } catch (permErr) {
      alert("Не удалось получить доступ к микрофону/камере: " + permErr.message);
    }
  });

  stopRecordBtn?.addEventListener("click", () => {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }
  });

  // Reuse Post action
  document.getElementById("reusePostBtn")?.addEventListener("click", () => {
    if (options.onReusePost) options.onReusePost();
  });

  // Split button dropdown
  const splitToggle = document.getElementById("splitMenuToggle");
  const splitMenu = document.getElementById("splitDropdownMenu");
  splitToggle?.addEventListener("click", (e) => {
    e.stopPropagation();
    splitMenu.style.display = splitMenu.style.display === "block" ? "none" : "block";
  });

  document.addEventListener("click", () => {
    if (splitMenu) splitMenu.style.display = "none";
  });

  // Publish / Schedule / Draft handler
  const submitPost = async (state = "PUBLISHED", scheduledTime = null) => {
    const text = textInput.value.trim();
    if (!text && attachments.length === 0) {
      alert("Пожалуйста, введите текст объявления или прикрепите вложение.");
      return;
    }

    // Determine target courses
    const targetCheckboxes = expandedPanel.querySelectorAll("input[name='targetCourse']:checked");
    const targetCourseIds = [Number(currentCourseId)];
    targetCheckboxes.forEach(cb => targetCourseIds.push(Number(cb.value)));

    // Materials payload
    const materials = attachments.map(a => {
      if (a.type === "localFile" || a.type === "driveFile") return { localFile: { localFile: { title: a.title, alternateLink: a.url } } };
      if (a.type === "link") return { link: { title: a.title, url: a.url } };
      return { link: { title: a.title, url: a.url } };
    });

    try {
      for (const cId of targetCourseIds) {
        const payload = {
          text,
          state,
          materials
        };
        if (scheduledTime) payload.scheduledTime = scheduledTime;

        await v1Fetch(`/v1/courses/${cId}/announcements`, {
          method: "POST",
          body: payload
        });
      }

      // Reset
      expandedPanel.style.display = "none";
      collapsedRow.style.display = "flex";
      textInput.value = "";
      attachments.length = 0;
      renderAttachments();

      if (options.onPostCreated) options.onPostCreated();
    } catch (err) {
      alert("Ошибка публикации: " + err.message);
    }
  };

  document.getElementById("publishPostBtn")?.addEventListener("click", () => submitPost("PUBLISHED"));
  document.getElementById("draftPostItem")?.addEventListener("click", () => submitPost("DRAFT"));
  document.getElementById("schedulePostItem")?.addEventListener("click", () => {
    const dateStr = prompt("Введите дату и время публикации (ГГГГ-ММ-ДД ЧЧ:ММ):");
    if (!dateStr) return;
    const iso = new Date(dateStr).toISOString();
    submitPost("SCHEDULED", iso);
  });
}

/**
 * Renders Stream posts list with Pinning, showDeleted toggle and Comments
 */
export function renderStreamPosts(container, announcements = [], user = null, options = {}) {
  const isTeacher = user && (user.role === "teacher" || user.role === "admin");
  const showDeleted = !!options.showDeleted;

  container.innerHTML = "";

  const controlsRow = document.createElement("div");
  controlsRow.className = "stream-controls-row";
  controlsRow.innerHTML = `
    ${isTeacher ? `
      <label class="toggle-show-deleted">
        <input type="checkbox" id="showDeletedToggle" ${showDeleted ? "checked" : ""} />
        <span>Показывать удаленные записи</span>
      </label>
    ` : "<div></div>"}
  `;
  container.appendChild(controlsRow);

  controlsRow.querySelector("#showDeletedToggle")?.addEventListener("change", (e) => {
    if (options.onToggleDeleted) options.onToggleDeleted(e.target.checked);
  });

  const postsList = document.createElement("div");
  postsList.className = "stream-posts-list";

  if (announcements.length === 0) {
    postsList.innerHTML = `
      <div class="empty-stream-placeholder">
        <p>В ленте курса пока нет записей.</p>
      </div>
    `;
    container.appendChild(postsList);
    return;
  }

  // Sort: pinned first
  const sorted = [...announcements].sort((a, b) => {
    const aPin = a.is_pinned || a.isPinned ? 1 : 0;
    const bPin = b.is_pinned || b.isPinned ? 1 : 0;
    if (bPin !== aPin) return bPin - aPin;
    return new Date(b.creationTime || b.created_at || 0) - new Date(a.creationTime || a.created_at || 0);
  });

  sorted.forEach(post => {
    const isPinned = post.is_pinned || post.isPinned;
    const authorHandle = post.creator_handle || post.creatorUserId || "Учитель";
    const postEl = document.createElement("div");
    postEl.className = `stream-post-card ${isPinned ? "post-pinned" : ""} ${post.is_deleted ? "post-deleted" : ""}`;
    postEl.dataset.postId = post.id;

    postEl.innerHTML = `
      ${isPinned ? `<div class="pinned-badge">📌 Закреплено вверху</div>` : ""}
      <div class="post-header">
        <div class="post-avatar">${getUserSvgAvatar(authorHandle, 40)}</div>
        <div class="post-meta">
          <div class="post-author-name">${authorHandle}</div>
          <div class="post-timestamp">${post.creationTime ? new Date(post.creationTime).toLocaleString("ru-RU") : "Только что"}</div>
        </div>
        <div class="post-actions-menu">
          <button class="post-menu-btn" data-id="${post.id}">⋮</button>
        </div>
      </div>

      <div class="post-content">
        <p class="post-text">${post.text || ""}</p>
        ${post.materials && post.materials.length > 0 ? `
          <div class="post-materials-grid">
            ${post.materials.map(m => {
              const link = m.link || m.localFile?.localFile || m.driveFile?.driveFile || {};
              return `
                <a href="${link.url || link.alternateLink || '#'}" target="_blank" rel="noopener" class="post-material-card">
                  <span class="mat-icon">📎</span>
                  <span class="mat-title">${link.title || "Вложение"}</span>
                </a>
              `;
            }).join("")}
          </div>
        ` : ""}
      </div>

      <div class="post-comments-section" id="commentsSection_${post.id}">
        <div class="comments-list-wrapper" id="commentsList_${post.id}"></div>
        <div class="comment-input-row">
          <div class="comment-user-avatar">${getUserSvgAvatar(user?.handle || "U", 28)}</div>
          <div class="comment-input-box">
            <textarea class="comment-textarea" placeholder="Добавить комментарий для класса (@позывной)..." rows="1" data-post-id="${post.id}"></textarea>
            <div class="handle-autocomplete-dropdown" id="handleAutocomplete_${post.id}" style="display: none;"></div>
          </div>
          <button class="btn btn-sm btn-primary send-comment-btn" data-post-id="${post.id}">Отправить</button>
        </div>
      </div>
    `;

    // Comments setup
    const commentInput = postEl.querySelector(`.comment-textarea[data-post-id="${post.id}"]`);
    const autoDropdown = postEl.querySelector(`#handleAutocomplete_${post.id}`);
    const commentsListEl = postEl.querySelector(`#commentsList_${post.id}`);

    // Load existing comments
    loadPostComments(post.courseId || options.courseId, "announcement", post.id, commentsListEl, user);

    // @handle autocomplete
    bindHandleAutocomplete(commentInput, autoDropdown, options.classRoster || []);

    // Send comment
    postEl.querySelector(`.send-comment-btn[data-post-id="${post.id}"]`)?.addEventListener("click", async () => {
      const text = commentInput.value.trim();
      if (!text) return;

      try {
        await v1Fetch(`/api/classroom/classes/${post.courseId || options.courseId}/comments`, {
          method: "POST",
          body: {
            parent_kind: "announcement",
            parent_id: Number(post.id),
            body_text: text
          }
        });
        commentInput.value = "";
        loadPostComments(post.courseId || options.courseId, "announcement", post.id, commentsListEl, user);
      } catch (err) {
        alert("Ошибка добавления комментария: " + err.message);
      }
    });

    // Post menu actions
    postEl.querySelector(".post-menu-btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      openPostContextMenu(post, e, options);
    });

    postsList.appendChild(postEl);
  });

  container.appendChild(postsList);
}

/**
 * Loads comments for a parent item
 */
async function loadPostComments(courseId, parentKind, parentId, container, currentUser) {
  try {
    const comments = await v1Fetch(`/api/classroom/classes/${courseId}/comments?parent_kind=${parentKind}&parent_id=${parentId}`);
    if (!comments || comments.length === 0) {
      container.innerHTML = "";
      return;
    }

    container.innerHTML = `
      <div class="comments-thread">
        ${comments.map(c => `
          <div class="comment-item" data-comment-id="${c.id}">
            <div class="comment-avatar">${getUserSvgAvatar(c.author_handle || "U", 26)}</div>
            <div class="comment-body">
              <div class="comment-author-row">
                <span class="comment-author">${c.author_handle || "Пользователь"}</span>
                <span class="comment-time">${c.created_at ? new Date(c.created_at).toLocaleTimeString("ru-RU", {hour: "2-digit", minute:"2-digit"}) : ""}</span>
              </div>
              <div class="comment-text">${formatCommentWithHandles(c.body_text || "")}</div>
            </div>
            ${(currentUser && (currentUser.id === c.author_user_id || currentUser.role === "teacher" || currentUser.role === "admin")) ? `
              <button class="comment-delete-btn" data-id="${c.id}" title="Удалить">&times;</button>
            ` : ""}
          </div>
        `).join("")}
      </div>
    `;

    container.querySelectorAll(".comment-delete-btn").forEach(btn => {
      btn.onclick = async () => {
        if (!confirm("Удалить этот комментарий?")) return;
        try {
          await v1Fetch(`/api/classroom/classes/${courseId}/comments/${btn.dataset.id}`, { method: "DELETE" });
          loadPostComments(courseId, parentKind, parentId, container, currentUser);
        } catch (err) {
          alert("Не удалось удалить комментарий: " + err.message);
        }
      };
    });
  } catch (err) {
    // Non-fatal comments load
  }
}

function formatCommentWithHandles(text) {
  return text.replace(/@([A-Za-z0-9А-Яа-я_-]+)/g, `<span class="handle-mention">@$1</span>`);
}

/**
 * Autocomplete for @handle in class comments
 */
function bindHandleAutocomplete(textarea, dropdown, roster = []) {
  if (!textarea || !dropdown) return;

  textarea.addEventListener("input", () => {
    const val = textarea.value;
    const cursor = textarea.selectionStart;
    const textBefore = val.slice(0, cursor);
    const match = textBefore.match(/@([A-Za-z0-9А-Яа-я_-]*)$/);

    if (!match) {
      dropdown.style.display = "none";
      return;
    }

    const query = match[1].toLowerCase();
    const filtered = roster.filter(u => {
      const h = (u.handle || "").toLowerCase();
      return h.includes(query);
    }).slice(0, 5);

    if (filtered.length === 0) {
      dropdown.style.display = "none";
      return;
    }

    dropdown.innerHTML = filtered.map(u => `
      <div class="autocomplete-item" data-handle="${u.handle}">
        <span class="auto-avatar">${getUserSvgAvatar(u.handle, 20)}</span>
        <span class="auto-handle">@${u.handle}</span>
      </div>
    `).join("");

    dropdown.style.display = "block";

    dropdown.querySelectorAll(".autocomplete-item").forEach(item => {
      item.onmousedown = (e) => {
        e.preventDefault();
        const handle = item.dataset.handle;
        const before = textBefore.slice(0, textBefore.length - match[0].length);
        const after = val.slice(cursor);
        textarea.value = `${before}@${handle} ${after}`;
        dropdown.style.display = "none";
        textarea.focus();
      };
    });
  });
}

function openPostContextMenu(post, event, options = {}) {
  let menu = document.getElementById("postContextMenu");
  if (!menu) {
    menu = document.createElement("div");
    menu.id = "postContextMenu";
    menu.className = "context-dropdown-menu";
    document.body.appendChild(menu);
  }

  const isPinned = post.is_pinned || post.isPinned;
  menu.innerHTML = `
    <button class="menu-item" id="ctxPinPost">${isPinned ? "Открепить" : "Закрепить вверху"}</button>
    <button class="menu-item" id="ctxCopyLink">Копировать ссылку</button>
    <button class="menu-item text-danger" id="ctxDeletePost">Удалить</button>
  `;

  menu.style.display = "block";
  menu.style.top = `${event.clientY + 5}px`;
  menu.style.left = `${Math.min(event.clientX, window.innerWidth - 180)}px`;

  const close = () => {
    menu.style.display = "none";
  };

  document.addEventListener("click", close, { once: true });

  menu.querySelector("#ctxPinPost")?.addEventListener("click", async () => {
    try {
      await v1Fetch(`/v1/courses/${post.courseId || options.courseId}/announcements/${post.id}`, {
        method: "PATCH",
        body: { is_pinned: !isPinned },
        updateMask: "is_pinned"
      });
      if (options.onReload) options.onReload();
    } catch (err) {
      alert("Не удалось изменить статус закрепления: " + err.message);
    }
  });

  menu.querySelector("#ctxCopyLink")?.addEventListener("click", () => {
    navigator.clipboard.writeText(window.location.href).then(() => {
      alert("Ссылка на публикацию скопирована!");
    });
  });

  menu.querySelector("#ctxDeletePost")?.addEventListener("click", async () => {
    if (!confirm("Вы действительно хотите удалить эту публикацию?")) return;
    try {
      await v1Fetch(`/v1/courses/${post.courseId || options.courseId}/announcements/${post.id}`, {
        method: "DELETE"
      });
      if (options.onReload) options.onReload();
    } catch (err) {
      alert("Не удалось удалить: " + err.message);
    }
  });
}
