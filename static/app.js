(function () {
  // Theme itself is already applied by the inline <head> script (avoids a
  // flash of the wrong theme). This just wires up the toggle button.
  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("theme-toggle");
    if (!btn) return;
    updateIcon(document.documentElement.getAttribute("data-theme"));

    btn.addEventListener("click", function () {
      var current = document.documentElement.getAttribute("data-theme");
      var next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("irrigation-theme", next);
      updateIcon(next);
    });
  });

  function updateIcon(theme) {
    var btn = document.getElementById("theme-toggle");
    if (!btn) return;
    btn.innerHTML = theme === "dark" ? SUN_ICON : MOON_ICON;
  }

  var SUN_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path></svg>';
  var MOON_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z"></path></svg>';
})();
