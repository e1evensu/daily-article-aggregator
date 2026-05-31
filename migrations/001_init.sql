-- Intelligence System: Initial Schema
-- Apply: mysql -h 127.0.0.1 -P 13306 -u intelligence -p intelligence < migrations/001_init.sql

CREATE TABLE IF NOT EXISTS sources (
    id              VARCHAR(64) PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    domain          ENUM('security','ai','finance','general') NOT NULL,
    type            ENUM('rss','api','github_api','internal_api') NOT NULL,
    url             VARCHAR(1000) NOT NULL,
    auth_mode       VARCHAR(50) NOT NULL DEFAULT 'none',
    fetch_strategy  VARCHAR(50) NOT NULL,
    authority       ENUM('official','authoritative','regular') NOT NULL,
    status          ENUM('candidate','trial','approved','rejected','deferred') NOT NULL DEFAULT 'candidate',
    health          ENUM('good','degraded','disabled') NOT NULL DEFAULT 'good',
    consecutive_failures INT NOT NULL DEFAULT 0,
    last_fetch_at   TIMESTAMP NULL,
    last_fetch_status VARCHAR(50) NULL,
    config_json     JSON NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS runs (
    id              VARCHAR(64) PRIMARY KEY,
    kind            VARCHAR(50) NOT NULL,
    status          ENUM('running','partial','succeeded','failed') NOT NULL,
    window_start    TIMESTAMP NOT NULL,
    window_end      TIMESTAMP NOT NULL,
    started_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at     TIMESTAMP NULL,
    stats_json      JSON NULL,
    error_json      JSON NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version         VARCHAR(64) PRIMARY KEY,
    applied_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS items (
    id                      VARCHAR(96) PRIMARY KEY,
    source_id               VARCHAR(64) NOT NULL,
    domain                  ENUM('security','ai','finance','general') NOT NULL,
    run_id                  VARCHAR(64) NULL,
    title                   VARCHAR(500) NOT NULL,
    canonical_url           VARCHAR(1000) NOT NULL,
    content_text            MEDIUMTEXT NULL,
    author                  VARCHAR(200) NULL,
    published_at            TIMESTAMP NULL,
    fetched_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dedup_hash              VARCHAR(64) NOT NULL,
    also_seen_in            JSON NULL,
    metadata_json           JSON NULL,
    -- Stage 1
    category                VARCHAR(50) NULL,
    tags                    JSON NULL,
    summary_zh              VARCHAR(500) NULL,
    insight_score           TINYINT UNSIGNED NULL,
    credibility             ENUM('high','medium','low','unknown') NOT NULL DEFAULT 'unknown',
    -- Stage 2
    confidence              ENUM('tentative','firm','confirmed') NULL,
    recommendation_reason   TEXT NULL,
    trend_signal            ENUM('emerging','growing','stable','declining') NULL,
    action_suggestion       TEXT NULL,
    -- Analysis metadata
    analysis_stage          TINYINT NOT NULL DEFAULT 0,
    stage1_model            VARCHAR(200) NULL,
    stage1_provider         VARCHAR(100) NULL,
    stage1_prompt_version   VARCHAR(50) NULL,
    stage1_analyzed_at      TIMESTAMP NULL,
    stage1_error            VARCHAR(200) NULL,
    stage2_model            VARCHAR(200) NULL,
    stage2_provider         VARCHAR(100) NULL,
    stage2_prompt_version   VARCHAR(50) NULL,
    stage2_analyzed_at      TIMESTAMP NULL,
    stage2_error            VARCHAR(200) NULL,
    -- Retention
    expires_at              TIMESTAMP NULL,
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_dedup_hash (dedup_hash),
    KEY ix_source_id (source_id),
    KEY ix_domain_score (domain, insight_score DESC),
    KEY ix_domain_published (domain, published_at DESC),
    KEY ix_expires_at (expires_at),
    FULLTEXT KEY ft_search (title, summary_zh, content_text) WITH PARSER ngram
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS digests (
    id                  VARCHAR(96) PRIMARY KEY,
    run_id              VARCHAR(64) NULL,
    date                DATE NOT NULL,
    domain              VARCHAR(32) NOT NULL,
    title               VARCHAR(200) NOT NULL,
    summary             TEXT NULL,
    stats_json          JSON NULL,
    highlights_json     JSON NULL,
    content_markdown    MEDIUMTEXT NOT NULL,
    oss_url             VARCHAR(1000) NULL,
    generated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_date_domain (date, domain)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS deep_analyses (
    id              VARCHAR(96) PRIMARY KEY,
    subject         VARCHAR(128) NOT NULL,
    item_id         VARCHAR(96) NULL,
    kind            VARCHAR(32) NOT NULL DEFAULT 'vuln_rca',
    repo            VARCHAR(255) NULL,
    vuln_commit     VARCHAR(64) NULL,
    fix_commit      VARCHAR(64) NULL,
    model           VARCHAR(64) NULL,
    status          VARCHAR(32) NULL,
    attempts        JSON NULL,
    report_md       MEDIUMTEXT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    KEY ix_subject (subject),
    KEY ix_item_id (item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS site_experiences (
    domain_name     VARCHAR(200) PRIMARY KEY,
    best_strategy   VARCHAR(50) NOT NULL,
    rate_limit      INT NULL,
    notes           TEXT NULL,
    last_success    TIMESTAMP NULL,
    failure_count   INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
