/**
 * SanPiN 1.2.3685-21 Continuous Screen Time Controller
 * Grade limits:
 * - 1..2 grades: 20 min
 * - 3..4 grades: 25 min
 * - 5..9 grades: 30 min
 * - 10..11 grades: 35 min
 * Zero External Audio CDN: Pure Web Audio API tone generator.
 */

export class SanPiNTimer {
  constructor(gradeLevel = 8, onExpire = null) {
    this.gradeLevel = Number(gradeLevel) || 8;
    this.limitMinutes = this.getLimitForGrade(this.gradeLevel);
    this.totalSeconds = this.limitMinutes * 60;
    this.remainingSeconds = this.totalSeconds;
    this.isRunning = false;
    this.intervalId = null;
    this.onExpire = onExpire;
    this.listeners = new Set();
  }

  getLimitForGrade(grade) {
    if (grade <= 2) return 20;
    if (grade <= 4) return 25;
    if (grade <= 9) return 30;
    return 35;
  }

  start() {
    if (this.isRunning) return;
    this.isRunning = true;
    this.intervalId = setInterval(() => {
      if (this.remainingSeconds > 0) {
        this.remainingSeconds--;
        this.notify();
      } else {
        this.stop();
        this.playBeep();
        if (this.onExpire) this.onExpire();
        this.notify();
      }
    }, 1000);
    this.notify();
  }

  stop() {
    this.isRunning = false;
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    this.notify();
  }

  reset() {
    this.stop();
    this.remainingSeconds = this.totalSeconds;
    this.notify();
  }

  getFormattedTime() {
    const mins = Math.floor(this.remainingSeconds / 60);
    const secs = this.remainingSeconds % 60;
    return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }

  subscribe(listener) {
    this.listeners.add(listener);
    listener({
      remaining: this.remainingSeconds,
      formatted: this.getFormattedTime(),
      isRunning: this.isRunning,
      isExpired: this.remainingSeconds <= 0
    });
    return () => this.listeners.delete(listener);
  }

  notify() {
    const state = {
      remaining: this.remainingSeconds,
      formatted: this.getFormattedTime(),
      isRunning: this.isRunning,
      isExpired: this.remainingSeconds <= 0
    };
    this.listeners.forEach(fn => fn(state));
  }

  playBeep() {
    try {
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();

      osc.type = "sine";
      osc.frequency.setValueAtTime(587.33, audioCtx.currentTime); // D5
      osc.frequency.setValueAtTime(880, audioCtx.currentTime + 0.15); // A5

      gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.6);

      osc.connect(gain);
      gain.connect(audioCtx.destination);

      osc.start();
      osc.stop(audioCtx.currentTime + 0.6);
    } catch (e) {
      console.warn("Web Audio API not allowed or supported", e);
    }
  }
}
