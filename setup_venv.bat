@echo off
chcp 65001 >nul
setlocal EnableExtensions

rem ============================================================
rem  新建虚拟环境 venv_{版本}_{日期时间}，并安装全部依赖
rem
rem  用法（双击，或在命令行运行）：
rem    src\setup_venv.bat                       使用 py -3 或 python
rem    src\setup_venv.bat "C:\Path\python.exe"  指定用哪个 Python 创建
rem  不想在结束时暂停：先 set NO_PAUSE=1
rem ============================================================

rem 项目根目录 = 本脚本所在目录（src）的上一级
for %%I in ("%~dp0..") do set "ROOT=%%~fI"

rem ---- 选择 Python ----
if not "%~1"=="" (
    set PY="%~1"
) else (
    where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 (
    echo [错误] 找不到 Python 3.10 及以上版本：%PY%
    echo        可以把 python.exe 的完整路径作为参数传进来。
    goto :fail
)

rem ---- 版本号（VERSION 文件第一行）----
set "VERSION="
if exist "%ROOT%\VERSION" (
    for /f "usebackq delims=" %%V in ("%ROOT%\VERSION") do if not defined VERSION set "VERSION=%%V"
)
if not defined VERSION set "VERSION=0.0.0.0"

rem ---- 日期时间（与系统区域设置无关）----
for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%T"

set "VENV=%ROOT%\venv_%VERSION%_%STAMP%"
set "VPY=%VENV%\Scripts\python.exe"

echo.
echo 项目目录：%ROOT%
echo Python  ：%PY%
echo 新环境  ：%VENV%
echo.

echo [1/4] 创建虚拟环境…
%PY% -m venv "%VENV%"
if errorlevel 1 ( echo [错误] 创建虚拟环境失败 & goto :fail )

echo [2/4] 升级 pip…
"%VPY%" -m pip install --upgrade pip
if errorlevel 1 ( echo [错误] 升级 pip 失败 & goto :fail )

echo [3/4] 安装依赖（pyproject.toml）…
"%VPY%" -m pip install -e "%ROOT%"
if errorlevel 1 ( echo [错误] 安装依赖失败 & goto :fail )

echo [4/4] 检查…
"%VPY%" -c "import fastapi, uvicorn, truststore, sys; print('Python', sys.version.split()[0], '| fastapi', fastapi.__version__, '| uvicorn', uvicorn.__version__)"
if errorlevel 1 ( echo [错误] 依赖检查失败 & goto :fail )

echo.
echo 完成！新环境：%VENV%
echo.
echo 直接运行服务器：
echo     cd /d "%ROOT%\src" ^&^& "%VPY%" -m server
echo.
echo 注册 / 升级 Windows 服务（以管理员身份打开命令行）：
echo     cd /d "%ROOT%\src" ^&^& "%VPY%" -m server install
echo     "%VPY%" -m server restart
echo （详见 docs\README.md 的"部署为 Windows 服务"）
echo.
if not defined NO_PAUSE pause
endlocal
exit /b 0

:fail
echo.
if not defined NO_PAUSE pause
endlocal
exit /b 1
