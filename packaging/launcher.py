"""Standalone EXE entry: start FastAPI and open the browser."""
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1] / "backend"


def main() -> None:
    import mimetypes

    for ext, mime in ((".js", "application/javascript"), (".css", "text/css"), (".svg", "image/svg+xml")):
        mimetypes.add_type(mime, ext)

    root = _root()
    os.chdir(str(root))
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    path_dirs = [root, root / "_internal", root / "_internal" / "torch" / "lib"]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        path_dirs.append(Path(meipass))
        path_dirs.append(Path(meipass) / "torch" / "lib")
    pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    path_dirs.extend([
        pf / "NVIDIA Corporation" / "NVSMI",
        pf / "NVIDIA GPU Computing Toolkit" / "CUDA" / "v12.4" / "bin",
        pf / "NVIDIA GPU Computing Toolkit" / "CUDA" / "v12.1" / "bin",
        pf / "NVIDIA GPU Computing Toolkit" / "CUDA" / "v11.8" / "bin",
        pf / "NVIDIA GPU Computing Toolkit" / "CUDA" / "v11.4" / "bin",
        pf / "NVIDIA GPU Computing Toolkit" / "CUDA" / "v11.3" / "bin",
    ])
    extras = [str(p) for p in path_dirs if p.is_dir()]
    if extras:
        os.environ["PATH"] = os.pathsep.join(extras + [os.environ.get("PATH", "")])
        if sys.version_info >= (3, 8):
            for p in extras:
                try:
                    os.add_dll_directory(p)
                except (OSError, FileNotFoundError, AttributeError):
                    pass

    os.environ.setdefault("DEBUG", "false")
    os.environ.setdefault("HOST", "127.0.0.1")
    os.environ.setdefault("PORT", "8000")
    os.environ.setdefault("WORKERS", "1")
    os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
    os.environ.setdefault("YOLO_OFFLINE", "1")
    os.environ.setdefault("ULTRALYTICS_OFFLINE", "1")
    os.environ.setdefault("TRAIN_WORKERS", "0")

    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = (data_dir / "app.db").as_posix()
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{db_path}")

    static_candidates = [root / "static"]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        static_candidates.append(Path(meipass) / "static")
    for static in static_candidates:
        if static.exists():
            os.environ.setdefault("STATIC_DIR", str(static))
            break

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))

    def _open_browser() -> None:
        time.sleep(2.0)
        webbrowser.open(f"http://127.0.0.1:{port}/")

    threading.Thread(target=_open_browser, daemon=True).start()

    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port, reload=False, workers=1)


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
