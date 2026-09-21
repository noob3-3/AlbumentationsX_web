# 在 Win10 上用 Python 3.8 + PyTorch cu113 打出可在 Win7 SP1 运行的 CUDA 目录包。
# 目标机：Win7 SP1 x64、驱动 471.xx / CUDA 11.4（如 471.68）。CUDA 11.7 包无法在该驱动上加载 c10.dll。
# 用法（仓库根目录）：powershell -ExecutionPolicy Bypass -File packaging\build_win7_cuda.ps1

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$EnvName = "axweb-win7"
$Conda = "C:\Miniforge3\Scripts\conda.exe"
if (-not (Test-Path $Conda)) {
    $Conda = (Get-Command conda -ErrorAction SilentlyContinue).Source
}
if (-not $Conda) {
    throw "未找到 conda。请先安装 Miniforge/Miniconda。"
}

Write-Host "==> conda env: $EnvName (python 3.8)"
& $Conda env list
$exists = & $Conda env list | Select-String -Pattern "^\s*$EnvName\s"
if (-not $exists) {
    & $Conda create -y -n $EnvName python=3.8
}

function Invoke-Env {
    param([string[]]$Args)
    & $Conda run -n $EnvName --no-capture-output @Args
}

Write-Host "==> PyTorch 1.12.1 + CUDA 11.3 (Win7 + 471 驱动)"
Invoke-Env python -m pip install -U pip setuptools wheel
Invoke-Env python -m pip uninstall -y torch torchvision torchaudio
Invoke-Env python -m pip install torch==1.12.1+cu113 torchvision==0.13.1+cu113 torchaudio==0.12.1 `
    --index-url https://download.pytorch.org/whl/cu113

Write-Host "==> app dependencies"
Invoke-Env python -m pip install -r "$Repo\packaging\requirements-win7-cuda.txt"

Write-Host "==> frontend"
Push-Location "$Repo\frontend"
if (-not (Test-Path "node_modules")) {
    npm install
}
npm run build
Pop-Location

Write-Host "==> PyInstaller"
$Dist = Join-Path $Repo "packaging\dist"
$Build = Join-Path $Repo "packaging\build"
Invoke-Env python -m PyInstaller --noconfirm --clean `
    --distpath $Dist `
    --workpath $Build `
    "$Repo\packaging\AlbumentationsX.spec"

$OutDir = Join-Path $Dist "AlbumentationsX"
$StaticSrc = Join-Path $Repo "frontend\dist"
$StaticDst = Join-Path $OutDir "static"
if (Test-Path $StaticSrc) {
    Copy-Item -Recurse -Force $StaticSrc $StaticDst
}

Copy-Item -Force (Join-Path $PSScriptRoot "启动.bat") (Join-Path $OutDir "启动.bat")
Copy-Item -Force (Join-Path $PSScriptRoot "安装VC运行库.bat") (Join-Path $OutDir "安装VC运行库.bat") -ErrorAction SilentlyContinue

$internal = Join-Path $OutDir "_internal"
$torchLib = Join-Path $internal "torch\lib"
$dllNames = @(
    "vcruntime140.dll", "vcruntime140_1.dll",
    "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
    "concrt140.dll", "vccorlib140.dll"
)
# Win7 必须用 VS2019 (14.29) CRT。打包机 System32 里的 14.50+ 会让 c10.dll 报 WinError 127。
$dllSrc = @(
    (Join-Path $PSScriptRoot "vc_runtime_dlls"),
    "C:\Miniforge3\envs\axweb-win7\Library\bin"
)
foreach ($name in $dllNames) {
    $copied = $false
    foreach ($dir in $dllSrc) {
        $src = Join-Path $dir $name
        if (-not (Test-Path $src)) { continue }
        $ver = (Get-Item $src).VersionInfo.FileVersion
        if ($ver -match '^14\.(3|4|5)') {
            Write-Host "skip $src (CRT $ver 不支持 Win7)"
            continue
        }
        foreach ($destDir in @($OutDir, $internal)) {
            if (Test-Path $destDir) {
                Copy-Item -Force $src (Join-Path $destDir $name)
            }
        }
        # torch 启动会加载 lib 下所有 dll；vccorlib140 依赖 Win8 WinRT，Win7 会报 126
        if ($name -ne "vccorlib140.dll" -and (Test-Path $torchLib)) {
            Copy-Item -Force $src (Join-Path $torchLib $name)
        }
        Write-Host "CRT $name $ver"
        $copied = $true
        break
    }
    if (-not $copied) {
        Write-Host "WARNING: missing Win7 CRT $name"
    }
}

$redist = Join-Path $PSScriptRoot "vc_redist.x64.exe"
if (-not (Test-Path $redist)) {
    Write-Host "==> download vc_redist.x64.exe"
    try {
        Invoke-WebRequest -Uri "https://aka.ms/vs/16/release/vc_redist.x64.exe" -OutFile $redist
    } catch {
        Write-Host "vc_redist download failed: $($_.Exception.Message)"
    }
}
if (Test-Path $redist) {
    Copy-Item -Force $redist (Join-Path $OutDir "vc_redist.x64.exe")
}

Write-Host "==> done: $OutDir"
Write-Host "将整个 AlbumentationsX 目录拷到 Win7 机器。license.dat 写在 exe 同级目录。"
Write-Host "签发：conda run -n $EnvName python -m app.license generate <机器码> --permanent   （cwd=backend）"
