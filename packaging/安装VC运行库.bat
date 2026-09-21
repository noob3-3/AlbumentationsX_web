@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在安装 Microsoft Visual C++ 2015-2019 x64 运行库（训练/CUDA 必需）...
if exist "%~dp0vc_redist.x64.exe" (
  "%~dp0vc_redist.x64.exe" /install /norestart
) else (
  echo 未找到 vc_redist.x64.exe，改为打开下载页。
  start "" "https://aka.ms/vs/16/release/vc_redist.x64.exe"
)
echo 安装完成后请重新运行 启动.bat
pause
