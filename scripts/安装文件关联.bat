@echo off
chcp 936 >nul 2>&1
echo ===================================
echo   HanUI File Association Setup
echo ===================================
echo.

set "EXEPATH=%~dp0hanui.exe"
if not exist "%EXEPATH%" (
    echo [ERROR] hanui.exe not found in this folder.
    pause
    exit /b 1
)

echo Will register .hrpa files to:
echo   %EXEPATH%
echo.
echo Press any key to continue, or close this window to cancel...
pause >nul

set "REGTEMP=%TEMP%\hanui_assoc.reg"
(
echo Windows Registry Editor Version 5.00
echo.
echo [HKEY_CLASSES_ROOT\.hrpa]
echo @="HanUI.Script"
echo.
echo [HKEY_CLASSES_ROOT\HanUI.Script]
echo @="HanUI Script"
echo.
echo [HKEY_CLASSES_ROOT\HanUI.Script\shell]
echo @="run"
echo.
echo [HKEY_CLASSES_ROOT\HanUI.Script\shell\run\command]
echo @="\"%EXEPATH:\=\\%\" \"%%1\""
echo.
echo [HKEY_CLASSES_ROOT\HanUI.Script\shell\edit]
echo @="Edit with HanUI"
echo.
echo [HKEY_CLASSES_ROOT\HanUI.Script\shell\edit\command]
echo @="\"%EXEPATH:\=\\%\" \"%%1\""
) > "%REGTEMP%"

regedit /s "%REGTEMP%"
if %errorlevel% equ 0 (
    echo.
    echo [OK] File association installed!
    echo Double-click any .hrpa file to run it.
) else (
    echo.
    echo [FAIL] Registry write failed. Run as Administrator.
)

del "%REGTEMP%" 2>nul
echo.
pause