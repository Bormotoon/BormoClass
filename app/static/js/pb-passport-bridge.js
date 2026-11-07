/**
 * Client-side Pedobraz-Passport Bridge (window.pbPassport)
 * Loads and delegates to the full PedObraz Passport system.
 */
if (typeof window !== "undefined" && !window.pbPassport) {
  // If pb-passport.js is already loaded, window.pbPassport is active.
  // Otherwise, load /static/js/pb-passport.js dynamically
  const s = document.createElement("script");
  s.src = "/static/js/pb-passport.js";
  document.head.appendChild(s);
}
