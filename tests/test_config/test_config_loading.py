"""
配置加载属性测试
Property-Based Tests for Configuration Loading

测试配置加载模块的默认值处理功能。
Tests default value handling in the configuration loading module.

Feature: aggregator-advanced-features
"""

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import given, strategies as st, settings, assume

from src.config import (
    DEFAULT_CONFIG,
    apply_defaults,
    get_config_value,
    get_data_source_config,
    get_priority_scoring_config,
    get_tiered_push_config,
    get_vulnerability_filter_config,
    load_config,
    load_config_with_defaults,
    _deep_merge,
)


# ============================================================================
# Strategies for generating test data
# ============================================================================

# Strategy for generating valid configuration keys (alphanumeric + underscore)
config_key_strategy = st.from_regex(r"^[a-z][a-z0-9_]{0,20}$", fullmatch=True)

# Strategy for generating configuration values
config_value_strategy = st.one_of(
    st.text(min_size=0, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_"),
    st.integers(min_value=-1000, max_value=1000),
    st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    st.booleans(),
)

# Strategy for generating data source names
data_source_name_strategy = st.sampled_from(["dblp", "nvd", "kev", "huggingface", "pwc", "blogs"])


# Strategy for generating timeout values
timeout_strategy = st.integers(min_value=1, max_value=300)

# Strategy for generating threshold values
threshold_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)

# Strategy for generating star threshold values
star_threshold_strategy = st.integers(min_value=0, max_value=100000)

# Strategy for generating IP asset threshold values
ip_asset_threshold_strategy = st.integers(min_value=0, max_value=10000)


# ============================================================================
# Property 20: Default Configuration Values
# ============================================================================

