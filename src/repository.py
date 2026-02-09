"""
文章仓库模块

提供文章数据的数据库操作，包括存储、查询、去重等功能。
使用SQLite作为存储引擎。
"""

import sqlite3
import time
import functools
import logging
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


def retry_on_locked(max_retries: int = 5, base_delay: float = 0.1):
    """
    装饰器：在数据库锁定时自动重试
    
    使用指数退避策略重试数据库操作。
    
    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟时间（秒）
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e):
                        last_exception = e
                        if attempt < max_retries:
                            delay = base_delay * (2 ** attempt)
                            logger.warning(
                                f"Database locked, retrying in {delay:.2f}s "
                                f"(attempt {attempt + 1}/{max_retries})"
                            )
                            time.sleep(delay)
                        continue
                    raise
            raise last_exception
        return wrapper
    return decorator


class ArticleRepository:
    """
    文章仓库：数据库操作
    
    提供文章的CRUD操作，支持URL去重和标题相似度去重。
    
    Attributes:
        db_path: SQLite数据库文件路径
    """
    
    def __init__(self, db_path: str, timeout: float = 30.0):
        """
        初始化仓库
        
        Args:
            db_path: SQLite数据库文件路径，使用':memory:'创建内存数据库
            timeout: 数据库锁等待超时时间（秒），默认30秒
        """
        self.db_path = db_path
        self.timeout = timeout
        self._connection: sqlite3.Connection | None = None
    
    def _get_connection(self) -> sqlite3.Connection:
        """
        获取数据库连接
        
        使用WAL模式提高并发性能，设置超时时间避免锁定错误。
        
        Returns:
            SQLite连接对象
        """
        if self._connection is None:
            self._connection = sqlite3.connect(
                self.db_path, 
                timeout=self.timeout,
                check_same_thread=False
            )
            self._connection.row_factory = sqlite3.Row
            # 启用WAL模式，提高并发读写性能
            self._connection.execute("PRAGMA journal_mode=WAL")
            # 设置busy_timeout（毫秒）
            self._connection.execute(f"PRAGMA busy_timeout={int(self.timeout * 1000)}")
        return self._connection
    
    def close(self):
        """关闭数据库连接"""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
    
    @retry_on_locked(max_retries=5, base_delay=0.1)
    def init_db(self):
        """
        初始化数据库表结构
        
        创建articles表和相关索引。如果表已存在则不会重复创建。
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 创建articles表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                source TEXT NOT NULL,
                source_type TEXT NOT NULL,
                published_date TEXT,
                fetched_at TEXT NOT NULL,
                content TEXT,
                summary TEXT,
                zh_summary TEXT,
                category TEXT,
                is_pushed INTEGER DEFAULT 0,
                pushed_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_url ON articles(url)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_is_pushed ON articles(is_pushed)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_source ON articles(source)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fetched_at ON articles(fetched_at)")
        
        conn.commit()
    
    def exists_by_url(self, url: str) -> bool:
        """
        检查URL是否已存在
        
        Args:
            url: 文章URL
            
        Returns:
            如果URL已存在返回True，否则返回False
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1 FROM articles WHERE url = ? LIMIT 1", (url,))
        result = cursor.fetchone()
        
        return result is not None
    
    def find_similar_by_title(self, title: str, threshold: float = 0.8) -> dict[str, Any] | None:
        """
        根据标题相似度查找文章
        
        使用difflib.SequenceMatcher计算标题相似度，
        返回第一个相似度超过阈值的文章。
        
        Args:
            title: 文章标题
            threshold: 相似度阈值，默认0.8（80%相似）
            
        Returns:
            相似文章的字典，如果不存在返回None
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 获取所有文章的标题进行比较
        cursor.execute("SELECT * FROM articles")
        rows = cursor.fetchall()
        
        for row in rows:
            existing_title = row['title']
            similarity = SequenceMatcher(None, title, existing_title).ratio()
            
            if similarity >= threshold:
                return self._row_to_dict(row)
        
        return None
    
    @retry_on_locked(max_retries=5, base_delay=0.1)
    def save_article(self, article: dict[str, Any]) -> int:
        """
        保存文章
        
        将文章数据插入数据库。如果URL已存在，会抛出IntegrityError。
        
        Args:
            article: 文章数据字典，必须包含title, url, source, source_type, fetched_at
            
        Returns:
            新插入文章的ID
            
        Raises:
            sqlite3.IntegrityError: 如果URL已存在
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 准备插入数据
        cursor.execute("""
            INSERT INTO articles (
                title, url, source, source_type, published_date,
                fetched_at, content, summary, zh_summary, category,
                is_pushed, pushed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            article.get('title', ''),
            article.get('url', ''),
            article.get('source', ''),
            article.get('source_type', ''),
            article.get('published_date', ''),
            article.get('fetched_at', ''),
            article.get('content', ''),
            article.get('summary', ''),
            article.get('zh_summary', ''),
            article.get('category', ''),
            1 if article.get('is_pushed', False) else 0,
            article.get('pushed_at')
        ))
        
        conn.commit()
        return cursor.lastrowid
    
    def get_by_id(self, article_id: int) -> dict[str, Any] | None:
        """
        根据ID获取文章
        
        Args:
            article_id: 文章ID
            
        Returns:
            文章数据字典，如果不存在返回None
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
        row = cursor.fetchone()
        
        if row is None:
            return None
        
        return self._row_to_dict(row)
    
    def get_unpushed_articles(self) -> list[dict[str, Any]]:
        """
        获取未推送的文章
        
        Returns:
            未推送文章列表，每个文章为字典格式
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM articles WHERE is_pushed = 0 ORDER BY fetched_at DESC")
        rows = cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]
    
    def get_all_articles(self) -> list[dict[str, Any]]:
        """
        获取所有文章
        
        Returns:
            所有文章列表，每个文章为字典格式
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM articles ORDER BY fetched_at DESC")
        rows = cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]
    
    @retry_on_locked(max_retries=5, base_delay=0.1)
    def mark_as_pushed(self, article_ids: list[int]):
        """
        标记文章为已推送
        
        更新指定文章的is_pushed状态为True，并记录推送时间。
        
        Args:
            article_ids: 文章ID列表
        """
        if not article_ids:
            return
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        pushed_at = datetime.now().isoformat()
        
        # 使用参数化查询批量更新
        placeholders = ','.join('?' * len(article_ids))
        cursor.execute(f"""
            UPDATE articles 
            SET is_pushed = 1, pushed_at = ?
            WHERE id IN ({placeholders})
        """, [pushed_at] + article_ids)
        
        conn.commit()
    
    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """
        将数据库行转换为字典
        
        Args:
            row: SQLite Row对象
            
        Returns:
            文章数据字典
        """
        return {
            'id': row['id'],
            'title': row['title'],
            'url': row['url'],
            'source': row['source'],
            'source_type': row['source_type'],
            'published_date': row['published_date'],
            'fetched_at': row['fetched_at'],
            'content': row['content'],
            'summary': row['summary'],
            'zh_summary': row['zh_summary'],
            'category': row['category'],
            'is_pushed': bool(row['is_pushed']),
            'pushed_at': row['pushed_at'],
        }
