"""
配置加载模块
Config Loading Module

实现YAML配置文件加载和环境变量替换功能。
Implements YAML config file loading and environment variable substitution.

需求 8.6: 配置文件支持通过环境变量覆盖敏感配置（如API密钥）
"""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


def load_env_file(env_path: str | None = None) -> bool:
    """
    加载.env文件中的环境变量。
    Load environment variables from .env file.
    
    Args:
        env_path: .env文件路径，默认为None（自动查找）
                  Path to .env file, defaults to None (auto-discover)
    
    Returns:
        是否成功加载了.env文件
        Whether .env file was successfully loaded
    
    Examples:
        >>> load_env_file()  # 自动查找.env文件
        True
        >>> load_env_file("/path/to/.env")  # 指定路径
        True
    """
    if env_path:
        env_file = Path(env_path)
        if env_file.exists():
            load_dotenv(env_file)
            return True
        return False
    
    # 自动查找.env文件
    # Auto-discover .env file
    return load_dotenv()


def replace_env_vars(value: Any) -> Any:
    """
    递归替换配置值中的环境变量占位符。
    Recursively substitute environment variable placeholders in config values.
    
    支持 ${VAR_NAME} 格式的环境变量替换。
    Supports ${VAR_NAME} format for environment variable substitution.
    
    Args:
        value: 配置值，可以是字符串、字典、列表或其他类型
               Config value, can be string, dict, list, or other types
    
    Returns:
        替换后的配置值。如果环境变量不存在，替换为空字符串。
        Substituted config value. If env var doesn't exist, replaces with empty string.
    
    Examples:
        >>> os.environ['TEST_VAR'] = 'test_value'
        >>> replace_env_vars('${TEST_VAR}')
        'test_value'
        >>> replace_env_vars({'key': '${TEST_VAR}'})
        {'key': 'test_value'}
        >>> replace_env_vars('${NONEXISTENT_VAR}')
        ''
    """
    if isinstance(value, str):
        # 匹配 ${VAR_NAME} 或 ${VAR_NAME:default} 格式的环境变量占位符
        # Match ${VAR_NAME} or ${VAR_NAME:default} format environment variable placeholders
        pattern = r'\$\{([^}:]+)(?::([^}]*))?\}'
        
        def replacer(match: re.Match) -> str:
            var_name = match.group(1)
            default_value = match.group(2) if match.group(2) is not None else ''
            # 如果环境变量存在，返回其值；否则返回默认值
            # If env var exists, return its value; otherwise return default value
            return os.environ.get(var_name, default_value)
        
        return re.sub(pattern, replacer, value)
    
    elif isinstance(value, dict):
        # 递归处理字典中的每个值
        # Recursively process each value in the dictionary
        return {k: replace_env_vars(v) for k, v in value.items()}
    
    elif isinstance(value, list):
        # 递归处理列表中的每个元素
        # Recursively process each element in the list
        return [replace_env_vars(item) for item in value]
    
    # 对于其他类型（int, float, bool, None等），直接返回
    # For other types (int, float, bool, None, etc.), return as-is
    return value


# 保留旧函数名作为别名，保持向后兼容
# Keep old function name as alias for backward compatibility
substitute_env_vars = replace_env_vars


def load_config(config_path: str = "config.yaml", env_path: str | None = None) -> dict:
    """
    加载YAML配置文件并替换环境变量。
    Load YAML config file and substitute environment variables.
    
    会自动加载.env文件中的环境变量（如果存在）。
    Automatically loads environment variables from .env file (if exists).
    
    Args:
        config_path: 配置文件路径，默认为 "config.yaml"
                     Config file path, defaults to "config.yaml"
        env_path: .env文件路径，默认为None（自动查找）
                  Path to .env file, defaults to None (auto-discover)
    
    Returns:
        解析并替换环境变量后的配置字典
        Parsed config dict with environment variables substituted
    
    Raises:
        FileNotFoundError: 配置文件不存在
                          Config file not found
        yaml.YAMLError: YAML解析错误
                       YAML parsing error
    
    Examples:
        >>> config = load_config("config.yaml")
        >>> config['ai']['api_key']  # 如果设置了 OPENAI_API_KEY 环境变量
        'sk-xxx...'
    """
    # 首先加载.env文件中的环境变量
    # First load environment variables from .env file
    load_env_file(env_path)
    
    config_file = Path(config_path)
    
    if not config_file.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 如果配置文件为空，返回空字典
    # If config file is empty, return empty dict
    if config is None:
        return {}
    
    # 递归替换所有环境变量
    # Recursively substitute all environment variables
    return replace_env_vars(config)


