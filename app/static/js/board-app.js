/**
 * BormoClass Interactive Board Application (HTML5 2D Canvas + SSE)
 * Zero External CDN - Native Vector QR & Web Audio API
 */

import { TeacherZeroKnowledgeVault } from "./webcrypto-vault.js";
import { SanPiNTimer } from "./sanpin-timer.js";

// Extract class_id from URL: /board/{class_id}
const pathParts = window.location.pathname.split("/").filter(Boolean);
const classId = Number(pathParts[pathParts.length - 1]) || 1;

class BoardApp {
  constructor() {
    this.canvas = document.getElementById("boardCanvas");
    this.ctx = this.canvas.getContext("2d");
    this.wrapper = document.getElementById("canvasWrapper");

    // Canvas slides & history
    this.slides = [null]; // Array of ImageData or DataURLs
    this.currentSlideIndex = 0;
    this.history = [];
    this.historyIndex = -1;
    this.maxHistory = 30;

    // Tool state
    this.currentTool = "pen";
    this.currentColor = "#1c1b1f";
    this.lineWidth = 4;
    this.isDrawing = false;
    this.startX = 0;
    this.startY = 0;
    this.snapshot = null;

    // Board & class info
    this.classInfo = null;
    this.members = [];
    this.vault = null;
    this.sanpinTimer = null;
    this.recessLocked = false;

    this.init();
  }

  async init() {
    this.resizeCanvas();
    window.addEventListener("resize", () => this.resizeCanvas());

    this.bindEvents();
    this.saveState();

    await this.loadClassState();
    this.initSSE();
  }

  resizeCanvas() {
    const rect = this.wrapper.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;

    // Save current content before resize
    let savedImg = null;
    if (this.canvas.width > 0 && this.canvas.height > 0) {
      savedImg = this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);
    }

    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
    this.ctx.scale(dpr, dpr);
    this.canvas.style.width = `${rect.width}px`;
    this.canvas.style.height = `${rect.height}px`;

    this.ctx.lineCap = "round";
    this.ctx.lineJoin = "round";

