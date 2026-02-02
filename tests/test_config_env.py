"""
配置加载模块单元测试
Unit tests for config loading module

测试 YAML 配置文件加载和环境变量替换功能。
Tests YAML config file loading and environment variable substitution.
"""

import os
import tempfile
from pathlib import Path

import pytest

from src.config import (
    get_config_value,
    load_config,
    load_env_file,
    replace_env_vars,
    substitute_env_vars,
)


class TestReplaceEnvVars:
    """测试环境变量替换功能"""

    def test_replace_simple_string(self):
        """测试简单字符串中的环境变量替换"""
        os.environ['TEST_VAR_1'] = 'hello'
        result = replace_env_vars('${TEST_VAR_1}')
        assert result == 'hello'
        del os.environ['TEST_VAR_1']

    def test_replace_string_with_prefix_suffix(self):
        """测试带前缀和后缀的字符串中的环境变量替换"""
        os.environ['TEST_VAR_2'] = 'world'
        result = replace_env_vars('Hello ${TEST_VAR_2}!')
        assert result == 'Hello world!'
        del os.environ['TEST_VAR_2']

    def test_replace_multiple_vars_in_string(self):
        """测试字符串中多个环境变量的替换"""
        os.environ['VAR_A'] = 'foo'
        os.environ['VAR_B'] = 'bar'
        result = replace_env_vars('${VAR_A} and ${VAR_B}')
        assert result == 'foo and bar'
        del os.environ['VAR_A']
        del os.environ['VAR_B']

    def test_replace_nonexistent_var_returns_empty(self):
        """测试不存在的环境变量返回空字符串"""
        # 确保变量不存在
        if 'NONEXISTENT_VAR_XYZ' in os.environ:
            del os.environ['NONEXISTENT_VAR_XYZ']
        result = replace_env_vars('${NONEXISTENT_VAR_XYZ}')
        assert result == ''

    def test_replace_in_dict(self):
        """测试字典中的环境变量替换"""
        os.environ['DICT_VAR'] = 'dict_value'
        config = {
            'key1': '${DICT_VAR}',
            'key2': 'static_value',
        }
        result = replace_env_vars(config)
        assert result['key1'] == 'dict_value'
        assert result['key2'] == 'static_value'
        del os.environ['DICT_VAR']

    def test_replace_in_nested_dict(self):
        """测试嵌套字典中的环境变量替换"""
        os.environ['NESTED_VAR'] = 'nested_value'
        config = {
            'level1': {
                'level2': {
                    'key': '${NESTED_VAR}'
                }
            }
        }
        result = replace_env_vars(config)
        assert result['level1']['level2']['key'] == 'nested_value'
        del os.environ['NESTED_VAR']

    def test_replace_in_list(self):
        """测试列表中的环境变量替换"""
        os.environ['LIST_VAR'] = 'list_value'
        config = ['${LIST_VAR}', 'static', '${LIST_VAR}']
        result = replace_env_vars(config)
        assert result == ['list_value', 'static', 'list_value']
        del os.environ['LIST_VAR']

    def test_replace_in_mixed_structure(self):
        """测试混合结构（字典+列表）中的环境变量替换"""
        os.environ['MIX_VAR'] = 'mix_value'
        config = {
            'items': ['${MIX_VAR}', 'static'],
            'nested': {
                'list': ['a', '${MIX_VAR}', 'b']
            }
        }
        result = replace_env_vars(config)
        assert result['items'] == ['mix_value', 'static']
        assert result['nested']['list'] == ['a', 'mix_value', 'b']
        del os.environ['MIX_VAR']

    def test_replace_preserves_non_string_types(self):
        """测试非字符串类型保持不变"""
        config = {
            'int_val': 42,
            'float_val': 3.14,
            'bool_val': True,
            'none_val': None,
        }
        result = replace_env_vars(config)
        assert result['int_val'] == 42
        assert result['float_val'] == 3.14
        assert result['bool_val'] is True
        assert result['none_val'] is None

    def test_substitute_env_vars_alias(self):
        """测试 substitute_env_vars 别名函数"""
        os.environ['ALIAS_VAR'] = 'alias_value'
        result = substitute_env_vars('${ALIAS_VAR}')
        assert result == 'alias_value'
        del os.environ['ALIAS_VAR']


class TestLoadConfig:
    """测试配置文件加载功能"""

    def test_load_simple_config(self, tmp_path):
        """测试加载简单配置文件"""
        config_content = """
name: test
version: 1.0
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        
        config = load_config(str(config_file))
        assert config['name'] == 'test'
        assert config['version'] == 1.0

    def test_load_config_with_env_vars(self, tmp_path):
        """测试加载带环境变量的配置文件"""
        os.environ['CONFIG_API_KEY'] = 'sk-test-key'
        config_content = """
