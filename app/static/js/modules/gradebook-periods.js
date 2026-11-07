/**
 * BormoClass Gradebook & Academic Periods (Zero-PII, 152-FZ, Simonov SOU)
 * Features:
 *  - Fixed 2D table (sticky student column, sticky Class Average row, sticky coursework headers)
 *  - Academic period filter (All periods / 1-4 quarters)
 *  - In-cell rapid draft grade entry with keyboard navigation (Enter, ArrowDown, ArrowUp)
 *  - Cell context menu (Return, Excused, Open in SpeedGrader)
 *  - Final grade calculation (TOTAL_POINTS / WEIGHTED_CATEGORIES)
 *  - Russian educational metrics panel (Усп%, КЗ%, СОУ%)
 *  - Standards Mastery Matrix tab
 *  - Client-side Zero-PII CSV export
 */

import { openSpeedGrader } from "./speedgrader.js";

export class GradebookPeriodsView {
  constructor(options = {}) {
    this.container = options.container || document.getElementById("appMain");
    this.classId = options.classId;
    this.activePeriodId = null; // null = all periods
    this.activeTab = "gradebook"; // 'gradebook' | 'matrix'
    this.gradebookData = null;
    this.matrixData = null;
    this.activeContextMenu = null;
  }

  async render() {
    if (!this.container) return;
    this.container.innerHTML = `
      <div class="gradebook-wrapper" style="display: flex; flex-direction: column; gap: 16px; height: 100%; box-sizing: border-box;">
        <!-- Top Controls Bar -->
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
          <div style="display: flex; align-items: center; gap: 12px;">
            <h2 style="margin: 0; font-size: 1.4rem;">Журнал успеваемости</h2>
            <div class="nav-rail" style="display: inline-flex; border-radius: 8px; background: var(--md-sys-color-surface-container-high, #e3e8ef); padding: 2px;">
              <button id="gbTabGradebook" class="nav-tab-btn ${this.activeTab === "gradebook" ? "active" : ""}" style="
                padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.85rem;
                background: ${this.activeTab === "gradebook" ? "var(--md-sys-color-surface, #ffffff)" : "transparent"};
              ">Оценки</button>
              <button id="gbTabMatrix" class="nav-tab-btn ${this.activeTab === "matrix" ? "active" : ""}" style="
                padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.85rem;
                background: ${this.activeTab === "matrix" ? "var(--md-sys-color-surface, #ffffff)" : "transparent"};
              ">Матрица стандартов</button>
            </div>
          </div>

          <div style="display: flex; align-items: center; gap: 10px;">
            <!-- Period Selector -->
            <select id="gbPeriodSelector" style="
              padding: 6px 12px; border-radius: 8px; border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
              background: var(--md-sys-color-surface, #ffffff); font-size: 0.85rem; cursor: pointer; font-weight: 600;
            ">
              <option value="">Все учебные периоды</option>
              <option value="1">1 четверть</option>
              <option value="2">2 четверть</option>
              <option value="3">3 четверть</option>
              <option value="4">4 четверть</option>
            </select>

            <!-- Zero-PII CSV Export Button -->
            <button id="gbBtnExportCsv" class="btn btn-secondary" style="
              display: flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 8px;
              border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5); background: var(--md-sys-color-surface-container-low, #f7f9fc);
              font-weight: 600; font-size: 0.85rem; cursor: pointer;
            ">
              📥 Экспорт в CSV (Zero-PII)
            </button>
          </div>
        </div>

        <!-- Russian Metrics Panel (Усп%, КЗ%, СОУ%) -->
        <div id="gbMetricsPanel" style="
          display: flex; gap: 16px; flex-wrap: wrap; padding: 12px 18px;
          background: var(--md-sys-color-surface-container-lowest, #ffffff);
          border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
          border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        ">
          <div style="flex: 1; min-width: 120px;">
            <div style="font-size: 0.8rem; color: var(--md-sys-color-on-surface-variant, #444746);">Успеваемость (Усп%)</div>
            <div id="gbMetricUsp" style="font-size: 1.35rem; font-weight: 800; color: #2e7d32;">--%</div>
            <div style="font-size: 0.72rem; color: #777;">Оценки 3, 4, 5</div>
          </div>
          <div style="width: 1px; background: var(--md-sys-color-outline-variant, #c4c7c5);"></div>
          <div style="flex: 1; min-width: 120px;">
            <div style="font-size: 0.8rem; color: var(--md-sys-color-on-surface-variant, #444746);">Качество знаний (КЗ%)</div>
            <div id="gbMetricKz" style="font-size: 1.35rem; font-weight: 800; color: #005ac1;">--%</div>
            <div style="font-size: 0.72rem; color: #777;">Оценки 4 и 5</div>
          </div>
          <div style="width: 1px; background: var(--md-sys-color-outline-variant, #c4c7c5);"></div>
          <div style="flex: 1; min-width: 120px;">
            <div style="font-size: 0.8rem; color: var(--md-sys-color-on-surface-variant, #444746);">Степень обученности (СОУ%)</div>
            <div id="gbMetricSou" style="font-size: 1.35rem; font-weight: 800; color: #6a1b9a;">--%</div>
            <div style="font-size: 0.72rem; color: #777;">Формула Симонова</div>
          </div>
          <div style="width: 1px; background: var(--md-sys-color-outline-variant, #c4c7c5);"></div>
          <div style="flex: 1; min-width: 140px;">
            <div style="font-size: 0.8rem; color: var(--md-sys-color-on-surface-variant, #444746);">Метод расчёта</div>
            <div id="gbMetricCalcType" style="font-size: 1.05rem; font-weight: 700; color: #333; margin-top: 4px;">Сумма баллов</div>
            <div style="font-size: 0.72rem; color: #777;">TOTAL_POINTS</div>
          </div>
        </div>

        <!-- Main Viewport for Gradebook Table or Standards Matrix -->
        <div id="gbMainContent" style="flex: 1; overflow: auto; border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5); border-radius: 12px; background: #fff;">
          <div style="padding: 40px; text-align: center; color: #777;">Загрузка данных журнала...</div>
        </div>
      </div>
    `;

    this.bindTopControls();
    await this.loadData();
  }