class TestDefaultConfigurationValues:
    """
    Feature: aggregator-advanced-features, Property 20: Default Configuration Values
    
    Property 20: Default Configuration Values
    *For any* configuration key that is missing from the config file, the system SHALL 
    use a predefined default value and continue operation without error.
    
    **Validates: Requirements 13.4**
    """

    @given(source_name=data_source_name_strategy)
    @settings(max_examples=100)
    def test_missing_data_source_uses_defaults(self, source_name: str):
        """
        Feature: aggregator-advanced-features, Property 20: Default Configuration Values
        
        Property: When a data source configuration is completely missing, the system
        uses predefined default values for all fields.
        
        **Validates: Requirements 13.4**
        """
        # Empty config - no data sources configured
        empty_config: dict[str, Any] = {}
        
        # Get the data source config - should return defaults
        result = get_data_source_config(empty_config, source_name)
        
        # Verify defaults are applied
        expected_defaults = DEFAULT_CONFIG["data_sources"][source_name]
        
        # All default keys should be present
        for key, default_value in expected_defaults.items():
            assert key in result, f"Missing default key '{key}' for source '{source_name}'"
            assert result[key] == default_value, (
                f"Expected default value '{default_value}' for key '{key}', got '{result[key]}'"
            )

    @given(source_name=data_source_name_strategy, enabled=st.booleans())
    @settings(max_examples=100)
    def test_partial_data_source_config_fills_missing_with_defaults(
        self, source_name: str, enabled: bool
    ):
        """
        Feature: aggregator-advanced-features, Property 20: Default Configuration Values
        
        Property: When a data source has partial configuration, missing fields are
        filled with default values while provided values are preserved.
        
        **Validates: Requirements 13.4**
        """
        # Partial config - only 'enabled' is set
        partial_config = {"data_sources": {source_name: {"enabled": enabled}}}
        
        result = get_data_source_config(partial_config, source_name)
        
        # User-provided value should be preserved
        assert result["enabled"] == enabled, (
            f"User-provided 'enabled' value should be preserved, expected {enabled}, got {result['enabled']}"
        )
        
        # Other fields should use defaults
        expected_defaults = DEFAULT_CONFIG["data_sources"][source_name]
        for key, default_value in expected_defaults.items():
            if key != "enabled":
                assert key in result, f"Missing default key '{key}'"
                assert result[key] == default_value, (
                    f"Expected default '{default_value}' for '{key}', got '{result[key]}'"
                )


    @given(
        github_star_threshold=st.one_of(st.none(), star_threshold_strategy),
        ip_asset_threshold=st.one_of(st.none(), ip_asset_threshold_strategy),
        enable_ai_assessment=st.one_of(st.none(), st.booleans())
    )
    @settings(max_examples=100)
    def test_vulnerability_filter_missing_fields_use_defaults(
        self,
        github_star_threshold,
        ip_asset_threshold,
        enable_ai_assessment
    ):
        """
        Feature: aggregator-advanced-features, Property 20: Default Configuration Values
        
        Property: When vulnerability filter has partial configuration, missing fields
        are filled with default values.
        
        **Validates: Requirements 13.4**
        """
        # Build partial config with only non-None values
        vuln_config: dict[str, Any] = {}
        if github_star_threshold is not None:
            vuln_config["github_star_threshold"] = github_star_threshold
        if ip_asset_threshold is not None:
            vuln_config["ip_asset_threshold"] = ip_asset_threshold
        if enable_ai_assessment is not None:
            vuln_config["enable_ai_assessment"] = enable_ai_assessment
        
        config = {"vulnerability_filter": vuln_config} if vuln_config else {}
        
        result = get_vulnerability_filter_config(config)
        
        # Verify user-provided values are preserved
        if github_star_threshold is not None:
            assert result["github_star_threshold"] == github_star_threshold
        else:
            assert result["github_star_threshold"] == DEFAULT_CONFIG["vulnerability_filter"]["github_star_threshold"]
        
        if ip_asset_threshold is not None:
            assert result["ip_asset_threshold"] == ip_asset_threshold
        else:
            assert result["ip_asset_threshold"] == DEFAULT_CONFIG["vulnerability_filter"]["ip_asset_threshold"]
        
        if enable_ai_assessment is not None:
            assert result["enable_ai_assessment"] == enable_ai_assessment
        else:
            assert result["enable_ai_assessment"] == DEFAULT_CONFIG["vulnerability_filter"]["enable_ai_assessment"]
        
        # Verify all default keys are present
        for key in DEFAULT_CONFIG["vulnerability_filter"]:
            assert key in result, f"Missing key '{key}' in vulnerability filter config"

    @given(
        level1_threshold=st.one_of(st.none(), threshold_strategy),
        level2_threshold=st.one_of(st.none(), threshold_strategy)
    )
    @settings(max_examples=100)
    def test_tiered_push_missing_fields_use_defaults(self, level1_threshold, level2_threshold):
        """
        Feature: aggregator-advanced-features, Property 20: Default Configuration Values
        
        Property: When tiered push has partial configuration, missing fields
        are filled with default values.
        
        **Validates: Requirements 13.4**
        """
        # Build partial config
        tiered_config: dict[str, Any] = {}
        if level1_threshold is not None:
            tiered_config["level1_threshold"] = level1_threshold
        if level2_threshold is not None:
            tiered_config["level2_threshold"] = level2_threshold
        
        config = {"tiered_push": tiered_config} if tiered_config else {}
        
        result = get_tiered_push_config(config)
        
        # Verify user-provided values are preserved
        if level1_threshold is not None:
            assert result["level1_threshold"] == level1_threshold
        else:
            assert result["level1_threshold"] == DEFAULT_CONFIG["tiered_push"]["level1_threshold"]
        
        if level2_threshold is not None:
            assert result["level2_threshold"] == level2_threshold
        else:
            assert result["level2_threshold"] == DEFAULT_CONFIG["tiered_push"]["level2_threshold"]
        
        # Verify all default keys are present
        for key in DEFAULT_CONFIG["tiered_push"]:
            assert key in result, f"Missing key '{key}' in tiered push config"


    @given(enabled=st.one_of(st.none(), st.booleans()))
    @settings(max_examples=100)
    def test_priority_scoring_missing_fields_use_defaults(self, enabled):
        """
        Feature: aggregator-advanced-features, Property 20: Default Configuration Values
        
        Property: When priority scoring has partial configuration, missing fields
        are filled with default values.
        
        **Validates: Requirements 13.4**
        """
        # Build partial config
        scoring_config: dict[str, Any] = {}
        if enabled is not None:
            scoring_config["enabled"] = enabled
        
        config = {"priority_scoring": scoring_config} if scoring_config else {}
        
        result = get_priority_scoring_config(config)
        
        # Verify user-provided values are preserved
        if enabled is not None:
            assert result["enabled"] == enabled
        else:
            assert result["enabled"] == DEFAULT_CONFIG["priority_scoring"]["enabled"]
        
        # Verify source_weights defaults are present
        assert "source_weights" in result
        for source, weight in DEFAULT_CONFIG["priority_scoring"]["source_weights"].items():
            assert source in result["source_weights"], f"Missing source weight for '{source}'"

    @given(source_name=data_source_name_strategy, timeout=timeout_strategy)
    @settings(max_examples=100)
    def test_data_source_timeout_override_preserves_other_defaults(
        self, source_name: str, timeout: int
    ):
        """
        Feature: aggregator-advanced-features, Property 20: Default Configuration Values
        
        Property: When only timeout is overridden, all other fields use defaults.
        
        **Validates: Requirements 13.4**
        """
        config = {"data_sources": {source_name: {"timeout": timeout}}}
        
        result = get_data_source_config(config, source_name)
        
        # Timeout should be overridden
        assert result["timeout"] == timeout
        
        # Other fields should use defaults
        expected_defaults = DEFAULT_CONFIG["data_sources"][source_name]
        for key, default_value in expected_defaults.items():
            if key != "timeout":
                assert result[key] == default_value, (
                    f"Expected default '{default_value}' for '{key}', got '{result[key]}'"
                )

    def test_completely_empty_config_uses_all_defaults(self):
        """
        Feature: aggregator-advanced-features, Property 20: Default Configuration Values
        
        Property: When config is completely empty, all default values are used.
        
        **Validates: Requirements 13.4**
        """
        empty_config: dict[str, Any] = {}
        
        result = apply_defaults(empty_config)
        
        # Verify all top-level sections exist
        assert "data_sources" in result
        assert "vulnerability_filter" in result
        assert "tiered_push" in result
        assert "priority_scoring" in result
        
        # Verify data sources have all defaults
        for source_name in ["dblp", "nvd", "kev", "huggingface", "pwc", "blogs"]:
            assert source_name in result["data_sources"]
            for key, value in DEFAULT_CONFIG["data_sources"][source_name].items():
                assert result["data_sources"][source_name][key] == value

    def test_load_config_with_defaults_applies_defaults(self):
        """
        Feature: aggregator-advanced-features, Property 20: Default Configuration Values
        
        Property: load_config_with_defaults applies defaults to loaded config.
        
        **Validates: Requirements 13.4**
        """
        # Create a minimal config file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"data_sources": {"dblp": {"enabled": False}}}, f)
            temp_path = f.name
        
        try:
            result = load_config_with_defaults(temp_path)
            
            # User config should be preserved
            assert result["data_sources"]["dblp"]["enabled"] is False
            
            # Defaults should be applied
            assert result["data_sources"]["dblp"]["timeout"] == 30
            assert "nvd" in result["data_sources"]
            assert result["vulnerability_filter"]["github_star_threshold"] == 1000
        finally:
            os.unlink(temp_path)



