@echo off
chcp 65001 >nul
cd /d "%~dp0"
if "%~1"=="" (
  echo 用法：把本文件夹里的 dll 拷到 AlbumentationsX.exe 所在目录。
  echo 例如：拷到软件目录.bat D:\AlbumentationsX
  set /p TARGET=请输入 AlbumentationsX.exe 所在目录:
) else (
  set TARGET=%~1
)
if not exist "%TARGET%\AlbumentationsX.exe" (
  echo 目录里没有 AlbumentationsX.exe：%TARGET%
  pause
  exit /b 1
)
copy /y "%~dp0*.dll" "%TARGET%\" >nul
if exist "%TARGET%\_internal\" copy /y "%~dp0*.dll" "%TARGET%\_internal\" >nul
if exist "%TARGET%\_internal\torch\lib\" (
  copy /y "%~dp0vcruntime140.dll" "%TARGET%\_internal\torch\lib\" >nul
  copy /y "%~dp0vcruntime140_1.dll" "%TARGET%\_internal\torch\lib\" >nul
  copy /y "%~dp0msvcp140.dll" "%TARGET%\_internal\torch\lib\" >nul
  copy /y "%~dp0msvcp140_1.dll" "%TARGET%\_internal\torch\lib\" >nul
  copy /y "%~dp0msvcp140_2.dll" "%TARGET%\_internal\torch\lib\" >nul
  copy /y "%~dp0concrt140.dll" "%TARGET%\_internal\torch\lib\" >nul
  if exist "%TARGET%\_internal\torch\lib\vccorlib140.dll" del /f /q "%TARGET%\_internal\torch\lib\vccorlib140.dll"
)
echo 已拷贝运行库。已从 torch\lib 删除 vccorlib140.dll（Win7 不能加载它）。
pause
