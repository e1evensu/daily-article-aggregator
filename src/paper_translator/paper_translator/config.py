"""
配置管理
"""

import os
from pathlib import Path
from typing import Optional
import yaml


def _load_env_file():
    """加载.env文件"""
    env_file = Path(__file__).parent.parent / '.env'
    if env_file.exists():
        with open(env_file, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

# 加载环境变量
_load_env_file()


class Config:
    """配置管理类"""

    _instance: Optional['Config'] = None

    def __init__(self):
        self._config = {}
        self._load_default_config()

    @classmethod
    def get_instance(cls) -> 'Config':
        """单例模式获取配置"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_default_config(self):
        """加载默认配置"""
        # 默认值
        self._config = {
            'input_pdf_dir': 'input_papers',
            'output_dir': 'translated_papers',
            'batch_size': 5,
            'max_workers': 3,
            'timeout': 120,
            'translation_style': 'academic',
            'add_terminology': True,
            'add_formula_explanation': True,
            'add_figure_description': True,
            'terminology_db_path': 'data/terminology.db',
        }

        # 从环境变量加载API配置
        self._config['deepseek_api_key'] = os.getenv('DEEPSEEK_API_KEY', '')
        self._config['deepseek_base_url'] = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
        self._config['deepseek_model'] = os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')
        self._config['siliconflow_api_key'] = os.getenv('SILICONFLOW_API_KEY', '')
        self._config['siliconflow_base_url'] = os.getenv('SILICONFLOW_BASE_URL', 'https://api.siliconflow.cn/v1')

    def load_from_yaml(self, yaml_path: str):
        """从YAML文件加载配置"""
        path = Path(yaml_path)
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
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
        return self._config.get('deepseek_api_key', '')

    @property
    def deepseek_base_url(self) -> str:
        return self._config.get('deepseek_base_url', 'https://api.deepseek.com')

    @property
    def deepseek_model(self) -> str:
        return self._config.get('deepseek_model', 'deepseek-chat')

    @property
    def siliconflow_api_key(self) -> str:
        return self._config.get('siliconflow_api_key', '')

    @property
    def siliconflow_base_url(self) -> str:
        return self._config.get('siliconflow_base_url', 'https://api.siliconflow.cn/v1')

    @property
    def input_dir(self) -> str:
        return self._config.get('input_pdf_dir', 'input_papers')

    @property
    def output_dir(self) -> str:
        return self._config.get('output_dir', 'translated_papers')


# 全局配置实例
config = Config.get_instance()
