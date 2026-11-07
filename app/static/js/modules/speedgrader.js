/**
 * BormoClass SpeedGrader Workspace (Zero-PII, WCAG 2.1 AA)
 * Two-panel grading station:
 *  - Top bar: student switcher, filters, status badges, return/batch-return
 *  - Left panel (70%): PDF/image viewer, Red Pen & coordinate annotations,
 *    code/text viewer, Excalidraw board canvas, Quiz breakdown, Originality drawer
 *  - Right panel (30%): draftGrade, Excused toggle, interactive Rubric grid,
 *    Comment Bank (#hashtags), 1-on-1 private comments, SubmissionHistory modal
 */

import { ICONS, getIcon } from "../icons.js";

export class SpeedGrader {
  constructor(options = {}) {
    this.container = options.container || document.body;
    this.classId = options.classId || null;
    this.courseworkId = options.courseworkId || null;
    this.studentId = options.studentId || null;
    this.onClose = options.onClose || (() => {});

    this.students = [];
    this.currentIndex = 0;
    this.currentFilter = "all"; // 'all' | 'turned_in' | 'graded' | 'missing'
    this.coursework = null;
    this.rubric = null;
    this.currentSubmission = null;
    this.annotations = [];
    this.activeTool = "pointer"; // 'pointer' | 'pen' | 'box'
    this.zoomLevel = 1.0;
    this.commentBank = [];
    this.isOriginalityOpen = false;
    this.activeCriterionLevels = {}; // criterionId -> levelId
  }

  async init() {
    this.renderSkeleton();
    await this.loadData();
    this.bindGlobalKeyboardShortcuts();
  }

