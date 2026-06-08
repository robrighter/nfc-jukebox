/* NFC Jukebox — minimal vanilla JS */

// Write-tag page polling is handled inline in write_tag.html.
// Settings preview is handled inline in settings.html.
// This file is loaded on every page for any shared utilities.

// Auto-refresh dashboard scans table every 10s if on the dashboard page.
(function () {
  if (window.location.pathname !== '/') return;
  setInterval(function () {
    fetch('/api/status')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var badge = document.querySelector('.card .badge');
        if (badge && data.nfc && data.nfc.mode) {
          badge.textContent = data.nfc.mode;
        }
      })
      .catch(function () {});
  }, 5000);
}());