# ============================================================================
# Deep Merge Tests
# ============================================================================

class TestDeepMerge:
    """Tests for the _deep_merge helper function."""

    @given(base_value=config_value_strategy, override_value=config_value_strategy)
    @settings(max_examples=100)
    def test_deep_merge_override_takes_precedence(self, base_value: Any, override_value: Any):
        """
        Property: Override values take precedence over base values.
        """
        base = {"key": base_value}
        override = {"key": override_value}
        
        result = _deep_merge(base, override)
        
        assert result["key"] == override_value

    @given(key=config_key_strategy, value=config_value_strategy)
    @settings(max_examples=100)
    def test_deep_merge_preserves_base_keys_not_in_override(self, key: str, value: Any):
        """
        Property: Keys in base that are not in override are preserved.
        """
        base = {key: value, "other": "preserved"}
        override = {key: "overridden"}
        
        result = _deep_merge(base, override)
        
        assert result["other"] == "preserved"
        assert result[key] == "overridden"

    def test_deep_merge_nested_dicts(self):
        """
        Property: Nested dictionaries are merged recursively.
        """
        base = {"level1": {"level2": {"a": 1, "b": 2}}}
        override = {"level1": {"level2": {"b": 20, "c": 3}}}
        
        result = _deep_merge(base, override)
        
        assert result["level1"]["level2"]["a"] == 1  # preserved from base
        assert result["level1"]["level2"]["b"] == 20  # overridden
        assert result["level1"]["level2"]["c"] == 3  # added from override

    def test_deep_merge_empty_override(self):
        """
        Property: Empty override returns base unchanged.
        """
        base = {"a": 1, "b": {"c": 2}}
        override: dict[str, Any] = {}
        
        result = _deep_merge(base, override)
        
        assert result == base

    def test_deep_merge_empty_base(self):
        """
        Property: Empty base returns override.
        """
        base: dict[str, Any] = {}
        override = {"a": 1, "b": {"c": 2}}
        
        result = _deep_merge(base, override)
        
        assert result == override



# ============================================================================
# get_config_value Tests
# ============================================================================

class TestGetConfigValue:
    """Tests for the get_config_value helper function."""

    @given(key=config_key_strategy, value=config_value_strategy, default=config_value_strategy)
    @settings(max_examples=100)
    def test_get_config_value_returns_value_when_exists(self, key: str, value: Any, default: Any):
        """
        Property: Returns the value when the key path exists.
        """
        config = {key: value}
        
        result = get_config_value(config, key, default)
        
        assert result == value

    @given(default=config_value_strategy)
    @settings(max_examples=100)
    def test_get_config_value_returns_default_when_missing(self, default: Any):
        """
        Property: Returns default when key path doesn't exist.
        """
        config: dict[str, Any] = {}
        
        result = get_config_value(config, "nonexistent.path", default)
        
        assert result == default

    def test_get_config_value_nested_path(self):
        """
        Property: Dot-separated paths navigate nested dictionaries.
        """
        config = {"level1": {"level2": {"value": "found"}}}
        
        result = get_config_value(config, "level1.level2.value", "default")
        
        assert result == "found"

    def test_get_config_value_partial_path_returns_default(self):
        """
        Property: Returns default when path is partially valid.
        """
        config = {"level1": {"level2": "not_a_dict"}}
        
        result = get_config_value(config, "level1.level2.level3", "default")
        
        assert result == "default"
