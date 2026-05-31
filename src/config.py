from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = ""
    source_seed_path: str = "config/sources.json"

    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    stage1_model: str = "deepseek-ai/deepseek-v4-flash"
    stage2_model: str = "deepseek-ai/deepseek-v4-pro"
    digest_model: str = "deepseek-ai/deepseek-v4-flash"
    stage1_timeout_s: float = 120.0
    stage1_retries: int = 2
    stage1_retry_backoff_s: str = "2,4"
    stage1_temperature: float = 0.1
    stage1_max_tokens: int = 2048
    stage1_concurrency: int = 3
    stage2_timeout_s: float = 300.0
    stage2_retries: int = 2
    stage2_retry_backoff_s: str = "5,10"
    stage2_temperature: float = 0.2
    stage2_max_tokens: int = 4096
    stage2_concurrency: int = 1
    digest_timeout_s: float = 300.0
    digest_retries: int = 2
    digest_retry_backoff_s: str = "2,4"
    digest_temperature: float = 0.3
    digest_max_tokens: int = 1024
    digest_concurrency: int = 1
    digest_overview_max_items: int = 20
    sub2api_base_url: str = ""
    sub2api_api_key: str = ""

    oss_endpoint: str = ""
    oss_bucket: str = ""
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_prefix: str = "intelligence/digests"

    github_token: str = ""

    feishu_webhook_url: str = ""
    feishu_app_id: str = ""
    feishu_app_secret: str = ""

    stage2_threshold: int = 75
    digest_candidate_threshold: int = 40
    digest_top_n_per_category: int = 5
    digest_domains: str = "security,ai"
    realtime_push_threshold: int = 85

    # Deep-analysis (pi Finder) stage. The pipeline only *enqueues* qualifying
    # security items (cheap DB rows); a separate worker runs the slow,
    # RPM-limited pi agent serially. min_score filters which GHSA items
    # qualify; max_per_run caps queue growth per daily run.
    deep_analysis_enabled: bool = True
    deep_analysis_min_score: int = 0
    deep_analysis_max_per_run: int = 20
    deep_analysis_stale_claim_timeout_hours: int = 6

    retention_below_10: int = 0
    retention_below_30: int = 5
    retention_below_50: int = 10
    retention_below_75: int = 30
    retention_delete_below_score: int = 10
    retention_5_days_below_score: int = 30
    retention_10_days_below_score: int = 50

    collect_cron: str = "0 16 * * *"
    run_lock_name: str = "intelligence_daily_pipeline"
    run_stale_timeout_hours: int = 12
    run_default_window_hours: int = 24
    collector_timeout_s: float = 30.0
    collector_default_since_hours: int = 24
    collector_failure_disable_threshold: int = 3
    collector_github_per_page: int = 100
    collector_hn_max_items: int = 50
    collector_hn_max_concurrency: int = 10
    collector_nvd_results_per_page: int = 2000
    api_command: str = "uvicorn src.main:app"

    api_host: str = "127.0.0.1"
    api_port: int = 8100
    api_token: str = ""
    log_level: str = "info"
    api_default_limit: int = 20
    api_max_limit: int = 100
    api_recent_digests_limit: int = 20
    source_spark_days: int = 14
    database_pool_size: int = 5
    database_max_overflow: int = 5
    database_pool_recycle_s: int = 3600
    database_verify_tls: bool = False

    hexo_posts_dir: str = "/opt/blog/source/_posts"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()


def parse_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_float_tuple(value: str) -> tuple[float, ...]:
    return tuple(float(part.strip()) for part in value.split(",") if part.strip())
