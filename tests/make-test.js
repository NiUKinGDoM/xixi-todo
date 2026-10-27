/**
 * 生成冒烟测试副本：把 smoke.js 注入 index.html，
 * 并复制 ui 资源到同目录，确保相对路径可解析。
 */
const fs = require('fs');
const path = require('path');

const uiDir = path.join(__dirname, '..', 'ui');
const tbDir = __dirname;

let html = fs.readFileSync(path.join(uiDir, 'index.html'), 'utf8');
const smoke = fs.readFileSync(path.join(tbDir, 'smoke.js'), 'utf8');

html = html.replace('</body>', '<script>\n' + smoke + '\n<\/script>\n</body>');

fs.writeFileSync(path.join(tbDir, 'test.html'), html);
fs.copyFileSync(path.join(uiDir, 'styles.css'), path.join(tbDir, 'styles.css'));
fs.copyFileSync(path.join(uiDir, 'app.js'), path.join(tbDir, 'app.js'));

console.log('测试副本已生成: .tb/test.html (+ styles.css, app.js)');
