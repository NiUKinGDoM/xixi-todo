@echo off
REM 一键回归测试：前端冒烟 + 桌面集成
REM 用法：在项目根目录双击，或在命令行运行 run_tests.bat
setlocal
cd /d "%~dp0"

echo ========================================
echo  1/2  前端冒烟测试（Chrome headless）
echo ========================================
where node >nul 2>nul
if errorlevel 1 (
    echo [跳过] 未安装 Node.js
    goto :integration
)

node tests\make-test.js
set CHROME="C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist %CHROME% set CHROME="C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not exist %CHROME% (
    echo [跳过] 未找到 Chrome / Edge
    goto :integration
)

%CHROME% --headless=new --disable-gpu --virtual-time-budget=9000 --dump-dom "file:///%CD:\=/%/tests/test.html" 2>nul | findstr /C:"<title>" > tests\result.tmp
echo.
type tests\result.tmp | more +0
echo.

:integration
echo ========================================
echo  2/4  窗口形态逻辑测试
echo ========================================
if not exist venv\Scripts\python.exe (
    echo [跳过] 未找到 venv，请先执行:
    echo   python -m venv venv
    echo   venv\Scripts\pip install pywebview pyinstaller pillow
    goto :end
)
venv\Scripts\python.exe test_window.py

echo ========================================
echo  3/4  新功能后端测试（分组/备份/提醒）
echo ========================================
venv\Scripts\python.exe test_features.py

echo ========================================
echo  4/4  数据集成测试（真实 WebView2）
echo ========================================
venv\Scripts\python.exe test_integration.py

:end
echo.
echo 测试结束。
pause
