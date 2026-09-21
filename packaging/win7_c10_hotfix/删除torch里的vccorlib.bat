@echo off
chcp 65001 >nul
set "F=D:\AlbumentationsX\_internal\torch\lib\vccorlib140.dll"
if exist "%F%" (
  del /f /q "%F%"
  echo 已删除 %F%
) else (
  echo 文件本来就不在: %F%
)
pause