  renderSkeleton() {
    let overlay = document.getElementById("speedGraderOverlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "speedGraderOverlay";
      this.container.appendChild(overlay);
    }

    overlay.style.cssText = `
      position: fixed;
      inset: 0;
      background: var(--md-sys-color-surface, #ffffff);
      color: var(--md-sys-color-on-surface, #1f1f1f);
      z-index: 9999;
      display: flex;
      flex-direction: column;
      font-family: var(--font-sans, system-ui, sans-serif);
      overflow: hidden;
    `;

    overlay.innerHTML = `
      <!-- Top Navigation & Control Bar -->
      <header id="sgHeader" style="
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 16px;
        background: var(--md-sys-color-surface-container, #f0f4f9);
        border-bottom: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
        min-height: 56px;
        gap: 12px;
        flex-wrap: wrap;
      ">
        <div style="display: flex; align-items: center; gap: 12px;">
          <button id="sgBtnClose" class="btn btn-icon" title="Закрыть SpeedGrader (Esc)" aria-label="Закрыть" style="
            background: transparent; border: none; font-size: 1.3rem; cursor: pointer; padding: 6px; border-radius: 50%;
          ">✕</button>
          <div>
            <div id="sgCourseworkTitle" style="font-weight: 700; font-size: 1.05rem; line-height: 1.2;">Загрузка задания...</div>
            <div id="sgAssignmentMeta" style="font-size: 0.8rem; color: var(--md-sys-color-on-surface-variant, #444746);">
              Макс. балл: <span id="sgMaxPoints">-</span>
            </div>
          </div>
        </div>

        <!-- Student Switcher and Filter -->
        <div style="display: flex; align-items: center; gap: 8px; flex: 1; max-width: 520px; justify-content: center;">
          <select id="sgFilterSelect" aria-label="Фильтр списка учащихся" style="
            padding: 6px 10px; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
            background: var(--md-sys-color-surface, #ffffff); font-size: 0.85rem; cursor: pointer;
          ">
            <option value="all">Все ученики</option>
            <option value="turned_in">Сдано</option>
            <option value="graded">Оценено</option>
            <option value="missing">Пропущено</option>
          </select>

          <button id="sgBtnPrevStudent" title="Предыдущий ученик ([)" aria-label="Предыдущий ученик" class="btn btn-secondary" style="
            padding: 6px 12px; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
            background: var(--md-sys-color-surface-container-high, #e3e8ef); cursor: pointer;
          ">◀</button>

          <select id="sgStudentSelect" aria-label="Выбор ученика" style="
            padding: 6px 12px; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
            background: var(--md-sys-color-surface, #ffffff); font-weight: 600; font-size: 0.9rem; flex: 1; cursor: pointer;
          ">
            <option>Загрузка учащихся...</option>
          </select>

          <button id="sgBtnNextStudent" title="Следующий ученик (])" aria-label="Следующий ученик" class="btn btn-secondary" style="
            padding: 6px 12px; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
            background: var(--md-sys-color-surface-container-high, #e3e8ef); cursor: pointer;
          ">▶</button>
        </div>

        <!-- Status badge & Actions -->
        <div style="display: flex; align-items: center; gap: 10px;">
          <span id="sgStatusBadge" style="
            padding: 4px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600;
            background: var(--md-sys-color-surface-variant, #e1e2ec); color: var(--md-sys-color-on-surface-variant, #444746);
          ">Черновик</span>

          <button id="sgBtnHistory" title="История сдачи и оценок" class="btn btn-secondary" style="
            padding: 6px 10px; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
            background: transparent; font-size: 0.85rem; cursor: pointer; display: flex; align-items: center; gap: 4px;
          ">
            🕒 История
          </button>

          <!-- Split-Button Return -->
          <div style="display: flex; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <button id="sgBtnReturnSingle" class="btn btn-primary" style="
              padding: 7px 14px; background: var(--md-sys-color-primary, #005ac1); color: #fff;
              border: none; font-weight: 600; font-size: 0.85rem; cursor: pointer;
            ">Вернуть работу</button>
            <button id="sgBtnReturnBatch" title="Вернуть несколько работ" class="btn btn-primary" style="
              padding: 7px 10px; background: var(--md-sys-color-primary, #005ac1); color: #fff;
              border: none; border-left: 1px solid rgba(255,255,255,0.3); font-weight: 600; font-size: 0.85rem; cursor: pointer;
            ">▼</button>
          </div>
        </div>
      </header>

      <!-- Main Two-Panel Split Layout -->
      <div style="display: flex; flex: 1; overflow: hidden; position: relative;">
        <!-- Left Panel: 70% Width Preview & Tools -->
        <main id="sgLeftPanel" style="
          flex: 7;
          display: flex;
          flex-direction: column;
          background: #2b2b2b;
          color: #ffffff;
          overflow: hidden;
          position: relative;
        ">
          <!-- Document / Canvas Toolbar -->
          <div id="sgDocToolbar" style="
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 6px 16px;
            background: #1e1e1e;
            border-bottom: 1px solid #3d3d3d;
            font-size: 0.85rem;
            z-index: 10;
          ">
            <div id="sgFileSelectorGroup" style="display: flex; align-items: center; gap: 8px;">
              <span style="font-weight: 600; color: #bbb;">Материал:</span>
              <select id="sgFileSelect" style="
                background: #333; color: #fff; border: 1px solid #555; padding: 4px 8px; border-radius: 6px; font-size: 0.85rem;
              ">
                <option value="none">Нет вложений</option>
              </select>
            </div>

            <!-- Annotation & Zoom Tools -->
            <div style="display: flex; align-items: center; gap: 8px;">
              <button id="sgToolPointer" class="sg-tool-btn active" title="Курсор" style="
                background: #444; border: 1px solid #666; color: #fff; padding: 4px 8px; border-radius: 4px; cursor: pointer;
              ">👆 Выбор</button>
              <button id="sgToolPen" class="sg-tool-btn" title="Красная ручка" style="
                background: #333; border: 1px solid #555; color: #ff6b6b; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-weight: 700;
              ">🖊 Красная ручка</button>
              <button id="sgToolBox" class="sg-tool-btn" title="Рамочный комментарий" style="
                background: #333; border: 1px solid #555; color: #ffd166; padding: 4px 8px; border-radius: 4px; cursor: pointer;
              ">🔲 Рамка с заметкой</button>
              <span style="color: #666;">|</span>
              <button id="sgBtnZoomOut" title="Уменьшить" style="background:#333;color:#fff;border:1px solid #555;padding:4px 8px;border-radius:4px;cursor:pointer;">−</button>
              <span id="sgZoomVal" style="min-width: 42px; text-align: center;">100%</span>
              <button id="sgBtnZoomIn" title="Увеличить" style="background:#333;color:#fff;border:1px solid #555;padding:4px 8px;border-radius:4px;cursor:pointer;">+</button>
              <button id="sgBtnZoomReset" title="Сбросить зум" style="background:#333;color:#fff;border:1px solid #555;padding:4px 8px;border-radius:4px;cursor:pointer;">Сброс</button>
              <span style="color: #666;">|</span>
              <button id="sgBtnOriginalityToggle" title="Отчёт об уникальности (Антиплагиат)" style="
                background: #004d40; color: #80cbc4; border: 1px solid #00695c; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-weight: 600;
              ">🛡 Антиплагиат <span id="sgOrigBadge">--%</span></button>
            </div>
          </div>

          <!-- Document Canvas Workspace Viewport -->
          <div id="sgViewport" style="
            flex: 1;
            position: relative;
            overflow: auto;
            display: flex;
            justify-content: center;
            align-items: flex-start;
            padding: 24px;
            background: #222222;
          ">
            <div id="sgViewerContainer" style="
              position: relative;
              box-shadow: 0 4px 20px rgba(0,0,0,0.5);
              background: #ffffff;
              min-width: 320px;
              min-height: 480px;
              display: flex;
              align-items: center;
              justify-content: center;
              color: #333;
            ">
              <div id="sgViewerEmpty" style="padding: 40px; text-align: center; color: #888;">
                Загрузка содержимого работы...
              </div>
              <canvas id="sgAnnotationCanvas" style="
                position: absolute;
                inset: 0;
                width: 100%;
                height: 100%;
                pointer-events: none;
                z-index: 5;
              "></canvas>
            </div>
          </div>

          <!-- Slide-out Originality Report Drawer -->
          <div id="sgOriginalityDrawer" style="
            position: absolute;
            top: 45px;
            right: 0;
            bottom: 0;
            width: 380px;
            background: #181c1e;
            color: #e2e2e5;
            border-left: 2px solid #00695c;
            padding: 20px;
            display: none;
            flex-direction: column;
            gap: 14px;
            z-index: 20;
            box-shadow: -4px 0 16px rgba(0,0,0,0.6);
            overflow-y: auto;
          ">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #333; padding-bottom: 8px;">
              <div style="font-weight: 700; font-size: 1.1rem; color: #80cbc4;">Отчёт об уникальности</div>
              <button id="sgBtnCloseOrig" style="background:transparent;border:none;color:#aaa;cursor:pointer;font-size:1.2rem;">✕</button>
            </div>
            <div style="display: flex; align-items: baseline; gap: 8px;">
              <span id="sgOrigPercentVal" style="font-size: 2.2rem; font-weight: 800; color: #4db6ac;">0%</span>
              <span style="color: #aaa; font-size: 0.9rem;">совпадений в открытых источниках</span>
            </div>
            <div id="sgOrigSourcesList" style="font-size: 0.85rem; line-height: 1.4; display: flex; flex-direction: column; gap: 8px;">
              <div style="color: #888;">Анализ проведён по локальной базе и депонированным работам.</div>
            </div>
          </div>
        </main>

        <!-- Right Panel: 30% Width Inspector -->
        <aside id="sgRightPanel" style="
          flex: 3;
          min-width: 320px;
          max-width: 440px;
          background: var(--md-sys-color-surface, #ffffff);
          border-left: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
          display: flex;
          flex-direction: column;
          overflow-y: auto;
          padding: 16px;
          gap: 16px;
        ">
          <!-- Grade input and Excused toggle section -->
          <div style="
            background: var(--md-sys-color-surface-container-low, #f7f9fc);
            border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
            border-radius: 12px;
            padding: 14px;
            display: flex;
            flex-direction: column;
            gap: 10px;
          ">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <label for="sgDraftGradeInput" style="font-weight: 700; font-size: 0.95rem;">Оценка (Черновик)</label>
              <label style="display: flex; align-items: center; gap: 6px; font-size: 0.85rem; cursor: pointer;">
                <input type="checkbox" id="sgExcusedCheckbox" style="cursor: pointer;">
                <span>Освобождён (Excused)</span>
              </label>
            </div>

            <div style="display: flex; align-items: center; gap: 8px;">
              <input type="number" id="sgDraftGradeInput" min="0" step="0.5" placeholder="0" style="
                width: 90px; padding: 8px 12px; font-size: 1.25rem; font-weight: 700; text-align: center;
                border-radius: 8px; border: 2px solid var(--md-sys-color-primary, #005ac1);
                background: var(--md-sys-color-surface, #ffffff);
              ">
              <span style="font-size: 1.2rem; font-weight: 600; color: var(--md-sys-color-on-surface-variant, #444746);">
                / <span id="sgMaxPointsDisplay">100</span>
              </span>

              <!-- Quick Russian 5-point scale buttons -->
              <div style="display: flex; gap: 4px; margin-left: auto;">
                <button class="sg-quick-grade-btn" data-pts="5" title="Отлично (5)">5</button>
                <button class="sg-quick-grade-btn" data-pts="4" title="Хорошо (4)">4</button>
                <button class="sg-quick-grade-btn" data-pts="3" title="Удовл. (3)">3</button>
                <button class="sg-quick-grade-btn" data-pts="2" title="Неуд. (2)">2</button>
              </div>
            </div>
            <div style="font-size: 0.78rem; color: var(--md-sys-color-outline, #747775);">
              Черновая оценка видна только учителю до нажатия «Вернуть».
            </div>
          </div>

          <!-- Interactive Rubric Grid Section -->
          <div id="sgRubricSection" style="
            background: var(--md-sys-color-surface-container-low, #f7f9fc);
            border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
            border-radius: 12px;
            padding: 14px;
            display: flex;
            flex-direction: column;
            gap: 10px;
          ">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-weight: 700; font-size: 0.95rem;">Рубрика оценивания</span>
              <span id="sgRubricScoreSummary" style="font-size: 0.85rem; font-weight: 600; color: var(--md-sys-color-primary, #005ac1);">0 б.</span>
            </div>
            <div id="sgRubricCriteriaContainer" style="display: flex; flex-direction: column; gap: 12px;">
              <div style="font-size: 0.85rem; color: #888;">К заданию не прикреплена рубрика.</div>
            </div>
          </div>

          <!-- Comment Bank with #hashtag Search -->
          <div style="
            background: var(--md-sys-color-surface-container-low, #f7f9fc);
            border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
            border-radius: 12px;
            padding: 14px;
            display: flex;
            flex-direction: column;
            gap: 8px;
          ">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-weight: 700; font-size: 0.9rem;">Банк комментариев</span>
              <button id="sgBtnAddCommentBank" title="Добавить частый комментарий" style="
                border: none; background: transparent; color: var(--md-sys-color-primary, #005ac1); font-weight: 600; cursor: pointer; font-size: 0.8rem;
              ">+ Сохранить</button>
            </div>
            <input type="text" id="sgBankSearchInput" placeholder="Поиск по #хештегу (например, #отлично)..." style="
              padding: 6px 10px; border-radius: 6px; border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
              font-size: 0.85rem; background: var(--md-sys-color-surface, #ffffff);
            ">
            <div id="sgCommentChipsContainer" style="display: flex; flex-wrap: wrap; gap: 6px; max-height: 80px; overflow-y: auto;">
              <!-- Comment chips inserted dynamically -->
            </div>
          </div>

          <!-- Private Comments 1-on-1 Section -->
          <div style="
            flex: 1;
            display: flex;
            flex-direction: column;
            background: var(--md-sys-color-surface-container-low, #f7f9fc);
            border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
            border-radius: 12px;
            padding: 14px;
            gap: 10px;
            min-height: 200px;
          ">
            <div style="font-weight: 700; font-size: 0.9rem;">Личные комментарии (1-на-1)</div>
            <div id="sgPrivateCommentsList" style="
              flex: 1;
              overflow-y: auto;
              display: flex;
              flex-direction: column;
              gap: 8px;
              max-height: 220px;
              padding-right: 4px;
            ">
              <div style="font-size: 0.82rem; color: #888; text-align: center; margin-top: 20px;">Нет комментариев</div>
            </div>

            <div style="display: flex; flex-direction: column; gap: 6px;">
              <textarea id="sgCommentInput" rows="2" placeholder="Напишите личный комментарий ученику..." style="
                width: 100%; box-sizing: border-box; padding: 8px; border-radius: 8px;
                border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
                font-family: inherit; font-size: 0.85rem; resize: none; background: var(--md-sys-color-surface, #ffffff);
              "></textarea>
              <button id="sgBtnSendComment" class="btn btn-secondary" style="
                align-self: flex-end; padding: 5px 14px; border-radius: 6px; font-weight: 600; font-size: 0.82rem;
                background: var(--md-sys-color-secondary-container, #dbe4f0); border: none; cursor: pointer;
              ">Отправить</button>
            </div>
          </div>
        </aside>
      </div>

      <!-- Submission History Modal -->
      <div id="sgHistoryModal" style="
        position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 10000;
        display: none; align-items: center; justify-content: center;
      ">
        <div style="
          background: var(--md-sys-color-surface, #ffffff); width: 480px; max-width: 90vw;
          border-radius: 16px; padding: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.3);
          display: flex; flex-direction: column; gap: 14px; max-height: 80vh;
        ">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <h3 style="margin: 0; font-size: 1.15rem;">История сдачи и оценок</h3>
            <button id="sgBtnCloseHistory" style="background:transparent;border:none;font-size:1.2rem;cursor:pointer;">✕</button>
          </div>
          <div id="sgHistoryTimeline" style="flex:1; overflow-y:auto; display:flex; flex-direction:column; gap:12px; padding: 4px;">
            <div style="color: #888;">Загрузка истории...</div>
          </div>
        </div>
      </div>
    `;

    this.bindSkeletonEvents();
  }

