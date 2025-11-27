@echo off
REM PyInstaller 打包脚本 - PID模拟与OPCUA Server工具
REM 打包成单个可执行文件，不显示控制台窗口

echo ========================================
echo 开始打包 PID模拟与OPCUA Server 工具...
echo ========================================

REM 检查 PyInstaller 是否安装
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller 未安装，正在安装...
    pip install pyinstaller
)

echo.
echo ========================================
echo 打包 PID模拟与OPCUA Server 工具...
echo ========================================

pyinstaller --windowed --onefile --name="PID模拟OPCUA服务器" --clean tool/pid_simu_ua_server.py

if errorlevel 1 (
    echo 打包失败！
    pause
    exit /b 1
)

echo.
echo ========================================
echo 打包完成！
echo ========================================
echo.
echo 可执行文件位置：
echo   - PID模拟OPCUA服务器.exe: dist\PID模拟OPCUA服务器.exe
echo.
pause

