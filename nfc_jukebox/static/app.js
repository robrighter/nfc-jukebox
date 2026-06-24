/* NFC Jukebox — minimal vanilla JS */

// Write-tag page polling is handled inline in write_tag.html.
// Settings preview is handled inline in settings.html.
// This file is loaded on every page for any shared utilities.

// Auto-refresh dashboard status + now-playing every few seconds.
(function () {
  if (window.location.pathname !== '/') return;

  function updateNowPlaying(np) {
    var card = document.getElementById('now-playing-card');
    if (!card) return;
    if (np && np.playing) {
      card.style.display = '';
      var title = document.getElementById('np-title');
      var artist = document.getElementById('np-artist');
      var art = document.getElementById('np-art');
      if (title) title.textContent = np.title || '';
      if (artist) {
        artist.textContent = (np.artist || '') + (np.album ? ' — ' + np.album : '');
      }
      if (art) {
        if (np.art) { art.src = np.art; art.style.display = ''; }
        else { art.style.display = 'none'; }
      }
    } else {
      card.style.display = 'none';
    }
  }

  setInterval(function () {
    fetch('/api/status')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var badge = document.querySelector('.card .badge');
        if (badge && data.nfc && data.nfc.mode) {
          badge.textContent = data.nfc.mode;
        }
        updateNowPlaying(data.now_playing);
      })
      .catch(function () {});
  }, 5000);
}());
