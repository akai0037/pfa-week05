@echo off
rem Copies the bridge into Documents\UnrealEngine\Python, which Unreal runs on startup.
for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('MyDocuments')"`) do set DOCS=%%D
set DEST=%DOCS%\UnrealEngine\Python
if not exist "%DEST%" mkdir "%DEST%"
copy /Y "%~dp0claude_bridge.py" "%DEST%\" >nul
copy /Y "%~dp0init_unreal.py" "%DEST%\" >nul
echo Installed claude_bridge to %DEST%
echo Restart Unreal Editor, then run:  python ue_send.py --ping
