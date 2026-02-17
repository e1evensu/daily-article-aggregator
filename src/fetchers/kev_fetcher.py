"""
KEVFetcher - CISA KEV 获取器
KEVFetcher - CISA Known Exploited Vulnerabilities Fetcher

从 CISA 获取已知被利用漏洞目录。
Fetches Known Exploited Vulnerabilities catalog from CISA.

需求 Requirements:
- 2.3: 获取在野利用漏洞目录
- 2.4: 提取 CVE ID、漏洞名称、厂商、产品和添加日期
- 2.5: 请求失败时记录错误并继续处理其他数据源
"""

import logging
from datetime import datetime, timedelta
from typing import Any

import requests

from .base import BaseFetcher, FetchResult

logger = logging.getLogger(__name__)


class KEVFetcher(BaseFetcher):
    """
    CISA KEV 获取器
    CISA Known Exploited Vulnerabilities Fetcher
    
    从 CISA 获取已知被利用漏洞目录，这些漏洞已被确认在野外被利用。
    Fetches Known Exploited Vulnerabilities catalog from CISA.
    These vulnerabilities have been confirmed to be exploited in the wild.
    
    Attributes:
        enabled: 是否启用此 Fetcher
        days_back: 获取最近 N 天添加的漏洞
        timeout: 请求超时时间（秒）
    """
    
    KEV_JSON_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
    
    def __init__(self, config: dict[str, Any]):
        """
        初始化 KEV Fetcher
        Initialize KEV Fetcher
        
        Args:
            config: 配置字典，包含以下键：
                   - enabled: 是否启用 (bool, default=True)
                   - days_back: 获取最近 N 天添加的漏洞 (int, default=30)
                   - timeout: 请求超时时间秒数 (int, default=30)
        
        Examples:
            >>> config = {
            ...     'enabled': True,
            ...     'days_back': 30,
            ...     'timeout': 30
            ... }
            >>> fetcher = KEVFetcher(config)
        """
        self.enabled: bool = config.get('enabled', True)
        self.days_back: int = config.get('days_back', 30)
        self.timeout: int = config.get('timeout', 30)
    
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
        获取 KEV 列表
        Fetch KEV list
        
        从 CISA 获取已知被利用漏洞目录，并过滤出指定时间范围内添加的漏洞。
        Fetches KEV catalog from CISA and filters vulnerabilities added within
        the specified time range.
        
        Returns:
            FetchResult: 包含获取的 KEV 列表和可能的错误信息
        """
        if not self.is_enabled():
            return FetchResult(
                items=[],
                source_name='CISA KEV',
                source_type='kev',
                error='Fetcher is disabled'
            )
        
        try:
            logger.info(f"Fetching KEV catalog from CISA (last {self.days_back} days)...")
            
            # 发送请求
            # Send request
            response = requests.get(
                self.KEV_JSON_URL,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            
            # 计算时间范围
            # Calculate time range
            cutoff_date = datetime.now() - timedelta(days=self.days_back)
            
            # 解析 KEV 列表
            # Parse KEV list
            items: list[dict[str, Any]] = []
            vulnerabilities = data.get('vulnerabilities', [])
            
            for vuln in vulnerabilities:
                parsed = self._parse_kev_entry(vuln)
                if parsed:
                    # 过滤时间范围
                    # Filter by time range
                    date_added = parsed.get('date_added', '')
                    if date_added:
                        try:
                            added_dt = datetime.strptime(date_added, '%Y-%m-%d')
                            if added_dt >= cutoff_date:
                                items.append(parsed)
                        except ValueError:
                            # 如果日期解析失败，仍然包含该条目
                            items.append(parsed)
                    else:
                        items.append(parsed)
            
            logger.info(f"KEV Fetcher: 获取了 {len(items)} 个在野利用漏洞")
            
            return FetchResult(
                items=items,
                source_name='CISA KEV',
                source_type='kev'
            )
            
        except requests.exceptions.Timeout:
            error_msg = f"CISA KEV request timeout after {self.timeout}s"
            logger.error(error_msg)
            return FetchResult(
                items=[],
                source_name='CISA KEV',
                source_type='kev',
                error=error_msg
            )
        except requests.exceptions.RequestException as e:
            error_msg = f"CISA KEV request failed: {str(e)}"
            logger.error(error_msg)
            return FetchResult(
                items=[],
                source_name='CISA KEV',
                source_type='kev',
                error=error_msg
            )
        except Exception as e:
            error_msg = f"KEV Fetcher error: {str(e)}"
            logger.error(error_msg)
            return FetchResult(
                items=[],
                source_name='CISA KEV',
                source_type='kev',
                error=error_msg
            )
    
    def _parse_kev_entry(self, entry: dict) -> dict[str, Any] | None:
        """
        解析 KEV 条目
        Parse KEV entry
        
        Args:
            entry: CISA KEV JSON 中的漏洞条目
        
        Returns:
            解析后的 KEV 字典，包含 cve_id, vulnerability_name, vendor, 
            product, date_added, short_description, required_action
            如果缺少必要字段则返回 None
        """
        # 提取 CVE ID
        # Extract CVE ID
        cve_id = entry.get('cveID', '').strip()
        if not cve_id:
            return None
        
        # 提取漏洞名称
        # Extract vulnerability name
        vulnerability_name = entry.get('vulnerabilityName', '').strip()
        
        # 提取厂商
        # Extract vendor
        vendor = entry.get('vendorProject', '').strip()
        
        # 提取产品
        # Extract product
        product = entry.get('product', '').strip()
        
        # 提取添加日期
        # Extract date added
        date_added = entry.get('dateAdded', '').strip()
        
        # 提取简短描述
        # Extract short description
        short_description = entry.get('shortDescription', '').strip()
        
        # 提取要求的行动
        # Extract required action
        required_action = entry.get('requiredAction', '').strip()
        
        # 提取截止日期
        # Extract due date
        due_date = entry.get('dueDate', '').strip()
        
        # 提取已知勒索软件活动
        # Extract known ransomware campaign use
        known_ransomware = entry.get('knownRansomwareCampaignUse', '').strip()
        
        # 构建 URL
        # Build URL
        url = f"https://nvd.nist.gov/vuln/detail/{cve_id}"
        
        # 构建标题
        # Build title
        title = f"[KEV] {cve_id}: {vulnerability_name}" if vulnerability_name else f"[KEV] {cve_id}"
        
        return {
            'cve_id': cve_id,
            'title': title,
            'vulnerability_name': vulnerability_name,
            'vendor': vendor,
            'product': product,
            'date_added': date_added,
            'short_description': short_description,
            'required_action': required_action,
            'due_date': due_date,
            'known_ransomware': known_ransomware,
            'url': url,
            'source': 'CISA KEV',
            'source_type': 'kev',
            'published_date': date_added,
        }


def parse_kev_entry(entry: dict) -> dict[str, Any] | None:
    """
    解析 KEV 条目（独立函数，用于属性测试）
    Parse KEV entry (standalone function for property testing)
    
    Args:
        entry: KEV 字典，包含 cveID, vulnerabilityName, vendorProject 等字段
    
    Returns:
        解析后的 KEV 字典，如果缺少必要字段则返回 None
    
    Examples:
        >>> entry = {
        ...     'cveID': 'CVE-2024-1234',
        ...     'vulnerabilityName': 'Remote Code Execution',
        ...     'vendorProject': 'Microsoft',
        ...     'product': 'Windows',
        ...     'dateAdded': '2024-01-15'
        ... }
        >>> result = parse_kev_entry(entry)
        >>> result['cve_id']
        'CVE-2024-1234'
    """
    # 提取 CVE ID
    cve_id = entry.get('cveID', '').strip()
    if not cve_id:
        return None
    
    # 提取漏洞名称
    vulnerability_name = entry.get('vulnerabilityName', '').strip()
    
    # 提取厂商
    vendor = entry.get('vendorProject', '').strip()
    
    # 提取产品
    product = entry.get('product', '').strip()
    
    # 提取添加日期
    date_added = entry.get('dateAdded', '').strip()
    
    # 提取简短描述
    short_description = entry.get('shortDescription', '').strip()
    
    # 提取要求的行动
    required_action = entry.get('requiredAction', '').strip()
    
    # 提取截止日期
    due_date = entry.get('dueDate', '').strip()
    
    # 提取已知勒索软件活动
    known_ransomware = entry.get('knownRansomwareCampaignUse', '').strip()
    
    # 构建 URL
    url = f"https://nvd.nist.gov/vuln/detail/{cve_id}"
    
    # 构建标题
    title = f"[KEV] {cve_id}: {vulnerability_name}" if vulnerability_name else f"[KEV] {cve_id}"
    
    return {
        'cve_id': cve_id,
        'title': title,
        'vulnerability_name': vulnerability_name,
        'vendor': vendor,
        'product': product,
        'date_added': date_added,
        'short_description': short_description,
        'required_action': required_action,
        'due_date': due_date,
        'known_ransomware': known_ransomware,
        'url': url,
        'source': 'CISA KEV',
        'source_type': 'kev',
        'published_date': date_added,
    }