  bindSkeletonEvents() {
    const closeBtn = document.getElementById("sgBtnClose");
    if (closeBtn) closeBtn.onclick = () => this.destroy();

    const filterSelect = document.getElementById("sgFilterSelect");
    if (filterSelect) {
      filterSelect.onchange = (e) => {
        this.currentFilter = e.target.value;
        this.updateStudentDropdown();
      };
    }

    const prevBtn = document.getElementById("sgBtnPrevStudent");
    if (prevBtn) prevBtn.onclick = () => this.goToPrevStudent();

    const nextBtn = document.getElementById("sgBtnNextStudent");
    if (nextBtn) nextBtn.onclick = () => this.goToNextStudent();

    const studentSelect = document.getElementById("sgStudentSelect");
    if (studentSelect) {
      studentSelect.onchange = (e) => {
        const idx = this.filteredStudents.findIndex((s) => String(s.student_id) === String(e.target.value));
        if (idx !== -1) {
          this.currentIndex = idx;
          this.loadStudentSubmission();
        }
      };
    }

    // Zoom buttons
    const btnZoomIn = document.getElementById("sgBtnZoomIn");
    if (btnZoomIn) btnZoomIn.onclick = () => this.setZoom(this.zoomLevel + 0.15);
    const btnZoomOut = document.getElementById("sgBtnZoomOut");
    if (btnZoomOut) btnZoomOut.onclick = () => this.setZoom(this.zoomLevel - 0.15);
    const btnZoomReset = document.getElementById("sgBtnZoomReset");
    if (btnZoomReset) btnZoomReset.onclick = () => this.setZoom(1.0);

    // Tools
    const toolPointer = document.getElementById("sgToolPointer");
    const toolPen = document.getElementById("sgToolPen");
    const toolBox = document.getElementById("sgToolBox");
    const setTool = (tool, activeEl) => {
      this.activeTool = tool;
      [toolPointer, toolPen, toolBox].forEach((b) => b && b.classList.remove("active"));
      if (activeEl) activeEl.classList.add("active");
      this.setupToolCanvas();
    };
    if (toolPointer) toolPointer.onclick = () => setTool("pointer", toolPointer);
    if (toolPen) toolPen.onclick = () => setTool("pen", toolPen);
    if (toolBox) toolBox.onclick = () => setTool("box", toolBox);

    // Originality drawer toggle
    const btnOrig = document.getElementById("sgBtnOriginalityToggle");
    const btnCloseOrig = document.getElementById("sgBtnCloseOrig");
    const drawerOrig = document.getElementById("sgOriginalityDrawer");
    if (btnOrig) {
      btnOrig.onclick = () => {
        this.isOriginalityOpen = !this.isOriginalityOpen;
        if (drawerOrig) drawerOrig.style.display = this.isOriginalityOpen ? "flex" : "none";
      };
    }
    if (btnCloseOrig && drawerOrig) {
      btnCloseOrig.onclick = () => {
        this.isOriginalityOpen = false;
        drawerOrig.style.display = "none";
      };
    }

    // Quick Grade buttons
    document.querySelectorAll(".sg-quick-grade-btn").forEach((btn) => {
      btn.onclick = () => {
        const val = Number(btn.dataset.pts);
        const input = document.getElementById("sgDraftGradeInput");
        if (input) {
          input.value = val;
          this.saveDraftGrade(val);
        }
      };
    });

    const gradeInput = document.getElementById("sgDraftGradeInput");
    if (gradeInput) {
      gradeInput.onchange = (e) => {
        this.saveDraftGrade(Number(e.target.value));
      };
    }

    const excCheck = document.getElementById("sgExcusedCheckbox");
    if (excCheck) {
      excCheck.onchange = (e) => {
        this.toggleExcused(e.target.checked);
      };
    }

    // Single return
    const btnReturnSingle = document.getElementById("sgBtnReturnSingle");
    if (btnReturnSingle) {
      btnReturnSingle.onclick = () => this.returnCurrentSubmission();
    }

    // Batch return
    const btnReturnBatch = document.getElementById("sgBtnReturnBatch");
    if (btnReturnBatch) {
      btnReturnBatch.onclick = () => this.openBatchReturnDialog();
    }

    // History modal
    const btnHistory = document.getElementById("sgBtnHistory");
    const histModal = document.getElementById("sgHistoryModal");
    const btnCloseHist = document.getElementById("sgBtnCloseHistory");
    if (btnHistory && histModal) {
      btnHistory.onclick = () => {
        histModal.style.display = "flex";
        this.loadSubmissionHistory();
      };
    }
    if (btnCloseHist && histModal) {
      btnCloseHist.onclick = () => {
        histModal.style.display = "none";
      };
    }

    // Comment Bank search
    const bankInput = document.getElementById("sgBankSearchInput");
    if (bankInput) {
      bankInput.oninput = (e) => this.filterCommentBank(e.target.value);
    }

    const btnAddBank = document.getElementById("sgBtnAddCommentBank");
    if (btnAddBank) {
      btnAddBank.onclick = () => this.saveToCommentBank();
    }

    // Send comment
    const btnSend = document.getElementById("sgBtnSendComment");
    if (btnSend) {
      btnSend.onclick = () => this.sendPrivateComment();
    }
  }

