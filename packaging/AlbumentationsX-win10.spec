# -*- mode: python ; coding: utf-8 -*-
"""Win10 + CUDA 11.8 onedir bundle. Build via packaging/build_win10_cuda.ps1."""
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

spec_dir = os.path.dirname(os.path.abspath(SPEC))
repo = os.path.dirname(spec_dir)
backend = os.path.join(repo, "backend")
frontend_dist = os.path.join(repo, "frontend", "dist")

datas = []
binaries = []
hiddenimports = [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "app.main",
    "app.license",
    "app.license_codec",
    "aiosqlite",
    "jaraco",
    "jaraco.text",
    "jaraco.functools",
    "jaraco.context",
    "pkg_resources",
    "more_itertools",
    "multipart",
    "email.mime.multipart",
]

if os.path.isdir(frontend_dist):
    datas.append((frontend_dist, "static"))

for pkg in ("torch", "torchvision", "ultralytics", "cv2", "albumentations", "engineio", "socketio"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        pass

try:
    hiddenimports += collect_submodules("app")
except Exception:
    pass

a = Analysis(
    [os.path.join(spec_dir, "launcher.py")],
    pathex=[backend, spec_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[
        os.path.join(spec_dir, "rthook_mime.py"),
        os.path.join(spec_dir, "rthook_win7_cuda.py"),
    ],
    excludes=["matplotlib.tests", "tkinter", "pytest"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AlbumentationsX",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AlbumentationsX",
)
