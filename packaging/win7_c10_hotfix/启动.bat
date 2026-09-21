@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "AlbumentationsX.exe" (
  echo 请把本 bat 放在 AlbumentationsX.exe 同一目录后双击。
  pause
  exit /b 1
)
set "PATH=%~dp0;%~dp0_internal;%~dp0_internal\torch\lib;C:\Program Files\NVIDIA Corporation\NVSMI;C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.4\bin;C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.3\bin;%PATH%"
echo 正在启动，请稍候...
start "" "%~dp0AlbumentationsX.exe"
