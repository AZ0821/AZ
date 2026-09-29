@echo off
chcp 65001 >nul
echo ===================================
echo   汉UI 文件关联安装
echo ===================================
echo.

:: 获取当前目录下的 hanui.exe 路径
set "EXEPATH=%~dp0hanui.exe"
if not exist "%EXEPATH%" (
    echo [错误] 未找到 hanui.exe，请把此文件放在 hanui.exe 同一目录
    pause
    exit /b 1
)

echo 将注册以下文件关联:
echo   .hrpa 文件 → %EXEPATH%
echo.
echo 按任意键继续，或关闭窗口取消...
pause >nul

:: 生成临时 reg 文件
set "REGTEMP=%TEMP%\hanui_assoc.reg"
(
echo Windows Registry Editor Version 5.00
echo.
echo [HKEY_CLASSES_ROOT\.hrpa]
echo @="HanUI.Script"
echo.
echo [HKEY_CLASSES_ROOT\HanUI.Script]
echo @="汉UI 脚本"
echo.
echo [HKEY_CLASSES_ROOT\HanUI.Script\shell]
echo @="run"
echo.
echo [HKEY_CLASSES_ROOT\HanUI.Script\shell\run\command]
echo @="\"%EXEPATH:\=\\%\" \"%%1\""
echo.
echo [HKEY_CLASSES_ROOT\HanUI.Script\shell\edit]
echo @="用汉UI 编辑"
echo.
echo [HKEY_CLASSES_ROOT\HanUI.Script\shell\edit\command]
echo @="\"%EXEPATH:\=\\%\" \"%%1\""
) > "%REGTEMP%"

:: 导入注册表
regedit /s "%REGTEMP%"
if %errorlevel% equ 0 (
    echo.
    echo [成功] 文件关联已安装！
    echo 现在双击 .hrpa 文件即可直接运行。
) else (
    echo.
    echo [失败] 注册表写入失败，请以管理员身份运行此脚本。
)

del "%REGTEMP%" 2>nul
echo.
pause
