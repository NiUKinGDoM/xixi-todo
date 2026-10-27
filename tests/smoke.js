/* 冒烟测试注入脚本：验证待办应用核心业务流 */
(function () {
  window.__errors = [];
  window.addEventListener('error', function (e) { window.__errors.push(e.message); });

  function pad(n) { return n < 10 ? '0' + n : '' + n; }

  function run() {
    var R = [];
    function t(name, fn) {
      var r;
      try { r = fn(); }
      catch (e) { R.push('ERR  ' + name + ' :: ' + e.message); return; }
      if (r === true) { R.push('OK   ' + name); }
      else if (r === false) { R.push('FAIL ' + name); }
      else { R.push('FAIL ' + name + ' :: ' + r); }
    }

    var A = window.__todoApp;
    var list = function () { return document.querySelectorAll('.todo-item'); };
    var byTitle = function (title) {
      return A.todos.filter(function (x) { return x.title === title; })[0];
    };
    var itemEl = function (id) { return document.querySelector('.todo-item[data-id="' + id + '"]'); };

    t('应用对象已暴露', function () { return (A && A.todos !== undefined) ? true : 'window.__todoApp 未定义'; });
    t('日期标签已填充', function () {
      var v = document.getElementById('todayLabel').textContent;
      return /\d+月\d+日/.test(v) ? true : '值=' + v;
    });
    t('空状态初始可见', function () {
      return document.getElementById('emptyState').hidden === false ? true : '空状态未显示';
    });
    t('初始列表为空', function () { return list().length === 0 ? true : 'n=' + list().length; });

    /* ---- 添加 ---- */
    t('添加待办', function () {
      document.getElementById('inputText').value = '测试任务A';
      document.getElementById('addBtn').click();
      return A.todos.length === 1 ? true : 'len=' + A.todos.length;
    });
    t('添加后输入框清空', function () {
      return document.getElementById('inputText').value === '' ? true : '未清空';
    });
    t('列表渲染出 1 项', function () { return list().length === 1 ? true : 'n=' + list().length; });
    t('列表项显示标题', function () {
      var el = document.querySelector('.todo-title');
      return el && el.textContent === '测试任务A' ? true : 'text=' + (el && el.textContent);
    });
    t('空白输入被忽略', function () {
      document.getElementById('inputText').value = '   ';
      document.getElementById('addBtn').click();
      return A.todos.length === 1 ? true : 'len=' + A.todos.length;
    });
    t('回车键添加生效', function () {
      var inp = document.getElementById('inputText');
      inp.value = '回车添加';
      inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
      return A.todos.length === 2 ? true : 'len=' + A.todos.length;
    });

    /* ---- 优先级 ---- */
    t('优先级切换生效', function () {
      document.querySelector('#prioritySeg .seg-btn[data-priority="high"]').click();
      document.getElementById('inputText').value = '高优任务';
      document.getElementById('addBtn').click();
      var item = byTitle('高优任务');
      return item && item.priority === 'high' ? true : 'prio=' + (item && item.priority);
    });
    t('优先级标签渲染', function () {
      return document.querySelectorAll('.todo-item .tag-high').length === 1 ? true : 'tag-high数=' + document.querySelectorAll('.todo-item .tag-high').length;
    });
    t('中高低三档标签都存在', function () {
      document.querySelector('#prioritySeg .seg-btn[data-priority="medium"]').click();
      document.getElementById('inputText').value = '中优任务';
      document.getElementById('addBtn').click();
      document.querySelector('#prioritySeg .seg-btn[data-priority="low"]').click();
      document.getElementById('inputText').value = '低优任务';
      document.getElementById('addBtn').click();
      var c = document.querySelectorAll('.todo-item .tag-medium').length;
      var d = document.querySelectorAll('.todo-item .tag-low').length;
      return (c === 3 && d === 1) ? true : 'medium=' + c + ' low=' + d;
    });

    /* ---- 勾选完成 ---- */
    t('勾选完成切换', function () {
      var id = A.todos[0].id;
      itemEl(id).querySelector('.check').click();
      var done = A.todos.filter(function (x) { return x.done; }).length;
      return done === 1 ? true : 'done数=' + done;
    });
    t('已完成项加 is-done 类', function () {
      return document.querySelectorAll('.todo-item.is-done').length === 1 ? true : 'is-done 数=' + document.querySelectorAll('.todo-item.is-done').length;
    });
    t('再次点击恢复未完成', function () {
      document.querySelector('.todo-item.is-done .check').click();
      return A.todos.filter(function (x) { return x.done; }).length === 0 ? true : '仍有已完成';
    });

    /* ---- 截止日期与逾期 ---- */
    t('日期设置与逾期判定', function () {
      var past = new Date(); past.setDate(past.getDate() - 3);
      var ds = past.getFullYear() + '-' + pad(past.getMonth() + 1) + '-' + pad(past.getDate());
      document.getElementById('inputDate').value = ds;
      document.getElementById('inputText').value = '逾期任务';
      document.getElementById('addBtn').click();
      var item = byTitle('逾期任务');
      return A.isOverdue(item) === true ? true : 'isOverdue=false';
    });
    t('逾期项加 is-overdue 类', function () {
      return document.querySelectorAll('.todo-item.is-overdue').length === 1 ? true : '未标记';
    });
    t('逾期文案正确', function () {
      var el = document.querySelectorAll('.tag-overdue')[0];
      return el && /逾期/.test(el.textContent) ? true : 'text=' + (el && el.textContent);
    });
    t('逾期计数更新', function () {
      return document.getElementById('countOverdue').textContent === '1' ? true : 'count=' + document.getElementById('countOverdue').textContent;
    });
    t('今日到期不算逾期', function () {
      var d = new Date();
      var ds = d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
      document.getElementById('inputDate').value = ds;
      document.getElementById('inputText').value = '当天任务';
      document.getElementById('addBtn').click();
      var item = byTitle('当天任务');
      return A.isOverdue(item) === false ? true : '误判为逾期';
    });
    t('今日到期标签文案', function () {
      var item = byTitle('当天任务');
      var el = itemEl(item.id).querySelector('.tag-date');
      return el && el.textContent === '今天' ? true : 'text=' + (el && el.textContent);
    });

    /* ---- 筛选 ---- */
    t('筛选-已逾期', function () {
      document.querySelector('.nav-item[data-filter="overdue"]').click();
      return A.visibleTodos().length === 1 ? true : 'n=' + A.visibleTodos().length;
    });
    t('筛选-已完成(空)', function () {
      document.querySelector('.nav-item[data-filter="done"]').click();
      return A.visibleTodos().length === 0 ? true : 'n=' + A.visibleTodos().length;
    });
    t('筛选-全部', function () {
      document.querySelector('.nav-item[data-filter="all"]').click();
      return A.visibleTodos().length === 7 ? true : 'n=' + A.visibleTodos().length;
    });
    t('筛选-今天', function () {
      document.querySelector('.nav-item[data-filter="today"]').click();
      return A.visibleTodos().length === 1 ? true : 'n=' + A.visibleTodos().length;
    });
    t('筛选状态切换到列表', function () {
      document.querySelector('.nav-item[data-filter="all"]').click();
      return list().length === 7 ? true : 'n=' + list().length;
    });

    /* ---- 排序 ---- */
    t('排序-高优先级在前', function () {
      var vis = A.visibleTodos();
      return vis[0].priority === 'high' ? true : '首项=' + vis[0].priority;
    });

    /* ---- 删除 ---- */
    t('删除待办', function () {
      var item = byTitle('测试任务A');
      itemEl(item.id).querySelector('.icon-btn.danger').click();
      return A.todos.length === 6 ? true : 'len=' + A.todos.length;
    });
    t('删除后列表同步', function () {
      return list().length === 6 ? true : 'n=' + list().length;
    });

    /* ---- 编辑 ---- */
    t('打开编辑弹窗', function () {
      var item = A.todos[0];
      itemEl(item.id).querySelector('.icon-btn').click();
      return document.getElementById('modalMask').hidden === false ? true : '弹窗未打开';
    });
    t('弹窗回填标题', function () {
      var item = A.todos[0];
      return document.getElementById('editText').value === item.title ? true : '值=' + document.getElementById('editText').value;
    });
    t('弹窗回填优先级', function () {
      var item = A.todos[0];
      var active = document.querySelector('#editPrioritySeg .seg-btn.is-active');
      return active && active.getAttribute('data-priority') === item.priority ? true : 'prio不匹配';
    });
    t('保存编辑生效', function () {
      document.getElementById('editText').value = '改名后的任务';
      document.getElementById('editSave').click();
      var ok = A.todos.some(function (x) { return x.title === '改名后的任务'; });
      return (ok && document.getElementById('modalMask').hidden === true) ? true : '未生效';
    });
    t('弹窗内删除生效', function () {
      var item = A.todos[0];
      itemEl(item.id).querySelector('.icon-btn').click();
      document.getElementById('editDelete').click();
      return A.todos.length === 5 ? true : 'len=' + A.todos.length;
    });
    t('ESC 关闭弹窗', function () {
      var item = A.todos[0];
      itemEl(item.id).querySelector('.icon-btn').click();
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      return document.getElementById('modalMask').hidden === true ? true : '弹窗未关闭';
    });

    /* ---- 进度与统计 ---- */
    t('进度百分比计算', function () {
      var all = A.todos.length;
      var done = A.todos.filter(function (x) { return x.done; }).length;
      var pct = all ? Math.round(done / all * 100) : 0;
      return document.getElementById('progressPct').textContent === pct + '%' ? true : 'pct=' + document.getElementById('progressPct').textContent;
    });
    t('进度条宽度同步', function () {
      var w = document.getElementById('progressFill').style.width;
      var pctText = document.getElementById('progressPct').textContent;
      return w === pctText ? true : 'width=' + w + ' pct=' + pctText;
    });
    t('各分类计数正确', function () {
      var all = A.todos.length;
      var done = A.todos.filter(function (x) { return x.done; }).length;
      var pend = all - done;
      var od = A.todos.filter(A.isOverdue).length;
      return (document.getElementById('countAll').textContent === String(all) &&
              document.getElementById('countPending').textContent === String(pend) &&
              document.getElementById('countDone').textContent === String(done) &&
              document.getElementById('countOverdue').textContent === String(od))
        ? true : '计数不符';
    });

    /* ---- 清除已完成 ---- */
    t('清除已完成', function () {
      document.getElementById('inputText').value = '待完成任务';
      document.getElementById('addBtn').click();
      document.querySelector('.todo-item .check').click();
      var before = A.todos.filter(function (x) { return x.done; }).length;
      document.getElementById('clearDoneBtn').click();
      var after = A.todos.filter(function (x) { return x.done; }).length;
      return (before > 0 && after === 0) ? true : 'before=' + before + ' after=' + after;
    });

    /* ---- 持久化 ---- */
    t('持久化已写入 localStorage', function () {
      try {
        var raw = localStorage.getItem('todos');
        if (!raw) return 'localStorage 为空';
        var parsed = JSON.parse(raw);
        return parsed.length === A.todos.length ? true : '持久化数=' + parsed.length + ' 内存数=' + A.todos.length;
      } catch (e) { return '读取失败: ' + e.message; }
    });
    t('持久化内容可回载', function () {
      var raw = JSON.parse(localStorage.getItem('todos'));
      var again = JSON.stringify(raw);
      return (JSON.parse(again).length === raw.length) ? true : '往返不一致';
    });

    /* ---- 空状态 ---- */
    t('空列表显示空状态', function () {
      document.querySelector('.nav-item[data-filter="done"]').click();
      return document.getElementById('emptyState').hidden === false ? true : '空状态未显示';
    });

    /* ---- 样式生效 ---- */
    t('Liquid Glass 面板有 backdrop-filter', function () {
      var el = document.querySelector('.glass-refract');
      var bf = getComputedStyle(el).backdropFilter || getComputedStyle(el).webkitBackdropFilter;
      return (bf && bf !== 'none') ? true : 'backdrop-filter=' + bf;
    });
    t('玻璃面板背景为半透明', function () {
      var el = document.querySelector('.glass-panel');
      var bg = getComputedStyle(el).backgroundColor;
      return /rgba/.test(bg) ? true : 'bg=' + bg;
    });
    t('SVG 折射滤镜已定义', function () {
      var f = document.getElementById('lgRefract');
      return (f && f.querySelector('feDisplacementMap')) ? true : '滤镜缺失';
    });
    t('色散三通道已配置', function () {
      var f = document.getElementById('lgRefract');
      // 只统计 type=matrix 的通道分离节点（saturate 那个不算）
      var mats = [].slice.call(f.querySelectorAll('feColorMatrix')).filter(function (n) {
        return (n.getAttribute('type') || 'matrix') === 'matrix';
      });
      return mats.length === 3 ? true : '色散矩阵数=' + mats.length;
    });
    t('折射滤镜含位移与模糊', function () {
      var f = document.getElementById('lgRefract');
      var disp = f.querySelector('feDisplacementMap');
      var blurs = f.querySelectorAll('feGaussianBlur');
      return (disp && blurs.length >= 1) ? true : 'disp=' + !!disp + ' blur数=' + blurs.length;
    });
    t('背景光斑层存在', function () {
      return document.querySelectorAll('.bg-orb').length === 4 ? true : 'orb数=' + document.querySelectorAll('.bg-orb').length;
    });

    /* ---- 可交互性：确认没有被遮挡 ---- */
    t('输入框可获得焦点', function () {
      var inp = document.getElementById('inputText');
      inp.focus();
      return document.activeElement === inp ? true : '焦点落在 ' + (document.activeElement && document.activeElement.tagName);
    });
    t('输入框未被遮挡', function () {
      var inp = document.getElementById('inputText');
      var r = inp.getBoundingClientRect();
      var hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return (hit === inp || inp.contains(hit)) ? true
        : '命中元素为 ' + (hit && (hit.tagName + '.' + hit.className));
    });
    t('添加按钮未被遮挡', function () {
      var b = document.getElementById('addBtn');
      var r = b.getBoundingClientRect();
      var hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return (hit === b || b.contains(hit)) ? true
        : '命中元素为 ' + (hit && (hit.tagName + '.' + hit.className));
    });
    t('勾选框未被遮挡', function () {
      // 保证列表中有项目可测
      document.querySelector('.nav-item[data-filter="all"]').click();
      if (!document.querySelector('.todo-item .check')) {
        document.getElementById('inputText').value = '遮挡检测用项';
        document.getElementById('addBtn').click();
      }
      var c = document.querySelector('.todo-item .check');
      if (!c) return '仍无列表项';
      var r = c.getBoundingClientRect();
      var hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return (hit === c || c.contains(hit)) ? true
        : '命中元素为 ' + (hit && (hit.tagName + '.' + hit.className));
    });

    /* ---- 迷你/完整模式切换 ---- */
    // 测试视口较宽，先显式切到迷你模式再断言
    t('可切换到迷你模式', function () {
      A.applyMode('mini');
      return document.body.classList.contains('mode-mini') ? true : 'class=' + document.body.className;
    });
    t('迷你模式显示筛选胶囊', function () {
      var d = getComputedStyle(document.getElementById('filterChips')).display;
      return d === 'flex' ? true : 'display=' + d;
    });
    t('迷你模式隐藏侧边栏', function () {
      var d = getComputedStyle(document.querySelector('.sidebar')).display;
      return d === 'none' ? true : 'display=' + d;
    });
    t('迷你模式显示底部进度', function () {
      var d = getComputedStyle(document.querySelector('.mini-foot')).display;
      return d === 'flex' ? true : 'display=' + d;
    });
    t('迷你计数与内存一致', function () {
      var pending = A.todos.filter(function (x) { return !x.done; }).length;
      var shown = document.getElementById('miniCount').textContent;
      return shown === String(pending) ? true : 'DOM=' + shown + ' 期望=' + pending;
    });
    t('迷你进度条与百分比一致', function () {
      var w = document.getElementById('miniFill').style.width;
      var pct = document.getElementById('progressPct').textContent;
      return w === pct ? true : 'width=' + w + ' pct=' + pct;
    });
    t('小框无横向溢出', function () {
      // 关键：380 宽小框里筛选胶囊与按钮不能被挤出去
      var chips = document.getElementById('filterChips');
      var last = chips.lastElementChild.getBoundingClientRect();
      var box = chips.getBoundingClientRect();
      return last.right <= box.right + 1 ? true
        : '末项右缘 ' + Math.round(last.right) + ' 超出容器右缘 ' + Math.round(box.right);
    });
    t('窗口按钮排布在框内', function () {
      var acts = document.querySelector('.minibar-actions');
      var closeBtn = document.getElementById('btnClose');
      var r = closeBtn.getBoundingClientRect();
      var a = acts.getBoundingClientRect();
      return (r.right <= a.right + 1 && r.width > 0) ? true
        : 'close right=' + Math.round(r.right) + ' actions right=' + Math.round(a.right) + ' w=' + Math.round(r.width);
    });
    t('图钉按钮反映置顶状态', function () {
      A.applyOnTop(true);
      var on = document.getElementById('btnPin').classList.contains('is-on');
      A.applyOnTop(false);
      var off = document.getElementById('btnPin').classList.contains('is-on');
      A.applyOnTop(true);
      return (on === true && off === false) ? true : 'on=' + on + ' off=' + off;
    });
    t('可切回完整模式', function () {
      A.applyMode('full');
      var cls = document.body.classList.contains('mode-full');
      var side = getComputedStyle(document.querySelector('.sidebar')).display;
      var chips = getComputedStyle(document.getElementById('filterChips')).display;
      return (cls && side !== 'none' && chips === 'none') ? true
        : 'class=' + document.body.className + ' sidebar=' + side + ' chips=' + chips;
    });
    t('筛选胶囊与侧边栏状态同步', function () {
      A.applyMode('mini');
      document.querySelector('#filterChips .chip[data-filter="today"]').click();
      var navAct = document.querySelector('.nav-item.is-active').getAttribute('data-filter');
      var chipAct = document.querySelector('#filterChips .chip.is-active').getAttribute('data-filter');
      document.querySelector('.nav-item[data-filter="all"]').click();
      var chipAct2 = document.querySelector('#filterChips .chip.is-active').getAttribute('data-filter');
      return (navAct === 'today' && chipAct === 'today' && chipAct2 === 'all') ? true
        : 'nav=' + navAct + ' chip=' + chipAct + ' chip2=' + chipAct2;
    });

    /* ==========================================================
       新增功能：重复任务 / 分组 / 备注 / 快速语法 / 拖拽
       ========================================================== */

    /* ---- 重复任务周期推进 ---- */
    // 说明：nextDueDate 会把过期日期一路追到「今天之后」，
    // 所以验证「推进一个周期」必须用未来日期做基准。
    function shiftDate(days) {
      var d = new Date();
      d.setDate(d.getDate() + days);
      return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
    }
    function addDaysTo(dateStr, n) {
      var d = new Date(dateStr + 'T00:00:00');
      d.setDate(d.getDate() + n);
      return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
    }

    t('重复-每天推进一天', function () {
      var base = shiftDate(30);
      var n = A.nextDueDate(base, 'daily');
      return n === addDaysTo(base, 1) ? true : n + ' 期望 ' + addDaysTo(base, 1);
    });
    t('重复-每周推进七天', function () {
      var base = shiftDate(30);
      var n = A.nextDueDate(base, 'weekly');
      return n === addDaysTo(base, 7) ? true : n + ' 期望 ' + addDaysTo(base, 7);
    });
    t('重复-每月跨月正确', function () {
      // 找下一个 1 月 31 日，验证压到 2 月末
      var y = new Date().getFullYear() + 1;
      var n = A.nextDueDate(y + '-01-31', 'monthly');
      var expect = y + '-02-' + (new Date(y, 2, 0).getDate() < 10 ? '0' : '') + new Date(y, 2, 0).getDate();
      return n === expect ? true : n + ' 期望 ' + expect;
    });
    t('重复-每年闰日处理', function () {
      // 2028 是闰年，2/29 的下一次应为 2029-02-28
      var n = A.nextDueDate('2028-02-29', 'yearly');
      return n === '2029-02-28' ? true : n;
    });
    t('重复-工作日跳过周末', function () {
      // 从未来某天起推进，结果必须是周一到周五
      var n = A.nextDueDate(shiftDate(30), 'weekday');
      var wd = new Date(n + 'T00:00:00').getDay();
      return (wd >= 1 && wd <= 5) ? true : n + ' 是周' + wd;
    });
    t('重复-逾期后推到未来', function () {
      var n = A.nextDueDate('2020-01-01', 'daily');
      return A.daysUntil(n) >= 0 ? true : '推到 ' + n + ' 仍是过去';
    });
    t('重复-很久以前的工作日也能追上', function () {
      var n = A.nextDueDate('2019-05-01', 'weekday');
      return A.daysUntil(n) >= 0 ? true : '推到 ' + n + ' 仍是过去';
    });

    /* ---- 重复任务完成行为 ---- */
    t('重复任务完成不置为已完成', function () {
      A.todos = [{
        id: 'rep1', title: '每日站会', priority: 'medium',
        due: A.daysUntil('2026-10-27') === null ? '' : '2026-10-27',
        time: '09:00', repeat: 'daily', group: '', note: '',
        done: false, createdAt: 1
      }];
      A.render();
      A.toggle('rep1');
      var t = A.todos[0];
      return (t.done === false) ? true : 'done 被置为 true';
    });
    t('重复任务完成会推进日期', function () {
      var t = A.todos[0];
      return (t.due && A.daysUntil(t.due) >= 0) ? true : 'due=' + t.due;
    });
    t('重复任务记录完成次数', function () {
      var t = A.todos[0];
      return t.doneCount === 1 ? true : 'doneCount=' + t.doneCount;
    });
    t('非重复任务完成后置为已完成', function () {
      A.todos = [{ id: 'once1', title: '一次性任务', priority: 'medium', due: '', done: false, createdAt: 1 }];
      A.render();
      A.toggle('once1');
      return A.todos[0].done === true ? true : 'done 未变化';
    });

    /* ---- 分组 ---- */
    t('默认分组已就绪', function () {
      return (A.groups.length >= 4 && A.groups.indexOf('工作') >= 0) ? true : A.groups.join(',');
    });
    t('分组可写入任务', function () {
      A.todos = [{
        id: 'g1', title: '写周报', priority: 'medium', due: '',
        group: '工作', done: false, createdAt: 2
      }];
      A.render();
      var tag = document.querySelector('.todo-item .tag-group');
      return tag && tag.textContent === '工作' ? true : '没有分组标签';
    });
    t('按分组筛选只显示该组', function () {
      A.todos = [
        { id: 'g1', title: '写周报', priority: 'medium', due: '', group: '工作', done: false, createdAt: 2 },
        { id: 'g2', title: '买菜', priority: 'medium', due: '', group: '生活', done: false, createdAt: 1 }
      ];
      A.setGroupFilter('工作');
      var vis = A.visibleTodos();
      var ok = vis.length === 1 && vis[0].title === '写周报';
      A.setGroupFilter('all');
      return ok ? true : 'n=' + vis.length;
    });
    t('分组筛选恢复全部', function () {
      return A.visibleTodos().length === 2 ? true : 'n=' + A.visibleTodos().length;
    });
    t('侧边栏分组列表已渲染', function () {
      var items = document.querySelectorAll('#groupList .group-item');
      return items.length >= 2 ? true : '项数=' + items.length;
    });

    /* ---- 备注 ---- */
    t('备注显示在任务下方', function () {
      A.todos = [{
        id: 'n1', title: '有备注的任务', priority: 'medium', due: '',
        note: '这是补充说明', done: false, createdAt: 1
      }];
      A.render();
      var note = document.querySelector('.todo-item .todo-note');
      return note && note.textContent === '这是补充说明' ? true : '没有备注元素';
    });
    t('无备注不渲染备注元素', function () {
      A.todos = [{ id: 'n2', title: '无备注', priority: 'medium', due: '', note: '', done: false, createdAt: 1 }];
      A.render();
      return document.querySelector('.todo-item .todo-note') === null ? true : '多余备注元素';
    });

    /* ---- 快速添加语法 ---- */
    t('语法-解析优先级', function () {
      var r = A.parseQuickInput('写方案 !高');
      return (r.priority === 'high' && r.title === '写方案') ? true : JSON.stringify(r);
    });
    t('语法-解析分组', function () {
      var r = A.parseQuickInput('整理资料 #工作');
      return (r.group === '工作' && r.title === '整理资料') ? true : JSON.stringify(r);
    });
    t('语法-解析明天', function () {
      var r = A.parseQuickInput('交报告 明天');
      var d = new Date(); d.setDate(d.getDate() + 1);
      var expect = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
      return (r.due === expect && r.title === '交报告') ? true : 'due=' + r.due + ' expect=' + expect;
    });
    t('语法-解析几点几分', function () {
      var r = A.parseQuickInput('开会 9点30分');
      return (r.time === '09:30') ? true : 'time=' + r.time;
    });
    t('语法-解析冒号时间', function () {
      var r = A.parseQuickInput('晨会 8:15');
      return (r.time === '08:15') ? true : 'time=' + r.time;
    });
    t('语法-解析每周', function () {
      var r = A.parseQuickInput('周会 每周');
      return (r.repeat === 'weekly' && r.title === '周会') ? true : JSON.stringify(r);
    });
    t('语法-组合解析', function () {
      var r = A.parseQuickInput('明天9点 客户拜访 !高 #工作 每天');
      var ok = r.priority === 'high' && r.group === '工作' &&
               r.repeat === 'daily' && r.time === '09:00' && !!r.due;
      return ok ? true : JSON.stringify(r);
    });
    t('语法-普通文本不被误伤', function () {
      var r = A.parseQuickInput('买 3 个苹果');
      return (r.title === '买 3 个苹果' && !r.due && !r.priority) ? true : JSON.stringify(r);
    });
    t('语法-解析下周几', function () {
      var r = A.parseQuickInput('开会 下周三');
      return (r.due && A.daysUntil(r.due) > 0) ? true : 'due=' + r.due;
    });

    /* ---- 用语法添加真任务 ---- */
    t('语法添加后字段生效', function () {
      A.todos = [];
      var inp = document.getElementById('inputText');
      inp.value = '语法任务 明天 !高 #学习';
      document.getElementById('addBtn').click();
      var t = A.todos[0];
      return (t && t.priority === 'high' && t.group === '学习' && t.due && t.title === '语法任务')
        ? true : JSON.stringify(t);
    });
    t('语法新增的分组自动登记', function () {
      return A.groups.indexOf('学习') >= 0 ? true : A.groups.join(',');
    });

    /* ---- 拖拽排序 ---- */
    t('拖拽调整顺序并写入 order', function () {
      A.todos = [
        { id: 'd1', title: 'A', priority: 'medium', due: '', done: false, createdAt: 3 },
        { id: 'd2', title: 'B', priority: 'medium', due: '', done: false, createdAt: 2 },
        { id: 'd3', title: 'C', priority: 'medium', due: '', done: false, createdAt: 1 }
      ];
      A.render();
      // 把 C 拖到 A 前面
      A.moveTodo('d3', 'd1', false);
      var order = A.visibleTodos().map(function (x) { return x.title; }).join('');
      return order === 'CAB' ? true : '实际顺序=' + order;
    });

    /* ---- 提醒时间 ---- */
    t('带时间的任务显示时间', function () {
      A.todos = [{
        id: 'tm1', title: '晨会', priority: 'medium', due: '',
        time: '09:15', done: false, createdAt: 1
      }];
      A.render();
      var tags = A.visibleTodos()[0];
      var el2 = document.querySelector('.todo-item .tag-date');
      return el2 && /09:15/.test(el2.textContent) ? true : 'text=' + (el2 && el2.textContent);
    });

    /* ---- 备份（浏览器降级路径不报错） ---- */
    t('备份导出不抛异常', function () {
      // headless 环境下真实触发下载会挂起，这里把下载动作打桩掉
      var origCreate = URL.createObjectURL;
      var origRevoke = URL.revokeObjectURL;
      var origClick = HTMLAnchorElement.prototype.click;
      URL.createObjectURL = function () { return 'blob:stub'; };
      URL.revokeObjectURL = function () { };
      HTMLAnchorElement.prototype.click = function () { };
      try {
        document.getElementById('menuBackup').click();
        return true;
      } catch (e) {
        return '抛出 ' + e.message;
      } finally {
        URL.createObjectURL = origCreate;
        URL.revokeObjectURL = origRevoke;
        HTMLAnchorElement.prototype.click = origClick;
      }
    });
    t('菜单可开合', function () {
      var m = document.getElementById('appMenu');
      document.getElementById('btnMenu').click();
      var opened = m.hidden === false;
      document.getElementById('btnMenu').click();
      var closed = m.hidden === true;
      return (opened && closed) ? true : 'opened=' + opened + ' closed=' + closed;
    });

    /* ---- 版本号比较（更新检查的核心判断） ---- */
    t('版本-相同版本判定无更新', function () {
      return A.compareVer('1.1.0', '1.1.0') === 0 ? true : '结果=' + A.compareVer('1.1.0', '1.1.0');
    });
    t('版本-补丁位更高', function () {
      return A.compareVer('1.1.1', '1.1.0') === 1 ? true : '结果=' + A.compareVer('1.1.1', '1.1.0');
    });
    t('版本-次版本更高', function () {
      return A.compareVer('1.2.0', '1.1.9') === 1 ? true : '结果=' + A.compareVer('1.2.0', '1.1.9');
    });
    t('版本-主版本更高', function () {
      return A.compareVer('2.0.0', '1.99.99') === 1 ? true : '结果=' + A.compareVer('2.0.0', '1.99.99');
    });
    t('版本-当前更新时应为负', function () {
      return A.compareVer('1.0.9', '1.1.0') === -1 ? true : '结果=' + A.compareVer('1.0.9', '1.1.0');
    });
    t('版本-位数不同也能比较', function () {
      return A.compareVer('1.2', '1.2.0') === 0 ? true : '结果=' + A.compareVer('1.2', '1.2.0');
    });
    t('版本-允许 v 前缀', function () {
      return A.compareVer('v1.2.0', '1.1.0') === 1 ? true : '结果=' + A.compareVer('v1.2.0', '1.1.0');
    });
    t('版本-非法字符不崩溃', function () {
      var r = A.compareVer('abc', '1.0.0');
      return (r === -1 || r === 0 || r === 1) ? true : '返回 ' + r;
    });

    t('更新角标可开关', function () {
      A.setUpdateBadge(true);
      var on = document.getElementById('btnMenu').classList.contains('has-update');
      A.setUpdateBadge(false);
      var off = document.getElementById('btnMenu').classList.contains('has-update');
      return (on === true && off === false) ? true : 'on=' + on + ' off=' + off;
    });
    t('有新版本时按钮文案变化', function () {
      A.setUpdateBadge(true);
      var txt = document.getElementById('updateLabel').textContent;
      A.setUpdateBadge(false);
      return /发现新版本/.test(txt) ? true : 'text=' + txt;
    });

    /* ---- 异常 ---- */
    t('无未捕获异常', function () {
      return window.__errors.length === 0 ? true : window.__errors.join('; ');
    });

    document.title = R.join(' ;; ');
  }

  setTimeout(run, 1400);
})();