  bindTopControls() {
    const tabGb = document.getElementById("gbTabGradebook");
    const tabMx = document.getElementById("gbTabMatrix");
    if (tabGb) {
      tabGb.onclick = () => {
        this.activeTab = "gradebook";
        this.render();
      };
    }
    if (tabMx) {
      tabMx.onclick = () => {
        this.activeTab = "matrix";
        this.render();
      };
    }

    const periodSel = document.getElementById("gbPeriodSelector");
    if (periodSel) {
      periodSel.value = this.activePeriodId || "";
      periodSel.onchange = (e) => {
        this.activePeriodId = e.target.value || null;
        this.loadData();
      };
    }

    const btnExport = document.getElementById("gbBtnExportCsv");
    if (btnExport) {
      btnExport.onclick = () => this.exportZeroPiiCsv();
    }

    // Dismiss context menu on click outside
    document.addEventListener("click", () => this.dismissContextMenu());
  }

  async loadData() {
    const content = document.getElementById("gbMainContent");
    if (!content) return;

    if (this.activeTab === "matrix") {
      await this.loadStandardsMatrix();
      return;
    }

    try {
      const url = this.activePeriodId
        ? `/api/classroom/classes/${this.classId}/gradebook?grading_period_id=${this.activePeriodId}`
        : `/api/classroom/classes/${this.classId}/gradebook`;
      const res = await fetch(url);
      if (!res.ok) {
        content.innerHTML = `<div style="padding: 40px; text-align: center; color: #d32f2f;">Не удалось загрузить журнал.</div>`;
        return;
      }
      this.gradebookData = await res.json();
      this.renderGradebookTable(this.gradebookData);
      this.updateMetricsPanel(this.gradebookData.analytics, this.gradebookData.grade_calc_type);
    } catch (e) {
      console.error("Failed to load gradebook", e);
      content.innerHTML = `<div style="padding: 40px; text-align: center; color: #d32f2f;">Ошибка сети при загрузке журнала.</div>`;
    }
  }

