/**
 * Client-side Pedobraz-Passport Bridge (window.pbPassport)
 * Handles postMessage iframe communication, solveTask API and ad-free attributes.
 */

(function () {
  const state = {
    user: null,
    ad_free: true,
    listeners: new Set(),
    adFreeListeners: new Set()
  };

  async function refreshSession() {
    try {
      const res = await fetch("/api/passport/me");
      if (res.ok) {
        const data = await res.json();
        state.user = data.user;
        setAdFree(true);
        notifyListeners();
        return data;
      }
    } catch (e) {
      console.warn("Passport bridge: failed to fetch /api/passport/me", e);
    }
    return { user: null, ad_free: true };
  }

  function setAdFree(value = true) {
    state.ad_free = true;
    document.documentElement.setAttribute("data-ad-free", "true");
  }

  function notifyListeners() {
    state.listeners.forEach(fn => {
      try { fn(state.user); } catch (err) { console.error(err); }
    });
  }

  async function solveTask(taskId, score, courseworkId = null) {
    try {
      const res = await fetch("/api/passport/solve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          task_id: taskId,
          score: Math.max(0, Math.min(100, score)),
          coursework_id: courseworkId
        })
      });
      const data = await res.json();
      if (res.ok && state.user && data.recess_seconds !== undefined) {
        state.user.recess_seconds = data.recess_seconds;
        notifyListeners();
      }
      return data;
    } catch (err) {
      console.error("Passport bridge: solveTask error", err);
      return { ok: false, error: err.message };
    }
  }

  async function spendRecess(seconds) {
    try {
      const res = await fetch("/api/passport/recess/spend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seconds })
      });
      const data = await res.json();
      if (res.ok && state.user && data.remaining_seconds !== undefined) {
        state.user.recess_seconds = data.remaining_seconds;
        notifyListeners();
      }
      return data;
    } catch (err) {
      return { ok: false, error: err.message };
    }
  }

  // Cross-frame communication filter
  window.addEventListener("message", async (event) => {
    // Безопасность origin: только доверенный источник того же хоста
    if (event.origin !== window.location.origin) {
      return;
    }

    const data = event.data;
    if (!data || typeof data !== "object") return;

    if (data.type === "PB_TASK_SOLVED" && data.task_id) {
      const score = typeof data.score === "number" ? data.score : 100;
      await solveTask(data.task_id, score, data.coursework_id || null);
    }
  });

  const pbPassport = {
    isAdFree: () => true,
    getUser: () => state.user,
    solveTask,
    spendRecess,
    refreshSession,
    onUserChange: (cb) => {
      state.listeners.add(cb);
      if (state.user) cb(state.user);
      return () => state.listeners.delete(cb);
    },
    onAdFreeChange: (cb) => {
      state.adFreeListeners.add(cb);
      cb(state.ad_free);
      return () => state.adFreeListeners.delete(cb);
    }
  };

  window.pbPassport = pbPassport;

  // Initial session refresh
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", refreshSession);
  } else {
    refreshSession();
  }
})();
