"""
NVDFetcher - NVD API 2.0 获取器
NVDFetcher - NVD API 2.0 Fetcher

从美国国家漏洞数据库 (NVD) 获取最新 CVE 信息。
Fetches latest CVE information from the National Vulnerability Database.

需求 Requirements:
- 2.1: 通过 NVD API 2.0 获取最新 CVE 信息
- 2.2: 提取 CVE ID、描述、CVSS 评分、发布日期和受影响产品
- 2.5: 请求失败时记录错误并继续处理其他数据源
"""

import logging
from datetime import datetime, timedelta
from typing import Any

import requests

from .base import BaseFetcher, FetchResult

logger = logging.getLogger(__name__)


class NVDFetcher(BaseFetcher):
    """
    NVD API 2.0 获取器
    NVD API 2.0 Fetcher
    
    从美国国家漏洞数据库获取最新的 CVE 漏洞信息。
    Fetches latest CVE vulnerability information from NVD.
    
    Attributes:
        enabled: 是否启用此 Fetcher
        api_key: NVD API 密钥（可选，有密钥速率更高）
        days_back: 获取最近 N 天的 CVE
        timeout: 请求超时时间（秒）
    """
    
    API_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"
    
    def __init__(self, config: dict[str, Any]):
        """
        初始化 NVD Fetcher
        Initialize NVD Fetcher
        
        Args:
            config: 配置字典，包含以下键：
                   - enabled: 是否启用 (bool, default=True)
                   - api_key: NVD API 密钥 (str, optional)
                   - days_back: 获取最近 N 天的 CVE (int, default=7)
                   - timeout: 请求超时时间秒数 (int, default=60)
        
        Examples:
            >>> config = {
            ...     'enabled': True,
            ...     'api_key': 'your-api-key',
            ...     'days_back': 7,
            ...     'timeout': 60
            ... }
            >>> fetcher = NVDFetcher(config)
        """
        self.enabled: bool = config.get('enabled', True)
        self.api_key: str | None = config.get('api_key') or None
        self.days_back: int = config.get('days_back', 7)
        self.timeout: int = config.get('timeout', 60)
        self.min_cvss_score: float = config.get('min_cvss_score', 0.0)  # CVSS 最低分数过滤
    
    def is_enabled(self) -> bool:
        """
        检查 Fetcher 是否启用
        Check if the Fetcher is enabled
        
        Returns:
            bool: True 如果 Fetcher 已启用
        """
        return self.enabled
    
    def fetch(self) -> FetchResult:
        """
        获取最新 CVE
        Fetch latest CVEs
        
        从 NVD API 获取指定时间范围内的 CVE 漏洞信息。
        Fetches CVE vulnerability information from NVD API within specified time range.
        
        Returns:
            FetchResult: 包含获取的 CVE 列表和可能的错误信息
        """
        if not self.is_enabled():
            return FetchResult(
                items=[],
                source_name='NVD',
                source_type='nvd',
                error='Fetcher is disabled'
            )
        
        try:
            # 计算时间范围
            # Calculate time range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=self.days_back)
            
            # 构建请求参数
            # Build request parameters
            params = {
                'pubStartDate': start_date.strftime('%Y-%m-%dT00:00:00.000'),
                'pubEndDate': end_date.strftime('%Y-%m-%dT23:59:59.999'),
            }
            
            # 构建请求头
            # Build request headers
            headers = {
                'Accept': 'application/json',
            }
            if self.api_key:
                headers['apiKey'] = self.api_key
            
            logger.info(f"Fetching CVEs from NVD (last {self.days_back} days)...")
            
            # 发送请求
            # Send request
            response = requests.get(
                self.API_BASE,
                params=params,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            
            # 解析 CVE 列表
            # Parse CVE list
            items: list[dict[str, Any]] = []
            vulnerabilities = data.get('vulnerabilities', [])
            
            for vuln in vulnerabilities:
                cve_item = vuln.get('cve', {})
                parsed = self._parse_cve(cve_item)
                if parsed:
                    # CVSS 分数过滤
                    cvss_score = parsed.get('cvss_score')
                    if self.min_cvss_score > 0 and (cvss_score is None or cvss_score < self.min_cvss_score):
                        continue
                    items.append(parsed)
            
            # 统计过滤结果
            filtered_count = len(vulnerabilities) - len(items)
            if filtered_count > 0:
                logger.info(f"NVD: 过滤掉 {filtered_count} 个低危漏洞 (CVSS < {self.min_cvss_score})")
            
            logger.info(f"NVD Fetcher: 获取了 {len(items)} 个高危 CVE")
            
            return FetchResult(
                items=items,
                source_name='NVD',
                source_type='nvd'
            )
            
        except requests.exceptions.Timeout:
            error_msg = f"NVD API request timeout after {self.timeout}s"
            logger.error(error_msg)
            return FetchResult(
                items=[],
                source_name='NVD',
                source_type='nvd',
                error=error_msg
            )
        except requests.exceptions.RequestException as e:
            error_msg = f"NVD API request failed: {str(e)}"
            logger.error(error_msg)
            return FetchResult(
                items=[],
                source_name='NVD',
                source_type='nvd',
                error=error_msg
            )
        except Exception as e:
            error_msg = f"NVD Fetcher error: {str(e)}"
            logger.error(error_msg)
            return FetchResult(
                items=[],
                source_name='NVD',
                source_type='nvd',
                error=error_msg
            )
    
    def _parse_cve(self, cve_item: dict) -> dict[str, Any] | None:
        """
        解析 CVE 条目
        Parse CVE entry
        
        Args:
            cve_item: NVD API 返回的 CVE 对象
        
        Returns:
            解析后的 CVE 字典，包含 cve_id, description, cvss_score, 
            published_date, affected_products, references
            如果缺少必要字段则返回 None
        """
        # 提取 CVE ID
        # Extract CVE ID
        cve_id = cve_item.get('id', '').strip()
        if not cve_id:
            return None
        
        # 提取描述
        # Extract description
        description = self._extract_description(cve_item)
        
        # 提取 CVSS 评分
        # Extract CVSS score
        cvss_score, cvss_vector = self._extract_cvss(cve_item)
        
        # 提取发布日期
        # Extract published date
        published_date = cve_item.get('published', '')
        if published_date:
            # 转换为日期格式
            try:
                dt = datetime.fromisoformat(published_date.replace('Z', '+00:00'))
                published_date = dt.strftime('%Y-%m-%d')
            except (ValueError, TypeError):
                published_date = published_date[:10] if len(published_date) >= 10 else ''
        
        # 提取受影响产品
        # Extract affected products
        affected_products = self._extract_affected_products(cve_item)
        
        # 提取引用链接
        # Extract references
        references = self._extract_references(cve_item)
        
        # 构建 URL
        # Build URL
        url = f"https://nvd.nist.gov/vuln/detail/{cve_id}"
        
        return {
            'cve_id': cve_id,
            'title': f"{cve_id}: {description[:100]}..." if len(description) > 100 else f"{cve_id}: {description}",
            'description': description,
            'cvss_score': cvss_score,
            'cvss_vector': cvss_vector,
            'published_date': published_date,
            'affected_products': affected_products,
            'references': references,
            'url': url,
            'source': 'NVD',
            'source_type': 'nvd',
        }
    
    def _extract_description(self, cve_item: dict) -> str:
        """
        从 CVE 条目中提取描述
        Extract description from CVE entry
        
        Args:
            cve_item: CVE 对象
        
        Returns:
            描述字符串，优先返回英文描述
        """
        descriptions = cve_item.get('descriptions', [])
        
        # 优先查找英文描述
        # Prefer English description
        for desc in descriptions:
            if desc.get('lang') == 'en':
                return desc.get('value', '').strip()
        
        # 如果没有英文描述，返回第一个描述
        # If no English description, return the first one
        if descriptions:
            return descriptions[0].get('value', '').strip()
        
        return ''
    
    def _extract_cvss(self, cve_item: dict) -> tuple[float | None, str | None]:
        """
        从 CVE 条目中提取 CVSS 评分
        Extract CVSS score from CVE entry
        
        Args:
            cve_item: CVE 对象
        
        Returns:
            (CVSS 评分, CVSS 向量) 元组
        """
        metrics = cve_item.get('metrics', {})
        
        # 优先使用 CVSS 3.1
        # Prefer CVSS 3.1
        cvss_v31 = metrics.get('cvssMetricV31', [])
        if cvss_v31:
            cvss_data = cvss_v31[0].get('cvssData', {})
            return (
                cvss_data.get('baseScore'),
                cvss_data.get('vectorString')
            )
        
        # 尝试 CVSS 3.0
        # Try CVSS 3.0
        cvss_v30 = metrics.get('cvssMetricV30', [])
        if cvss_v30:
            cvss_data = cvss_v30[0].get('cvssData', {})
            return (
                cvss_data.get('baseScore'),
                cvss_data.get('vectorString')
            )
        
        # 尝试 CVSS 2.0
        # Try CVSS 2.0
        cvss_v2 = metrics.get('cvssMetricV2', [])
        if cvss_v2:
            cvss_data = cvss_v2[0].get('cvssData', {})
            return (
                cvss_data.get('baseScore'),
                cvss_data.get('vectorString')
            )
        
        return None, None
    
    def _extract_affected_products(self, cve_item: dict) -> list[str]:
        """
        从 CVE 条目中提取受影响产品
        Extract affected products from CVE entry
        
        Args:
            cve_item: CVE 对象
        
        Returns:
            受影响产品列表
        """
        products: list[str] = []
        
        configurations = cve_item.get('configurations', [])
        for config in configurations:
            nodes = config.get('nodes', [])
            for node in nodes:
                cpe_matches = node.get('cpeMatch', [])
                for cpe in cpe_matches:
                    criteria = cpe.get('criteria', '')
                    if criteria:
                        # 从 CPE 字符串中提取产品信息
                        # Extract product info from CPE string
                        parts = criteria.split(':')
                        if len(parts) >= 5:
                            vendor = parts[3]
                            product = parts[4]
                            products.append(f"{vendor}:{product}")
        
        # 去重
        return list(set(products))
    
    def _extract_references(self, cve_item: dict) -> list[dict[str, str]]:
        """
        从 CVE 条目中提取引用链接
        Extract references from CVE entry
        
        Args:
            cve_item: CVE 对象
        
        Returns:
            引用链接列表，每个元素包含 url 和 source
        """
        references: list[dict[str, str]] = []
        
        refs = cve_item.get('references', [])
        for ref in refs:
            url = ref.get('url', '').strip()
            if url:
                references.append({
                    'url': url,
                    'source': ref.get('source', ''),
                    'tags': ref.get('tags', [])
                })
        
        return references


def parse_cve(cve_item: dict) -> dict[str, Any] | None:
    """
    解析 CVE 条目（独立函数，用于属性测试）
    Parse CVE entry (standalone function for property testing)
    
    Args:
        cve_item: CVE 字典，包含 id, descriptions, metrics 等字段
    
    Returns:
        解析后的 CVE 字典，如果缺少必要字段则返回 None
    
    Examples:
        >>> cve_item = {
        ...     'id': 'CVE-2024-1234',
        ...     'descriptions': [{'lang': 'en', 'value': 'A vulnerability'}],
        ...     'metrics': {'cvssMetricV31': [{'cvssData': {'baseScore': 7.5}}]},
        ...     'published': '2024-01-15T00:00:00.000'
        ... }
        >>> result = parse_cve(cve_item)
        >>> result['cve_id']
        'CVE-2024-1234'
    """
    # 提取 CVE ID
    cve_id = cve_item.get('id', '').strip()
    if not cve_id:
        return None
    
    # 提取描述
    description = ''
    descriptions = cve_item.get('descriptions', [])
    for desc in descriptions:
        if desc.get('lang') == 'en':
            description = desc.get('value', '').strip()
            break
    if not description and descriptions:
        description = descriptions[0].get('value', '').strip()
    
    # 提取 CVSS 评分
    cvss_score: float | None = None
    cvss_vector: str | None = None
    metrics = cve_item.get('metrics', {})
    
    for metric_key in ['cvssMetricV31', 'cvssMetricV30', 'cvssMetricV2']:
        metric_list = metrics.get(metric_key, [])
        if metric_list:
            cvss_data = metric_list[0].get('cvssData', {})
            cvss_score = cvss_data.get('baseScore')
            cvss_vector = cvss_data.get('vectorString')
            break
    
    # 提取发布日期
    published_date = cve_item.get('published', '')
    if published_date:
        try:
            dt = datetime.fromisoformat(published_date.replace('Z', '+00:00'))
            published_date = dt.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            published_date = published_date[:10] if len(published_date) >= 10 else ''
    
    # 提取受影响产品
    affected_products: list[str] = []
    configurations = cve_item.get('configurations', [])
    for config in configurations:
        nodes = config.get('nodes', [])
        for node in nodes:
            cpe_matches = node.get('cpeMatch', [])
            for cpe in cpe_matches:
                criteria = cpe.get('criteria', '')
                if criteria:
                    parts = criteria.split(':')
                    if len(parts) >= 5:
                        vendor = parts[3]
                        product = parts[4]
                        affected_products.append(f"{vendor}:{product}")
    affected_products = list(set(affected_products))
    
    # 构建 URL
    url = f"https://nvd.nist.gov/vuln/detail/{cve_id}"
    
    return {
        'cve_id': cve_id,
        'title': f"{cve_id}: {description[:100]}..." if len(description) > 100 else f"{cve_id}: {description}",
        'description': description,
        'cvss_score': cvss_score,
        'cvss_vector': cvss_vector,
        'published_date': published_date,
        'affected_products': affected_products,
        'url': url,
        'source': 'NVD',
        'source_type': 'nvd',
    }
