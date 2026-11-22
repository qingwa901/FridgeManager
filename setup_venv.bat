@echo off
chcp 65001 >nul
setlocal EnableExtensions

rem ============================================================
rem  新建虚拟环境 venv_{版本}_{日期时间}，并安装全部依赖
rem
rem  用法（双击，或在命令行运行）：
rem    setup_venv.bat                       使用 py -3 或 python
rem    setup_venv.bat "C:\Path\python.exe"  指定用哪个 Python 创建
rem  不想在结束时暂停：先 set NO_PAUSE=1
rem ============================================================

rem 项目根目录 = 本脚本所在目录（去掉末尾的 \）
for %%I in ("%~dp0.") do set "ROOT=%%~fI"

rem ---- 选择 Python ----
if not "%~1"=="" (
    set PY="%~1"
) else (
    where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)" >nul 2>nul
if errorlevel 1 (
    echo [错误] 找不到 Python 3.13 及以上版本：%PY%
    echo        可以把 python.exe 的完整路径作为参数传进来。
    goto :fail
)

rem ---- 公共库（git 子模块 libs\CommonLib）----
set "COMMON=%ROOT%\libs\CommonLib"
if not exist "%COMMON%\pyproject.toml" (
    echo [错误] 找不到公共库 %COMMON%
    echo        子模块还没下载，请在项目目录运行：git submodule update --init
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

echo [1/5] 创建虚拟环境…
%PY% -m venv "%VENV%"
if errorlevel 1 ( echo [错误] 创建虚拟环境失败 & goto :fail )

echo [2/5] 升级 pip…
"%VPY%" -m pip install --upgrade pip
if errorlevel 1 ( echo [错误] 升级 pip 失败 & goto :fail )

rem 公共库不在 PyPI 上，必须先以 -e 模式装好，下一步 pyproject.toml 里的 ZQCommonLib[api] 才能满足
echo [3/5] 安装公共库（-e libs\CommonLib[api]）…
"%VPY%" -m pip install -e "%COMMON%[api]"
if errorlevel 1 ( echo [错误] 安装公共库失败 & goto :fail )

echo [4/5] 安装依赖（pyproject.toml）…
"%VPY%" -m pip install -e "%ROOT%"
if errorlevel 1 ( echo [错误] 安装依赖失败 & goto :fail )

echo [5/5] 检查…
"%VPY%" -c "import common_lib, fastapi, uvicorn, truststore, win32serviceutil, sys; print('Python', sys.version.split()[0], '| ZQCommonLib', common_lib.__version__, '| fastapi', fastapi.__version__, '| uvicorn', uvicorn.__version__, '| pywin32 ok')"
if errorlevel 1 ( echo [错误] 依赖检查失败 & goto :fail )

echo.
echo 完成！新环境：%VENV%
echo.
echo 直接运行服务器：
echo     cd /d "%ROOT%\src" ^&^& "%VPY%" -m main
echo.
echo 在控制台按服务方式测试：
echo     cd /d "%ROOT%\src" ^&^& "%VPY%" -m service debug
echo.
echo 注册为 Windows 服务时，服务程序填：
echo     "%VPY%" "%ROOT%\src\service.py"
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