  updateMetricsPanel(analytics, calcType) {
    if (!analytics) return;
    const usp = document.getElementById("gbMetricUsp");
    const kz = document.getElementById("gbMetricKz");
    const sou = document.getElementById("gbMetricSou");
    const type = document.getElementById("gbMetricCalcType");

    if (usp) usp.textContent = `${analytics.usp ?? analytics.usp_percent ?? 0}%`;
    if (kz) kz.textContent = `${analytics.kz ?? analytics.kz_percent ?? 0}%`;
    if (sou) sou.textContent = `${analytics.sou ?? analytics.sou_percent ?? 0}%`;
    if (type) type.textContent = calcType === "WEIGHTED_CATEGORIES" ? "Весовые категории" : "Сумма баллов";
  }

  renderGradebookTable(data) {
    const content = document.getElementById("gbMainContent");
    if (!content) return;

    const { courseworks, coursework_averages, students, categories } = data;

    if (!students || students.length === 0) {
      content.innerHTML = `<div style="padding: 40px; text-align: center; color: #777;">В этом курсе нет зачисленных учащихся.</div>`;
      return;
    }

    const catMap = {};
    if (categories) {
      categories.forEach((c) => (catMap[c.id] = c.category_title));
    }

    let html = `
      <table id="gbTable" style="
        width: 100%; border-collapse: separate; border-spacing: 0; font-size: 0.88rem;
      ">
        <thead>
          <tr style="background: var(--md-sys-color-surface-container, #f0f4f9);">
            <!-- Sticky Student Name Header -->
            <th style="
              position: sticky; top: 0; left: 0; z-index: 20; background: var(--md-sys-color-surface-container, #f0f4f9);
              padding: 12px 16px; text-align: left; border-bottom: 2px solid var(--md-sys-color-outline-variant, #c4c7c5);
              border-right: 2px solid var(--md-sys-color-outline-variant, #c4c7c5); min-width: 200px;
            ">
              Учащиеся (${students.length})
            </th>

            <!-- Sticky Overall Grade Header -->
            <th style="
              position: sticky; top: 0; z-index: 10; background: var(--md-sys-color-surface-container, #f0f4f9);
              padding: 12px 10px; text-align: center; border-bottom: 2px solid var(--md-sys-color-outline-variant, #c4c7c5);
              border-right: 1px solid var(--md-sys-color-outline-variant, #c4c7c5); min-width: 90px;
            ">
              Итог (%)
            </th>

            <!-- Dynamic Coursework Headers -->
            ${courseworks.map((cw) => `
              <th style="
                position: sticky; top: 0; z-index: 10; background: var(--md-sys-color-surface-container, #f0f4f9);
                padding: 10px 14px; text-align: center; border-bottom: 2px solid var(--md-sys-color-outline-variant, #c4c7c5);
                border-right: 1px solid var(--md-sys-color-outline-variant, #c4c7c5); min-width: 130px; max-width: 200px;
              ">
                <div style="font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${this.escapeHtml(cw.title)}">
                  ${this.escapeHtml(cw.title)}
                </div>
                <div style="font-size: 0.72rem; color: #555; margin-top: 2px;">
                  ${cw.grade_category_id && catMap[cw.grade_category_id] ? `[${this.escapeHtml(catMap[cw.grade_category_id])}]` : ""}
                  макс. ${cw.max_points || 100} б.
                </div>
              </th>
            `).join("")}
          </tr>

          <!-- Sticky Class Average Row -->
          <tr style="background: var(--md-sys-color-surface-container-high, #e3e8ef); font-weight: 700;">
            <td style="
              position: sticky; left: 0; z-index: 15; background: var(--md-sys-color-surface-container-high, #e3e8ef);
              padding: 8px 16px; border-bottom: 2px solid var(--md-sys-color-outline-variant, #c4c7c5);
              border-right: 2px solid var(--md-sys-color-outline-variant, #c4c7c5);
            ">
              Средний балл класса
            </td>
            <td style="
              text-align: center; padding: 8px 10px; border-bottom: 2px solid var(--md-sys-color-outline-variant, #c4c7c5);
              border-right: 1px solid var(--md-sys-color-outline-variant, #c4c7c5); color: #005ac1;
            ">
              --
            </td>
            ${courseworks.map((cw) => {
              const avg = coursework_averages[cw.id];
              return `
                <td style="
                  text-align: center; padding: 8px 10px; border-bottom: 2px solid var(--md-sys-color-outline-variant, #c4c7c5);
                  border-right: 1px solid var(--md-sys-color-outline-variant, #c4c7c5); color: #005ac1;
                ">
                  ${avg !== null && avg !== undefined ? `${avg} б.` : "—"}
                </td>
              `;
            }).join("")}
          </tr>
        </thead>
        <tbody>
          ${students.map((st, rowIdx) => `
            <tr style="background: ${rowIdx % 2 === 0 ? "#ffffff" : "#fbfcfe"};">
              <!-- Sticky Student Handle / Note -->
              <td style="
                position: sticky; left: 0; z-index: 5; background: ${rowIdx % 2 === 0 ? "#ffffff" : "#fbfcfe"};
                padding: 10px 16px; border-bottom: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
                border-right: 2px solid var(--md-sys-color-outline-variant, #c4c7c5); font-weight: 600;
              ">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="display: inline-block; width: 24px; height: 24px; border-radius: 50%; background: #005ac1; color: #fff; font-size: 0.75rem; line-height: 24px; text-align: center;">
                    ${st.seat_number || "?"}
                  </span>
                  <span>${this.escapeHtml(st.handle)}</span>
                </div>
              </td>

              <!-- Overall percentage -->
              <td style="
                text-align: center; padding: 10px; border-bottom: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
                border-right: 1px solid var(--md-sys-color-outline-variant, #c4c7c5); font-weight: 700;
                color: ${st.overall_percent !== null ? (st.overall_percent >= 70 ? "#2e7d32" : "#c62828") : "#777"};
              ">
                ${st.overall_percent !== null ? `${st.overall_percent}%` : "—"}
              </td>

              <!-- Editable Grade Cells -->
              ${courseworks.map((cw, colIdx) => {
                const sub = (st.grades && st.grades[cw.id]) || {};
                const score = sub.assigned_grade !== null && sub.assigned_grade !== undefined ? sub.assigned_grade : "";
                const isExc = sub.is_excused;

                return `
                  <td class="gb-grade-cell" data-row="${rowIdx}" data-col="${colIdx}" data-cwid="${cw.id}" data-sid="${st.student_id}" data-max="${cw.max_points || 100}" style="
                    text-align: center; padding: 4px; border-bottom: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
                    border-right: 1px solid var(--md-sys-color-outline-variant, #c4c7c5); position: relative;
                  ">
                    <input type="text" class="gb-cell-input" value="${isExc ? "EXC" : score}" placeholder="—" style="
                      width: 100%; border: none; background: transparent; text-align: center; font-size: 0.95rem;
                      font-weight: 600; padding: 6px 0; outline: none; border-radius: 4px;
                      color: ${isExc ? "#6a1b9a" : "inherit"};
                    ">
                  </td>
                `;
              }).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;

    content.innerHTML = html;
    this.bindCellInteractions(courseworks, students);
  }

  bindCellInteractions(courseworks, students) {
    const inputs = document.querySelectorAll(".gb-cell-input");

    inputs.forEach((input) => {
      const cell = input.closest(".gb-grade-cell");
      const row = Number(cell.dataset.row);
      const col = Number(cell.dataset.col);
      const cwId = Number(cell.dataset.cwid);
      const studentId = Number(cell.dataset.sid);

      // Rapid keyboard navigation
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === "ArrowDown") {
          e.preventDefault();
          this.focusCell(row + 1, col);
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          this.focusCell(row - 1, col);
        }
      });

      // Quick saving draft grade on change
      input.addEventListener("change", async (e) => {
        const val = e.target.value.trim();
        if (val.toUpperCase() === "EXC") {
          await this.saveExcused(cwId, studentId, true);
          input.value = "EXC";
          input.style.color = "#6a1b9a";
        } else if (val === "" || !isNaN(Number(val))) {
          const num = val === "" ? null : Number(val);
          await this.saveCellGrade(cwId, studentId, num);
        }
      });

      // Context menu on right click
      cell.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        this.showContextMenu(e.clientX, e.clientY, cwId, studentId);
      });
    });
  }

  focusCell(row, col) {
    const targetCell = document.querySelector(`.gb-grade-cell[data-row="${row}"][data-col="${col}"] input`);
    if (targetCell) {
      targetCell.focus();
      targetCell.select();
    }
  }

  async saveCellGrade(courseworkId, studentId, gradePoints) {
    try {
      await fetch(`/api/classroom/submissions/${courseworkId}/${studentId}/grade`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ grade_points: gradePoints }),
      });
    } catch (e) {
      console.warn("Failed to save cell grade", e);
    }
  }