def get_config_value(config: dict, key_path: str, default: Any = None) -> Any:
    """
    通过点分隔的路径获取配置值。
    Get config value by dot-separated path.
    
    Args:
        config: 配置字典
                Config dictionary
        key_path: 点分隔的键路径，如 "ai.api_key"
                  Dot-separated key path, e.g., "ai.api_key"
        default: 默认值，当路径不存在时返回
                 Default value to return when path doesn't exist
    
    Returns:
        配置值或默认值
        Config value or default value
    
    Examples:
        >>> config = {'ai': {'api_key': 'test'}}
        >>> get_config_value(config, 'ai.api_key')
        'test'
        >>> get_config_value(config, 'ai.missing', 'default')
        'default'
    """
    keys = key_path.split('.')
    value = config
    
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    
    return value


# 默认配置值
# Default Configuration Values
DEFAULT_CONFIG: dict[str, Any] = {
    # 新数据源默认配置
    # New data sources default configuration
    'data_sources': {
        'dblp': {
            'enabled': True,
            'conferences': ['sp', 'ccs', 'uss', 'ndss'],
            'timeout': 30
        },
        'nvd': {
            'enabled': True,
            'api_key': '',
            'days_back': 7,
            'timeout': 60
        },
        'kev': {
            'enabled': True,
            'days_back': 30,
            'timeout': 30
        },
        'huggingface': {
            'enabled': True,
            'timeout': 30
        },
        'pwc': {
            'enabled': True,
            'limit': 50,
            'timeout': 30
        },
        'blogs': {
            'enabled': True,
            'sources': ['openai', 'deepmind', 'anthropic'],
            'timeout': 30
        }
    },
    # 漏洞过滤默认配置
    # Vulnerability filter default configuration
    'vulnerability_filter': {
        'enabled': True,
        'github_star_threshold': 1000,
        'ip_asset_threshold': 300,
        'enable_ai_assessment': True,
        'github_token': ''
    },
    # 分级推送默认配置
    # Tiered push default configuration
    'tiered_push': {
        'enabled': True,
        'level1_threshold': 0.10,
        'level2_threshold': 0.40
    },
    # 优先级评分默认配置
    # Priority scoring default configuration
    'priority_scoring': {
        'enabled': True,
        'source_weights': {
            'kev': 1.5,
            'nvd': 1.2,
            'dblp': 1.3,
            'huggingface': 1.1,
            'pwc': 1.1,
            'blog': 1.0,
            'arxiv': 1.0,
            'rss': 0.8
        }
    }
}


def _deep_merge(base: dict, override: dict) -> dict:
    """
    深度合并两个字典，override中的值覆盖base中的值。
    Deep merge two dictionaries, values in override take precedence over base.
    
    Args:
        base: 基础字典（默认值）
              Base dictionary (defaults)
        override: 覆盖字典（用户配置）
                  Override dictionary (user config)
    
    Returns:
        合并后的字典
        Merged dictionary
    
    Examples:
        >>> base = {'a': {'b': 1, 'c': 2}}
        >>> override = {'a': {'b': 10}}
        >>> _deep_merge(base, override)
        {'a': {'b': 10, 'c': 2}}
    """
    result = base.copy()
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # 递归合并嵌套字典
            # Recursively merge nested dictionaries
            result[key] = _deep_merge(result[key], value)
        else:
            # 直接覆盖
            # Direct override
            result[key] = value
    
    return result


def apply_defaults(config: dict) -> dict:
    """
    将默认配置应用到用户配置中，缺失的配置项使用默认值。
    Apply default configuration to user config, missing items use defaults.
    
    Args:
        config: 用户配置字典
                User configuration dictionary
    
    Returns:
        应用默认值后的配置字典
        Configuration dictionary with defaults applied
    
    Examples:
        >>> config = {'data_sources': {'dblp': {'enabled': False}}}
        >>> result = apply_defaults(config)
        >>> result['data_sources']['dblp']['enabled']
        False
        >>> result['data_sources']['dblp']['timeout']  # 使用默认值
        30
    """
    return _deep_merge(DEFAULT_CONFIG, config)


