@echo off
REM PyInstaller 打包脚本
REM 用于打包 PID 模拟器和 OPCUA Server 工具

echo ========================================
echo 开始打包工具...
echo ========================================

REM 检查 PyInstaller 是否安装
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller 未安装，正在安装...
    pip install pyinstaller
)

echo.
echo ========================================
echo 打包 PID 模拟器工具...
echo ========================================

pyinstaller --windowed --onefile --name="PID模拟器" ^
    --add-data "tool/__init__.py;tool" ^
    tool/pid_simulator.py

if errorlevel 1 (
    echo PID 模拟器打包失败！
    pause
    exit /b 1
)

echo.
echo ========================================
echo 打包 OPCUA Server 工具...
echo ========================================

pyinstaller --windowed --onefile --name="OPCUA服务器" ^
    --add-data "tool/__init__.py;tool" ^
    tool/opcua_server.py

if errorlevel 1 (
    echo OPCUA Server 工具打包失败！
    pause
    exit /b 1
)

echo.
echo ========================================
echo 打包完成！
echo ========================================
echo.
echo 可执行文件位置：
echo   - PID模拟器.exe: dist\PID模拟器.exe
echo   - OPCUA服务器.exe: dist\OPCUA服务器.exe
echo.
pause

