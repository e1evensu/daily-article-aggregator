"""
GitHub 热门项目抓取器

从 GitHub 获取热门/新兴项目，支持去重和更新检测。
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import requests

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class GitHubFetcher(BaseFetcher):
    """
    GitHub 热门项目抓取器
    
    功能：
    - 获取 trending 项目
    - 搜索高星项目
    - 检测项目重大更新（避免重复推送）
    """
    
    API_BASE = "https://api.github.com"
    
    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化抓取器
        
        Args:
            config: 配置字典
                - token: GitHub API token（可选，提高限额）
                - topics: 关注的话题列表
                - min_stars: 最低星数
                - days_back: 获取多少天内创建/更新的项目
                - timeout: 请求超时
        """
        self.config = config or {}
        self.token = self.config.get('token', '')
        self.topics = self.config.get('topics', ['security', 'llm', 'ai', 'machine-learning'])
        self.min_stars = self.config.get('min_stars', 100)
        self.days_back = self.config.get('days_back', 7)
        self.timeout = self.config.get('timeout', 30)
        self.max_results = self.config.get('max_results', 50)
        
        # 用于记录已推送项目的版本信息
        self._pushed_versions: dict[str, dict] = {}
        
        logger.info(
            f"GitHubFetcher initialized: topics={self.topics}, "
            f"min_stars={self.min_stars}, days_back={self.days_back}"
        )
    
    @property
    def _headers(self) -> dict:
        """获取请求头"""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "DailyArticleAggregator/1.0"
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers
    
    def fetch(self) -> list[dict[str, Any]]:
        """
        获取 GitHub 热门项目
        
        Returns:
            项目列表
        """
        all_projects = []
        
        # 1. 按话题搜索热门项目
        for topic in self.topics:
            try:
                projects = self._search_by_topic(topic)
                all_projects.extend(projects)
            except Exception as e:
                logger.error(f"Error searching topic {topic}: {e}")
        
        # 2. 搜索最近创建的高星项目
        try:
            new_projects = self._search_new_trending()
            all_projects.extend(new_projects)
        except Exception as e:
            logger.error(f"Error searching new trending: {e}")
        
        # 去重（按 repo full_name）
        seen = set()
        unique_projects = []
        for p in all_projects:
            repo_name = p.get('repo_full_name', '')
            if repo_name and repo_name not in seen:
                seen.add(repo_name)
                unique_projects.append(p)
        
        logger.info(f"Fetched {len(unique_projects)} unique GitHub projects")
        return unique_projects
    
    def _search_by_topic(self, topic: str) -> list[dict[str, Any]]:
        """按话题搜索项目"""
        cutoff_date = (datetime.now() - timedelta(days=self.days_back)).strftime('%Y-%m-%d')
        
        # 搜索最近有更新的高星项目
        query = f"topic:{topic} stars:>={self.min_stars} pushed:>={cutoff_date}"
        
        url = f"{self.API_BASE}/search/repositories"
        params = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": min(30, self.max_results)
        }
        
        response = requests.get(
            url,
            headers=self._headers,
            params=params,
            timeout=self.timeout
        )
        response.raise_for_status()
        
        data = response.json()
        items = data.get('items', [])
        
        projects = []
        for item in items:
            project = self._parse_repo(item, topic)
            if project and self._should_push(project):
                projects.append(project)
        
        logger.info(f"Topic '{topic}': found {len(projects)} projects to push")
        return projects
    
    def _search_new_trending(self) -> list[dict[str, Any]]:
        """搜索最近创建的热门项目"""
        cutoff_date = (datetime.now() - timedelta(days=self.days_back)).strftime('%Y-%m-%d')
        
        # 最近创建且快速增长的项目
        query = f"created:>={cutoff_date} stars:>={self.min_stars // 2}"
        
        url = f"{self.API_BASE}/search/repositories"
        params = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": min(20, self.max_results)
        }
        
        response = requests.get(
            url,
            headers=self._headers,
            params=params,
            timeout=self.timeout
        )
        response.raise_for_status()
        
        data = response.json()
        items = data.get('items', [])
        
        projects = []
        for item in items:
            project = self._parse_repo(item, 'new_trending')
            if project and self._should_push(project):
                projects.append(project)
        
        return projects
    
    def _parse_repo(self, item: dict, topic: str) -> dict[str, Any] | None:
        """解析仓库信息"""
        full_name = item.get('full_name', '')
        if not full_name:
            return None
        
        # 获取最新 release 信息
        latest_release = self._get_latest_release(full_name)
        
        description = item.get('description', '') or ''
        
        return {
            'title': f"[GitHub] {full_name}",
            'url': item.get('html_url', ''),
            'summary': description[:500] if description else '',
            'content': self._build_content(item, latest_release),
            'published_date': item.get('pushed_at', item.get('created_at', '')),
            'source': 'GitHub',
            'source_type': 'github',
            'repo_full_name': full_name,
            'stars': item.get('stargazers_count', 0),
            'forks': item.get('forks_count', 0),
            'language': item.get('language', ''),
            'topics': item.get('topics', []),
            'search_topic': topic,
            'latest_release': latest_release,
            'created_at': item.get('created_at', ''),
            'pushed_at': item.get('pushed_at', ''),
            'fetched_at': datetime.now().isoformat(),
        }
    
    def _build_content(self, item: dict, release: Optional[dict]) -> str:
        """构建项目内容描述"""
        parts = []
        
        # 基本信息
        parts.append(f"**{item.get('full_name', '')}**")
        parts.append(f"\n{item.get('description', '') or '无描述'}")
        parts.append(f"\n⭐ Stars: {item.get('stargazers_count', 0):,}")
        parts.append(f"🍴 Forks: {item.get('forks_count', 0):,}")
        
        if item.get('language'):
            parts.append(f"💻 Language: {item['language']}")
        
        topics = item.get('topics', [])
        if topics:
            parts.append(f"🏷️ Topics: {', '.join(topics[:5])}")
        
        # Release 信息
        if release:
            parts.append(f"\n📦 Latest Release: {release.get('tag_name', 'N/A')}")
            if release.get('published_at'):
                parts.append(f"📅 Released: {release['published_at'][:10]}")
        
        return '\n'.join(parts)
    
    def _get_latest_release(self, full_name: str) -> Optional[dict]:
        """获取最新 release"""
        try:
            url = f"{self.API_BASE}/repos/{full_name}/releases/latest"
            response = requests.get(
                url,
                headers=self._headers,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    'tag_name': data.get('tag_name', ''),
                    'name': data.get('name', ''),
                    'published_at': data.get('published_at', ''),
                    'body': data.get('body', '')[:500] if data.get('body') else '',
                }
        except Exception:
            pass
        return None
    
    def _should_push(self, project: dict) -> bool:
        """
        判断项目是否应该推送
        
        避免重复推送同一个项目，除非有重大更新：
        - 新项目：首次发现
        - 新 release：版本号变化
        - 星数大幅增长：增长超过 20%
        """
        repo_name = project.get('repo_full_name', '')
        if not repo_name:
            return False
        
        # 检查是否已推送过
        if repo_name not in self._pushed_versions:
            # 首次发现，应该推送
            self._pushed_versions[repo_name] = {
                'stars': project.get('stars', 0),
                'release': project.get('latest_release', {}).get('tag_name', ''),
                'pushed_at': datetime.now().isoformat(),
            }
            return True
        
        prev = self._pushed_versions[repo_name]
        
        # 检查是否有新 release
        current_release = project.get('latest_release', {}).get('tag_name', '')
        if current_release and current_release != prev.get('release', ''):
            logger.info(f"New release for {repo_name}: {current_release}")
            self._pushed_versions[repo_name]['release'] = current_release
            self._pushed_versions[repo_name]['pushed_at'] = datetime.now().isoformat()
            project['update_reason'] = f"新版本发布: {current_release}"
            return True
        
        # 检查星数增长
        prev_stars = prev.get('stars', 0)
        current_stars = project.get('stars', 0)
        if prev_stars > 0 and current_stars > prev_stars * 1.2:
            logger.info(f"Star growth for {repo_name}: {prev_stars} -> {current_stars}")
            self._pushed_versions[repo_name]['stars'] = current_stars
            self._pushed_versions[repo_name]['pushed_at'] = datetime.now().isoformat()
            project['update_reason'] = f"星数增长: {prev_stars:,} → {current_stars:,}"
            return True
        
        # 没有重大更新，不推送
        return False
    
    def load_pushed_versions(self, data: dict) -> None:
        """加载已推送版本记录（从数据库恢复）"""
        self._pushed_versions = data
    
    def get_pushed_versions(self) -> dict:
        """获取已推送版本记录（用于持久化）"""
        return self._pushed_versions
    
    @property
    def source_type(self) -> str:
        return 'github'
    
    @property
    def source_name(self) -> str:
        return 'GitHub'
    
    def is_enabled(self) -> bool:
        """检查是否启用"""
        return self.config.get('enabled', True)
