(function () {
  window.__errors = [];
  window.addEventListener('error', function (e) { window.__errors.push(e.message); });
  setTimeout(function () {
    var A = window.__todoApp;
    var out = [];
    out.push('当前版本=[' + A.getCurrentVersion() + ']');

    // 静默检查（不会弹 confirm）
    A.checkUpdate(true).then(function (data) {
      if (!data) {
        out.push('RESULT=FETCH_FAILED');
        out.push('errors=' + window.__errors.join(';'));
      } else {
        out.push('RESULT=OK');
        out.push('远端版本=' + data.version);
        out.push('下载源数=' + Object.keys(data.downloads || {}).length);
        out.push('hasUpdate=' + A.getUpdateState().hasUpdate);
        out.push('角标=' + document.getElementById('btnMenu').classList.contains('has-update'));
        out.push('按钮文案=' + document.getElementById('updateLabel').textContent);
      }
      document.title = out.join(' ;; ');
    }).catch(function (e) {
      out.push('RESULT=EXCEPTION ' + e.message);
      document.title = out.join(' ;; ');
    });
  }, 1200);
})();
