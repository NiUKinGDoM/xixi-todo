/* 截图用：注入示例数据（含重复、分组、备注、提醒时间） */
(function () {
  function pad(n) { return n < 10 ? '0' + n : '' + n; }
  function ds(off) {
    var x = new Date();
    x.setDate(x.getDate() + off);
    return x.getFullYear() + '-' + pad(x.getMonth() + 1) + '-' + pad(x.getDate());
  }
  setTimeout(function () {
    var A = window.__todoApp;
    A.groups = ['工作', '生活', '学习'];
    A.todos = [
      {
        id: 's1', title: '晨会同步生产进度', priority: 'high',
        due: ds(0), time: '09:00', repeat: 'weekday', group: '工作',
        note: '', done: false, createdAt: 9
      },
      {
        id: 's2', title: '回复 A320 供应商询价邮件', priority: 'high',
        due: ds(-1), time: '', repeat: 'none', group: '工作',
        note: '对方催了两次，今天必须给报价', done: false, createdAt: 8
      },
      {
        id: 's3', title: '整理本周钛铸件客户拜访记录', priority: 'medium',
        due: ds(2), time: '14:30', repeat: 'none', group: '工作',
        note: '', done: false, createdAt: 7
      },
      {
        id: 's4', title: '背单词 30 个', priority: 'low',
        due: ds(0), time: '', repeat: 'daily', group: '学习',
        note: '', done: false, createdAt: 6
      },
      {
        id: 's5', title: '周末爬山', priority: 'low',
        due: ds(5), time: '', repeat: 'weekly', group: '生活',
        note: '带上新买的水壶', done: false, createdAt: 5
      },
      {
        id: 's6', title: '寄送技术资料给宝鸡客户', priority: 'low',
        due: '', time: '', repeat: 'none', group: '工作',
        note: '', done: true, createdAt: 4
      }
    ];
    A.render();
    document.title = 'seeded';
  }, 900);
})();
