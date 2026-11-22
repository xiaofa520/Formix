@echo off
setlocal
for /f "usebackq delims=" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "vsdir=%%i"
if not defined vsdir exit /b 1
call "%vsdir%\Common7\Tools\VsDevCmd.bat" -no_logo -arch=%~2 >nul
if errorlevel 1 exit /b 1
set "version=%~3"
>formix_version.h echo #define FORMIX_VERSION_NUM %version:.=,%,0
>>formix_version.h echo #define FORMIX_VERSION_TEXT "%version%"
rc /nologo /i "%~dp0..\src\formix\assets" /i . /fo formix.res "%~dp0formix_host.rc"
if errorlevel 1 exit /b 1
cl /nologo /O2 /MT "%~dp0formix_host.c" formix.res "%~1\libs\python311.lib" /link /subsystem:windows /out:"%~4"
exit /b %errorlevel%
