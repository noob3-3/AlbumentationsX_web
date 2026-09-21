# Win10 x64: Python 3.10 + PyTorch 2.2.2 + CUDA 11.8
# Output: packaging\dist-win10\AlbumentationsX

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$EnvName = "axweb-win10"
$Conda = "C:\Miniforge3\Scripts\conda.exe"
if (-not (Test-Path $Conda)) {
    $Conda = (Get-Command conda -ErrorAction SilentlyContinue).Source
}
if (-not $Conda) {
    throw "conda not found"
}

Write-Host "==> conda env: $EnvName (python 3.10)"
$exists = & $Conda env list | Select-String -Pattern "^\s*$EnvName\s"
if (-not $exists) {
    & $Conda create -y -n $EnvName python=3.10
}

Write-Host "==> pip + torch 2.2.2 cu118"
& $Conda run -n $EnvName --no-capture-output python -m pip install -U pip setuptools wheel
& $Conda run -n $EnvName --no-capture-output python -m pip install torch==2.2.2 torchvision==0.17.2 torchaudio==2.2.2 --index-url https://download.pytorch.org/whl/cu118

Write-Host "==> app dependencies"
& $Conda run -n $EnvName --no-capture-output python -m pip install -r "$Repo\packaging\requirements-win10-cuda.txt"

Write-Host "==> frontend"
Push-Location "$Repo\frontend"
if (-not (Test-Path "node_modules")) {
    npm install
}
npm run build
if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }
Pop-Location

Write-Host "==> PyInstaller"
$Dist = Join-Path $Repo "packaging\dist-win10"
$Build = Join-Path $Repo "packaging\build-win10"
& $Conda run -n $EnvName --no-capture-output python -m PyInstaller --noconfirm --clean --distpath $Dist --workpath $Build "$Repo\packaging\AlbumentationsX-win10.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$OutDir = Join-Path $Dist "AlbumentationsX"
$StaticSrc = Join-Path $Repo "frontend\dist"
$StaticDst = Join-Path $OutDir "static"
if (Test-Path $StaticSrc) {
    Copy-Item -Recurse -Force $StaticSrc $StaticDst
}
Copy-Item -Force (Join-Path $PSScriptRoot "启动.bat") (Join-Path $OutDir "启动.bat")

$internal = Join-Path $OutDir "_internal"
$torchLib = Join-Path $internal "torch\lib"
$dllNames = @(
    "vcruntime140.dll", "vcruntime140_1.dll",
    "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
    "concrt140.dll"
)
foreach ($name in $dllNames) {
    $src = Join-Path $env:SystemRoot "System32\$name"
    if (-not (Test-Path $src)) { continue }
    foreach ($destDir in @($OutDir, $internal)) {
        if (Test-Path $destDir) {
            Copy-Item -Force $src (Join-Path $destDir $name)
        }
    }
    if (Test-Path $torchLib) {
        Copy-Item -Force $src (Join-Path $torchLib $name)
    }
}
$bad = Join-Path $torchLib "vccorlib140.dll"
if (Test-Path $bad) { Remove-Item -Force $bad }

$exe = Get-Item (Join-Path $OutDir "AlbumentationsX.exe")
Write-Host "==> done: $OutDir"
Write-Host "exe=$($exe.Length) time=$($exe.LastWriteTime)"
