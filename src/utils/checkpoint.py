"""
断点续传管理器
Checkpoint Manager for Resume Support

实现抓取和处理过程中的断点保存和恢复功能。
Implements checkpoint save and resume functionality during fetching and processing.

功能：
- 保存已完成的订阅源 URL
- 保存已处理的文章
- 支持从断点恢复
- 自动清理过期检查点
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class FetchCheckpoint:
    """
    抓取阶段检查点
    Fetch Phase Checkpoint
    
    记录 RSS 抓取的进度状态。
    """
    # 检查点元数据
    checkpoint_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    
    # 抓取进度
    total_feeds: int = 0
    completed_feeds: list[str] = field(default_factory=list)
    failed_feeds: list[str] = field(default_factory=list)
    
    # 已抓取的文章（按订阅源分组）
    fetched_articles: dict[str, list[dict]] = field(default_factory=dict)
    
    # 状态
    phase: str = "fetching"  # fetching, processing, pushing, completed
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "FetchCheckpoint":
        return cls(**data)


@dataclass
class ProcessCheckpoint:
    """
    处理阶段检查点
    Process Phase Checkpoint
    
    记录文章处理的进度状态。
    """
    checkpoint_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    
    # 处理进度
    total_articles: int = 0
    processed_urls: list[str] = field(default_factory=list)
    failed_urls: list[str] = field(default_factory=list)
    
    # 已处理的文章（带分析结果）
    processed_articles: list[dict] = field(default_factory=list)
    
    # 状态
    phase: str = "processing"
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "ProcessCheckpoint":
        return cls(**data)


class CheckpointManager:
    """
    断点续传管理器
    Checkpoint Manager
    
    管理抓取和处理过程中的检查点，支持断点恢复。
    
    Attributes:
        checkpoint_dir: 检查点文件存储目录
        max_age_hours: 检查点最大保留时间（小时）
        auto_save_interval: 自动保存间隔（处理多少条后保存）
    """
    
    def __init__(
        self, 
        checkpoint_dir: str = "data/checkpoints",
        max_age_hours: int = 24,
        auto_save_interval: int = 10
    ):
        """
        初始化检查点管理器
        
        Args:
            checkpoint_dir: 检查点文件存储目录
            max_age_hours: 检查点最大保留时间（小时）
            auto_save_interval: 自动保存间隔
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.max_age_hours = max_age_hours
        self.auto_save_interval = auto_save_interval
        
        # 当前检查点
        self._fetch_checkpoint: FetchCheckpoint | None = None
        self._process_checkpoint: ProcessCheckpoint | None = None
        
        # 计数器（用于自动保存）
        self._feed_counter = 0
        self._article_counter = 0
    
    @property
    def fetch_checkpoint_path(self) -> Path:
        return self.checkpoint_dir / "fetch_checkpoint.json"
    
    @property
    def process_checkpoint_path(self) -> Path:
        return self.checkpoint_dir / "process_checkpoint.json"
    
    # =========================================================================
    # 抓取阶段检查点
    # =========================================================================
    
    def start_fetch(self, feed_urls: list[str]) -> FetchCheckpoint:
        """
        开始新的抓取任务或恢复已有任务
        
        Args:
            feed_urls: 所有订阅源 URL 列表
        
        Returns:
            FetchCheckpoint 对象
        """
        # 尝试加载已有检查点
        existing = self.load_fetch_checkpoint()
        
        if existing and existing.phase == "fetching":
            # 检查是否过期
            created = datetime.fromisoformat(existing.created_at)
            if datetime.now() - created < timedelta(hours=self.max_age_hours):
                logger.info(
                    f"恢复抓取检查点: 已完成 {len(existing.completed_feeds)}/{existing.total_feeds} 个订阅源"
                )
                self._fetch_checkpoint = existing
                return existing
        
        # 创建新检查点
        now = datetime.now().isoformat()
        checkpoint = FetchCheckpoint(
            checkpoint_id=f"fetch_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            created_at=now,
            updated_at=now,
            total_feeds=len(feed_urls),
            phase="fetching"
        )
        self._fetch_checkpoint = checkpoint
        self.save_fetch_checkpoint()
        
        logger.info(f"创建新抓取检查点: {checkpoint.checkpoint_id}")
        return checkpoint
    
    def mark_feed_completed(
        self, 
        feed_url: str, 
        articles: list[dict],
        feed_name: str = ""
    ):
        """
        标记订阅源抓取完成
        
        Args:
            feed_url: 订阅源 URL
            articles: 抓取到的文章列表
            feed_name: 订阅源名称
        """
        if not self._fetch_checkpoint:
            return
        
        if feed_url not in self._fetch_checkpoint.completed_feeds:
            self._fetch_checkpoint.completed_feeds.append(feed_url)
        
        # 保存文章
        key = feed_name or feed_url
        self._fetch_checkpoint.fetched_articles[key] = articles
        
        self._fetch_checkpoint.updated_at = datetime.now().isoformat()
        
        # 自动保存
        self._feed_counter += 1
        if self._feed_counter >= self.auto_save_interval:
            self.save_fetch_checkpoint()
            self._feed_counter = 0
            logger.debug(f"自动保存抓取检查点: {len(self._fetch_checkpoint.completed_feeds)} 个订阅源")
    
    def mark_feed_failed(self, feed_url: str, error: str = ""):
        """
        标记订阅源抓取失败
        
        Args:
            feed_url: 订阅源 URL
            error: 错误信息
        """
        if not self._fetch_checkpoint:
            return
        
        if feed_url not in self._fetch_checkpoint.failed_feeds:
            self._fetch_checkpoint.failed_feeds.append(feed_url)
        
        self._fetch_checkpoint.updated_at = datetime.now().isoformat()
    
    def get_pending_feeds(self, all_feeds: list[str]) -> list[str]:
        """
        获取待抓取的订阅源列表
        
        Args:
            all_feeds: 所有订阅源 URL 列表
        
        Returns:
            尚未完成的订阅源 URL 列表
        """
        if not self._fetch_checkpoint:
            return all_feeds
        
        completed = set(self._fetch_checkpoint.completed_feeds)
        failed = set(self._fetch_checkpoint.failed_feeds)
        done = completed | failed
        
        return [url for url in all_feeds if url not in done]
    
    def complete_fetch(self):
        """标记抓取阶段完成"""
        if self._fetch_checkpoint:
            self._fetch_checkpoint.phase = "processing"
            self._fetch_checkpoint.updated_at = datetime.now().isoformat()
            self.save_fetch_checkpoint()
            logger.info("抓取阶段完成")
    
    def get_all_fetched_articles(self) -> list[dict]:
        """
        获取所有已抓取的文章
        
        Returns:
            所有文章的列表
        """
        if not self._fetch_checkpoint:
            return []
        
        all_articles = []
        for articles in self._fetch_checkpoint.fetched_articles.values():
            all_articles.extend(articles)
        return all_articles
    
    def save_fetch_checkpoint(self):
        """保存抓取检查点到文件"""
        if not self._fetch_checkpoint:
            return
        
        try:
            with open(self.fetch_checkpoint_path, 'w', encoding='utf-8') as f:
                json.dump(self._fetch_checkpoint.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存抓取检查点失败: {e}")
    
    def load_fetch_checkpoint(self) -> FetchCheckpoint | None:
        """从文件加载抓取检查点"""
        if not self.fetch_checkpoint_path.exists():
            return None
        
        try:
            with open(self.fetch_checkpoint_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return FetchCheckpoint.from_dict(data)
        except Exception as e:
            logger.error(f"加载抓取检查点失败: {e}")
            return None
    
    # =========================================================================
    # 处理阶段检查点
    # =========================================================================
    
    def start_process(self, articles: list[dict]) -> ProcessCheckpoint:
        """
        开始新的处理任务或恢复已有任务
        
        Args:
            articles: 待处理的文章列表
        
        Returns:
            ProcessCheckpoint 对象
        """
        # 尝试加载已有检查点
        existing = self.load_process_checkpoint()
        
        if existing and existing.phase == "processing":
            created = datetime.fromisoformat(existing.created_at)
            if datetime.now() - created < timedelta(hours=self.max_age_hours):
                logger.info(
                    f"恢复处理检查点: 已处理 {len(existing.processed_urls)}/{existing.total_articles} 篇文章"
                )
                self._process_checkpoint = existing
                return existing
        
        # 创建新检查点
        now = datetime.now().isoformat()
        checkpoint = ProcessCheckpoint(
            checkpoint_id=f"process_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            created_at=now,
            updated_at=now,
            total_articles=len(articles),
            phase="processing"
        )
        self._process_checkpoint = checkpoint
        self.save_process_checkpoint()
        
        logger.info(f"创建新处理检查点: {checkpoint.checkpoint_id}")
        return checkpoint
    
    def mark_article_processed(self, article: dict):
        """
        标记文章处理完成
        
        Args:
            article: 处理完成的文章（包含分析结果）
        """
        if not self._process_checkpoint:
            return
        
        url = article.get('url', '')
        if url and url not in self._process_checkpoint.processed_urls:
            self._process_checkpoint.processed_urls.append(url)
            self._process_checkpoint.processed_articles.append(article)
        
        self._process_checkpoint.updated_at = datetime.now().isoformat()
        
        # 自动保存
        self._article_counter += 1
        if self._article_counter >= self.auto_save_interval:
            self.save_process_checkpoint()
            self._article_counter = 0
            logger.debug(f"自动保存处理检查点: {len(self._process_checkpoint.processed_urls)} 篇文章")
    
    def mark_article_failed(self, url: str, error: str = ""):
        """
        标记文章处理失败
        
        Args:
            url: 文章 URL
            error: 错误信息
        """
        if not self._process_checkpoint:
            return
        
        if url not in self._process_checkpoint.failed_urls:
            self._process_checkpoint.failed_urls.append(url)
        
        self._process_checkpoint.updated_at = datetime.now().isoformat()
    
    def is_article_processed(self, url: str) -> bool:
        """
        检查文章是否已处理
        
        Args:
            url: 文章 URL
        
        Returns:
            是否已处理
        """
        if not self._process_checkpoint:
            return False
        
        return url in self._process_checkpoint.processed_urls
    
    def get_pending_articles(self, articles: list[dict]) -> list[dict]:
        """
        获取待处理的文章列表
        
        Args:
            articles: 所有文章列表
        
        Returns:
            尚未处理的文章列表
        """
        if not self._process_checkpoint:
            return articles
        
        processed = set(self._process_checkpoint.processed_urls)
        failed = set(self._process_checkpoint.failed_urls)
        done = processed | failed
        
        return [a for a in articles if a.get('url', '') not in done]
    
    def complete_process(self):
        """标记处理阶段完成"""
        if self._process_checkpoint:
            self._process_checkpoint.phase = "pushing"
            self._process_checkpoint.updated_at = datetime.now().isoformat()
            self.save_process_checkpoint()
            logger.info("处理阶段完成")
    
    def get_processed_articles(self) -> list[dict]:
        """
        获取所有已处理的文章
        
        Returns:
            已处理文章的列表
        """
        if not self._process_checkpoint:
            return []
        return self._process_checkpoint.processed_articles
    
    def save_process_checkpoint(self):
        """保存处理检查点到文件"""
        if not self._process_checkpoint:
            return
        
        try:
            with open(self.process_checkpoint_path, 'w', encoding='utf-8') as f:
                json.dump(self._process_checkpoint.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存处理检查点失败: {e}")
    
    def load_process_checkpoint(self) -> ProcessCheckpoint | None:
        """从文件加载处理检查点"""
        if not self.process_checkpoint_path.exists():
            return None
        
        try:
            with open(self.process_checkpoint_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return ProcessCheckpoint.from_dict(data)
        except Exception as e:
            logger.error(f"加载处理检查点失败: {e}")
            return None
    
    # =========================================================================
    # 通用方法
    # =========================================================================
    
    def clear_checkpoints(self):
        """清除所有检查点"""
        try:
            if self.fetch_checkpoint_path.exists():
                self.fetch_checkpoint_path.unlink()
            if self.process_checkpoint_path.exists():
                self.process_checkpoint_path.unlink()
            
            self._fetch_checkpoint = None
            self._process_checkpoint = None
            
            logger.info("已清除所有检查点")
        except Exception as e:
            logger.error(f"清除检查点失败: {e}")
    
    def cleanup_old_checkpoints(self):
        """清理过期的检查点"""
        cutoff = datetime.now() - timedelta(hours=self.max_age_hours)
        
        for path in [self.fetch_checkpoint_path, self.process_checkpoint_path]:
            if path.exists():
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    created = datetime.fromisoformat(data.get('created_at', ''))
                    if created < cutoff:
                        path.unlink()
                        logger.info(f"清理过期检查点: {path.name}")
                except Exception:
                    pass
    
    def get_status(self) -> dict:
        """
        获取当前检查点状态
        
        Returns:
            状态信息字典
        """
        status = {
            "fetch": None,
            "process": None
        }
        
        if self._fetch_checkpoint:
            status["fetch"] = {
                "id": self._fetch_checkpoint.checkpoint_id,
                "phase": self._fetch_checkpoint.phase,
                "progress": f"{len(self._fetch_checkpoint.completed_feeds)}/{self._fetch_checkpoint.total_feeds}",
                "articles": sum(len(a) for a in self._fetch_checkpoint.fetched_articles.values())
            }
        
        if self._process_checkpoint:
            status["process"] = {
                "id": self._process_checkpoint.checkpoint_id,
                "phase": self._process_checkpoint.phase,
                "progress": f"{len(self._process_checkpoint.processed_urls)}/{self._process_checkpoint.total_articles}"
            }
        
        return status
