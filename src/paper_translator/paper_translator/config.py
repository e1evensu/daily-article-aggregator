"""
配置管理
"""

import os
from pathlib import Path
from typing import Optional
import yaml


def _load_env_file():
    """加载.env文件"""
    possible_paths = [
        Path(__file__).parent.parent / ".env",
        Path(__file__).parent.parent.parent.parent / ".env",
        Path.cwd() / ".env",
    ]

    for env_file in possible_paths:
        if env_file.exists():
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        os.environ[key.strip()] = value.strip()
            break
            break


# 加载环境变量
_load_env_file()


class Config:
    """配置管理类"""

    _instance: Optional["Config"] = None

    def __init__(self):
        self._config = {}
        self._load_default_config()

    @classmethod
    def get_instance(cls) -> "Config":
        """单例模式获取配置"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_default_config(self):
        """加载默认配置"""
        # 默认值
        self._config = {
            "input_pdf_dir": "input_papers",
            "output_dir": "translated_papers",
            "batch_size": 5,
            "max_workers": 3,
            "timeout": 120,
            "translation_style": "academic",
            "add_terminology": True,
            "add_formula_explanation": True,
            "add_figure_description": True,
            "terminology_db_path": "data/terminology.db",
        }

        # 从环境变量加载API配置
        self._config["deepseek_api_key"] = os.getenv("DEEPSEEK_API_KEY", "")
        self._config["deepseek_base_url"] = os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        )
        self._config["deepseek_model"] = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self._config["siliconflow_api_key"] = os.getenv("SILICONFLOW_API_KEY", "")
        self._config["siliconflow_base_url"] = os.getenv(
            "SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"
        )
        # MiniMax API配置（Claude格式，用于翻译）
        self._config["minimax_api_key"] = os.getenv("MINIMAX_API_KEY", "")
        self._config["minimax_base_url"] = os.getenv(
            "MINIMAX_BASE_URL", "https://api.minimaxi.com/anthropic"
        )
        self._config["minimax_model"] = os.getenv("MINIMAX_MODEL", "MiniMax-M2.5")
        # 翻译API提供商选择: 'deepseek' 或 'minimax'
        self._config["translation_provider"] = os.getenv(
            "TRANSLATION_PROVIDER", "deepseek"
        )

    def load_from_yaml(self, yaml_path: str):
        """从YAML文件加载配置"""
        path = Path(yaml_path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config:
                    self._config.update(yaml_config)

    def get(self, key: str, default=None):
        """获取配置项"""
        return self._config.get(key, default)

    def set(self, key: str, value):
        """设置配置项"""
        self._config[key] = value

    @property
    def deepseek_api_key(self) -> str:
        return self._config.get("deepseek_api_key", "")

    @property
    def deepseek_base_url(self) -> str:
        return self._config.get("deepseek_base_url", "https://api.deepseek.com")

    @property
    def deepseek_model(self) -> str:
        return self._config.get("deepseek_model", "deepseek-chat")

    @property
    def siliconflow_api_key(self) -> str:
        return self._config.get("siliconflow_api_key", "")

    @property
    def siliconflow_base_url(self) -> str:
        return self._config.get("siliconflow_base_url", "https://api.siliconflow.cn/v1")

    @property
    def minimax_api_key(self) -> str:
        return self._config.get("minimax_api_key", "")

    @property
    def minimax_base_url(self) -> str:
        return self._config.get(
            "minimax_base_url", "https://api.minimaxi.com/anthropic"
        )

    @property
    def minimax_model(self) -> str:
        return self._config.get("minimax_model", "MiniMax-M2.5")

    @property
    def translation_provider(self) -> str:
        return self._config.get("translation_provider", "deepseek")

    @property
    def input_dir(self) -> str:
        return self._config.get("input_pdf_dir", "input_papers")

    @property
    def output_dir(self) -> str:
        return self._config.get("output_dir", "translated_papers")


# 全局配置实例
config = Config.get_instance()