api:
  key: "${CONFIG_API_KEY}"
  url: "https://api.example.com"
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        
        config = load_config(str(config_file))
        assert config['api']['key'] == 'sk-test-key'
        assert config['api']['url'] == 'https://api.example.com'
        del os.environ['CONFIG_API_KEY']

    def test_load_config_file_not_found(self):
        """测试配置文件不存在时抛出异常"""
        with pytest.raises(FileNotFoundError):
            load_config('/nonexistent/path/config.yaml')

    def test_load_empty_config(self, tmp_path):
        """测试加载空配置文件"""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")
        
        config = load_config(str(config_file))
        assert config == {}

    def test_load_config_with_env_file(self, tmp_path):
        """测试加载配置时同时加载.env文件"""
        # 创建.env文件
        env_file = tmp_path / ".env"
        env_file.write_text("ENV_FILE_VAR_UNIQUE=from_env_file\n")
        
        # 创建配置文件
        config_content = """
value: "${ENV_FILE_VAR_UNIQUE}"
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        
        # 使用指定的env_path加载配置
        config = load_config(str(config_file), env_path=str(env_file))
        assert config['value'] == 'from_env_file'
        
        # 清理环境变量
        if 'ENV_FILE_VAR_UNIQUE' in os.environ:
            del os.environ['ENV_FILE_VAR_UNIQUE']


class TestGetConfigValue:
    """测试配置值获取功能"""

    def test_get_simple_value(self):
        """测试获取简单配置值"""
        config = {'key': 'value'}
        assert get_config_value(config, 'key') == 'value'

    def test_get_nested_value(self):
        """测试获取嵌套配置值"""
        config = {
            'level1': {
                'level2': {
                    'key': 'nested_value'
                }
            }
        }
        assert get_config_value(config, 'level1.level2.key') == 'nested_value'

    def test_get_missing_value_returns_default(self):
        """测试获取不存在的配置值返回默认值"""
        config = {'key': 'value'}
        assert get_config_value(config, 'missing', 'default') == 'default'

    def test_get_missing_nested_value_returns_default(self):
        """测试获取不存在的嵌套配置值返回默认值"""
        config = {'level1': {'key': 'value'}}
        assert get_config_value(config, 'level1.missing.key', 'default') == 'default'

    def test_get_value_default_is_none(self):
        """测试默认值为None"""
        config = {'key': 'value'}
        assert get_config_value(config, 'missing') is None


class TestLoadEnvFile:
    """测试.env文件加载功能"""

    def test_load_env_file_with_path(self, tmp_path):
        """测试指定路径加载.env文件"""
        env_file = tmp_path / ".env"
        env_file.write_text("LOAD_ENV_TEST=test_value\n")
        
        result = load_env_file(str(env_file))
        assert result is True
        assert os.environ.get('LOAD_ENV_TEST') == 'test_value'
        del os.environ['LOAD_ENV_TEST']

    def test_load_env_file_not_found(self, tmp_path):
        """测试.env文件不存在时返回False"""
        result = load_env_file(str(tmp_path / "nonexistent.env"))
        assert result is False


# ============================================================================
# Property-Based Tests using Hypothesis
# ============================================================================

from hypothesis import given, strategies as st, settings, assume


# Strategy for generating valid environment variable names
# Valid names: alphanumeric + underscore, must start with letter or underscore
var_name_strategy = st.from_regex(r'^[A-Za-z_][A-Za-z0-9_]{0,30}$', fullmatch=True)

# Strategy for generating safe values (no ${} patterns to avoid nested substitution)
# Also exclude null characters as they cannot be stored in environment variables
safe_value_strategy = st.text(
    alphabet=st.characters(
        blacklist_categories=('Cs',),  # Exclude surrogate characters
        blacklist_characters='${}\x00',  # Exclude characters that could form env var patterns or null
    ),
    min_size=0,
    max_size=100
)


class TestEnvVarSubstitutionProperty:
    """
    Feature: daily-article-aggregator, Property 11: 环境变量替换
    
    Property 11: 环境变量替换
    *对于任意*包含`${VAR_NAME}`格式的配置值，当对应环境变量存在时，应该被替换为环境变量的值。
    Also support `${VAR_NAME:default}` format where default value is used when env var doesn't exist.
    
    **Validates: Requirements 8.6**
    """

    @given(
        var_name=var_name_strategy,
        var_value=safe_value_strategy
    )
    @settings(max_examples=100)
    def test_env_var_replacement_when_exists(self, var_name: str, var_value: str):
        """
        Feature: daily-article-aggregator, Property 11: 环境变量替换
        
        Property: For any string containing ${VAR_NAME}, when the env var exists,
        it gets replaced with the env var value.
        
        **Validates: Requirements 8.6**
        """
        # Ensure the variable name is unique to avoid conflicts
        test_var_name = f"PROP_TEST_{var_name}"
        
        try:
            # Set the environment variable
            os.environ[test_var_name] = var_value
            
            # Test simple replacement
            input_str = f'${{{test_var_name}}}'
            result = replace_env_vars(input_str)
            assert result == var_value, f"Expected '{var_value}', got '{result}'"
            
            # Test replacement with prefix and suffix
            input_str_with_context = f'prefix ${{{test_var_name}}} suffix'
            result_with_context = replace_env_vars(input_str_with_context)
            assert result_with_context == f'prefix {var_value} suffix', \
                f"Expected 'prefix {var_value} suffix', got '{result_with_context}'"
        finally:
            # Clean up
            if test_var_name in os.environ:
                del os.environ[test_var_name]

    @given(
        var_name=var_name_strategy,
        default_value=safe_value_strategy
    )
    @settings(max_examples=100)
    def test_default_value_when_env_var_not_exists(self, var_name: str, default_value: str):
        """
        Feature: daily-article-aggregator, Property 11: 环境变量替换
        
        Property: For any string containing ${VAR_NAME:default}, when env var doesn't exist,
        it gets replaced with the default value.
        
        **Validates: Requirements 8.6**
        """
        # Ensure the variable name is unique and doesn't exist
        test_var_name = f"PROP_TEST_NOEXIST_{var_name}"
        
        # Make sure the env var doesn't exist
        if test_var_name in os.environ:
            del os.environ[test_var_name]
        
        # Test default value replacement
        input_str = f'${{{test_var_name}:{default_value}}}'
        result = replace_env_vars(input_str)
        assert result == default_value, f"Expected '{default_value}', got '{result}'"
        
        # Test with prefix and suffix
        input_str_with_context = f'prefix ${{{test_var_name}:{default_value}}} suffix'
        result_with_context = replace_env_vars(input_str_with_context)
        assert result_with_context == f'prefix {default_value} suffix', \
            f"Expected 'prefix {default_value} suffix', got '{result_with_context}'"

    @given(
        var_name=var_name_strategy,
        var_value=safe_value_strategy,
        default_value=safe_value_strategy
    )
    @settings(max_examples=100)
    def test_env_var_takes_precedence_over_default(self, var_name: str, var_value: str, default_value: str):
        """
        Feature: daily-article-aggregator, Property 11: 环境变量替换
        
        Property: When env var exists, its value takes precedence over the default value.
        
        **Validates: Requirements 8.6**
        """
        test_var_name = f"PROP_TEST_PREC_{var_name}"
        
        try:
            # Set the environment variable
            os.environ[test_var_name] = var_value
            
            # Test that env var value is used instead of default
            input_str = f'${{{test_var_name}:{default_value}}}'
            result = replace_env_vars(input_str)
            assert result == var_value, \
                f"Expected env var value '{var_value}', got '{result}' (default was '{default_value}')"
        finally:
            if test_var_name in os.environ:
                del os.environ[test_var_name]

    @given(
        var_name=var_name_strategy,
        var_value=safe_value_strategy,
        dict_keys=st.lists(st.text(min_size=1, max_size=20, alphabet='abcdefghijklmnopqrstuvwxyz'), min_size=1, max_size=5)
    )
    @settings(max_examples=100)
    def test_recursive_replacement_in_dicts(self, var_name: str, var_value: str, dict_keys: list):
        """
        Feature: daily-article-aggregator, Property 11: 环境变量替换
        
        Property: The replacement works recursively in dicts.
        
        **Validates: Requirements 8.6**
        """
        # Ensure unique keys
        dict_keys = list(set(dict_keys))
        assume(len(dict_keys) >= 1)
        
        test_var_name = f"PROP_TEST_DICT_{var_name}"
        
        try:
            os.environ[test_var_name] = var_value
            
            # Build a nested dict structure
            config = {}
            current = config
            for i, key in enumerate(dict_keys[:-1]):
                current[key] = {}
                current = current[key]
            current[dict_keys[-1]] = f'${{{test_var_name}}}'
            
            # Apply replacement
            result = replace_env_vars(config)
            
            # Navigate to the leaf value
            current_result = result
            for key in dict_keys:
                current_result = current_result[key]
            
            assert current_result == var_value, \
                f"Expected '{var_value}' at nested path, got '{current_result}'"
        finally:
            if test_var_name in os.environ:
                del os.environ[test_var_name]

    @given(
        var_name=var_name_strategy,
        var_value=safe_value_strategy,
        list_size=st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=100)
    def test_recursive_replacement_in_lists(self, var_name: str, var_value: str, list_size: int):
        """
        Feature: daily-article-aggregator, Property 11: 环境变量替换
        
        Property: The replacement works recursively in lists.
        
        **Validates: Requirements 8.6**
        """
        test_var_name = f"PROP_TEST_LIST_{var_name}"
        
        try:
            os.environ[test_var_name] = var_value
            
            # Build a list with env var placeholders at various positions
            config_list = [f'${{{test_var_name}}}' if i % 2 == 0 else 'static' for i in range(list_size)]
            
            result = replace_env_vars(config_list)
            
            # Verify all placeholders were replaced
            for i, item in enumerate(result):
                if i % 2 == 0:
                    assert item == var_value, f"Expected '{var_value}' at index {i}, got '{item}'"
                else:
                    assert item == 'static', f"Expected 'static' at index {i}, got '{item}'"
        finally:
            if test_var_name in os.environ:
                del os.environ[test_var_name]

    @given(
        var_name=var_name_strategy,
        var_value=safe_value_strategy,
        default_value=safe_value_strategy
    )
    @settings(max_examples=100)
    def test_mixed_structure_replacement(self, var_name: str, var_value: str, default_value: str):
        """
        Feature: daily-article-aggregator, Property 11: 环境变量替换
        
        Property: The replacement works correctly in mixed structures (dicts containing lists).
        
        **Validates: Requirements 8.6**
        """
        test_var_name_exists = f"PROP_TEST_MIX_E_{var_name}"
        test_var_name_not_exists = f"PROP_TEST_MIX_NE_{var_name}"
        
        # Ensure the non-existent var doesn't exist
        if test_var_name_not_exists in os.environ:
            del os.environ[test_var_name_not_exists]
        
        try:
            os.environ[test_var_name_exists] = var_value
            
            config = {
                'items': [f'${{{test_var_name_exists}}}', 'static'],
                'nested': {
                    'list': ['a', f'${{{test_var_name_not_exists}:{default_value}}}', 'b'],
                    'value': f'${{{test_var_name_exists}}}'
                }
            }
            
            result = replace_env_vars(config)
            
            # Verify replacements
            assert result['items'][0] == var_value
            assert result['items'][1] == 'static'
            assert result['nested']['list'][0] == 'a'
            assert result['nested']['list'][1] == default_value
            assert result['nested']['list'][2] == 'b'
            assert result['nested']['value'] == var_value
        finally:
            if test_var_name_exists in os.environ:
                del os.environ[test_var_name_exists]

    @given(
        var_name1=var_name_strategy,
        var_name2=var_name_strategy,
        var_value1=safe_value_strategy,
        var_value2=safe_value_strategy
    )
    @settings(max_examples=100)
    def test_multiple_vars_in_single_string(self, var_name1: str, var_name2: str, var_value1: str, var_value2: str):
        """
        Feature: daily-article-aggregator, Property 11: 环境变量替换
        
        Property: Multiple environment variables in a single string are all replaced correctly.
        
        **Validates: Requirements 8.6**
        """
        # Ensure different variable names
        assume(var_name1 != var_name2)
        
        test_var_name1 = f"PROP_TEST_MULTI1_{var_name1}"
        test_var_name2 = f"PROP_TEST_MULTI2_{var_name2}"
        
        try:
            os.environ[test_var_name1] = var_value1
            os.environ[test_var_name2] = var_value2
            
            input_str = f'${{{test_var_name1}}} and ${{{test_var_name2}}}'
            result = replace_env_vars(input_str)
            
            expected = f'{var_value1} and {var_value2}'
            assert result == expected, f"Expected '{expected}', got '{result}'"
        finally:
            if test_var_name1 in os.environ:
                del os.environ[test_var_name1]
            if test_var_name2 in os.environ:
                del os.environ[test_var_name2]

    @given(
        non_string_value=st.one_of(
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.booleans(),
            st.none()
        )
    )
    @settings(max_examples=100)
    def test_non_string_types_preserved(self, non_string_value):
        """
        Feature: daily-article-aggregator, Property 11: 环境变量替换
        
        Property: Non-string types (int, float, bool, None) are preserved unchanged.
        
        **Validates: Requirements 8.6**
        """
        result = replace_env_vars(non_string_value)
        assert result == non_string_value, f"Expected {non_string_value}, got {result}"
        assert type(result) == type(non_string_value), \
            f"Type changed from {type(non_string_value)} to {type(result)}"
