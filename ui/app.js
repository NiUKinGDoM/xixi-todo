/* ============================================================
   xixiの待办清单 · 应用逻辑
   数据通过 window.pywebview.api 与桌面壳通信；
   在普通浏览器中打开时自动降级为 localStorage，方便调试。
   ============================================================ */
(function () {
  'use strict';

  /* ---------- 状态 ---------- */
  var todos = [];
  var groups = [];              // 分组名数组，顺序即显示顺序
  var filter = 'all';           // 状态筛选
  var groupFilter = 'all';      // 'all' 或分组名
  var editingId = null;
  var composePriority = 'medium';
  var editPriority = 'medium';
  var editGroup = '';
  var toastTimer = null;
  var dragId = null;

  var DEFAULT_GROUPS = ['工作', '生活', '学习', '其他'];

  /* ---------- DOM ---------- */
  var $ = function (id) { return document.getElementById(id); };

  var el = {
    list: $('todoList'),
    empty: $('emptyState'),
    inputText: $('inputText'),
    inputDate: $('inputDate'),
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
    editGroupChips: $('editGroupChips'),
    editPrioritySeg: $('editPrioritySeg'),
    editSave: $('editSave'),
    editDelete: $('editDelete'),
    toast: $('toast'),
    todayLabel: $('todayLabel'),
    heroTitle: $('heroTitle'),
    heroSub: $('heroSub'),
    groupBtn: $('groupBtn'),
    groupMenu: $('groupMenu'),
    groupList: $('groupList'),
    addGroupBtn: $('addGroupBtn'),
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
    btnMenu: $('btnMenu'),
    appMenu: $('appMenu'),
    menuBackup: $('menuBackup'),
    menuRestore: $('menuRestore'),
    menuClearDone: $('menuClearDone'),
    menuUpdate: $('menuUpdate'),
    updateLabel: $('updateLabel'),
    appVersion: $('appVersion'),
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
      var r = (arg === undefined) ? a[name]() : a[name](arg);
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

  function saveGroups() {
    var payload = JSON.stringify(groups);
    var a = bridge();
    if (a && typeof a.save_groups === 'function') {
      try {
        var r = a.save_groups(payload);
        if (r && typeof r.catch === 'function') r.catch(function () {});
      } catch (e) { /* ignore */ }
    } else {
      try { localStorage.setItem('groups', payload); } catch (e) { /* ignore */ }
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
    return Promise.all([loadKey('load_todos', 'todos'), loadKey('load_groups', 'groups')])
      .then(function (res) {
        return { todos: res[0], groups: res[1] };
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
    var out = { title: '', priority: '', group: '', due: '', time: '', repeat: '' };

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

    // 3) 分组
    text = text.replace(/\s#([^\s#]{1,12})/g, function (_, g) {
      out.group = g;
      return ' ';
    });

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

  function inGroup(t) {
    if (groupFilter === 'all') return true;
    return (t.group || '') === groupFilter;
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
    out = out.filter(inGroup);
    return sortTodos(out);
  }

  var FILTER_TITLE = {
    all: '全部待办', today: '今天的待办', pending: '未完成',
    overdue: '已逾期', done: '已完成'
  };

  function heroTitleText() {
    if (groupFilter === 'all') return FILTER_TITLE[filter];
    return groupFilter + ' · ' + FILTER_TITLE[filter];
  }

  function render() {
    var list = visibleTodos();

    el.list.innerHTML = '';
    list.forEach(function (t) { el.list.appendChild(buildItem(t)); });

    el.empty.hidden = list.length > 0;
    el.list.style.display = list.length ? '' : 'none';

    updateStats();
    renderGroupList();
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

    if (t.group) {
      meta.appendChild(tag('tag tag-group', t.group));
    }

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

  /* ---------- 分组 ---------- */
  function ensureGroups() {
    if (!groups.length) groups = DEFAULT_GROUPS.slice();
    // 任务里出现但分组列表没有的，补进去
    todos.forEach(function (t) {
      if (t.group && groups.indexOf(t.group) < 0) groups.push(t.group);
    });
  }

  function renderGroupList() {
    if (!el.groupList) return;
    var counts = {};
    todos.forEach(function (t) {
      if (t.done) return;
      var g = t.group || '';
      counts[g] = (counts[g] || 0) + 1;
    });

    el.groupList.innerHTML = '';

    var all = document.createElement('button');
    all.className = 'group-item' + (groupFilter === 'all' ? ' is-active' : '');
    all.setAttribute('data-group', 'all');
    all.innerHTML = '<span>全部分组</span><em>' +
      todos.filter(function (t) { return !t.done; }).length + '</em>';
    all.addEventListener('click', function () { setGroupFilter('all'); });
    el.groupList.appendChild(all);

    groups.forEach(function (g) {
      var b = document.createElement('button');
      b.className = 'group-item' + (groupFilter === g ? ' is-active' : '');
      b.setAttribute('data-group', g);
      b.innerHTML = '<span></span><em>' + (counts[g] || 0) + '</em>';
      b.firstChild.textContent = g;
      b.addEventListener('click', function () { setGroupFilter(g); });
      el.groupList.appendChild(b);
    });
  }

  function setGroupFilter(g) {
    groupFilter = g;
    el.groupMenu.hidden = true;
    if (el.groupBtn) el.groupBtn.classList.remove('is-open');
    render();
  }

  function renderGroupMenu() {
    if (!el.groupMenu) return;
    el.groupMenu.innerHTML = '';

    function item(name, label) {
      var b = document.createElement('button');
      b.className = 'gm-item' + (groupFilter === name ? ' is-active' : '');
      b.setAttribute('data-group', name);
      b.textContent = label;
      b.addEventListener('click', function () { setGroupFilter(name); });
      el.groupMenu.appendChild(b);
    }

    item('all', '全部分组');
    groups.forEach(function (g) { item(g, g); });

    var add = document.createElement('button');
    add.className = 'gm-item gm-add';
    add.textContent = '＋ 新建分组';
    add.addEventListener('click', function () {
      el.groupMenu.hidden = true;
      createGroup();
    });
    el.groupMenu.appendChild(add);
  }

  function createGroup() {
    if (!el.groupList || !el.groupList.parentNode) {
      // 完整模式下用侧边栏的输入框逻辑
    }
    var name = window.prompt('新分组名称', '');
    if (name === null) return;
    name = String(name).trim().slice(0, 12);
    if (!name) return;
    if (groups.indexOf(name) >= 0) { toast('分组已存在'); return; }
    groups.push(name);
    saveGroups();
    render();
    toast('已新建分组：' + name);
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
      repeat: q.repeat || 'none',
      group: q.group || '',
      note: '',
      done: false,
      createdAt: Date.now()
    };

    // 新分组自动登记
    if (task.group && groups.indexOf(task.group) < 0) {
      groups.push(task.group);
      saveGroups();
    }

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
    syncDateField();
    updateParseHint();
    el.inputText.focus();
    save();
    render();

    var extras = [];
    if (task.due) extras.push(formatDue(task.due));
    if (task.time) extras.push(task.time);
    if (task.repeat !== 'none') extras.push(REPEAT_TEXT[task.repeat]);
    if (task.group) extras.push('#' + task.group);
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
    editGroup = t.group || '';

    el.editText.value = t.title;
    el.editDate.value = t.due || '';
    el.editTime.value = t.time || '';
    el.editRepeat.value = t.repeat || 'none';
    el.editNote.value = t.note || '';
    syncSeg(el.editPrioritySeg, editPriority);
    renderGroupChips();

    el.modalMask.hidden = false;
    setTimeout(function () { el.editText.focus(); el.editText.select(); }, 60);
  }

  function closeModal() {
    el.modalMask.hidden = true;
    editingId = null;
  }

  function findTodo(id) {
    for (var i = 0; i < todos.length; i++) if (todos[i].id === id) return todos[i];
    return null;
  }

  function renderGroupChips() {
    if (!el.editGroupChips) return;
    el.editGroupChips.innerHTML = '';

    function chip(name, label) {
      var b = document.createElement('button');
      b.className = 'g-chip' + (editGroup === name ? ' is-active' : '');
      b.setAttribute('data-group', name);
      b.textContent = label;
      b.addEventListener('click', function () {
        editGroup = name;
        renderGroupChips();
      });
      el.editGroupChips.appendChild(b);
    }

    chip('', '未分组');
    groups.forEach(function (g) { chip(g, g); });

    var add = document.createElement('button');
    add.className = 'g-chip g-add';
    add.textContent = '＋';
    add.title = '新建分组';
    add.addEventListener('click', createGroup);
    el.editGroupChips.appendChild(add);
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
    t.group = editGroup || '';
    t.note = el.editNote.value.trim();

    if (t.group && groups.indexOf(t.group) < 0) {
      groups.push(t.group);
      saveGroups();
    }

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

  /* ---------- 日期占位状态 ---------- */
  function syncDateField() {
    var field = el.inputDate.closest('.date-field');
    if (!field) return;
    field.classList.toggle('is-empty', !el.inputDate.value);
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
    if (q.repeat) bits.push(REPEAT_TEXT[q.repeat]);
    if (q.priority) bits.push('优先级' + PRIO_TEXT[q.priority]);
    if (q.group) bits.push('#' + q.group);

    if (!bits.length) { el.parseHint.hidden = true; return; }
    el.parseHint.textContent = bits.join(' · ');
    el.parseHint.hidden = false;
  }

  /* ---------- 检查更新 ----------
     version.json 放在仓库根目录。GitHub 直连在国内经常不通，
     所以按「jsDelivr → gh-proxy → ghfast → GitHub raw」顺序依次尝试，
     任何一个成功即返回。全部失败则视为网络问题，不打扰用户。 */

  var REPO = 'NiUKinGDoM/xixi-todo';
  var UPDATE_SOURCES = [
    'https://cdn.jsdelivr.net/gh/' + REPO + '@main/version.json',
    'https://gh-proxy.com/https://raw.githubusercontent.com/' + REPO + '/main/version.json',
    'https://ghfast.top/https://raw.githubusercontent.com/' + REPO + '/main/version.json',
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
    var i = 0;
    function next() {
      if (i >= UPDATE_SOURCES.length) return Promise.reject(new Error('all sources failed'));
      var url = UPDATE_SOURCES[i++];
      return fetchWithTimeout(url, 6000).then(function (data) {
        if (!data || !data.version) throw new Error('bad manifest');
        return data;
      }).catch(function () { return next(); });
    }
    return next();
  }

  function setUpdateBadge(on) {
    updateState.hasUpdate = !!on;
    if (el.btnMenu) el.btnMenu.classList.toggle('has-update', !!on);
    if (el.updateLabel) {
      el.updateLabel.textContent = on ? '发现新版本 ' + updateState.latest : '检查更新';
    }
  }

  function checkUpdate(silent) {
    if (updateState.checking) return Promise.resolve(null);
    updateState.checking = true;
    if (!silent && el.updateLabel) el.updateLabel.textContent = '检查中…';

    return fetchUpdateManifest().then(function (data) {
      updateState.checking = false;
      updateState.latest = String(data.version);
      var newer = compareVer(data.version, currentVersion) > 0;

      if (newer) {
        setUpdateBadge(true);
        if (silent) {
          toast('发现新版本 v' + data.version + '，点 ⋯ 查看');
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
    var notes = data.notes ? '\n\n更新内容：\n' + data.notes : '';
    var msg = '发现新版本 v' + data.version + '（当前 v' + currentVersion + '）' + notes +
              '\n\n是否打开下载页面？';
    if (window.confirm(msg)) {
      var dl = data.downloads || {};
      var url = dl.jsdelivr || dl.ghproxy || dl.github ||
                ('https://github.com/' + REPO + '/releases/latest');
      callApi('open_url', url);
    }
  }

  function initVersion() {
    callApi('get_version').then(function (v) {
      currentVersion = String(v || '');
      if (el.appVersion) el.appVersion.textContent = 'v' + currentVersion;
    });
  }

  if (el.menuUpdate) {
    el.menuUpdate.addEventListener('click', function () {
      el.appMenu.hidden = true;
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
    var payload = JSON.stringify({ version: 2, groups: groups, todos: todos }, null, 2);
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

      if (todos.length && !window.confirm('导入会覆盖当前的 ' + todos.length + ' 条待办，继续？')) {
        return;
      }

      todos = incoming;
      if (!Array.isArray(data.groups)) {
        groups = (groups && groups.length) ? groups : DEFAULT_GROUPS.slice();
      } else {
        groups = data.groups.slice();
      }
      ensureGroups();
      save();
      saveGroups();
      render();
      toast('已导入 ' + todos.length + ' 条待办');
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
    if (e.key === 'Escape' && !el.modalMask.hidden) closeModal();
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); addTodo(); }
  });

  el.clearDoneBtn.addEventListener('click', clearDone);
  if (el.menuClearDone) el.menuClearDone.addEventListener('click', function () {
    el.appMenu.hidden = true;
    clearDone();
  });

  if (el.btnMenu) {
    el.btnMenu.addEventListener('click', function (e) {
      e.stopPropagation();
      el.appMenu.hidden = !el.appMenu.hidden;
    });
  }
  if (el.menuBackup) el.menuBackup.addEventListener('click', function () {
    el.appMenu.hidden = true;
    backup();
  });
  if (el.menuRestore) el.menuRestore.addEventListener('click', function () {
    el.appMenu.hidden = true;
    restore();
  });

  document.addEventListener('click', function (e) {
    if (el.appMenu && !el.appMenu.hidden) {
      if (!el.appMenu.contains(e.target) && e.target !== el.btnMenu) {
        el.appMenu.hidden = true;
      }
    }
    if (el.groupMenu && !el.groupMenu.hidden) {
      if (!el.groupMenu.contains(e.target) && !el.groupBtn.contains(e.target)) {
        el.groupMenu.hidden = true;
        el.groupBtn.classList.remove('is-open');
      }
    }
  });

  if (el.addGroupBtn) el.addGroupBtn.addEventListener('click', createGroup);

  if (el.groupBtn) {
    el.groupBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      if (el.groupMenu.hidden) {
        renderGroupMenu();
        el.groupMenu.hidden = false;
        el.groupBtn.classList.add('is-open');
      } else {
        el.groupMenu.hidden = true;
        el.groupBtn.classList.remove('is-open');
      }
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
  var winState = { mode: 'mini', on_top: true };

  function parseState(raw) {
    if (!raw) return null;
    try {
      var st = typeof raw === 'string' ? JSON.parse(raw) : raw;
      return (st && typeof st === 'object') ? st : null;
    } catch (e) { return null; }
  }

  function applyMode(mode) {
    winState.mode = mode;
    var isMini = mode === 'mini';
    document.body.classList.toggle('mode-mini', isMini);
    document.body.classList.toggle('mode-full', !isMini);
    if (el.btnMode) el.btnMode.title = isMini ? '切换到完整视图' : '收成桌面小卡片';
    syncNavActive();
  }

  function applyOnTop(onTop) {
    winState.on_top = !!onTop;
    if (el.btnPin) {
      el.btnPin.classList.toggle('is-on', winState.on_top);
      el.btnPin.title = winState.on_top ? '取消置顶' : '置顶到最前';
    }
  }

  function initWindowUi() {
    applyMode(window.innerWidth < 720 ? 'mini' : 'full');
    callApi('get_window_state').then(function (raw) {
      var st = parseState(raw);
      if (!st) return;
      applyMode(st.mode === 'full' ? 'full' : 'mini');
      applyOnTop(st.on_top);
    });
  }

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
    el.btnMin.addEventListener('click', function () { callApi('minimize_window'); });
  }

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
      groups = Array.isArray(data.groups) ? data.groups : [];
      ensureGroups();
      render();
      el.inputText.focus();
    });
  }

  function start() {
    // app.js 作为页面普通脚本执行时，pywebview 往往尚未注入 window.pywebview，
    // 所以先启动一次，桥接就绪后再启动一次以载入磁盘数据。
    syncDateField();
    initWindowUi();
    initVersion();
    boot();

    window.addEventListener('pywebviewready', function () { boot(); });

    var tries = 0;
    var timer = setInterval(function () {
      tries++;
      var a = bridge();
      if (a && typeof a.load_todos === 'function') {
        clearInterval(timer);
        boot();
        // 启动后延迟几秒静默检查更新，避免抢占首屏
        setTimeout(function () { checkUpdate(true); }, 4000);
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
    get groups() { return groups; },
    set groups(v) { groups = v; },
    get groupFilter() { return groupFilter; },
    setGroupFilter: setGroupFilter,
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
    moveTodo: moveTodo,
    createGroup: createGroup,
    boot: boot,
    start: start,
    applyMode: applyMode,
    applyOnTop: applyOnTop,
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