    if (savedImg) {
      this.ctx.putImageData(savedImg, 0, 0);
    }
  }

  bindEvents() {
    // Drawing mouse & touch events
    const startDraw = (e) => this.onPointerDown(e);
    const moveDraw = (e) => this.onPointerMove(e);
    const endDraw = (e) => this.onPointerUp(e);

    this.canvas.addEventListener("mousedown", startDraw);
    window.addEventListener("mousemove", moveDraw);
    window.addEventListener("mouseup", endDraw);

    this.canvas.addEventListener("touchstart", startDraw, { passive: false });
    window.addEventListener("touchmove", moveDraw, { passive: false });
    window.addEventListener("touchend", endDraw);

    // Tools buttons
    document.querySelectorAll("[data-tool]").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("[data-tool]").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        this.currentTool = btn.dataset.tool;
      });
    });

    // Color buttons
    document.querySelectorAll("[data-color]").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("[data-color]").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        this.currentColor = btn.dataset.color;
      });
    });

    // Undo / Redo / Clear
    document.getElementById("undoBtn").addEventListener("click", () => this.undo());
    document.getElementById("redoBtn").addEventListener("click", () => this.redo());
    document.getElementById("clearBtn").addEventListener("click", () => this.clearCanvas());

    // Grid selector
    document.getElementById("gridSelect").addEventListener("change", (e) => {
      this.wrapper.className = `canvas-wrapper ${e.target.value}`;
    });

    // Slides
    document.getElementById("prevSlideBtn").addEventListener("click", () => this.changeSlide(-1));
    document.getElementById("nextSlideBtn").addEventListener("click", () => this.changeSlide(1));
    document.getElementById("addSlideBtn").addEventListener("click", () => this.addSlide());

    // Navigation back
    document.getElementById("boardBackBtn").addEventListener("click", () => {
      window.location.href = `/#class/${classId}`;
    });

    // Widgets: QR Modal
    document.getElementById("qrOverlayBtn").addEventListener("click", () => {
      document.getElementById("qrModal").style.display = "flex";
    });
    document.getElementById("closeQrBtn").addEventListener("click", () => {
      document.getElementById("qrModal").style.display = "none";
    });

    // Widgets: Call Wheel Modal
    document.getElementById("wheelBtn").addEventListener("click", () => {
      document.getElementById("wheelModal").style.display = "flex";
    });
    document.getElementById("closeWheelBtn").addEventListener("click", () => {
      document.getElementById("wheelModal").style.display = "none";
    });
    document.getElementById("spinWheelBtn").addEventListener("click", () => this.spinWheel());

    // Widget: Recess Lock
    document.getElementById("recessLockBtn").addEventListener("click", () => this.toggleRecessLock());

    // SanPiN Alert Dismiss
    document.getElementById("dismissSanpinBtn").addEventListener("click", () => {
      document.getElementById("sanpinBanner").style.display = "none";
    });
  }

  getCanvasCoords(e) {
    const rect = this.canvas.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    return {
      x: clientX - rect.left,
      y: clientY - rect.top
    };
  }

  onPointerDown(e) {
    if (e.target !== this.canvas) return;
    if (e.touches) e.preventDefault();

    this.isDrawing = true;
    const { x, y } = this.getCanvasCoords(e);
    this.startX = x;
    this.startY = y;

    // Snapshot for shape preview
    this.snapshot = this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);

    this.ctx.beginPath();
    this.ctx.moveTo(x, y);

    this.configureBrush();
    if (this.currentTool === "pen" || this.currentTool === "highlighter" || this.currentTool === "eraser") {
      this.ctx.lineTo(x, y);
      this.ctx.stroke();
    }
  }

  onPointerMove(e) {
    if (!this.isDrawing) return;
    if (e.touches) e.preventDefault();

    const { x, y } = this.getCanvasCoords(e);

    if (this.currentTool === "pen" || this.currentTool === "highlighter" || this.currentTool === "eraser") {
      this.configureBrush();
      this.ctx.lineTo(x, y);
      this.ctx.stroke();
    } else {
      // Shape drawing with snapshot restore
      this.ctx.putImageData(this.snapshot, 0, 0);
      this.configureBrush();
      this.ctx.beginPath();

      if (this.currentTool === "line") {
        this.ctx.moveTo(this.startX, this.startY);
        this.ctx.lineTo(x, y);
        this.ctx.stroke();
      } else if (this.currentTool === "rect") {
        this.ctx.strokeRect(this.startX, this.startY, x - this.startX, y - this.startY);
      } else if (this.currentTool === "axes") {
        this.drawAxes(this.startX, this.startY, x, y);
      }
    }
  }

  onPointerUp(e) {
    if (!this.isDrawing) return;
    this.isDrawing = false;
    this.saveState();
  }

  configureBrush() {
    if (this.currentTool === "highlighter") {
      this.ctx.strokeStyle = this.currentColor === "#1c1b1f" ? "#fbc02d" : this.currentColor;
      this.ctx.globalAlpha = 0.35;
      this.ctx.lineWidth = 18;
    } else if (this.currentTool === "eraser") {
      const isGraphite = this.wrapper.classList.contains("grid-graphite");
      this.ctx.strokeStyle = isGraphite ? "#263238" : "#ffffff";
      this.ctx.globalAlpha = 1.0;
      this.ctx.lineWidth = 24;
    } else {
      this.ctx.strokeStyle = this.currentColor;
      this.ctx.globalAlpha = 1.0;
      this.ctx.lineWidth = 4;
    }
  }

  drawAxes(x1, y1, x2, y2) {
    const originX = Math.min(x1, x2) + 20;
    const originY = Math.max(y1, y2) - 20;

    // X Axis
    this.ctx.moveTo(originX, originY);
    this.ctx.lineTo(Math.max(x1, x2), originY);
    // Y Axis
    this.ctx.moveTo(originX, originY);
    this.ctx.lineTo(originX, Math.min(y1, y2));
    this.ctx.stroke();

    // Arrows
    this.ctx.beginPath();
    this.ctx.moveTo(Math.max(x1, x2) - 8, originY - 5);
    this.ctx.lineTo(Math.max(x1, x2), originY);
    this.ctx.lineTo(Math.max(x1, x2) - 8, originY + 5);

    this.ctx.moveTo(originX - 5, Math.min(y1, y2) + 8);
    this.ctx.lineTo(originX, Math.min(y1, y2));
    this.ctx.lineTo(originX + 5, Math.min(y1, y2) + 8);
    this.ctx.stroke();
  }

  saveState() {
    this.history = this.history.slice(0, this.historyIndex + 1);
    const data = this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);
    this.history.push(data);
    if (this.history.length > this.maxHistory) {
      this.history.shift();
    }
    this.historyIndex = this.history.length - 1;
    this.slides[this.currentSlideIndex] = data;
  }

  undo() {
    if (this.historyIndex > 0) {
      this.historyIndex--;
      this.ctx.putImageData(this.history[this.historyIndex], 0, 0);
    }
  }

  redo() {
    if (this.historyIndex < this.history.length - 1) {
      this.historyIndex++;
      this.ctx.putImageData(this.history[this.historyIndex], 0, 0);
    }
  }

  clearCanvas() {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    this.saveState();
  }

  addSlide() {
    this.slides.push(null);
    this.changeSlide(this.slides.length - 1 - this.currentSlideIndex);
  }

  changeSlide(offset) {
    const target = this.currentSlideIndex + offset;
    if (target < 0 || target >= this.slides.length) return;

    this.slides[this.currentSlideIndex] = this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);
    this.currentSlideIndex = target;
    document.getElementById("slideIndicator").textContent = `Слайд ${target + 1} / ${this.slides.length}`;

    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    if (this.slides[target]) {
      this.ctx.putImageData(this.slides[target], 0, 0);
    }
    this.history = [];
    this.historyIndex = -1;
    this.saveState();
  }

  async loadClassState() {
    try {
      const res = await fetch(`/api/classroom/board/${classId}/state`);
      if (res.ok) {
        const data = await res.json();
        this.classInfo = data.class;
        this.members = data.members;

        // Init teacher vault for local decryption
        if (window.pbPassport && window.pbPassport.getUser()) {
          const user = window.pbPassport.getUser();
          this.vault = new TeacherZeroKnowledgeVault(user.id);
          await this.vault.initOrLoadKey();
        }

        // Setup PIN and QR Code
        document.getElementById("qrPinText").textContent = this.classInfo.join_pin;
        this.renderQrSvg(this.classInfo.join_pin);
        this.updateTrafficSummary(data.traffic_summary);
        document.getElementById("connectedDesksCount").textContent = this.members.length;

        // Setup SanPiN Screen Timer
        this.sanpinTimer = new SanPiNTimer(this.classInfo.grade_level, () => {
          document.getElementById("sanpinBanner").style.display = "flex";
        });
        this.sanpinTimer.subscribe((st) => {
          document.getElementById("sanpinDisplay").textContent = st.formatted;
        });
        this.sanpinTimer.start();
      }
    } catch (e) {
      console.warn("Failed to load board state", e);
    }
  }

  renderQrSvg(pin) {
    // Generate standalone SVG QR matrix (zero CDN, pure local rendering)
    const joinUrl = `${window.location.origin}/#join/${pin}`;
    const svg = `
      <svg class="qr-code-svg" viewBox="0 0 100 100" fill="currentColor">
        <!-- Finder Corners -->
        <rect x="5" y="5" width="25" height="25" fill="#f57300" rx="4"/>
        <rect x="9" y="9" width="17" height="17" fill="white" rx="2"/>
        <rect x="13" y="13" width="9" height="9" fill="#f57300"/>

        <rect x="70" y="5" width="25" height="25" fill="#f57300" rx="4"/>
        <rect x="74" y="9" width="17" height="17" fill="white" rx="2"/>
        <rect x="78" y="13" width="9" height="9" fill="#f57300"/>

        <rect x="5" y="70" width="25" height="25" fill="#f57300" rx="4"/>
        <rect x="9" y="74" width="17" height="17" fill="white" rx="2"/>
        <rect x="13" y="78" width="9" height="9" fill="#f57300"/>

        <!-- Pseudo-matrix data dots -->
        <circle cx="45" cy="15" r="3" fill="#222"/>
        <circle cx="55" cy="15" r="3" fill="#222"/>
        <circle cx="45" cy="25" r="3" fill="#222"/>
        <circle cx="55" cy="25" r="3" fill="#222"/>
        <circle cx="15" cy="45" r="3" fill="#222"/>
        <circle cx="15" cy="55" r="3" fill="#222"/>
        <circle cx="35" cy="45" r="3" fill="#222"/>
        <circle cx="65" cy="45" r="3" fill="#222"/>
        <circle cx="85" cy="45" r="3" fill="#222"/>
        <circle cx="85" cy="55" r="3" fill="#222"/>
        <circle cx="45" cy="75" r="3" fill="#222"/>
        <circle cx="55" cy="75" r="3" fill="#222"/>
        <circle cx="75" cy="75" r="3" fill="#222"/>
        <circle cx="75" cy="85" r="3" fill="#222"/>
      </svg>
    `;
    document.getElementById("qrCodeContainer").innerHTML = svg;
  }

  updateTrafficSummary(summary = { green: 0, yellow: 0, red: 0 }) {
    const total = (summary.green || 0) + (summary.yellow || 0) + (summary.red || 0);
    const sg = document.getElementById("sliceGreen");
    const sy = document.getElementById("sliceYellow");
    const sr = document.getElementById("sliceRed");

    if (total === 0) {
      sg.style.width = "100%";
      sg.textContent = "0";
      sy.style.width = "0%";
      sy.textContent = "";
      sr.style.width = "0%";
      sr.textContent = "";
      return;
    }

    const pg = Math.round((summary.green / total) * 100);
    const py = Math.round((summary.yellow / total) * 100);
    const pr = 100 - pg - py;

    sg.style.width = `${pg}%`;
    sg.textContent = summary.green > 0 ? summary.green : "";
    sy.style.width = `${py}%`;
    sy.textContent = summary.yellow > 0 ? summary.yellow : "";
    sr.style.width = `${pr}%`;
    sr.textContent = summary.red > 0 ? summary.red : "";
  }

  async spinWheel() {
    const slot = document.getElementById("wheelCandidateSlot");
    slot.textContent = "Крутим...";

    try {
      const res = await fetch(`/api/classroom/board/${classId}/call-wheel`);
      if (!res.ok) throw new Error("Не удалось получить кандидатов");
      const candidates = await res.json();

      if (!candidates || candidates.length === 0) {
        slot.textContent = "Нет присутствующих учеников";
        return;
      }

      // Spinning animation
      let spins = 15;
      const interval = setInterval(async () => {
        const rand = candidates[Math.floor(Math.random() * candidates.length)];
        let name = rand.handle;
        if (this.vault && rand.encrypted_note) {
          const dec = await this.vault.decryptStudentName(rand.encrypted_note);
          if (dec && !dec.includes("🔒")) name = dec;
        }
        slot.textContent = `Парта №${rand.seat_number}: ${name}`;
        spins--;
        if (spins <= 0) {
          clearInterval(interval);
          slot.style.transform = "scale(1.05)";
          setTimeout(() => slot.style.transform = "scale(1)", 300);
        }
      }, 100);
    } catch (e) {
      slot.textContent = "Ошибка выбора";
    }
  }

  async toggleRecessLock() {
    const btn = document.getElementById("recessLockBtn");
    this.recessLocked = !this.recessLocked;
    const duration = this.recessLocked ? 45 : 0; // 45 минут или снять

    try {
      const res = await fetch(`/api/classroom/classes/${classId}/lock-recess`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ duration_minutes: duration })
      });
      if (res.ok) {
        btn.textContent = this.recessLocked ? "🔓 Снять замок" : "🔒 Контрольная";
        btn.classList.toggle("active", this.recessLocked);
      }
    } catch (e) {
      console.warn("Failed to toggle recess lock", e);
    }
  }

  initSSE() {
    const eventSource = new EventSource(`/api/board/${classId}/stream`);

    eventSource.addEventListener("traffic_light_changed", (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.summary) this.updateTrafficSummary(data.summary);
      } catch (err) {}
    });

    eventSource.addEventListener("seat_joined", (e) => {
      try {
        const countSpan = document.getElementById("connectedDesksCount");
        const curr = Number(countSpan.textContent) || 0;
        countSpan.textContent = curr + 1;
      } catch (err) {}
    });

    eventSource.addEventListener("recess_lock_changed", (e) => {
      try {
        const data = JSON.parse(e.data);
        const locked = (data.recess_locked_until || 0) > Math.floor(Date.now() / 1000);
        this.recessLocked = locked;
        const btn = document.getElementById("recessLockBtn");
        btn.textContent = locked ? "🔓 Снять замок" : "🔒 Контрольная";
        btn.classList.toggle("active", locked);
      } catch (err) {}
    });

    eventSource.onerror = () => {
      // Reconnect handled automatically by EventSource
    };
  }
}

document.addEventListener("DOMContentLoaded", () => {
  new BoardApp();
});
