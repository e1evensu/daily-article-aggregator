"""
飞书多维表格集成模块
Feishu Bitable Integration Module

将文章数据同步到飞书多维表格，实现数据可视化和管理。
Syncs article data to Feishu Bitable for visualization and management.

功能：
- 获取 tenant_access_token
- 创建多维表格
- 新增/更新记录
- 批量操作
"""

import logging
import time
from datetime import datetime
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


class FeishuBitable:
    """
    飞书多维表格客户端
    Feishu Bitable Client
    
    Attributes:
        app_id: 飞书应用 ID
        app_secret: 飞书应用密钥
        app_token: 多维表格 app_token（可选，不提供则自动创建）
        table_id: 数据表 ID（可选，不提供则自动创建）
        _access_token: 缓存的 access_token
        _token_expires_at: token 过期时间
    """
    
    BASE_URL = "https://open.feishu.cn/open-apis"
    
    # 文章表字段定义
    ARTICLE_FIELDS = [
        {"field_name": "标题", "type": 1},  # 1=文本
        {"field_name": "链接", "type": 15},  # 15=URL
        {"field_name": "来源", "type": 3, "property": {  # 3=单选
            "options": [
                {"name": "arxiv"},
                {"name": "rss"},
                {"name": "nvd"},
                {"name": "kev"},
                {"name": "dblp"},
                {"name": "huggingface"},
                {"name": "pwc"},
                {"name": "blog"},
            ]
        }},
        {"field_name": "分类", "type": 3, "property": {  # 3=单选
            "options": [
                {"name": "AI/机器学习"},
                {"name": "安全/隐私"},
                {"name": "系统/架构"},
                {"name": "编程语言"},
                {"name": "数据库/存储"},
                {"name": "网络/分布式"},
                {"name": "前端/移动端"},
                {"name": "DevOps/云计算"},
                {"name": "开源项目"},
                {"name": "漏洞/CVE"},
                {"name": "其他"},
            ]
        }},
        {"field_name": "摘要", "type": 1},  # 1=文本
        {"field_name": "中文摘要", "type": 1},  # 1=文本
        {"field_name": "优先级", "type": 2},  # 2=数字
        {"field_name": "抓取时间", "type": 5},  # 5=日期
        {"field_name": "已推送", "type": 7},  # 7=复选框
    ]
    
    def __init__(self, config: dict):
        """
        初始化飞书多维表格客户端
        
        Args:
            config: 配置字典，包含：
                - app_id: 飞书应用 ID（必需）
                - app_secret: 飞书应用密钥（必需）
                - app_token: 多维表格 token（可选）
                - table_id: 数据表 ID（可选）
                - folder_token: 文件夹 token（可选，用于创建表格）
        """
        self.app_id = config.get('app_id')
        self.app_secret = config.get('app_secret')
        self.app_token = config.get('app_token')
        self.table_id = config.get('table_id')
        self.folder_token = config.get('folder_token')
        
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
        
        if not self.app_id or not self.app_secret:
            raise ValueError("app_id and app_secret are required")
        
        logger.info(f"FeishuBitable initialized with app_id={self.app_id[:10]}...")
    
    def _get_access_token(self) -> str:
        """
        获取 tenant_access_token
        
        Returns:
            有效的 access_token
        """
        # 检查缓存的 token 是否有效
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token
        
        url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data.get('code') != 0:
                raise Exception(f"获取 token 失败: {data.get('msg')}")
            
            self._access_token = data.get('tenant_access_token')
            # token 有效期通常是 2 小时
            self._token_expires_at = time.time() + data.get('expire', 7200)
            
            logger.info("Successfully obtained tenant_access_token")
            return self._access_token
            
        except Exception as e:
            logger.error(f"获取 access_token 失败: {e}")
            raise
    
    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """
        发送 API 请求
        
        Args:
            method: HTTP 方法
            endpoint: API 端点（不含 BASE_URL）
            **kwargs: 传递给 requests 的参数
        
        Returns:
            API 响应数据
        """
        url = f"{self.BASE_URL}{endpoint}"
        token = self._get_access_token()
        
        headers = kwargs.pop('headers', {})
        headers['Authorization'] = f'Bearer {token}'
        headers['Content-Type'] = 'application/json'
        
        try:
            response = requests.request(
                method, url, headers=headers, timeout=30, **kwargs
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('code') != 0:
                logger.error(f"API 错误: {data}")
                raise Exception(f"API 错误: {data.get('msg')} (code={data.get('code')})")
            
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"请求失败 {method} {endpoint}: {e}")
            raise
    
    def create_bitable(self, name: str = "文章聚合器") -> str:
        """
        创建多维表格
        
        Args:
            name: 表格名称
        
        Returns:
            创建的 app_token
        """
        endpoint = "/bitable/v1/apps"
        payload = {
            "name": name
        }
        
        if self.folder_token:
            payload["folder_token"] = self.folder_token
        
        try:
            data = self._request("POST", endpoint, json=payload)
            app_data = data.get('data', {}).get('app', {})
            self.app_token = app_data.get('app_token')
            
            logger.info(f"创建多维表格成功: {name}, app_token={self.app_token}")
            return self.app_token
            
        except Exception as e:
            logger.error(f"创建多维表格失败: {e}")
            raise
    
    def create_table(self, name: str = "文章列表") -> str:
        """
        在多维表格中创建数据表
        
        Args:
            name: 数据表名称
        
        Returns:
            创建的 table_id
        """
        if not self.app_token:
            raise ValueError("app_token is required, call create_bitable first")
        
        endpoint = f"/bitable/v1/apps/{self.app_token}/tables"
        payload = {
            "table": {
                "name": name,
                "default_view_name": "默认视图",
                "fields": self.ARTICLE_FIELDS
            }
        }
        
        try:
            data = self._request("POST", endpoint, json=payload)
            self.table_id = data.get('data', {}).get('table_id')
            
            logger.info(f"创建数据表成功: {name}, table_id={self.table_id}")
            return self.table_id
            
        except Exception as e:
            logger.error(f"创建数据表失败: {e}")
            raise

    
    def setup(self, bitable_name: str = "文章聚合器", table_name: str = "文章列表") -> tuple[str, str]:
        """
        一键设置：创建多维表格和数据表
        
        Args:
            bitable_name: 多维表格名称
            table_name: 数据表名称
        
        Returns:
            (app_token, table_id) 元组
        """
        if not self.app_token:
            self.create_bitable(bitable_name)
        
        if not self.table_id:
            self.create_table(table_name)
        
        return self.app_token, self.table_id
    
    def _convert_article_to_record(self, article: dict) -> dict:
        """
        将文章数据转换为多维表格记录格式
        
        Args:
            article: 文章字典
        
        Returns:
            多维表格记录格式的字典
        """
        # 处理日期字段
        fetched_at = article.get('fetched_at', '')
        if fetched_at:
            try:
                if isinstance(fetched_at, str):
                    dt = datetime.fromisoformat(fetched_at.replace('Z', '+00:00'))
                    fetched_at_ts = int(dt.timestamp() * 1000)
                else:
                    fetched_at_ts = int(fetched_at.timestamp() * 1000)
            except (ValueError, AttributeError):
                fetched_at_ts = int(datetime.now().timestamp() * 1000)
        else:
            fetched_at_ts = int(datetime.now().timestamp() * 1000)
        
        # 处理优先级
        priority = article.get('priority_score', article.get('priority', 0))
        if isinstance(priority, float):
            priority = round(priority, 2)
        
        # 处理分类
        category = article.get('category', '其他')
        # 确保分类在预定义列表中
        valid_categories = [
            "AI/机器学习", "安全/隐私", "系统/架构", "编程语言",
            "数据库/存储", "网络/分布式", "前端/移动端", "DevOps/云计算",
            "开源项目", "漏洞/CVE", "其他"
        ]
        if category not in valid_categories:
            category = "其他"
        
        # 处理来源
        source_type = article.get('source_type', 'rss')
        valid_sources = ["arxiv", "rss", "nvd", "kev", "dblp", "huggingface", "pwc", "blog"]
        if source_type not in valid_sources:
            source_type = "rss"
        
        return {
            "fields": {
                "标题": article.get('title', '')[:1000],  # 限制长度
                "链接": {"link": article.get('url', ''), "text": "原文链接"},
                "来源": source_type,
                "分类": category,
                "摘要": (article.get('summary', '') or '')[:2000],
                "中文摘要": (article.get('zh_summary', '') or '')[:2000],
                "优先级": priority,
                "抓取时间": fetched_at_ts,
                "已推送": article.get('is_pushed', False),
            }
        }
    
    def add_record(self, article: dict) -> Optional[str]:
        """
        添加单条记录
        
        Args:
            article: 文章字典
        
        Returns:
            记录 ID，失败返回 None
        """
        if not self.app_token or not self.table_id:
            raise ValueError("app_token and table_id are required")
        
        endpoint = f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"
        record = self._convert_article_to_record(article)
        
        try:
            data = self._request("POST", endpoint, json=record)
            record_id = data.get('data', {}).get('record', {}).get('record_id')
            logger.debug(f"添加记录成功: {article.get('title', '')[:30]}...")
            return record_id
            
        except Exception as e:
            logger.error(f"添加记录失败: {e}")
            return None
    
    def batch_add_records(self, articles: list[dict], batch_size: int = 100) -> int:
        """
        批量添加记录
        
        Args:
            articles: 文章列表
            batch_size: 每批数量（最大 500）
        
        Returns:
            成功添加的记录数
        """
        if not self.app_token or not self.table_id:
            raise ValueError("app_token and table_id are required")
        
        endpoint = f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/batch_create"
        
        success_count = 0
        batch_size = min(batch_size, 500)  # API 限制最大 500
        
        for i in range(0, len(articles), batch_size):
            batch = articles[i:i + batch_size]
            records = [self._convert_article_to_record(a) for a in batch]
            
            payload = {"records": records}
            
            try:
                data = self._request("POST", endpoint, json=payload)
                added = len(data.get('data', {}).get('records', []))
                success_count += added
                logger.info(f"批量添加记录: {i+1}-{i+len(batch)}/{len(articles)}, 成功 {added}")
                
            except Exception as e:
                logger.error(f"批量添加记录失败 (batch {i//batch_size + 1}): {e}")
        
        return success_count
    
    def update_record(self, record_id: str, article: dict) -> bool:
        """
        更新单条记录
        
        Args:
            record_id: 记录 ID
            article: 文章字典
        
        Returns:
            是否成功
        """
        if not self.app_token or not self.table_id:
            raise ValueError("app_token and table_id are required")
        
        endpoint = f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/{record_id}"
        record = self._convert_article_to_record(article)
        
        try:
            self._request("PUT", endpoint, json=record)
            logger.debug(f"更新记录成功: {record_id}")
            return True
            
        except Exception as e:
            logger.error(f"更新记录失败: {e}")
            return False
    
    def list_records(self, page_size: int = 100, page_token: str = None) -> tuple[list[dict], Optional[str]]:
        """
        列出记录
        
        Args:
            page_size: 每页数量
            page_token: 分页 token
        
        Returns:
            (记录列表, 下一页 token) 元组
        """
        if not self.app_token or not self.table_id:
            raise ValueError("app_token and table_id are required")
        
        endpoint = f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"
        params = {"page_size": min(page_size, 500)}
        if page_token:
            params["page_token"] = page_token
        
        try:
            data = self._request("GET", endpoint, params=params)
            items = data.get('data', {}).get('items', [])
            next_token = data.get('data', {}).get('page_token')
            return items, next_token
            
        except Exception as e:
            logger.error(f"列出记录失败: {e}")
            return [], None
    
    def search_by_url(self, url: str) -> Optional[str]:
        """
        根据 URL 搜索记录
        
        Args:
            url: 文章 URL
        
        Returns:
            记录 ID，未找到返回 None
        """
        if not self.app_token or not self.table_id:
            raise ValueError("app_token and table_id are required")
        
        endpoint = f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/search"
        payload = {
            "filter": {
                "conjunction": "and",
                "conditions": [
                    {
                        "field_name": "链接",
                        "operator": "contains",
                        "value": [url]
                    }
                ]
            }
        }
        
        try:
            data = self._request("POST", endpoint, json=payload)
            items = data.get('data', {}).get('items', [])
            if items:
                return items[0].get('record_id')
            return None
            
        except Exception as e:
            logger.error(f"搜索记录失败: {e}")
            return None
    
    def sync_article(self, article: dict) -> Optional[str]:
        """
        同步单篇文章（存在则更新，不存在则新增）
        
        Args:
            article: 文章字典
        
        Returns:
            记录 ID
        """
        url = article.get('url', '')
        if not url:
            logger.warning("文章缺少 URL，跳过同步")
            return None
        
        # 先搜索是否存在
        record_id = self.search_by_url(url)
        
        if record_id:
            # 更新
            if self.update_record(record_id, article):
                return record_id
            return None
        else:
            # 新增
            return self.add_record(article)
    
    def get_statistics(self) -> dict:
        """
        获取统计信息
        
        Returns:
            统计数据字典
        """
        stats = {
            "total": 0,
            "by_source": {},
            "by_category": {},
            "pushed": 0,
            "unpushed": 0
        }
        
        page_token = None
        while True:
            records, page_token = self.list_records(page_size=500, page_token=page_token)
            
            for record in records:
                fields = record.get('fields', {})
                stats["total"] += 1
                
                # 按来源统计
                source = fields.get('来源', 'unknown')
                stats["by_source"][source] = stats["by_source"].get(source, 0) + 1
                
                # 按分类统计
                category = fields.get('分类', '其他')
                stats["by_category"][category] = stats["by_category"].get(category, 0) + 1
                
                # 推送状态
                if fields.get('已推送'):
                    stats["pushed"] += 1
                else:
                    stats["unpushed"] += 1
            
            if not page_token:
                break
        
        return stats
