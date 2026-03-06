"""
File handling utilities
"""
import shutil
import zipfile
import yaml
from pathlib import Path
from typing import List
from loguru import logger


def allowed_image(filename: str) -> bool:
    allowed = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}
    return Path(filename).suffix.lower() in allowed


def safe_remove(path: str):
    try:
        p = Path(path)
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)
    except Exception as e:
        logger.warning(f"Could not remove {path}: {e}")


def create_zip(source_dir: str, output_path: str, file_list: List[str] = None):
    """Zip a directory or a list of files"""
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if file_list:
            for f in file_list:
                zf.write(f, Path(f).name)
        else:
            for f in Path(source_dir).rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(source_dir))


def write_yaml(data: dict, path: str):
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def read_yaml(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def build_yolo_dataset_yaml(
    dataset_dir: str,
    classes: List[str],
    train_path: str = "images/train",
    val_path: str = "images/val",
) -> str:
    """Create dataset.yaml for YOLO training and return the path"""
    yaml_path = Path(dataset_dir) / "dataset.yaml"
    data = {
        "path": str(Path(dataset_dir).resolve()),
        "train": train_path,
        "val": val_path,
        "nc": len(classes),
        "names": classes,
    }
    write_yaml(data, str(yaml_path))
    return str(yaml_path)
