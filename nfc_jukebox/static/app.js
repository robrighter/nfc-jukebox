/* NFC Jukebox — minimal vanilla JS */

// Write-tag page polling is handled inline in write_tag.html.
// Settings preview is handled inline in settings.html.
// This file is loaded on every page for any shared utilities.

// Dashboard: now-playing hero, transport + volume controls, status refresh.
(function () {
  if (window.location.pathname !== '/') return;

  function setText(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function updateHero(np, contextDevice) {
    var hero = document.getElementById('hero');
    if (!hero) return;
    var art = document.getElementById('np-art');
    var blank = document.getElementById('np-art-blank');

    if (np && np.playing) {
      hero.classList.remove('hero--idle');
      setText('np-context', 'Now playing on ' + (contextDevice || 'the speaker'));
      setText('np-title', np.title || 'Playing');
      setText('np-artist', (np.artist || '') + (np.album ? ' — ' + np.album : ''));
      if (art) {
        if (np.art) { art.src = np.art; art.hidden = false; if (blank) blank.hidden = true; }
        else { art.hidden = true; if (blank) blank.hidden = false; }
      }
    } else {
      hero.classList.add('hero--idle');
      setText('np-context', 'Nothing playing');
      setText('np-title', 'Nothing playing');
      setText('np-artist', '');
      if (art) art.hidden = true;
      if (blank) blank.hidden = false;
    }
  }

  function updateVolume(vol) {
    if (vol === undefined || vol === null) return;
    var fill = document.getElementById('vol-fill');
    var num = document.getElementById('vol-num');
    if (fill) fill.style.width = vol + '%';
    if (num) num.textContent = vol;
  }

  function flash(btn) {
    if (!btn) return;
    btn.classList.add('pressed');
    setTimeout(function () { btn.classList.remove('pressed'); }, 180);
  }

  // ---- transport controls (play / pause / back / forward) ----
  var transport = document.getElementById('transport');
  if (transport) {
    transport.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-media]');
      if (!btn) return;
      flash(btn);
      btn.disabled = true;
      fetch('/api/alexa/media', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: btn.getAttribute('data-media')})
      })
        .then(function (r) { return r.json().catch(function () { return {}; }); })
        .then(function (d) { if (d && d.ok === false) console.error('media:', d.error); })
        .catch(function () {})
        .finally(function () {
          btn.disabled = false;
          // Refresh now-playing shortly after a transport action.
          setTimeout(refresh, 1200);
        });
    });
  }

  // ---- volume controls ----
  var volume = document.getElementById('volume');
  if (volume) {
    volume.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-vol]');
      if (!btn) return;
      flash(btn);
      btn.disabled = true;
      fetch('/api/alexa/volume', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: btn.getAttribute('data-vol')})
      })
        .then(function (r) { return r.json().catch(function () { return {}; }); })
        .then(function (d) { if (d && d.ok) updateVolume(d.volume); else if (d) console.error('volume:', d.error); })
        .catch(function () {})
        .finally(function () { btn.disabled = false; });
    });
  }

  // ---- status polling ----
  function refresh() {
    return fetch('/api/status')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var badge = document.querySelector('.card .badge');
        if (badge && data.nfc && data.nfc.mode) badge.textContent = data.nfc.mode;
        updateHero(data.now_playing, data.alexa_device_name);
        updateVolume(data.volume);
      })
      .catch(function () {});
  }

  refresh();
  setInterval(refresh, 5000);
}());
