/* ============================================================
   xixiの待办清单 · 应用逻辑
   数据通过 window.pywebview.api 与桌面壳通信；
   在普通浏览器中打开时自动降级为 localStorage，方便调试。
   ============================================================ */
(function () {
  'use strict';

  /* ---------- 状态 ---------- */
  var todos = [];
  var filter = 'all';           // 状态筛选
  var editingId = null;
  var composePriority = 'medium';
  var composeRepeat = 'none';
  var editPriority = 'medium';
  var toastTimer = null;
  var dragId = null;

  /* ---------- DOM ---------- */
  var $ = function (id) { return document.getElementById(id); };

  var el = {
    list: $('todoList'),
    empty: $('emptyState'),
    inputText: $('inputText'),
    inputDate: $('inputDate'),
    inputRepeat: $('inputRepeat'),
    repeatField: $('repeatField'),
    addBtn: $('addBtn'),
    clearDate: $('clearDate'),
    prioritySeg: $('prioritySeg'),
    parseHint: $('parseHint'),
    modalMask: $('modalMask'),
    modalClose: $('modalClose'),
    editText: $('editText'),
    editDate: $('editDate'),
    editTime: $('editTime'),
    editRepeat: $('editRepeat'),
    editNote: $('editNote'),
    editPrioritySeg: $('editPrioritySeg'),
    editSave: $('editSave'),
    editDelete: $('editDelete'),
    toast: $('toast'),
    todayLabel: $('todayLabel'),
    heroTitle: $('heroTitle'),
    heroSub: $('heroSub'),
    progressPct: $('progressPct'),
    progressFill: $('progressFill'),
    progressNote: $('progressNote'),
    countAll: $('countAll'),
    countToday: $('countToday'),
    countPending: $('countPending'),
    countOverdue: $('countOverdue'),
    countDone: $('countDone'),
    clearDoneBtn: $('clearDoneBtn'),
    /* 窗口 / 迷你模式 */
    btnSettings: $('btnSettings'),
    btnSettingsMini: $('btnSettingsMini'),
    btnQuickAdd: $('btnQuickAdd'),
    composer: document.querySelector('.composer'),
    setAutoStart: $('setAutoStart'),
    setCollapse: $('setCollapse'),
    setAutoCollapse: $('setAutoCollapse'),
    closeSeg: $('setCloseAction'),
    menuQuit: $('menuQuit'),
    menuBackup: $('menuBackup'),
    menuRestore: $('menuRestore'),
    menuClearDone: $('menuClearDone'),
    menuUpdate: $('menuUpdate'),
    updateLabel: $('updateLabel'),
    appVersion: $('appVersion'),
    dlgMask: $('dlgMask'),
    dlgTitle: $('dlgTitle'),
    dlgDesc: $('dlgDesc'),
    dlgInput: $('dlgInput'),
    dlgOk: $('dlgOk'),
    dlgCancel: $('dlgCancel'),
    resizeGrip: $('resizeGrip'),
    settingsPanel: $('settingsPanel'),
    setBack: $('setBack'),
    setName: $('setName'),
    setNameSave: $('setNameSave'),
    setSnap: $('setSnap'),
    setTop: $('setTop'),
    sizeSeg: $('setSize'),
    setCount: $('setCount'),
    collapsedMark: $('collapsedMark'),
    btnPin: $('btnPin'),
    btnMode: $('btnMode'),
    btnMin: $('btnMin'),
    btnClose: $('btnClose'),
    miniCount: $('miniCount'),
    miniFill: $('miniFill'),
    miniStat: $('miniStat'),
    chips: $('filterChips')
  };

  /* ---------- 桌面桥接 ---------- */
  function bridge() {
    return (window.pywebview && window.pywebview.api) ? window.pywebview.api : null;
  }

  function callApi(name, arg) {
    var a = bridge();
    if (!a || typeof a[name] !== 'function') return Promise.resolve(null);
    try {
      // 支持多参数：传数组时展开调用（如 resize_window(w, h)）
      var r;
      if (arg === undefined) r = a[name]();
      else if (Object.prototype.toString.call(arg) === '[object Array]') r = a[name].apply(a, arg);
      else r = a[name](arg);
      return (r && typeof r.then === 'function') ? r : Promise.resolve(r);
    } catch (e) { return Promise.resolve(null); }
  }

  function save() {
    var payload = JSON.stringify(todos);
    var a = bridge();
    if (a && typeof a.save_todos === 'function') {
      try {
        var r = a.save_todos(payload);
        if (r && typeof r.catch === 'function') r.catch(function () {});
      } catch (e) { /* ignore */ }
    } else {
      try { localStorage.setItem('todos', payload); } catch (e) { /* ignore */ }
    }
  }

  function parseJson(raw) {
    if (!raw) return null;
    try {
      var p = (typeof raw === 'string') ? JSON.parse(raw) : raw;
      if (Array.isArray(p)) return p;
    } catch (e) { /* ignore */ }
    return null;
  }

  function localGet(key) {
    try { return parseJson(localStorage.getItem(key)) || []; } catch (e) { return []; }
  }

  function loadKey(apiName, lsKey) {
    return new Promise(function (resolve) {
      var a = bridge();
      if (!a || typeof a[apiName] !== 'function') { resolve(localGet(lsKey)); return; }
      var settled = false;
      function done(v) { if (!settled) { settled = true; resolve(v); } }
      try {
        var r = a[apiName]();
        if (r && typeof r.then === 'function') {
          r.then(function (raw) { done(parseJson(raw) || localGet(lsKey)); })
           .catch(function () { done(localGet(lsKey)); });
          return;
        }
        done(parseJson(r) || localGet(lsKey));
      } catch (e) { done(localGet(lsKey)); }
      setTimeout(function () { done(localGet(lsKey)); }, 1200);
    });
  }

  function load() {
    return loadKey('load_todos', 'todos').then(function (list) {
      return { todos: list };
    });
  }

  /* ---------- 日期与周期工具 ---------- */
  function pad(n) { return n < 10 ? '0' + n : '' + n; }

  function todayStr() {
    var d = new Date();
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  }

  function fmtDate(d) {
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  }

  function parseDate(s) {
    return new Date(s + 'T00:00:00');
  }

  function nowHM() {
    var d = new Date();
    return pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  function daysUntil(dateStr) {
    if (!dateStr) return null;
    var a = parseDate(dateStr);
    var b = parseDate(todayStr());
    return Math.round((a - b) / 86400000);
  }

  function isOverdue(t) {
    if (t.done || !t.due) return false;
    var d = daysUntil(t.due);
    return d !== null && d < 0;
  }

  function formatDue(dateStr) {
    var d = daysUntil(dateStr);
    if (d === null) return '';
    if (d < 0) return '逾期 ' + Math.abs(d) + ' 天';
    if (d === 0) return '今天';
    if (d === 1) return '明天';
    if (d === 2) return '后天';
    if (d <= 7) return d + ' 天后';
    var parts = dateStr.split('-');
    return parseInt(parts[1], 10) + '月' + parseInt(parts[2], 10) + '日';
  }

  var PRIO_TEXT = { high: '高', medium: '中', low: '低' };
  var PRIO_ORDER = { high: 0, medium: 1, low: 2 };

  var REPEAT_TEXT = {
    none: '', daily: '每天', weekday: '工作日',
    weekly: '每周', monthly: '每月', yearly: '每年'
  };

  /* ---------- 重复任务：推进到下一个周期 ---------- */

  function addPeriod(d, repeat) {
    var r = new Date(d.getTime());
    switch (repeat) {
      case 'daily':
        r.setDate(r.getDate() + 1);
        break;
      case 'weekday':
        do { r.setDate(r.getDate() + 1); } while (r.getDay() === 0 || r.getDay() === 6);
        break;
      case 'weekly':
        r.setDate(r.getDate() + 7);
        break;
      case 'monthly': {
        var day = r.getDate();
        r.setDate(1);
        r.setMonth(r.getMonth() + 1);
        var last = new Date(r.getFullYear(), r.getMonth() + 1, 0).getDate();
        r.setDate(Math.min(day, last));
        break;
      }
      case 'yearly': {
        var dd = r.getDate();
        r.setDate(1);
        r.setFullYear(r.getFullYear() + 1);
        var lastY = new Date(r.getFullYear(), r.getMonth() + 1, 0).getDate();
        r.setDate(Math.min(dd, lastY));
        break;
      }
      default:
        r.setDate(r.getDate() + 1);
    }
    return r;
  }

  function nextDueDate(dueStr, repeat) {
    if (!repeat || repeat === 'none') return dueStr;
    // 没有截止日期时以今天为基准
    var base = dueStr ? parseDate(dueStr) : parseDate(todayStr());
    var today = parseDate(todayStr());

    // 先推进至少一个周期（保证始终向前）
    base = addPeriod(base, repeat);
    if (base >= today) return fmtDate(base);

    // 若仍在过去，按周期整数倍一次追上今天，避免逐日循环几千次
    if (repeat === 'daily') {
      var days = Math.ceil((today - base) / 86400000);
      if (days > 0) base.setDate(base.getDate() + days);
    } else if (repeat === 'weekly') {
      var weeks = Math.ceil((today - base) / (7 * 86400000));
      if (weeks > 0) base.setDate(base.getDate() + weeks * 7);
    } else {
      // 工作日/每月/每年：月份与星期依赖具体历法，只能逐步推，但给足上限
      var guard = 0;
      while (base < today && guard < 3000) {
        base = addPeriod(base, repeat);
        guard++;
      }
    }
    return fmtDate(base);
  }

  /* ---------- 快速添加语法解析 ----------
     支持：!高 !中 !低   #分组   今天/明天/后天/大后天/下周X/周X
           M月D日  M-D  M/D   H点 / H点M分 / H:MM
           每天/每日 每周 每月 每年 工作日
     解析成功的关键词会从标题里移除，剩余文字作为标题。 */

  var WEEK_MAP = { '日': 0, '天': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6 };

  // 关键词后的合法边界：空格、数字、行尾、中文等非 ASCII 字符、或语法符号。
  // 中文用户基本不加空格（「明天9点开会」），所以边界要放宽到中文字符。
  var BOUND = '(?=[\\s\\d]|$|[!#]|[^\\x00-\\x7F])';

  function parseQuickInput(raw) {
    var text = ' ' + raw + ' ';
    var out = { title: '', priority: '', due: '', time: '', repeat: '' };

    // 1) 优先级
    text = text.replace(new RegExp('\\s!([高中低hml])' + BOUND, 'g'), function (_, k) {
      out.priority = (k === '高' || k === 'h') ? 'high'
        : (k === '低' || k === 'l') ? 'low' : 'medium';
      return ' ';
    });

    // 2) 重复
    text = text.replace(new RegExp('\\s(每天|每日)' + BOUND, 'g'), function () { out.repeat = 'daily'; return ' '; });
    text = text.replace(new RegExp('\\s每个?工作日' + BOUND, 'g'), function () { out.repeat = 'weekday'; return ' '; });
    text = text.replace(new RegExp('\\s(每周|每星期)' + BOUND, 'g'), function () { out.repeat = 'weekly'; return ' '; });
    text = text.replace(new RegExp('\\s每月' + BOUND, 'g'), function () { out.repeat = 'monthly'; return ' '; });
    text = text.replace(new RegExp('\\s每年' + BOUND, 'g'), function () { out.repeat = 'yearly'; return ' '; });

    // 4) 日期（必须先于时间解析：日期被替换成空格后，时间才有分隔符可用）
    var today = new Date();
    var matched = false;

    if (!matched) {
      text = text.replace(new RegExp('\\s(大后天)' + BOUND, 'g'), function () {
        var d = new Date(today); d.setDate(d.getDate() + 3);
        out.due = fmtDate(d); matched = true; return ' ';
      });
    }
    if (!matched) {
      text = text.replace(new RegExp('\\s(后天)' + BOUND, 'g'), function () {
        var d = new Date(today); d.setDate(d.getDate() + 2);
        out.due = fmtDate(d); matched = true; return ' ';
      });
    }
    if (!matched) {
      text = text.replace(new RegExp('\\s(明天|明日)' + BOUND, 'g'), function () {
        var d = new Date(today); d.setDate(d.getDate() + 1);
        out.due = fmtDate(d); matched = true; return ' ';
      });
    }
    if (!matched) {
      text = text.replace(new RegExp('\\s(今天|今日)' + BOUND, 'g'), function () {
        out.due = fmtDate(today); matched = true; return ' ';
      });
    }

    // 下周X / 本周X / 周X
    if (!matched) {
      text = text.replace(new RegExp('\\s(下|本|这)?(?:周|星期)([一二三四五六日天])' + BOUND, 'g'),
        function (_, which, w) {
          var target = WEEK_MAP[w];
          if (target === undefined) return arguments[0];
          var d = new Date(today);
          var cur = d.getDay();
          var delta = (target - cur + 7) % 7;
          if (which === '下') delta = delta === 0 ? 7 : delta + 7;
          else if (delta === 0) delta = 7;
          d.setDate(d.getDate() + delta);
          out.due = fmtDate(d); matched = true;
          return ' ';
        });
    }

    // M月D日 / M月D号
    if (!matched) {
      text = text.replace(new RegExp('\\s(\\d{1,2})月(\\d{1,2})[日号]?' + BOUND, 'g'), function (_, m, d) {
        var mm = parseInt(m, 10), dd = parseInt(d, 10);
        if (mm < 1 || mm > 12 || dd < 1 || dd > 31) return arguments[0];
        var y = today.getFullYear();
        var cand = new Date(y, mm - 1, dd);
        if (cand < new Date(y, today.getMonth(), today.getDate())) cand.setFullYear(y + 1);
        out.due = fmtDate(cand); matched = true;
        return ' ';
      });
    }

    // M-D / M/D
    if (!matched) {
      text = text.replace(new RegExp('\\s(\\d{1,2})[-/](\\d{1,2})' + BOUND, 'g'), function (_, m, d) {
        var mm = parseInt(m, 10), dd = parseInt(d, 10);
        if (mm < 1 || mm > 12 || dd < 1 || dd > 31) return arguments[0];
        var y = today.getFullYear();
        var cand = new Date(y, mm - 1, dd);
        if (cand < new Date(y, today.getMonth(), today.getDate())) cand.setFullYear(y + 1);
        out.due = fmtDate(cand); matched = true;
        return ' ';
      });
    }

    // 5) 时间（日期已让出空格）
    text = text.replace(/\s(\d{1,2})[:：](\d{2})(?=[\s]|$|[^\x00-\x7F])/g, function (_, h, m) {
      var hh = parseInt(h, 10);
      if (hh > 23) return arguments[0];
      out.time = pad(hh) + ':' + m;
      return ' ';
    });
    text = text.replace(/\s(\d{1,2})点(半|\d{1,2}分?)?(?=[\s]|$|[^\x00-\x7F])/g, function (_, h, rest) {
      var hh = parseInt(h, 10);
      if (hh > 23) return arguments[0];
      var mm = 0;
      if (rest === '半') mm = 30;
      else if (rest) {
        var n = parseInt(rest, 10);
        if (!isNaN(n) && n >= 0 && n < 60) mm = n;
      }
      out.time = pad(hh) + ':' + pad(mm);
      return ' ';
    });

    out.title = text.replace(/\s+/g, ' ').trim();
    return out;
  }

  /* ---------- 渲染 ---------- */
  function sortTodos(list) {
    // 未完成在前 → 手动顺序（拖拽过）→ 优先级 → 截止日期 → 创建时间
    return list.sort(function (a, b) {
      if (a.done !== b.done) return a.done ? 1 : -1;
      var oa = (typeof a.order === 'number') ? a.order : Infinity;
      var ob = (typeof b.order === 'number') ? b.order : Infinity;
      if (oa !== ob) return oa - ob;
      var pa = PRIO_ORDER[a.priority] === undefined ? 1 : PRIO_ORDER[a.priority];
      var pb = PRIO_ORDER[b.priority] === undefined ? 1 : PRIO_ORDER[b.priority];
      if (pa !== pb) return pa - pb;
      if (a.due && b.due) return a.due < b.due ? -1 : a.due > b.due ? 1 : 0;
      if (a.due) return -1;
      if (b.due) return 1;
      return (b.createdAt || 0) - (a.createdAt || 0);
    });
  }

  function visibleTodos() {
    var t = todayStr();
    var out;
    switch (filter) {
      case 'today':
        out = todos.filter(function (x) { return !x.done && x.due === t; });
        break;
      case 'pending':
        out = todos.filter(function (x) { return !x.done; });
        break;
      case 'overdue':
        out = todos.filter(isOverdue);
        break;
      case 'done':
        out = todos.filter(function (x) { return x.done; });
        break;
      default:
        out = todos.slice();
    }
    return sortTodos(out);
  }

  var FILTER_TITLE = {
    all: '全部待办', today: '今天的待办', pending: '未完成',
    overdue: '已逾期', done: '已完成'
  };

  function heroTitleText() {
    return FILTER_TITLE[filter];
  }

  function render() {
    var list = visibleTodos();

    el.list.innerHTML = '';
    list.forEach(function (t) { el.list.appendChild(buildItem(t)); });

    el.empty.hidden = list.length > 0;
    el.list.style.display = list.length ? '' : 'none';

    updateStats();
  }

  function tag(cls, text) {
    var s = document.createElement('span');
    s.className = cls;
    s.textContent = text;
    return s;
  }

  function buildItem(t) {
    var li = document.createElement('li');
    li.className = 'todo-item' + (t.done ? ' is-done' : '') + (isOverdue(t) ? ' is-overdue' : '');
    li.setAttribute('data-id', t.id);
    li.setAttribute('draggable', 'true');

    // 拖拽把手
    var handle = document.createElement('span');
    handle.className = 'drag-handle';
    handle.title = '拖动排序';
    handle.innerHTML = '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="9" cy="6" r="1.5"/><circle cx="15" cy="6" r="1.5"/><circle cx="9" cy="12" r="1.5"/><circle cx="15" cy="12" r="1.5"/><circle cx="9" cy="18" r="1.5"/><circle cx="15" cy="18" r="1.5"/></svg>';

    // 勾选框
    var btn = document.createElement('button');
    btn.className = 'check' + (t.done ? ' is-checked' : '');
    btn.title = t.done ? '标记为未完成' : (t.repeat && t.repeat !== 'none' ? '完成并滚到下一次' : '标记为完成');
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.6 4.6L19 7.2"/></svg>';
    btn.addEventListener('click', function () { toggle(t.id); });

    // 主体
    var main = document.createElement('div');
    main.className = 'todo-main';

    var title = document.createElement('div');
    title.className = 'todo-title';
    title.textContent = t.title;
    main.appendChild(title);

    if (t.note) {
      var note = document.createElement('div');
      note.className = 'todo-note';
      note.textContent = t.note;
      main.appendChild(note);
    }

    var meta = document.createElement('div');
    meta.className = 'todo-meta';

    var pt = document.createElement('span');
    pt.className = 'tag tag-' + (t.priority || 'medium');
    // 迷你卡片窄，只显示「高/中/低」；完整模式补上「优先级」
    pt.innerHTML = '<span>' + PRIO_TEXT[t.priority || 'medium'] + '</span>' +
                   '<span class="prio-full">优先级</span>';
    meta.appendChild(pt);

    if (t.due) {
      var diff = daysUntil(t.due);
      var dt = tag('tag tag-date' + (diff === 0 ? ' is-today' : '') + (isOverdue(t) ? ' tag-overdue' : ''),
        formatDue(t.due) + (t.time ? ' ' + t.time : ''));
      meta.appendChild(dt);
    } else if (t.time) {
      meta.appendChild(tag('tag tag-date', t.time));
    }

    if (t.repeat && t.repeat !== 'none') {
      var rt = tag('tag tag-repeat', '↻ ' + REPEAT_TEXT[t.repeat]);
      meta.appendChild(rt);
    }

    main.appendChild(meta);

    // 操作
    var acts = document.createElement('div');
    acts.className = 'todo-actions';

    var editBtn = document.createElement('button');
    editBtn.className = 'icon-btn';
    editBtn.title = '编辑';
    editBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M15.5 4.6l3.9 3.9M4.5 19.5l.9-3.9L16 5a1.8 1.8 0 012.5 0l.5.5a1.8 1.8 0 010 2.5L8.4 18.6l-3.9.9z"/></svg>';
    editBtn.addEventListener('click', function () { openModal(t.id); });

    var delBtn = document.createElement('button');
    delBtn.className = 'icon-btn danger';
    delBtn.title = '删除';
    delBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9.5 7V5.4A1.4 1.4 0 0110.9 4h2.2a1.4 1.4 0 011.4 1.4V7M6.5 7l.8 12a1.6 1.6 0 001.6 1.5h6.2a1.6 1.6 0 001.6-1.5L17.5 7"/></svg>';
    delBtn.addEventListener('click', function () { remove(t.id); });

    acts.appendChild(editBtn);
    acts.appendChild(delBtn);

    li.appendChild(handle);
    li.appendChild(btn);
    li.appendChild(main);
    li.appendChild(acts);

    bindDrag(li, t.id);
    return li;
  }

  /* ---------- 拖拽排序 ---------- */
  function bindDrag(li, id) {
    li.addEventListener('dragstart', function (e) {
      dragId = id;
      li.classList.add('is-dragging');
      try { e.dataTransfer.setData('text/plain', id); } catch (err) { /* ignore */ }
      if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
    });

    li.addEventListener('dragend', function () {
      dragId = null;
      li.classList.remove('is-dragging');
      var marks = el.list.querySelectorAll('.drop-before, .drop-after');
      for (var i = 0; i < marks.length; i++) {
        marks[i].classList.remove('drop-before', 'drop-after');
      }
    });

    li.addEventListener('dragover', function (e) {
      if (!dragId || dragId === id) return;
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
      var r = li.getBoundingClientRect();
      var after = (e.clientY - r.top) > r.height / 2;
      li.classList.toggle('drop-after', after);
      li.classList.toggle('drop-before', !after);
    });

    li.addEventListener('dragleave', function () {
      li.classList.remove('drop-before', 'drop-after');
    });

    li.addEventListener('drop', function (e) {
      if (!dragId || dragId === id) return;
      e.preventDefault();
      var r = li.getBoundingClientRect();
      var after = (e.clientY - r.top) > r.height / 2;
      li.classList.remove('drop-before', 'drop-after');
      moveTodo(dragId, id, after);
    });
  }

  function moveTodo(srcId, targetId, after) {
    var visible = visibleTodos();
    var ids = visible.map(function (x) { return x.id; });
    var from = ids.indexOf(srcId);
    if (from < 0) return;
    ids.splice(from, 1);
    var to = ids.indexOf(targetId);
    if (to < 0) return;
    ids.splice(after ? to + 1 : to, 0, srcId);

    // 按新顺序给可见项编号，其余任务保持原有相对关系
    ids.forEach(function (id, i) {
      var t = findTodo(id);
      if (t) t.order = i * 10;
    });

    save();
    render();
  }

  /* ---------- 统计 ---------- */
  function updateStats() {
    var t = todayStr();
    var all = todos.length;
    var done = 0, pending = 0, overdue = 0, todayN = 0;
    todos.forEach(function (x) {
      if (x.done) { done++; }
      else {
        pending++;
        if (x.due === t) todayN++;
        if (isOverdue(x)) overdue++;
      }
    });

    setCount(el.countAll, all);
    setCount(el.countToday, todayN);
    setCount(el.countPending, pending);
    setCount(el.countOverdue, overdue);
    setCount(el.countDone, done);

    var pct = all ? Math.round((done / all) * 100) : 0;
    el.progressPct.textContent = pct + '%';
    el.progressFill.style.width = pct + '%';
    el.progressNote.textContent = all
      ? '已完成 ' + done + ' / ' + all + ' 项' + (overdue ? '，' + overdue + ' 项已逾期' : '')
      : '还没有待办，先添加一条吧';

    if (el.miniCount) setCount(el.miniCount, pending);
    if (el.miniFill) el.miniFill.style.width = pct + '%';
    if (el.miniStat) el.miniStat.textContent = done + ' / ' + all + ' 完成';

    el.heroTitle.textContent = heroTitleText();
    var shown = visibleTodos().length;
    if (filter === 'done') {
      el.heroSub.textContent = shown + ' 项已完成';
    } else if (filter === 'all') {
      el.heroSub.textContent = '共 ' + shown + ' 项 · ' + pending + ' 项未完成';
    } else {
      el.heroSub.textContent = shown + ' 项待处理';
    }
  }

  function setCount(node, n) {
    if (!node) return;
    node.textContent = n;
    if (n === 0) node.classList.add('is-zero');
    else node.classList.remove('is-zero');
  }

  /* ---------- 操作 ---------- */
  function addTodo() {
    var raw = el.inputText.value.trim();
    if (!raw) { el.inputText.focus(); return; }

    var q = parseQuickInput(raw);
    var title = q.title || raw;

    var task = {
      id: 't' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7),
      title: title,
      priority: q.priority || composePriority,
      due: q.due || el.inputDate.value || '',
      time: q.time || '',
      repeat: q.repeat || composeRepeat || 'none',
      note: '',
      done: false,
      createdAt: Date.now()
    };

    // 新任务排在最前：给一个比现有 order 更小的值
    var minOrder = null;
    todos.forEach(function (x) {
      if (typeof x.order === 'number') {
        if (minOrder === null || x.order < minOrder) minOrder = x.order;
      }
    });
    if (minOrder !== null) task.order = minOrder - 10;

    todos.unshift(task);

    el.inputText.value = '';
    el.inputDate.value = '';
    setComposeRepeat('none');
    syncDateField();
    updateParseHint();
    // 抽屉保持打开：连着记几条是常态，加完一条就收反而碍事。
    // 点抽屉外面或按 Esc 才收起。
    el.inputText.focus();
    save();
    render();

    var extras = [];
    if (task.due) extras.push(formatDue(task.due));
    if (task.time) extras.push(task.time);
    if (task.repeat !== 'none') extras.push(REPEAT_TEXT[task.repeat]);
    toast('已添加' + (extras.length ? '：' + extras.join(' · ') : ''));
  }

  function toggle(id) {
    var t = findTodo(id);
    if (!t) return;

    if (!t.done && t.repeat && t.repeat !== 'none') {
      // 重复任务：完成后直接滚到下一次，保持未完成
      var next = nextDueDate(t.due, t.repeat);
      t.lastDoneAt = Date.now();
      t.doneCount = (t.doneCount || 0) + 1;
      t.due = next;
      t.done = false;
      t.doneAt = null;
      save();
      render();
      toast('已完成 · 下次 ' + formatDue(next) + (t.time ? ' ' + t.time : ''));
      return;
    }

    t.done = !t.done;
    t.doneAt = t.done ? Date.now() : null;
    save();
    render();
  }

  function remove(id) {
    var idx = -1;
    for (var i = 0; i < todos.length; i++) if (todos[i].id === id) { idx = i; break; }
    if (idx < 0) return;
    var name = todos[idx].title;
    todos.splice(idx, 1);
    save();
    render();
    toast('已删除：' + (name.length > 18 ? name.slice(0, 18) + '…' : name));
  }

  function clearDone() {
    var n = 0;
    todos = todos.filter(function (t) { if (t.done) { n++; return false; } return true; });
    if (!n) { toast('没有已完成的待办'); return; }
    save();
    render();
    toast('已清除 ' + n + ' 项已完成');
  }

  /* ---------- 弹窗 ---------- */
  function openModal(id) {
    var t = findTodo(id);
    if (!t) return;
    editingId = id;
    editPriority = t.priority || 'medium';

    el.editText.value = t.title;
    el.editDate.value = t.due || '';
    el.editTime.value = t.time || '';
    el.editRepeat.value = t.repeat || 'none';
    el.editNote.value = t.note || '';
    syncSeg(el.editPrioritySeg, editPriority);

    el.modalMask.hidden = false;
    // 弹窗是整屏操作，标题栏（图钉/最小化/关闭）留在上面又挡又乱
    document.body.classList.add('modal-open');
    setTimeout(function () { el.editText.focus(); el.editText.select(); }, 60);
  }

  function closeModal() {
    el.modalMask.hidden = true;
    document.body.classList.remove('modal-open');
    editingId = null;
  }

  function findTodo(id) {
    for (var i = 0; i < todos.length; i++) if (todos[i].id === id) return todos[i];
    return null;
  }

  function saveEdit() {
    var t = findTodo(editingId);
    if (!t) { closeModal(); return; }
    var text = el.editText.value.trim();
    if (!text) { toast('内容不能为空'); el.editText.focus(); return; }

    t.title = text;
    t.priority = editPriority;
    t.due = el.editDate.value || '';
    t.time = el.editTime.value || '';
    t.repeat = el.editRepeat.value || 'none';
    t.note = el.editNote.value.trim();

    save();
    closeModal();
    render();
    toast('已保存');
  }

  /* ---------- 分段控件 ---------- */
  function syncSeg(seg, value) {
    if (!seg) return;
    var btns = seg.querySelectorAll('.seg-btn');
    for (var i = 0; i < btns.length; i++) {
      btns[i].classList.toggle('is-active', btns[i].getAttribute('data-priority') === value);
    }
  }

  /* ---------- Toast ---------- */
  function toast(msg) {
    el.toast.textContent = msg;
    el.toast.hidden = false;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.toast.hidden = true; }, 2400);
  }

  /* ---------- 通用输入 / 确认弹窗 ----------
     WebView2 不支持 window.prompt()，confirm() 的行为在各版本也不一致，
     所以统一用自绘弹窗，返回 Promise，风格与整体玻璃材质一致。 */
  var dlgResolve = null;

  function openDialog(opts) {
    if (!el.dlgMask) {
      // 极端兜底：界面缺少弹窗节点时退回原生（浏览器预览用）
      if (opts.input) {
        var v = window.prompt(opts.title || '', opts.value || '');
        return Promise.resolve(v === null ? null : v);
      }
      return Promise.resolve(window.confirm(opts.title || '') ? true : false);
    }
    return new Promise(function (resolve) {
      dlgResolve = resolve;
      el.dlgTitle.textContent = opts.title || '';
      var hasDesc = !!(opts.desc && opts.desc.length);
      el.dlgDesc.hidden = !hasDesc;
      el.dlgDesc.textContent = hasDesc ? opts.desc : '';
      el.dlgInput.hidden = !opts.input;
      if (opts.input) {
        el.dlgInput.value = opts.value || '';
        el.dlgInput.maxLength = opts.maxlength || 16;
      }
      el.dlgOk.textContent = opts.okText || '确定';
      el.dlgMask.hidden = false;
      if (opts.input) {
        setTimeout(function () { el.dlgInput.focus(); el.dlgInput.select(); }, 30);
      }
    });
  }

  function closeDialog(result) {
    if (el.dlgMask) el.dlgMask.hidden = true;
    var r = dlgResolve;
    dlgResolve = null;
    if (r) r(result);
  }

  function askText(title, value, maxlength) {
    return openDialog({ title: title, input: true, value: value || '', maxlength: maxlength || 16 });
  }

  function askConfirm(title, desc, okText) {
    return openDialog({ title: title, desc: desc, input: false, okText: okText || '确定' });
  }

  if (el.dlgOk) {
    el.dlgOk.addEventListener('click', function () {
      var inputShown = el.dlgInput && !el.dlgInput.hidden;
      closeDialog(inputShown ? el.dlgInput.value : true);
    });
  }
  if (el.dlgCancel) {
    el.dlgCancel.addEventListener('click', function () { closeDialog(null); });
  }
  if (el.dlgMask) {
    el.dlgMask.addEventListener('click', function (e) {
      if (e.target === el.dlgMask) closeDialog(null);
    });
  }
  if (el.dlgInput) {
    el.dlgInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); el.dlgOk.click(); }
    });
  }

  /* ---------- 日期占位状态 ---------- */
  function syncDateField() {
    var field = el.inputDate.closest('.date-field');
    if (!field) return;
    field.classList.toggle('is-empty', !el.inputDate.value);
  }

  /* ---------- 添加区的重复周期 ----------
     和日期并排：都是「什么时候做」的信息。
     选中非「不重复」时整块变强调色，一眼能看出这条是周期任务。 */
  function setComposeRepeat(value) {
    composeRepeat = value || 'none';
    if (el.inputRepeat) el.inputRepeat.value = composeRepeat;
    if (el.repeatField) el.repeatField.classList.toggle('is-set', composeRepeat !== 'none');
  }

  /* ---------- 快速语法提示 ---------- */
  function updateParseHint() {
    if (!el.parseHint) return;
    var raw = el.inputText.value.trim();
    if (!raw) { el.parseHint.hidden = true; return; }

    var q = parseQuickInput(raw);
    var bits = [];
    if (q.due) bits.push(formatDue(q.due));
    if (q.time) bits.push(q.time);
    if (q.repeat) {
      bits.push(REPEAT_TEXT[q.repeat]);
      // 文字里写了「每天/每周」就顺手把下拉同步过去，避免两处显示不一致
      if (q.repeat !== composeRepeat) setComposeRepeat(q.repeat);
    }
    if (q.priority) bits.push('优先级' + PRIO_TEXT[q.priority]);

    if (!bits.length) { el.parseHint.hidden = true; return; }
    el.parseHint.textContent = bits.join(' · ');
    el.parseHint.hidden = false;
  }

  /* ---------- 检查更新 ----------
     version.json 放在仓库根目录。GitHub 直连在国内经常不通，
     所以按「jsDelivr → gh-proxy → ghfast → GitHub raw」顺序依次尝试，
     任何一个成功即返回。全部失败则视为网络问题，不打扰用户。 */

  var REPO = 'NiUKinGDoM/xixi-todo';
  // 顺序说明：raw 永远是最新的，放第一位保证发版后立刻生效
  // （jsDelivr 对 @main 有最长 12 小时缓存，放后面做兜底）
  // 顺序有讲究：jsDelivr 对 @main 有最长 12 小时缓存，发版后可能还返回旧清单，
  // 所以先问两个 GitHub 反代，raw 在前一台机器上常被拦，放最后兜底。
  var UPDATE_SOURCES = [
    // ghfast 排第一：实测它的缓存最松，发版后基本能立刻拿到新清单。
    // gh-proxy 会按路径缓存，发版后可能还吐旧版本（并行取最高版本兜住了这点）。
    'https://ghfast.top/https://raw.githubusercontent.com/' + REPO + '/main/version.json',
    'https://gh-proxy.com/https://raw.githubusercontent.com/' + REPO + '/main/version.json',
    'https://cdn.jsdelivr.net/gh/' + REPO + '@main/version.json',
    'https://raw.githubusercontent.com/' + REPO + '/main/version.json'
  ];

  var updateState = { checking: false, latest: null, hasUpdate: false };
  var currentVersion = '';

  function parseVer(v) {
    return String(v || '').replace(/^v/i, '').split('.')
      .map(function (x) { return parseInt(x, 10) || 0; });
  }

  function compareVer(a, b) {
    var pa = parseVer(a), pb = parseVer(b);
    var n = Math.max(pa.length, pb.length);
    for (var i = 0; i < n; i++) {
      var x = pa[i] || 0, y = pb[i] || 0;
      if (x > y) return 1;
      if (x < y) return -1;
    }
    return 0;
  }

  function fetchWithTimeout(url, ms) {
    return new Promise(function (resolve, reject) {
      var done = false;
      var timer = setTimeout(function () {
        if (!done) { done = true; reject(new Error('timeout')); }
      }, ms);

      fetch(url, { cache: 'no-store' })
        .then(function (r) {
          if (!r.ok) throw new Error('http ' + r.status);
          return r.json();
        })
        .then(function (data) {
          if (!done) { done = true; clearTimeout(timer); resolve(data); }
        })
        .catch(function (e) {
          if (!done) { done = true; clearTimeout(timer); reject(e); }
        });
    });
  }

  function fetchUpdateManifest() {
    // 并行问所有源，取版本号最高的那份。
    // 之前是串行「第一个成功的就用」，结果撞上镜像缓存就废了：
    // gh-proxy 缓存着 1.5.0，后面的 ghfast 明明已经有 1.5.1，
    // 却因为前一个已经"成功"而根本不会被问到，用户永远收不到新版本。
    var jobs = UPDATE_SOURCES.map(function (url) {
      return fetchWithTimeout(url, 6000).then(function (data) {
        if (!data || !data.version) throw new Error('bad manifest');
        return data;
      }).catch(function () { return null; });
    });

    return Promise.all(jobs).then(function (list) {
      var best = null;
      list.forEach(function (data) {
        if (!data) return;
        if (!best || compareVer(data.version, best.version) > 0) best = data;
      });
      if (!best) throw new Error('all sources failed');
      return best;
    });
  }

  function setUpdateBadge(on) {
    updateState.hasUpdate = !!on;
    if (el.btnSettings) el.btnSettings.classList.toggle('has-update', !!on);
    if (el.btnSettingsMini) el.btnSettingsMini.classList.toggle('has-update', !!on);
    if (el.updateLabel) {
      el.updateLabel.textContent = on ? '发现新版本 ' + updateState.latest : '检查更新';
    }
  }

  function checkUpdate(silent) {
    if (updateState.checking) return Promise.resolve(null);
    updateState.checking = true;
    if (!silent && el.updateLabel) el.updateLabel.textContent = '检查中…';

    // 没拿到本地版本号就先补取。否则空版本会和任何远端版本比较，
    // 导致「明明是最新版却提示有新版本」的误报。
    var ready = currentVersion ? Promise.resolve() : initVersion();

    return ready.then(function () {
      if (!currentVersion) throw new Error('local version unknown');
      return fetchUpdateManifest();
    }).then(function (data) {
      updateState.checking = false;
      updateState.latest = String(data.version);
      var newer = compareVer(data.version, currentVersion) > 0;

      if (newer) {
        setUpdateBadge(true);
        if (silent) {
          toast('发现新版本 v' + data.version + '，进设置即可更新');
        } else {
          askToUpdate(data);
        }
      } else {
        setUpdateBadge(false);
        if (!silent) toast('已是最新版本 v' + currentVersion);
      }
      return data;
    }).catch(function () {
      updateState.checking = false;
      if (el.updateLabel) el.updateLabel.textContent = '检查更新';
      if (!silent) toast('检查失败，请检查网络');
      return null;
    });
  }

  function askToUpdate(data) {
    var desc = '当前 v' + currentVersion + ' → 最新 v' + data.version +
               (data.notes ? '\n\n' + data.notes : '') +
               '\n\n下载新安装包后双击运行即可覆盖升级，待办数据不受影响。';
    askConfirm('发现新版本 v' + data.version, desc, '下载安装包').then(function (ok) {
      if (!ok) return;
      var dl = data.downloads || {};
      // 只发安装包：下载 setup 覆盖安装，和旧版共用同一个安装目录与数据目录
      var url = dl.setup || dl.ghproxy || dl.ghfast || dl.github ||
                ('https://github.com/' + REPO + '/releases/latest');
      callApi('open_url', url);
    });
  }

  function initVersion() {
    return callApi('get_version').then(function (v) {
      if (v) {
        currentVersion = String(v);
        if (el.appVersion) el.appVersion.textContent = 'v' + currentVersion;
      }
      return currentVersion;
    });
  }

  if (el.menuUpdate) {
    el.menuUpdate.addEventListener('click', function () {
      if (updateState.hasUpdate) {
        // 已经知道有新版本，直接弹详情，不用再查一遍
        fetchUpdateManifest().then(askToUpdate).catch(function () {
          toast('检查失败，请检查网络');
        });
      } else {
        checkUpdate(false);
      }
    });
  }
  /* ---------- 备份 / 导入 ---------- */
  function backup() {
    var payload = JSON.stringify({ version: 3, todos: todos }, null, 2);
    var a = bridge();
    if (a && typeof a.export_backup === 'function') {
      callApi('export_backup', payload).then(function (path) {
        if (path && path !== '') toast('已导出到：' + String(path).split(/[\\/]/).pop());
        else toast('已取消导出');
      });
      return;
    }
    // 浏览器降级：直接下载
    try {
      var blob = new Blob([payload], { type: 'application/json' });
      var url = URL.createObjectURL(blob);
      var link = document.createElement('a');
      link.href = url;
      link.download = 'todos-backup.json';
      link.click();
      URL.revokeObjectURL(url);
      toast('已导出备份');
    } catch (e) { toast('导出失败'); }
  }

  function restore() {
    var a = bridge();
    if (!a || typeof a.import_backup !== 'function') {
      toast('仅桌面版支持导入');
      return;
    }
    callApi('import_backup').then(function (raw) {
      if (!raw) { toast('已取消导入'); return; }
      var data = null;
      try { data = (typeof raw === 'string') ? JSON.parse(raw) : raw; } catch (e) { data = null; }
      if (!data) { toast('文件格式不正确'); return; }

      var incoming = Array.isArray(data) ? data : data.todos;
      if (!Array.isArray(incoming)) { toast('文件里没有待办数据'); return; }

      var go = todos.length
        ? askConfirm('覆盖当前待办？', '导入会替换当前的 ' + todos.length + ' 条待办，此操作不可撤销。', '导入')
        : Promise.resolve(true);

      go.then(function (ok) {
        if (!ok) return;
        todos = incoming;
        save();
        render();
        toast('已导入 ' + todos.length + ' 条待办');
      });
    });
  }

  /* ---------- 事件绑定 ---------- */
  el.addBtn.addEventListener('click', addTodo);

  el.inputText.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); addTodo(); }
  });
  el.inputText.addEventListener('input', updateParseHint);

  el.inputDate.addEventListener('change', syncDateField);
  el.inputDate.addEventListener('input', syncDateField);

  var dateField = el.inputDate.closest('.date-field');
  if (dateField) {
    dateField.addEventListener('click', function (e) {
      if (e.target === el.clearDate || el.clearDate.contains(e.target)) return;
      if (typeof el.inputDate.showPicker === 'function') {
        try { el.inputDate.showPicker(); } catch (err) { /* 已打开时忽略 */ }
      }
    });
  }

  el.clearDate.addEventListener('click', function (e) {
    e.preventDefault();
    e.stopPropagation();
    el.inputDate.value = '';
    syncDateField();
  });

  el.prioritySeg.addEventListener('click', function (e) {
    var b = e.target.closest('.seg-btn');
    if (!b) return;
    composePriority = b.getAttribute('data-priority');
    syncSeg(el.prioritySeg, composePriority);
  });

  if (el.inputRepeat) {
    el.inputRepeat.addEventListener('change', function () {
      setComposeRepeat(el.inputRepeat.value);
      updateParseHint();
    });
  }

  el.editPrioritySeg.addEventListener('click', function (e) {
    var b = e.target.closest('.seg-btn');
    if (!b) return;
    editPriority = b.getAttribute('data-priority');
    syncSeg(el.editPrioritySeg, editPriority);
  });

  el.modalClose.addEventListener('click', closeModal);
  el.editSave.addEventListener('click', saveEdit);
  el.editDelete.addEventListener('click', function () {
    if (editingId) { remove(editingId); closeModal(); }
  });

  el.modalMask.addEventListener('click', function (e) {
    if (e.target === el.modalMask) closeModal();
  });

  el.editText.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); saveEdit(); }
    if (e.key === 'Escape') { e.preventDefault(); closeModal(); }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && el.dlgMask && !el.dlgMask.hidden) {
      e.preventDefault();
      closeDialog(null);
      return;
    }
    if (e.key === 'Escape' && el.settingsPanel && !el.settingsPanel.hidden) {
      e.preventDefault();
      closeSettings();
      return;
    }
    if (e.key === 'Escape' && !el.modalMask.hidden) closeModal();
    if (e.key === 'Escape' && document.body.classList.contains('is-adding')) closeComposer();
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); addTodo(); }
  });

  el.clearDoneBtn.addEventListener('click', clearDone);

  /* ---------- 设置页 ---------- */
  function openSettings() {
    if (!el.settingsPanel) return;
    el.settingsPanel.hidden = false;
    document.body.classList.add('is-settings');
    renderSettings();
  }

  function closeSettings() {
    if (!el.settingsPanel) return;
    el.settingsPanel.hidden = true;
    document.body.classList.remove('is-settings');
    // 下次进来从头看，别停在上次滚到的位置
    var body = el.settingsPanel.querySelector('.settings-body');
    if (body) body.scrollTop = 0;
  }

  function renderSettings() {
    if (el.setName) el.setName.value = winState.app_name || 'xixiの待办';
    if (el.setSnap) el.setSnap.classList.toggle('is-on', winState.snap);
    if (el.setTop) el.setTop.classList.toggle('is-on', winState.on_top);
    if (el.setCollapse) el.setCollapse.classList.toggle('is-on', winState.collapse_min);
    if (el.setAutoCollapse) el.setAutoCollapse.classList.toggle('is-on', winState.auto_collapse);
    if (el.closeSeg) {
      var cbs = el.closeSeg.querySelectorAll('button');
      for (var k = 0; k < cbs.length; k++) {
        cbs[k].classList.toggle('is-active',
          cbs[k].getAttribute('data-close') === winState.close_action);
      }
    }
    if (el.setAutoStart) el.setAutoStart.classList.toggle('is-on', winState.autostart);
    if (el.sizeSeg) {
      var btns = el.sizeSeg.querySelectorAll('button');
      for (var i = 0; i < btns.length; i++) {
        btns[i].classList.toggle('is-active',
          Number(btns[i].getAttribute('data-preset')) === winState.mini_preset);
      }
    }
    if (el.setCount) el.setCount.textContent = String(todos.length);
  }

  if (el.btnSettings) el.btnSettings.addEventListener('click', openSettings);
  if (el.btnSettingsMini) el.btnSettingsMini.addEventListener('click', openSettings);
  if (el.setBack) el.setBack.addEventListener('click', closeSettings);

  /* ---------- 设置页：整行都能点开关 ----------
     开关本体只有 44×25，很多人习惯点行里的文字，点偏一点就没反应，
     看着就像「开关坏了」。把整行的点击都转给开关。 */
  document.querySelectorAll('.set-row').forEach(function (row) {
    var sw = row.querySelector('.switch');
    if (!sw) return;
    if (row.classList.contains('as-btn') || row.classList.contains('column')) return;
    row.classList.add('is-clickable');
    row.addEventListener('click', function (e) {
      // 点开关本身时交给它自己的 handler，别重复触发一次
      if (e.target.closest('.switch')) return;
      sw.click();
    });
  });

  /* ---------- 小卡片的「+」添加抽屉 ----------
     380 宽的小卡片里添加区常驻太占地，列表被压到只剩两三行。
     改成底部一颗「+」，点开才展开输入区，选完自动收起。 */
  function isMiniMode() {
    return document.body.classList.contains('mode-mini');
  }

  function openComposer() {
    if (!isMiniMode()) {
      if (el.inputText) el.inputText.focus();
      return;
    }
    document.body.classList.add('is-adding');
    setTimeout(function () {
      if (el.inputText) el.inputText.focus();
    }, 80);
  }

  function closeComposer() {
    document.body.classList.remove('is-adding');
  }

  if (el.btnQuickAdd) {
    el.btnQuickAdd.addEventListener('click', function (e) {
      e.stopPropagation();
      if (document.body.classList.contains('is-adding')) closeComposer();
      else openComposer();
    });
  }

  // 点抽屉以外的地方就收起来（不设遮罩层，小卡片里遮罩会更压抑）
  document.addEventListener('mousedown', function (e) {
    if (!document.body.classList.contains('is-adding')) return;
    if (el.composer && el.composer.contains(e.target)) return;
    if (el.btnQuickAdd && el.btnQuickAdd.contains(e.target)) return;
    closeComposer();
  });

  function commitName() {
    var name = String(el.setName.value || '').trim().slice(0, 16);
    if (!name) { el.setName.value = winState.app_name || ''; return; }
    callApi('set_app_name', name).then(function (raw) {
      var st = parseState(raw);
      if (st) applyWindowState(st); else applyAppName(name);
      if (el.setName) el.setName.value = winState.app_name;
      toast('已重命名为「' + winState.app_name + '」');
    });
  }

  if (el.setNameSave) el.setNameSave.addEventListener('click', commitName);
  if (el.setName) {
    el.setName.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); commitName(); }
    });
  }

  if (el.setSnap) {
    el.setSnap.addEventListener('click', function () {
      var next = !winState.snap;
      callApi('set_snap', next ? '1' : '').then(function (raw) {
        var st = parseState(raw);
        if (st) applySnap(st.snap); else applySnap(next);
        renderSettings();
        // 注意：这里绝对不能立刻 snap_now()。
        // 一吸附就会触发 on_moved 的防抖判定，再叠上「贴边自动收起」，
        // 窗口会当场缩成小条、设置页跟着消失 —— 用户只会觉得开关「点不动」。
        // 吸附是拖动结束时的动作，不该由改设置触发。
        toast(next ? '自动贴边：开' : '自动贴边：关');
      });
    });
  }

  if (el.setCollapse) {
    el.setCollapse.addEventListener('click', function () {
      var next = !winState.collapse_min;
      callApi('set_collapse_min', next ? '1' : '').then(function (raw) {
        var st = parseState(raw);
        if (st) applyWindowState(st); else { winState.collapse_min = next; renderSettings(); }
        toast(next ? '最小化时收进边缘（已关掉拖边自动收起）'
                   : '最小化时不再收边');
      });
    });
  }

  if (el.setAutoCollapse) {
    el.setAutoCollapse.addEventListener('click', function () {
      var next = !winState.auto_collapse;
      callApi('set_auto_collapse', next ? '1' : '').then(function (raw) {
        var st = parseState(raw);
        if (st) applyWindowState(st); else { winState.auto_collapse = next; renderSettings(); }
        toast(next ? '拖到边缘松手就收进边缘（已关掉最小化收边）'
                   : '贴边只吸附，不自动收起');
      });
    });
  }

  if (el.closeSeg) {
    el.closeSeg.addEventListener('click', function (e) {
      var b = e.target.closest('button[data-close]');
      if (!b) return;
      var val = b.getAttribute('data-close');
      callApi('set_close_action', val).then(function (raw) {
        var st = parseState(raw);
        if (st) applyWindowState(st);
        renderSettings();
        toast(val === 'tray' ? '关闭按钮改为收进托盘' : '关闭按钮改为退出应用');
      });
    });
  }

  if (el.setAutoStart) {
    el.setAutoStart.addEventListener('click', function () {
      var next = !winState.autostart;
      callApi('set_autostart', next ? '1' : '').then(function (raw) {
        var st = parseState(raw);
        if (st) applyWindowState(st);
        renderSettings();
        // 写注册表可能被安全软件拦掉，开关会原地不动。
        // 这种情况必须说清楚，否则用户只会觉得「点了没反应」。
        if (winState.autostart !== next) {
          toast('设置失败，可能被安全软件拦截');
          return;
        }
        toast(next ? '已开启开机自启动' : '已关闭开机自启动');
      });
    });
  }

  if (el.setTop) {
    el.setTop.addEventListener('click', function () {
      callApi('toggle_on_top').then(function (raw) {
        var st = parseState(raw);
        if (st) applyOnTop(st.on_top);
        renderSettings();
        toast(winState.on_top ? '已置顶' : '已取消置顶');
      });
    });
  }

  if (el.sizeSeg) {
    el.sizeSeg.addEventListener('click', function (e) {
      var b = e.target.closest('button[data-preset]');
      if (!b) return;
      var idx = Number(b.getAttribute('data-preset'));
      callApi('set_mini_preset', idx).then(function (raw) {
        var st = parseState(raw);
        if (st) applyPreset(st.mini_preset === undefined ? idx : st.mini_preset);
        renderSettings();
        toast('小卡片尺寸：' + presetName(idx));
      });
    });
  }

  if (el.menuQuit) {
    el.menuQuit.addEventListener('click', function () {
      askConfirm('退出应用？', '退出后待办都还在，下次打开继续。', '退出')
        .then(function (ok) { if (ok) callApi('close_window'); });
    });
  }

  if (el.menuBackup) el.menuBackup.addEventListener('click', backup);
  if (el.menuRestore) el.menuRestore.addEventListener('click', restore);
  if (el.menuClearDone) {
    el.menuClearDone.addEventListener('click', function () {
      var finished = todos.filter(function (t) { return t.done; }).length;
      if (!finished) { toast('没有已完成的待办'); return; }
      askConfirm('清除已完成？', '将删除 ' + finished + ' 项已完成的待办，此操作不可撤销。', '清除')
        .then(function (ok) { if (ok) clearDone(); });
    });
  }

  // 拖动标题栏结束后触发一次吸附（pywebview 的拖动在前端收不到结束事件，
  // 但 mouseup 是可以监听的，借此得知“拖完了”）
  // 拖动是 JS 逐帧调 move 模拟的，拖到一半停手超过 0.45s 会被后端当成
  // 「拖完了」直接吸到边上。所以按住时先关掉吸附判定，松手再补一次吸附。
  var dragRegion = document.querySelector('.pywebview-drag-region');
  var draggingNow = false;
  if (dragRegion) {
    dragRegion.addEventListener('mousedown', function () {
      draggingNow = true;
      callApi('set_dragging', '1');
    });
  }
  document.addEventListener('mouseup', function () {
    // 只有真的从标题栏按下过才收尾，否则每次点按钮都会触发一次吸附
    if (!draggingNow) return;
    draggingNow = false;
    callApi('set_dragging', '').then(function () {
      if (!winState.snap) return;
      // 松手后这一刻才真正决定窗口命运：只是吸边，还是直接收成小条。
      // 后端把结论放在返回值里，前端必须照着切 UI —— 否则窗口变成
      // 104x20，页面还按 380x560 排版，整块界面就被压扁了。
      setTimeout(function () {
        callApi('snap_now').then(function (raw) {
          var st = parseState(raw);
          if (st) applyWindowState(st);
        });
      }, 60);
    });
  });

  /* ---------- 右下角自由缩放 ---------- */
  // 无边框窗口没有系统边框，用户没法拖边改大小。
  // 这里用右下角手柄 + screenX/screenY（屏幕绝对坐标）计算位移：
  // 用屏幕坐标而不是 clientX，是因为窗口自身在变尺寸，页面坐标会跟着漂移。
  var rz = null;

  function onResizeMove(e) {
    if (!rz) return;
    var w = Math.max(300, Math.round(rz.w + (e.screenX - rz.sx)));
    var h = Math.max(400, Math.round(rz.h + (e.screenY - rz.sy)));
    var now = Date.now();
    if (now - rz.tick < 26) return;
    rz.tick = now;
    rz.last = [w, h];
    callApi('resize_window', [w, h]);
  }

  function endResize() {
    if (!rz) return;
    var last = rz.last;
    rz = null;
    document.body.classList.remove('is-resizing');
    window.removeEventListener('mousemove', onResizeMove);
    var done = last ? callApi('resize_window', [last[0], last[1]]) : Promise.resolve(null);
    done.then(function () { return callApi('finish_resize'); }).then(function (raw) {
      var st = parseState(raw);
      if (st) applyWindowState(st);
    });
  }

  if (el.resizeGrip) {
    el.resizeGrip.addEventListener('mousedown', function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      rz = {
        sx: e.screenX,
        sy: e.screenY,
        w: window.innerWidth,
        h: window.innerHeight,
        tick: 0,
        last: null
      };
      document.body.classList.add('is-resizing');
      window.addEventListener('mousemove', onResizeMove);
      window.addEventListener('mouseup', endResize, { once: true });
    });
  }

  /* ---------- 筛选（侧边栏与迷你胶囊共用同一状态） ---------- */
  function syncNavActive() {
    var all = document.querySelectorAll('[data-filter]');
    for (var i = 0; i < all.length; i++) {
      all[i].classList.toggle('is-active', all[i].getAttribute('data-filter') === filter);
    }
  }

  document.querySelectorAll('[data-filter]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      filter = btn.getAttribute('data-filter');
      syncNavActive();
      render();
    });
  });

  /* ---------- 窗口控制 ---------- */
  var winState = {
    mode: 'mini', on_top: true, snap: true,
    app_name: 'xixiの待办', mini_preset: 1,
    collapsed: false, collapse_edge: '',
    collapse_min: true, auto_collapse: true,
    close_action: 'quit', autostart: false
  };

  var SIZE_NAMES = ['紧凑', '标准', '宽大'];

  function presetName(idx) {
    return SIZE_NAMES[idx] || '自定义';
  }

  function parseState(raw) {
    if (!raw) return null;
    try {
      var st = typeof raw === 'string' ? JSON.parse(raw) : raw;
      return (st && typeof st === 'object') ? st : null;
    } catch (e) { return null; }
  }

  function applyAppName(name) {
    if (!name) return;
    winState.app_name = name;
    // 小卡片标题与侧边栏标题联动（窗口标题由 Python 侧同步）
    var miniTitle = document.querySelector('.minibar-title');
    if (miniTitle) miniTitle.textContent = name;
    var brand = document.querySelector('.brand-text h1');
    if (brand) brand.textContent = name;
    if (el.inputText) {
      el.inputText.placeholder = '添加待办…';
    }
  }

  function applySnap(on) {
    winState.snap = !!on;
    if (el.setSnap) el.setSnap.classList.toggle('is-on', winState.snap);
  }

  function applyPreset(idx) {
    winState.mini_preset = idx;
    if (el.sizeSeg) {
      var bs = el.sizeSeg.querySelectorAll('button');
      for (var i = 0; i < bs.length; i++) {
        bs[i].classList.toggle('is-active',
          Number(bs[i].getAttribute('data-preset')) === idx);
      }
    }
  }

  function applyWindowState(st) {
    if (!st) return;
    // 这四个开关的状态也必须同步进来。
    // 之前只应用 mode/on_top/snap/preset/name/collapsed，
    // 结果 setAutoCollapse / setCollapse / setCloseAction / setAutoStart
    // 在点完之后 renderSettings() 读到的还是旧值，开关看上去「点不动」。
    if (typeof st.collapse_min === 'boolean') winState.collapse_min = st.collapse_min;
    if (typeof st.auto_collapse === 'boolean') winState.auto_collapse = st.auto_collapse;
    if (typeof st.close_action === 'string') winState.close_action = st.close_action;
    if (typeof st.autostart === 'boolean') winState.autostart = st.autostart;

    applyMode(st.mode === 'full' ? 'full' : 'mini');
    applyOnTop(st.on_top);
    applySnap(st.snap);
    applyPreset(st.mini_preset === undefined ? 1 : st.mini_preset);
    applyAppName(st.app_name);
    applyCollapsed(st.collapsed, st.collapse_edge);
    renderSettings();
  }

  function applyMode(mode) {
    winState.mode = mode;
    var isMini = mode === 'mini';
    document.body.classList.toggle('mode-mini', isMini);
    document.body.classList.toggle('mode-full', !isMini);
    if (!isMini) closeComposer();
    if (el.btnMode) el.btnMode.title = isMini ? '切换到完整视图' : '收成桌面小卡片';
    syncNavActive();
  }

  function applyOnTop(onTop) {
    winState.on_top = !!onTop;
    if (el.btnPin) {
      el.btnPin.classList.toggle('is-on', winState.on_top);
      el.btnPin.title = winState.on_top ? '取消置顶' : '置顶到最前';
    }
    if (el.setTop) el.setTop.classList.toggle('is-on', winState.on_top);
  }

  function applyCollapsed(collapsed, edge) {
    var on = !!collapsed;
    winState.collapsed = on;
    winState.collapse_edge = edge || '';
    var vertical = on && (edge === 'left' || edge === 'right');
    var horizontal = on && (edge === 'top' || edge === 'bottom');
    document.body.classList.toggle('is-collapsed', on);
    document.body.classList.toggle('collapsed-v', vertical);
    document.body.classList.toggle('collapsed-h', horizontal);
    if (el.collapsedMark) el.collapsedMark.hidden = !on;
    if (on) closeSettings();
  }

  function expandFromEdge() {
    if (!winState.collapsed || winState.expanding) return;
    winState.expanding = true;
    // 先同步置位：不要在等后端返回的这段时间里，
    // 让冒泡上来的 click 再触发一次展开
    winState.collapsed = false;
    callApi('expand_window').then(function (raw) {
      winState.expanding = false;
      var st = parseState(raw);
      if (st) applyWindowState(st);
    });
  }

  function syncWindowState() {
    callApi('get_window_state').then(function (raw) {
      var st = parseState(raw);
      if (st) applyWindowState(st);
    });
  }

  function initWindowUi() {
    applyMode(window.innerWidth < 720 ? 'mini' : 'full');
    // 这里通常还拿不到桥接（app.js 跑得比 pywebview 注入早），
    // 真正的同步由 start() 里桥接就绪后的那次负责。
    syncWindowState();
  }

  /* ---------- 兜底轮询：后端自己收起时前端也得知道 ----------
     拖动时鼠标滑出窗口，前端收不到 mouseup，自动收起就只能由后端的
     防抖线程完成 —— 那条路没有返回值。这里对一下状态，别让页面
     还按卡片尺寸排版、窗口却已经缩成 20px 的缝。
     只在「贴边自动收起」开着时才需要（其它路径都有返回值）。 */
  setInterval(function () {
    if (!winState.auto_collapse) return;
    callApi('get_collapsed_state').then(function (raw) {
      var st = parseState(raw);
      if (!st) return;
      var on = !!st.collapsed;
      var edge = st.collapse_edge || '';
      if (on === !!winState.collapsed && (!on || edge === winState.collapse_edge)) return;
      applyCollapsed(on, edge);
    });
  }, 700);

  if (el.btnMode) {
    el.btnMode.addEventListener('click', function () {
      var next = (winState.mode === 'mini') ? 'full' : 'mini';
      callApi('set_mode', next).then(function (raw) {
        var st = parseState(raw);
        applyMode(st && st.mode ? st.mode : next);
      });
    });
  }

  if (el.btnPin) {
    el.btnPin.addEventListener('click', function () {
      callApi('toggle_on_top').then(function (raw) {
        var st = parseState(raw);
        if (st) applyOnTop(st.on_top);
        toast(winState.on_top ? '已置顶' : '已取消置顶');
      });
    });
  }

  if (el.btnMin) {
    el.btnMin.addEventListener('click', function () {
      callApi('minimize_window').then(function (raw) {
        var st = parseState(raw);
        // 收边开关打开时后端返回收起状态；关掉则返回空（走系统最小化）
        if (st && st.collapsed) {
          applyWindowState(st);
          return;
        }
        if (st) applyWindowState(st);
      });
    });
  }

  if (el.collapsedMark) {
    el.collapsedMark.addEventListener('click', expandFromEdge);
  }
  document.addEventListener('click', function () {
    if (winState.collapsed) expandFromEdge();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && winState.collapsed) { e.preventDefault(); expandFromEdge(); }
  });

  if (el.btnClose) {
    el.btnClose.addEventListener('click', function () {
      save();
      callApi('close_window');
    });
  }

  /* ---------- 启动 ---------- */
  var bootSeq = 0;

  function boot() {
    var mySeq = ++bootSeq;
    var d = new Date();
    var week = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()];
    el.todayLabel.textContent = (d.getMonth() + 1) + '月' + d.getDate() + '日 周' + week;

    return load().then(function (data) {
      if (mySeq !== bootSeq) return;
      todos = Array.isArray(data.todos) ? data.todos : [];
      render();
      // 小卡片里输入框在抽屉中，别抢焦点（否则一启动就弹开抽屉）
      if (!document.body.classList.contains('mode-mini')) el.inputText.focus();
    });
  }

  function start() {
    // app.js 作为页面普通脚本执行时，pywebview 往往尚未注入 window.pywebview，
    // 所以先启动一次，桥接就绪后再启动一次以载入磁盘数据。
    syncDateField();
    initWindowUi();
    initVersion();
    boot();

    window.addEventListener('pywebviewready', function () {
      boot();
      syncWindowState();
    });

    var tries = 0;
    var timer = setInterval(function () {
      tries++;
      var a = bridge();
      if (a && typeof a.load_todos === 'function') {
        clearInterval(timer);
        boot();
        // 桥接就绪后必须再同步一次窗口状态：
        // initWindowUi 那次基本都拿不到 api，不同步的话开关会一直显示
        // 前端写死的默认值，跟磁盘里的真实配置对不上。
        syncWindowState();
        // 先拿到本地版本号，再延迟静默检查更新，避免误报
        initVersion().then(function () {
          setTimeout(function () { checkUpdate(true); }, 3000);
        });
      } else if (tries > 40) {
        clearInterval(timer);
      }
    }, 250);
  }

  start();

  // 暴露给冒烟测试
  window.__todoApp = {
    get todos() { return todos; },
    set todos(v) { todos = v; },
    addTodo: addTodo,
    toggle: toggle,
    remove: remove,
    render: render,
    visibleTodos: visibleTodos,
    isOverdue: isOverdue,
    formatDue: formatDue,
    daysUntil: daysUntil,
    nextDueDate: nextDueDate,
    parseQuickInput: parseQuickInput,
    setComposeRepeat: setComposeRepeat,
    getComposeRepeat: function () { return composeRepeat; },
    moveTodo: moveTodo,
    boot: boot,
    start: start,
    applyMode: applyMode,
    applyOnTop: applyOnTop,
    applyWindowState: applyWindowState,
    syncNavActive: syncNavActive,
    getFilter: function () { return filter; },
    /* 更新检查 */
    compareVer: compareVer,
    parseVer: parseVer,
    getUpdateState: function () { return updateState; },
    setUpdateBadge: setUpdateBadge,
    checkUpdate: checkUpdate,
    getCurrentVersion: function () { return currentVersion; }
  };
})();
