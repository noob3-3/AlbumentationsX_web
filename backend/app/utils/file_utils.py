"""
File handling utilities
"""
import shutil
import yaml
import zipfile
from loguru import logger
from pathlib import Path
from typing import List, Optional


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
        kpt_shape: Optional[List[int]] = None,
        task: Optional[str] = None,
) -> str:
    """Create dataset.yaml for YOLO training and return the path

    names 使用 {0: 'a', 1: 'b'} 字典形式，与 Ultralytics OBB/pose 示例（如 dota8）一致。
    task 建议通过 model.train(task=...) 传入；若需写入 yaml 可传 task。
    """
    yaml_path = Path(dataset_dir) / "dataset.yaml"
    nc = len(classes) if classes else 0
    names_dict = {i: (classes[i] if classes[i] else f"class_{i}") for i in range(nc)} if classes else {}
    data = {
        "path": str(Path(dataset_dir).resolve()),
        "train": train_path,
        "val": val_path,
        "nc": nc,
        "names": names_dict,
    }
    if kpt_shape:
        data["kpt_shape"] = kpt_shape
    if task:
        data["task"] = task
    write_yaml(data, str(yaml_path))
    return str(yaml_path)
