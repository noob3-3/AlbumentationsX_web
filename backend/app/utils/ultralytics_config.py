"""
Ultralytics YOLO Settings Configuration Manager
管理 Ultralytics YOLO 的全局设置配置
"""
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger


DEFAULT_ULTRALYTICS_SETTINGS = {
    "settings_version": "0.0.6",
    "datasets_dir": "/datasets",
    "weights_dir": "/ultralytics/weights",
    "runs_dir": "/ultralytics/runs",
    "uuid": "05a653ab0e8d32790722b61ca4c4560430841f4a3b35dc9179a4687400aa4eec",
    "sync": True,
    "api_key": "",
    "openai_api_key": "",
    # 集成平台开关 (默认关闭以避免不必要的网络请求)
    "clearml": False,
    "comet": False,
    "dvc": False,
    "hub": False,
    "mlflow": False,
    "neptune": False,
    "raytune": False,
    "tensorboard": True,  # 保持 TensorBoard 开启
    "wandb": False,
    # 消息提示
    "vscode_msg": True,
    "openvino_msg": True,
}


class UltralyticsConfigManager:
    """Ultralytics 配置管理器"""

    @staticmethod
    def get_settings_path(config_dir: Optional[Path] = None) -> Path:
        """
        获取 Ultralytics Settings.yaml 文件路径

        Args:
            config_dir: 配置目录，如果为 None 则使用环境变量 YOLO_CONFIG_DIR

        Returns:
            Settings.yaml 文件的完整路径
        """
        if config_dir is None:
            import os
            config_dir_str = os.getenv('YOLO_CONFIG_DIR')
            if config_dir_str:
                config_dir = Path(config_dir_str)
            else:
                # 默认使用用户主目录下的 .config/Ultralytics
                config_dir = Path.home() / '.config' / 'Ultralytics'

        config_dir = Path(config_dir)
        config_dir.mkdir(parents=True, exist_ok=True)

        return config_dir / 'settings.yaml'

    @staticmethod
    def generate_settings(
        datasets_dir: Optional[str] = None,
        weights_dir: Optional[str] = None,
        runs_dir: Optional[str] = None,
        enable_integrations: bool = False,
        custom_settings: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        生成 Ultralytics 设置配置

        Args:
            datasets_dir: 数据集目录路径
            weights_dir: 预训练权重目录路径
            runs_dir: 训练结果输出目录路径
            enable_integrations: 是否启用第三方集成平台 (clearml, comet, mlflow 等)
            custom_settings: 自定义设置字典，会覆盖默认设置

        Returns:
            设置配置字典
        """
        settings = DEFAULT_ULTRALYTICS_SETTINGS.copy()

        # 更新目录路径
        if datasets_dir:
            settings['datasets_dir'] = datasets_dir
        if weights_dir:
            settings['weights_dir'] = weights_dir
        if runs_dir:
            settings['runs_dir'] = runs_dir

        # 如果不启用集成平台，全部设为 False
        if not enable_integrations:
            integration_keys = [
                'clearml', 'comet', 'dvc', 'hub',
                'mlflow', 'neptune', 'raytune', 'wandb'
            ]
            for key in integration_keys:
                settings[key] = False

        # 应用自定义设置
        if custom_settings:
            settings.update(custom_settings)

        return settings

    @staticmethod
    def write_settings(
        settings: Dict[str, Any],
        config_path: Optional[Path] = None
    ) -> Path:
        """
        写入 Ultralytics 设置到 YAML 文件

        Args:
            settings: 设置配置字典
            config_path: 配置文件路径，如果为 None 则自动确定

        Returns:
            写入的配置文件路径
        """
        if config_path is None:
            config_path = UltralyticsConfigManager.get_settings_path()

        config_path = Path(config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(settings, f, default_flow_style=False, allow_unicode=True)

            logger.info(f"Ultralytics settings written to: {config_path}")
            return config_path

        except Exception as e:
            logger.error(f"Failed to write Ultralytics settings: {e}")
            raise

    @staticmethod
    def read_settings(config_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
        """
        读取 Ultralytics 设置

        Args:
            config_path: 配置文件路径，如果为 None 则自动确定

        Returns:
            设置配置字典，如果文件不存在则返回 None
        """
        if config_path is None:
            config_path = UltralyticsConfigManager.get_settings_path()

        config_path = Path(config_path)

        if not config_path.exists():
            return None

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                settings = yaml.safe_load(f)

            logger.info(f"Ultralytics settings loaded from: {config_path}")
            return settings

        except Exception as e:
            logger.error(f"Failed to read Ultralytics settings: {e}")
            return None

    @staticmethod
    def initialize_settings(
        config_dir: Optional[Path] = None,
        datasets_dir: Optional[str] = None,
        weights_dir: Optional[str] = None,
        runs_dir: Optional[str] = None,
        enable_integrations: bool = False,
        force_overwrite: bool = False
    ) -> Path:
        """
        初始化 Ultralytics 设置（如果不存在或强制覆盖）

        Args:
            config_dir: 配置目录
            datasets_dir: 数据集目录
            weights_dir: 权重目录
            runs_dir: 运行结果目录
            enable_integrations: 是否启用集成平台
            force_overwrite: 是否强制覆盖已存在的配置

        Returns:
            配置文件路径
        """
        config_path = UltralyticsConfigManager.get_settings_path(config_dir)

        # 如果文件已存在且不强制覆盖，直接返回
        if config_path.exists() and not force_overwrite:
            logger.info(f"Ultralytics settings already exists: {config_path}")
            return config_path

        # 生成并写入设置
        settings = UltralyticsConfigManager.generate_settings(
            datasets_dir=datasets_dir,
            weights_dir=weights_dir,
            runs_dir=runs_dir,
            enable_integrations=enable_integrations
        )

        return UltralyticsConfigManager.write_settings(settings, config_path)


def setup_ultralytics_config(
    model_dir: Path,
    dataset_dir: Path,
    enable_integrations: bool = False
) -> None:
    """
    设置 Ultralytics 配置（应用启动时调用）

    Args:
        model_dir: 模型存储目录
        dataset_dir: 数据集目录
        enable_integrations: 是否启用第三方集成
    """
    try:
        # 使用 MODEL_DIR 作为配置目录
        config_dir = model_dir

        # 初始化设置
        config_path = UltralyticsConfigManager.initialize_settings(
            config_dir=config_dir,
            datasets_dir=str(dataset_dir),
            weights_dir=str(model_dir),
            runs_dir=str(model_dir / "runs"),
            enable_integrations=enable_integrations,
            force_overwrite=False  # 不强制覆盖，保留用户自定义配置
        )

        logger.info(f"✓ Ultralytics configuration initialized: {config_path}")

        # 读取并显示当前配置
        settings = UltralyticsConfigManager.read_settings(config_path)
        if settings:
            logger.debug(f"Ultralytics settings: {settings}")

    except Exception as e:
        logger.warning(f"Failed to setup Ultralytics config (non-critical): {e}")