def get_data_source_config(config: dict, source_name: str) -> dict:
    """
    获取指定数据源的配置，自动应用默认值。
    Get configuration for a specific data source with defaults applied.
    
    Args:
        config: 完整配置字典
                Full configuration dictionary
        source_name: 数据源名称 (dblp, nvd, kev, huggingface, pwc, blogs)
                     Data source name
    
    Returns:
        数据源配置字典，包含默认值
        Data source configuration dict with defaults
    
    Examples:
        >>> config = {'data_sources': {'dblp': {'enabled': False}}}
        >>> get_data_source_config(config, 'dblp')
        {'enabled': False, 'conferences': ['sp', 'ccs', 'uss', 'ndss'], 'timeout': 30}
    """
    # 获取用户配置的数据源设置
    # Get user-configured data source settings
    user_config = config.get('data_sources', {}).get(source_name, {})
    
    # 获取默认配置
    # Get default configuration
    default_config = DEFAULT_CONFIG.get('data_sources', {}).get(source_name, {})
    
    # 合并配置，用户配置优先
    # Merge configs, user config takes precedence
    return _deep_merge(default_config, user_config)


def get_vulnerability_filter_config(config: dict) -> dict:
    """
    获取漏洞过滤配置，自动应用默认值。
    Get vulnerability filter configuration with defaults applied.
    
    Args:
        config: 完整配置字典
                Full configuration dictionary
    
    Returns:
        漏洞过滤配置字典，包含默认值
        Vulnerability filter configuration dict with defaults
    
    Examples:
        >>> config = {'vulnerability_filter': {'github_star_threshold': 500}}
        >>> result = get_vulnerability_filter_config(config)
        >>> result['github_star_threshold']
        500
        >>> result['ip_asset_threshold']  # 使用默认值
        300
    """
    user_config = config.get('vulnerability_filter', {})
    default_config = DEFAULT_CONFIG.get('vulnerability_filter', {})
    return _deep_merge(default_config, user_config)


def get_tiered_push_config(config: dict) -> dict:
    """
    获取分级推送配置，自动应用默认值。
    Get tiered push configuration with defaults applied.
    
    Args:
        config: 完整配置字典
                Full configuration dictionary
    
    Returns:
        分级推送配置字典，包含默认值
        Tiered push configuration dict with defaults
    
    Examples:
        >>> config = {'tiered_push': {'level1_threshold': 0.15}}
        >>> result = get_tiered_push_config(config)
        >>> result['level1_threshold']
        0.15
        >>> result['level2_threshold']  # 使用默认值
        0.40
    """
    user_config = config.get('tiered_push', {})
    default_config = DEFAULT_CONFIG.get('tiered_push', {})
    return _deep_merge(default_config, user_config)


def get_priority_scoring_config(config: dict) -> dict:
    """
    获取优先级评分配置，自动应用默认值。
    Get priority scoring configuration with defaults applied.
    
    Args:
        config: 完整配置字典
                Full configuration dictionary
    
    Returns:
        优先级评分配置字典，包含默认值
        Priority scoring configuration dict with defaults
    
    Examples:
        >>> config = {'priority_scoring': {'source_weights': {'kev': 2.0}}}
        >>> result = get_priority_scoring_config(config)
        >>> result['source_weights']['kev']
        2.0
        >>> result['source_weights']['nvd']  # 使用默认值
        1.2
    """
    user_config = config.get('priority_scoring', {})
    default_config = DEFAULT_CONFIG.get('priority_scoring', {})
    return _deep_merge(default_config, user_config)


def is_data_source_enabled(config: dict, source_name: str) -> bool:
    """
    检查指定数据源是否启用。
    Check if a specific data source is enabled.
    
    Args:
        config: 完整配置字典
                Full configuration dictionary
        source_name: 数据源名称
                     Data source name
    
    Returns:
        数据源是否启用
        Whether the data source is enabled
    
    Examples:
        >>> config = {'data_sources': {'dblp': {'enabled': False}}}
        >>> is_data_source_enabled(config, 'dblp')
        False
        >>> is_data_source_enabled(config, 'nvd')  # 默认启用
        True
    """
    source_config = get_data_source_config(config, source_name)
    return source_config.get('enabled', True)


def load_config_with_defaults(config_path: str = "config.yaml", env_path: str | None = None) -> dict:
    """
    加载配置文件并应用默认值。
    Load configuration file and apply defaults.
    
    这是推荐的配置加载方式，会自动处理环境变量替换和默认值应用。
    This is the recommended way to load config, handles env var substitution and defaults.
    
    Args:
        config_path: 配置文件路径
                     Config file path
        env_path: .env文件路径
                  Path to .env file
    
    Returns:
        完整的配置字典，包含所有默认值
        Complete configuration dict with all defaults
    
    Examples:
        >>> config = load_config_with_defaults("config.yaml")
        >>> config['data_sources']['dblp']['timeout']
        30
    """
    config = load_config(config_path, env_path)
    return apply_defaults(config)
