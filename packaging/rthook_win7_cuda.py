"""Win7: put CRT + torch CUDA dirs on PATH before torch loads."""
import os
import sys
from pathlib import Path


def _add(dirpath: Path) -> None:
    if not dirpath.is_dir():
        return
    s = str(dirpath)
    os.environ["PATH"] = s + os.pathsep + os.environ.get("PATH", "")
    if sys.version_info >= (3, 8):
        try:
            os.add_dll_directory(s)
        except (OSError, FileNotFoundError, AttributeError):
            pass


root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()
meipass = Path(getattr(sys, "_MEIPASS", root))
pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))

for p in (
    root,
    meipass,
    meipass / "torch" / "lib",
    root / "_internal" / "torch" / "lib",
    pf / "NVIDIA Corporation" / "NVSMI",
    pf / "NVIDIA GPU Computing Toolkit" / "CUDA" / "v12.4" / "bin",
    pf / "NVIDIA GPU Computing Toolkit" / "CUDA" / "v12.1" / "bin",
    pf / "NVIDIA GPU Computing Toolkit" / "CUDA" / "v11.8" / "bin",
    pf / "NVIDIA GPU Computing Toolkit" / "CUDA" / "v11.4" / "bin",
    pf / "NVIDIA GPU Computing Toolkit" / "CUDA" / "v11.3" / "bin",
):
    _add(p)