  setZoom(val) {
    this.zoomLevel = Math.max(0.4, Math.min(3.0, val));
    const lbl = document.getElementById("sgZoomVal");
    if (lbl) lbl.textContent = `${Math.round(this.zoomLevel * 100)}%`;
    const container = document.getElementById("sgViewerContainer");
    if (container) {
      container.style.transform = `scale(${this.zoomLevel})`;
      container.style.transformOrigin = "top center";
    }
  }

  bindGlobalKeyboardShortcuts() {
    this._keyHandler = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") {
        return;
      }
      if (e.key === "Escape") {
        const histModal = document.getElementById("sgHistoryModal");
        if (histModal && histModal.style.display === "flex") {
          histModal.style.display = "none";
          return;
        }
        this.destroy();
      } else if (e.key === "[" || e.key === "ArrowLeft") {
        this.goToPrevStudent();
      } else if (e.key === "]" || e.key === "ArrowRight") {
        this.goToNextStudent();
      }
    };
    window.addEventListener("keydown", this._keyHandler);
  }

  async loadData() {
    try {
      // 1. Load coursework info
      const cwRes = await fetch(`/api/classroom/coursework/${this.courseworkId}`);
      if (cwRes.ok) {
        this.coursework = await cwRes.json();
        document.getElementById("sgCourseworkTitle").textContent = this.coursework.title || "Задание";
        const maxPts = this.coursework.max_points || 100;
        document.getElementById("sgMaxPoints").textContent = maxPts;
        document.getElementById("sgMaxPointsDisplay").textContent = maxPts;
      }

      // 2. Load rubric if any
      const rubRes = await fetch(`/v1/courses/${this.classId}/courseWork/${this.courseworkId}/rubrics`);
      if (rubRes.ok) {
        const rubData = await rubRes.json();
        if (rubData.rubrics && rubData.rubrics.length > 0) {
          this.rubric = rubData.rubrics[0];
          this.renderRubric(this.rubric);
        }
      }

      // 3. Load submissions list for coursework
      const subRes = await fetch(`/api/classroom/coursework/${this.courseworkId}/submissions`);
      if (subRes.ok) {
        this.students = await subRes.json();
        this.updateStudentDropdown();
        if (this.studentId) {
          const idx = this.filteredStudents.findIndex((s) => String(s.student_id) === String(this.studentId));
          if (idx !== -1) this.currentIndex = idx;
        }
        await this.loadStudentSubmission();
      }

      // 4. Load comment bank
      await this.loadCommentBank();
    } catch (err) {
      console.error("Failed to load SpeedGrader data", err);
    }
  }

  get filteredStudents() {
    if (this.currentFilter === "all") return this.students;
    if (this.currentFilter === "turned_in") return this.students.filter((s) => s.status === "turned_in");
    if (this.currentFilter === "graded") return this.students.filter((s) => s.status === "returned" || s.grade_points !== null);
    if (this.currentFilter === "missing") return this.students.filter((s) => s.status === "assigned" || !s.status);
    return this.students;
  }

  updateStudentDropdown() {
    const select = document.getElementById("sgStudentSelect");
    if (!select) return;

    const list = this.filteredStudents;
    select.innerHTML = "";
    if (list.length === 0) {
      select.innerHTML = `<option value="">Нет учащихся для фильтра</option>`;
      return;
    }

    list.forEach((st, idx) => {
      const opt = document.createElement("option");
      opt.value = st.student_id;
      const statusIcon = st.status === "turned_in" ? "✅ " : st.status === "returned" ? "⭐ " : "";
      opt.textContent = `${statusIcon}Парта №${st.seat_number || "-"}: ${st.handle || "Ученик"}`;
      select.appendChild(opt);
    });

    if (this.currentIndex >= list.length) this.currentIndex = 0;
    if (list[this.currentIndex]) {
      select.value = list[this.currentIndex].student_id;
    }
  }

  goToNextStudent() {
    const list = this.filteredStudents;
    if (list.length <= 1) return;
    this.currentIndex = (this.currentIndex + 1) % list.length;
    document.getElementById("sgStudentSelect").value = list[this.currentIndex].student_id;
    this.loadStudentSubmission();
  }

  goToPrevStudent() {
    const list = this.filteredStudents;
    if (list.length <= 1) return;
    this.currentIndex = (this.currentIndex - 1 + list.length) % list.length;
    document.getElementById("sgStudentSelect").value = list[this.currentIndex].student_id;
    this.loadStudentSubmission();
  }

  async loadStudentSubmission() {
    const list = this.filteredStudents;
    if (!list || list.length === 0 || !list[this.currentIndex]) return;
    const st = list[this.currentIndex];
    this.studentId = st.student_id;

    // Update status badge
    const badge = document.getElementById("sgStatusBadge");
    if (badge) {
      if (st.status === "turned_in") {
        badge.textContent = st.is_late ? "Сдано с опозданием" : "Сдано";
        badge.style.background = st.is_late ? "#fff3e0" : "#e8f5e9";
        badge.style.color = st.is_late ? "#e65100" : "#2e7d32";
      } else if (st.status === "returned") {
        badge.textContent = "Возвращено (Оценено)";
        badge.style.background = "#e3f2fd";
        badge.style.color = "#1565c0";
      } else {
        badge.textContent = "Не сдано";
        badge.style.background = "#fce4ec";
        badge.style.color = "#c2185b";
      }
    }

    // Set grade inputs
    const gradeInput = document.getElementById("sgDraftGradeInput");
    if (gradeInput) {
      gradeInput.value = st.draft_grade ?? st.assigned_grade ?? st.grade_points ?? "";
    }
    const excCheck = document.getElementById("sgExcusedCheckbox");
    if (excCheck) {
      excCheck.checked = Boolean(st.is_excused);
    }

    // Load submission detail
    this.currentSubmission = st;
    await this.renderSubmissionPreview(st);
    await this.loadPrivateComments();
  }

  async renderSubmissionPreview(st) {
    const container = document.getElementById("sgViewerContainer");
    if (!container) return;

    let payload = {};
    try {
      payload = typeof st.payload_json === "string" ? JSON.parse(st.payload_json) : (st.payload_json || {});
    } catch {
      payload = { text: st.payload_json };
    }

    // Check for files or text answers
    const fileSelect = document.getElementById("sgFileSelect");
    fileSelect.innerHTML = "";

    const items = [];
    if (payload.files && Array.isArray(payload.files)) {
      payload.files.forEach((f, i) => items.push({ type: "file", title: f.title || `Файл ${i + 1}`, data: f }));
    }
    if (payload.text) {
      items.push({ type: "text", title: "Текстовый ответ", data: payload.text });
    }
    if (payload.quiz_answers) {
      items.push({ type: "quiz", title: "Ответы Quiz / Тест", data: payload.quiz_answers });
    }
    if (payload.board_id || (payload.files && payload.files.some((f) => f.title && f.title.endsWith(".excalidraw")))) {
      items.push({ type: "board", title: "Персональная доска Excalidraw", data: payload });
    }

    if (items.length === 0) {
      fileSelect.innerHTML = `<option value="none">Нет материалов для проверки</option>`;
      container.innerHTML = `
        <div style="padding: 40px; text-align: center; color: #888;">
          Ученик еще не прикрепил файлы или ответы к этому заданию.
        </div>
      `;
      return;
    }

    items.forEach((item, idx) => {
      const opt = document.createElement("option");
      opt.value = idx;
      opt.textContent = `${item.title} (${item.type})`;
      fileSelect.appendChild(opt);
    });

    fileSelect.onchange = (e) => {
      const selectedItem = items[Number(e.target.value)];
      this.displayItem(selectedItem);
    };

    // Display first item
    this.displayItem(items[0]);
  }

  displayItem(item) {
    const container = document.getElementById("sgViewerContainer");
    if (!container) return;

    if (item.type === "text") {
      container.innerHTML = `
        <div style="padding: 24px; width: 100%; box-sizing: border-box; font-family: var(--font-mono, monospace); white-space: pre-wrap; line-height: 1.6; color: #111;">
          ${this.escapeHtml(item.data)}
        </div>
        <canvas id="sgAnnotationCanvas" style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:5;"></canvas>
      `;
    } else if (item.type === "quiz") {
      const answers = item.data;
      container.innerHTML = `
        <div style="padding: 24px; width: 100%; box-sizing: border-box; color: #111;">
          <h3 style="margin-top:0;">Разбор ответов теста</h3>
          <div style="display: flex; flex-direction: column; gap: 12px;">
            ${Object.entries(answers).map(([qKey, val]) => `
              <div style="background:#f9f9f9; border:1px solid #ddd; border-radius:8px; padding:12px;">
                <div style="font-weight:600;">Вопрос: ${this.escapeHtml(qKey)}</div>
                <div style="color: #005ac1; margin-top:4px;">Ответ ученика: <strong>${this.escapeHtml(String(val))}</strong></div>
              </div>
            `).join("")}
          </div>
        </div>
      `;
    } else if (item.type === "board") {
      const boardUrl = `/board/${this.classId}?embed=1&readOnly=1`;
      container.innerHTML = `
        <iframe src="${boardUrl}" style="width: 100%; height: 600px; border: none; background: #ffffff;"></iframe>
      `;
    } else if (item.type === "file") {
      const f = item.data;
      const fileUrl = f.alternateLink || `/api/storage/files/${f.id || f.file_id}`;
      if (f.mimeType && f.mimeType.startsWith("image/")) {
        container.innerHTML = `
          <div style="position:relative; display:inline-block;">
            <img id="sgPreviewImg" src="${fileUrl}" alt="Скан тетради" style="max-width: 100%; display: block; border-radius: 4px;">
            <canvas id="sgAnnotationCanvas" style="position:absolute;inset:0;width:100%;height:100%;z-index:5;"></canvas>
          </div>
        `;
        const img = document.getElementById("sgPreviewImg");
        if (img) img.onload = () => this.setupToolCanvas();
      } else {
        container.innerHTML = `
          <div style="padding: 40px; text-align: center; color: #333;">
            <div style="font-size: 2.5rem; margin-bottom: 12px;">📄</div>
            <div style="font-weight: 700; font-size: 1.1rem;">${this.escapeHtml(f.title || "Документ")}</div>
            <div style="margin-top: 12px;">
              <a href="${fileUrl}" target="_blank" rel="noopener" class="btn btn-primary" style="
                display: inline-block; padding: 8px 16px; background: #005ac1; color: #fff; text-decoration: none; border-radius: 8px; font-weight: 600;
              ">Открыть документ</a>
            </div>
          </div>
        `;
      }
    }

    this.setupToolCanvas();
    this.updateOriginalityReport();
  }

  setupToolCanvas() {
    const canvas = document.getElementById("sgAnnotationCanvas");
    if (!canvas) return;

    const parent = canvas.parentElement;
    canvas.width = parent.clientWidth || 800;
    canvas.height = parent.clientHeight || 600;
    const ctx = canvas.getContext("2d");

    if (this.activeTool === "pointer") {
      canvas.style.pointerEvents = "none";
      return;
    }

    canvas.style.pointerEvents = "auto";
    canvas.style.cursor = this.activeTool === "pen" ? "crosshair" : "cell";

    let isDrawing = false;
    let startX = 0;
    let startY = 0;
    let currentStroke = [];

    canvas.onmousedown = (e) => {
      isDrawing = true;
      const rect = canvas.getBoundingClientRect();
      startX = e.clientX - rect.left;
      startY = e.clientY - rect.top;

      if (this.activeTool === "pen") {
        currentStroke = [[startX, startY]];
        ctx.strokeStyle = "#e53935";
        ctx.lineWidth = 3;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(startX, startY);
      }
    };

    canvas.onmousemove = (e) => {
      if (!isDrawing) return;
      const rect = canvas.getBoundingClientRect();
      const curX = e.clientX - rect.left;
      const curY = e.clientY - rect.top;

      if (this.activeTool === "pen") {
        currentStroke.push([curX, curY]);
        ctx.lineTo(curX, curY);
        ctx.stroke();
      } else if (this.activeTool === "box") {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        this.redrawAnnotations(ctx);
        ctx.strokeStyle = "#ffd166";
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 6]);
        ctx.strokeRect(startX, startY, curX - startX, curY - startY);
        ctx.setLineDash([]);
      }
    };

    canvas.onmouseup = async (e) => {
      if (!isDrawing) return;
      isDrawing = false;
      const rect = canvas.getBoundingClientRect();
      const endX = e.clientX - rect.left;
      const endY = e.clientY - rect.top;

      if (this.activeTool === "pen") {
        this.annotations.push({
          type: "pen",
          stroke: currentStroke,
          color: "#e53935"
        });
      } else if (this.activeTool === "box") {
        const width = endX - startX;
        const height = endY - startY;
        if (Math.abs(width) > 10 && Math.abs(height) > 10) {
          const noteText = prompt("Текст заметки к выделенной области:") || "";
          this.annotations.push({
            type: "box",
            rect: { x: Math.min(startX, endX), y: Math.min(startY, endY), width: Math.abs(width), height: Math.abs(height) },
            text: noteText
          });
        }
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        this.redrawAnnotations(ctx);
      }
    };
  }

  redrawAnnotations(ctx) {
    for (const ann of this.annotations) {
      if (ann.type === "pen" && ann.stroke) {
        ctx.strokeStyle = ann.color || "#e53935";
        ctx.lineWidth = 3;
        ctx.lineCap = "round";
        ctx.beginPath();
        ann.stroke.forEach(([x, y], idx) => {
          if (idx === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.stroke();
      } else if (ann.type === "box" && ann.rect) {
        ctx.strokeStyle = "#ffd166";
        ctx.lineWidth = 2;
        ctx.strokeRect(ann.rect.x, ann.rect.y, ann.rect.width, ann.rect.height);
        if (ann.text) {
          ctx.fillStyle = "rgba(255, 209, 102, 0.85)";
          ctx.fillRect(ann.rect.x, ann.rect.y - 20, Math.max(80, ann.text.length * 8), 20);
          ctx.fillStyle = "#111";
          ctx.font = "12px sans-serif";
          ctx.fillText(ann.text, ann.rect.x + 4, ann.rect.y - 6);
        }
      }
    }
  }

  renderRubric(rubric) {
    const container = document.getElementById("sgRubricCriteriaContainer");
    if (!container || !rubric) return;

    let criteria = [];
    try {
      criteria = typeof rubric.criteria_json === "string" ? JSON.parse(rubric.criteria_json) : (rubric.criteria_json || rubric.criteria || []);
    } catch {
      criteria = [];
    }

    if (criteria.length === 0) {
      container.innerHTML = `<div style="font-size: 0.85rem; color: #888;">Рубрика без критериев.</div>`;
      return;
    }

    container.innerHTML = "";
    criteria.forEach((crit) => {
      const critBox = document.createElement("div");
      critBox.style.cssText = `
        border-bottom: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
        padding-bottom: 10px;
      `;
      critBox.innerHTML = `
        <div style="font-weight: 600; font-size: 0.88rem; display: flex; justify-content: space-between;">
          <span>${this.escapeHtml(crit.title || "Критерий")}</span>
          <span id="sgCritScore_${crit.id}" style="color: var(--md-sys-color-primary, #005ac1);">0 б.</span>
        </div>
        <div style="font-size: 0.78rem; color: #666; margin-bottom: 6px;">${this.escapeHtml(crit.description || "")}</div>
        <div style="display: flex; gap: 6px; overflow-x: auto; padding: 4px 0;">
          ${(crit.levels || []).map((lvl) => `
            <button class="sg-rubric-lvl-btn" data-cid="${crit.id}" data-lid="${lvl.id}" data-pts="${lvl.points || 0}" style="
              flex: 1; min-width: 70px; padding: 6px 8px; border-radius: 6px;
              border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
              background: var(--md-sys-color-surface, #ffffff); font-size: 0.78rem; cursor: pointer; text-align: center;
            ">
              <div style="font-weight: 700;">${lvl.points || 0} б.</div>
              <div style="font-size: 0.72rem; color: #555;">${this.escapeHtml(lvl.title || "")}</div>
            </button>
          `).join("")}
        </div>
      `;
      container.appendChild(critBox);
    });

    container.querySelectorAll(".sg-rubric-lvl-btn").forEach((btn) => {
      btn.onclick = () => {
        const cid = btn.dataset.cid;
        const lid = btn.dataset.lid;
        const pts = Number(btn.dataset.pts);

        container.querySelectorAll(`.sg-rubric-lvl-btn[data-cid="${cid}"]`).forEach((b) => {
          b.style.borderColor = "var(--md-sys-color-outline-variant, #c4c7c5)";
          b.style.background = "var(--md-sys-color-surface, #ffffff)";
        });

        btn.style.borderColor = "var(--md-sys-color-primary, #005ac1)";
        btn.style.background = "var(--md-sys-color-secondary-container, #dbe4f0)";

        this.activeCriterionLevels[cid] = { levelId: lid, points: pts };
        const scoreSpan = document.getElementById(`sgCritScore_${cid}`);
        if (scoreSpan) scoreSpan.textContent = `${pts} б.`;

        // Recalculate total rubric points
        let total = 0;
        for (const c in this.activeCriterionLevels) {
          total += Number(this.activeCriterionLevels[c].points || 0);
        }
        document.getElementById("sgRubricScoreSummary").textContent = `${total} б.`;
        const gradeInput = document.getElementById("sgDraftGradeInput");
        if (gradeInput) {
          gradeInput.value = total;
          this.saveDraftGrade(total);
        }
      };
    });
  }

  async saveDraftGrade(points) {
    if (!this.studentId || !this.courseworkId) return;
    try {
      await fetch(`/coursework/${this.courseworkId}/submissions/${this.studentId}/grade-rubric`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          criteria_scores: this.activeCriterionLevels,
          teacher_comment: document.getElementById("sgCommentInput")?.value || "",
        }),
      });
    } catch (e) {
      console.warn("Failed to save draft rubric grade", e);
    }
  }

  async toggleExcused(isExcused) {
    if (!this.studentId || !this.courseworkId) return;
    try {
      await fetch(`/coursework/${this.courseworkId}/submissions/${this.studentId}/excuse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_excused: isExcused }),
      });
    } catch (e) {
      console.warn("Failed to excuse submission", e);
    }
  }

  async returnCurrentSubmission() {
    if (!this.studentId || !this.courseworkId) return;
    const grade = document.getElementById("sgDraftGradeInput")?.value;
    const comment = document.getElementById("sgCommentInput")?.value || "";

    try {
      const res = await fetch(`/api/classroom/submissions/${this.courseworkId}/${this.studentId}/grade`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          grade_points: grade ? Number(grade) : null,
          teacher_comment: comment,
        }),
      });

      if (res.ok) {
        alert("Работа успешно проверена и возвращена ученику!");
        const badge = document.getElementById("sgStatusBadge");
        if (badge) {
          badge.textContent = "Возвращено (Оценено)";
          badge.style.background = "#e3f2fd";
          badge.style.color = "#1565c0";
        }
      }
    } catch (err) {
      alert("Ошибка при возврате работы");
    }
  }

  openBatchReturnDialog() {
    const subsWithDraft = this.students.filter((s) => s.draft_grade !== null || s.grade_points !== null);
    const count = subsWithDraft.length;
    if (count === 0) {
      alert("Нет черновиков оценок для массового возврата.");
      return;
    }

    if (confirm(`Вернуть работы всем ${count} учащимся с черновиками оценок?`)) {
      fetch(`/api/classroom/classes/${this.classId}/coursework/${this.courseworkId}/batch-return`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comment: "Массовый возврат работ" }),
      }).then((res) => {
        if (res.ok) alert(`Успешно возвращено ${count} работ!`);
        else alert("Ошибка массового возврата");
      });
    }
  }

  async loadCommentBank() {
    try {
      const res = await fetch(`/api/classroom/comment-bank`);
      if (res.ok) {
        this.commentBank = await res.json();
        this.renderCommentChips(this.commentBank);
      }
    } catch (e) {
      // Fallback local tags
      this.commentBank = [
        { comment_text: "#отлично Замечательное и чистое решение!" },
        { comment_text: "#источники Укажите первоисточник данных." },
        { comment_text: "#оформление Соблюдайте правила форматирования." },
        { comment_text: "#пересдать Требуется доработать задание." },
      ];
      this.renderCommentChips(this.commentBank);
    }
  }

  renderCommentChips(items) {
    const container = document.getElementById("sgCommentChipsContainer");
    if (!container) return;
    container.innerHTML = "";
    items.forEach((item) => {
      const chip = document.createElement("button");
      chip.className = "sg-comment-chip";
      chip.style.cssText = `
        background: var(--md-sys-color-surface-container-high, #e3e8ef);
        border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
        border-radius: 14px; padding: 4px 10px; font-size: 0.75rem; cursor: pointer; color: #1f1f1f;
      `;
      chip.textContent = item.comment_text;
      chip.onclick = () => {
        const area = document.getElementById("sgCommentInput");
        if (area) {
          area.value = (area.value ? area.value + " " : "") + item.comment_text;
        }
      };
      container.appendChild(chip);
    });
  }

  filterCommentBank(query) {
    if (!query) {
      this.renderCommentChips(this.commentBank);
      return;
    }
    const q = query.toLowerCase();
    const filtered = this.commentBank.filter((it) => it.comment_text.toLowerCase().includes(q));
    this.renderCommentChips(filtered);
  }

  async saveToCommentBank() {
    const text = document.getElementById("sgCommentInput")?.value.trim();
    if (!text) {
      alert("Введите текст в поле личного комментария, чтобы сохранить его в Банк");
      return;
    }
    try {
      const res = await fetch("/api/classroom/comment-bank", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comment_text: text }),
      });
      if (res.ok) {
        await this.loadCommentBank();
      }
    } catch (e) {
      console.warn("Error saving comment to bank", e);
    }
  }

  async loadPrivateComments() {
    const list = document.getElementById("sgPrivateCommentsList");
    if (!list || !this.studentId || !this.courseworkId) return;

    try {
      const res = await fetch(`/api/classroom/coursework/${this.courseworkId}/submissions/${this.studentId}/private-comments`);
      if (res.ok) {
        const comments = await res.json();
        if (comments.length === 0) {
          list.innerHTML = `<div style="font-size: 0.82rem; color: #888; text-align: center; margin-top: 20px;">Нет комментариев</div>`;
          return;
        }
        list.innerHTML = comments.map((c) => `
          <div style="background: var(--md-sys-color-surface, #ffffff); border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5); border-radius: 8px; padding: 8px;">
            <div style="display: flex; justify-content: space-between; font-size: 0.78rem; color: #666; margin-bottom: 2px;">
              <strong>${this.escapeHtml(c.author_handle || "Пользователь")}</strong>
              <span>${new Date((c.created_at || Date.now() / 1000) * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
            </div>
            <div style="font-size: 0.85rem; line-height: 1.4;">${this.escapeHtml(c.body_text)}</div>
          </div>
        `).join("");
        list.scrollTop = list.scrollHeight;
      }
    } catch (e) {
      console.warn("Failed to load private comments", e);
    }
  }

  async sendPrivateComment() {
    const area = document.getElementById("sgCommentInput");
    if (!area || !area.value.trim() || !this.studentId || !this.courseworkId) return;
    const body = area.value.trim();

    try {
      const res = await fetch(`/api/classroom/coursework/${this.courseworkId}/submissions/${this.studentId}/private-comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body_text: body }),
      });
      if (res.ok) {
        area.value = "";
        await this.loadPrivateComments();
      }
    } catch (e) {
      console.warn("Failed to send private comment", e);
    }
  }

  async loadSubmissionHistory() {
    const container = document.getElementById("sgHistoryTimeline");
    if (!container || !this.studentId || !this.courseworkId) return;

    try {
      const res = await fetch(`/v1/courses/${this.classId}/courseWork/${this.courseworkId}/studentSubmissions/${this.studentId}`);
      if (res.ok) {
        const sub = await res.json();
        const history = sub.submissionHistory || [];
        if (history.length === 0) {
          container.innerHTML = `<div style="color: #888; text-align: center;">История операций пуста.</div>`;
          return;
        }
        container.innerHTML = history.map((item) => {
          if (item.stateHistory) {
            const sh = item.stateHistory;
            return `
              <div style="border-left: 3px solid #005ac1; padding-left: 10px; margin-bottom: 8px;">
                <div style="font-weight: 600; font-size: 0.9rem;">Изменение статуса: ${this.escapeHtml(sh.state)}</div>
                <div style="font-size: 0.78rem; color: #777;">${sh.stateTimestamp || ""}</div>
              </div>
            `;
          } else if (item.gradeHistory) {
            const gh = item.gradeHistory;
            return `
              <div style="border-left: 3px solid #2e7d32; padding-left: 10px; margin-bottom: 8px;">
                <div style="font-weight: 600; font-size: 0.9rem;">Балл: ${gh.pointsEarned} / ${gh.maxPoints} (${this.escapeHtml(gh.gradeChangeType || "")})</div>
                <div style="font-size: 0.78rem; color: #777;">${gh.gradeTimestamp || ""}</div>
              </div>
            `;
          }
          return "";
        }).join("");
      }
    } catch (e) {
      container.innerHTML = `<div style="color: #d32f2f;">Не удалось загрузить историю.</div>`;
    }
  }

  updateOriginalityReport() {
    const badge = document.getElementById("sgOrigBadge");
    const val = document.getElementById("sgOrigPercentVal");
    const list = document.getElementById("sgOrigSourcesList");

    // Zero-PII offline / match simulation
    const matchPercent = this.currentSubmission?.match_percent ?? 0;
    if (badge) badge.textContent = `${matchPercent}%`;
    if (val) val.textContent = `${matchPercent}%`;
    if (list) {
      if (matchPercent > 0) {
        list.innerHTML = `
          <div style="padding: 8px; background: #263238; border-radius: 6px; border-left: 4px solid #ffb74d;">
            <div style="font-weight: 600; color: #ffb74d;">Совпадение фрагментов (${matchPercent}%)</div>
            <div style="color: #ccc; margin-top: 4px;">Обнаружены схожие конструкции с материалами курса.</div>
          </div>
        `;
      } else {
        list.innerHTML = `
          <div style="color: #81c784; padding: 8px; background: #1b5e20; border-radius: 6px;">
            ✓ Текст оригинален, заимствований не обнаружено.
          </div>
        `;
      }
    }
  }

  escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  destroy() {
    window.removeEventListener("keydown", this._keyHandler);
    const overlay = document.getElementById("speedGraderOverlay");
    if (overlay) overlay.remove();
    this.onClose();
  }
}

export function openSpeedGrader(options) {
  const sg = new SpeedGrader(options);
  sg.init();
  return sg;
}