  async saveExcused(courseworkId, studentId, isExcused) {
    try {
      await fetch(`/api/classroom/coursework/${courseworkId}/submissions/${studentId}/excuse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_excused: isExcused }),
      });
    } catch (e) {
      console.warn("Failed to excuse student", e);
    }
  }

  showContextMenu(x, y, courseworkId, studentId) {
    this.dismissContextMenu();

    const menu = document.createElement("div");
    menu.id = "gbContextMenu";
    menu.style.cssText = `
      position: fixed; left: ${x}px; top: ${y}px; z-index: 99999;
      background: var(--md-sys-color-surface, #ffffff);
      border: 1px solid var(--md-sys-color-outline-variant, #c4c7c5);
      border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.2);
      padding: 6px 0; min-width: 180px; display: flex; flex-direction: column;
    `;

    menu.innerHTML = `
      <button id="gbMenuSpeedGrader" style="
        padding: 8px 16px; border: none; background: transparent; text-align: left;
        cursor: pointer; font-size: 0.85rem; font-weight: 600;
      ">🔍 Открыть в SpeedGrader</button>
      <button id="gbMenuExcuse" style="
        padding: 8px 16px; border: none; background: transparent; text-align: left;
        cursor: pointer; font-size: 0.85rem;
      ">🏷 Освободить (Excused)</button>
      <button id="gbMenuReturn" style="
        padding: 8px 16px; border: none; background: transparent; text-align: left;
        cursor: pointer; font-size: 0.85rem; color: #005ac1;
      ">↩ Вернуть работу</button>
    `;

    document.body.appendChild(menu);
    this.activeContextMenu = menu;

    document.getElementById("gbMenuSpeedGrader").onclick = () => {
      this.dismissContextMenu();
      openSpeedGrader({
        classId: this.classId,
        courseworkId: courseworkId,
        studentId: studentId,
        onClose: () => this.loadData(),
      });
    };

    document.getElementById("gbMenuExcuse").onclick = async () => {
      this.dismissContextMenu();
      await this.saveExcused(courseworkId, studentId, true);
      this.loadData();
    };

    document.getElementById("gbMenuReturn").onclick = async () => {
      this.dismissContextMenu();
      await fetch(`/v1/courses/${this.classId}/courseWork/${courseworkId}/studentSubmissions/${studentId}:return`, {
        method: "POST",
      });
      this.loadData();
    };
  }

  dismissContextMenu() {
    if (this.activeContextMenu) {
      this.activeContextMenu.remove();
      this.activeContextMenu = null;
    }
  }

  async loadStandardsMatrix() {
    const content = document.getElementById("gbMainContent");
    if (!content) return;

    try {
      const res = await fetch(`/api/classroom/classes/${this.classId}/matrix`);
      if (!res.ok) {
        content.innerHTML = `<div style="padding: 40px; text-align: center; color: #d32f2f;">Не удалось загрузить матрицу стандартов.</div>`;
        return;
      }
      this.matrixData = await res.json();
      this.renderStandardsMatrix(this.matrixData);
    } catch (e) {
      content.innerHTML = `<div style="padding: 40px; text-align: center; color: #d32f2f;">Ошибка сети при загрузке матрицы.</div>`;
    }
  }

  renderStandardsMatrix(matrix) {
    const content = document.getElementById("gbMainContent");
    if (!content) return;

    const { students = [], coursework = [], submissions = {} } = matrix;

    content.innerHTML = `
      <div style="padding: 16px;">
        <h3 style="margin-top: 0;">Матрица освоения стандартов (ФГОС / CASE)</h3>
        <p style="font-size: 0.85rem; color: #666;">
          Наглядная тепловая карта результатов учащихся по ключевым темам и заданиям курса.
        </p>
        <table style="width: 100%; border-collapse: collapse; font-size: 0.85rem; margin-top: 12px;">
          <thead>
            <tr style="background: #f0f4f9;">
              <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Ученик</th>
              ${coursework.map((c) => `
                <th style="padding: 10px; border: 1px solid #ddd; text-align: center;">${this.escapeHtml(c.title)}</th>
              `).join("")}
            </tr>
          </thead>
          <tbody>
            ${students.map((st) => `
              <tr>
                <td style="padding: 8px 12px; border: 1px solid #ddd; font-weight: 600;">
                  №${st.seat_number}: ${this.escapeHtml(st.handle)}
                </td>
                ${coursework.map((cw) => {
                  const sub = submissions[`${cw.id}_${st.student_id}`];
                  const grade = sub ? (sub.grade_five || sub.assigned_grade) : null;
                  let bg = "#f5f5f5";
                  if (grade >= 4.5 || grade === 5) bg = "#c8e6c9";
                  else if (grade >= 3.5 || grade === 4) bg = "#e8f5e9";
                  else if (grade >= 2.5 || grade === 3) bg = "#fff9c4";
                  else if (grade !== null) bg = "#ffcdd2";

                  return `
                    <td style="padding: 8px; border: 1px solid #ddd; text-align: center; background: ${bg}; font-weight: 700;">
                      ${grade !== null ? grade : "—"}
                    </td>
                  `;
                }).join("")}
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  async exportZeroPiiCsv() {
    if (!this.gradebookData) return;
    const { courseworks, students } = this.gradebookData;

    // Header row: Zero-PII (seat number and generated handle only)
    const headers = ["Парта", "Позывной", "Итог (%)", ...courseworks.map((c) => c.title)];
    const rows = [];

    for (const st of students) {
      const stRow = [
        st.seat_number || "",
        st.handle || "",
        st.overall_percent !== null ? `${st.overall_percent}%` : "",
      ];

      for (const cw of courseworks) {
        const sub = (st.grades && st.grades[cw.id]) || {};
        if (sub.is_excused) {
          stRow.push("EXC");
        } else {
          stRow.push(sub.assigned_grade !== null && sub.assigned_grade !== undefined ? sub.assigned_grade : "");
        }
      }
      rows.push(stRow);
    }

    // Zero-PII client-side UTF-8 with BOM
    const csvContent =
      "\uFEFF" +
      [headers, ...rows]
        .map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(","))
        .join("\r\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `bormoclass_grades_${this.classId}_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
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
}
