"""
Sitemap Importer - Sitemap XML 解析器
Sitemap Importer - Sitemap XML Parser

解析 sitemap.xml 文件，提取页面 URL 及其元数据。支持标准 sitemap 格式、
sitemap index 格式和 gzip 压缩。

Parses sitemap.xml files to extract page URLs and their metadata. Supports
standard sitemap format, sitemap index format, and gzip compression.

Requirements:
- 5.1: WHEN a valid sitemap.xml URL is provided, THE Sitemap_Importer SHALL parse and extract all page URLs
- 5.2: THE Sitemap_Importer SHALL support standard sitemap format with loc, lastmod, changefreq, and priority elements
- 5.3: THE Sitemap_Importer SHALL support sitemap index files containing references to multiple sitemaps
- 5.5: THE Sitemap_Importer SHALL handle gzip-compressed sitemaps transparently
- 8.1: THE Sitemap_Importer SHALL support include_patterns configuration as list of glob patterns
- 8.2: THE Sitemap_Importer SHALL support exclude_patterns configuration as list of glob patterns
- 8.3: WHEN both include and exclude patterns match a URL, THE Sitemap_Importer SHALL apply exclude pattern (exclude takes precedence)
- 8.4: WHEN no include_patterns are configured, THE Sitemap_Importer SHALL include all URLs by default
- 8.5: THE Sitemap_Importer SHALL support regex patterns in addition to glob patterns
- 8.6: IF a pattern is invalid, THEN THE Sitemap_Importer SHALL raise a configuration error with pattern details

Properties:
- Property 8: Sitemap Parsing Completeness
- Property 9: Malformed Sitemap Error Handling
- Property 14: Crawl Rule Matching
- Property 15: Invalid Pattern Error
"""

import fnmatch
import gzip
import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from xml.etree import ElementTree as ET

import requests


class SitemapParseError(Exception):
    """
    Sitemap 解析错误
    Sitemap Parse Error
    
    当 sitemap.xml 解析失败时抛出此异常。
    Raised when sitemap.xml parsing fails.
    
    Attributes:
        message: 错误描述信息
                 Error description message
        url: 导致错误的 sitemap URL（可选）
             The sitemap URL that caused the error (optional)
    """
    
    def __init__(self, message: str, url: str | None = None):
        self.message = message
        self.url = url
        super().__init__(self._format_message())
    
    def _format_message(self) -> str:
        """格式化错误消息"""
        if self.url:
            return f"Failed to parse sitemap at '{self.url}': {self.message}"
        return f"Sitemap parse error: {self.message}"


class ConfigurationError(Exception):
    """
    配置错误
    Configuration Error
    
    当抓取规则配置无效时抛出此异常。
    Raised when crawl rule configuration is invalid.
    
    Attributes:
        message: 错误描述信息
                 Error description message
        pattern: 导致错误的模式（可选）
                 The pattern that caused the error (optional)
        pattern_type: 模式类型（'glob' 或 'regex'）
                      Pattern type ('glob' or 'regex')
    
    Examples:
        >>> raise ConfigurationError("Invalid regex pattern", pattern="[invalid", pattern_type="regex")
        ConfigurationError: Configuration error: Invalid regex pattern (pattern: '[invalid', type: regex)
    """
    
    def __init__(
        self, 
        message: str, 
        pattern: str | None = None, 
        pattern_type: str | None = None
    ):
        self.message = message
        self.pattern = pattern
        self.pattern_type = pattern_type
        super().__init__(self._format_message())
    
    def _format_message(self) -> str:
        """格式化错误消息"""
        base_msg = f"Configuration error: {self.message}"
        if self.pattern is not None:
            base_msg += f" (pattern: '{self.pattern}'"
            if self.pattern_type:
                base_msg += f", type: {self.pattern_type}"
            base_msg += ")"
        return base_msg


@dataclass
class SitemapEntry:
    """
    Sitemap 条目
    Sitemap Entry
    
    表示 sitemap.xml 中的单个 URL 条目，包含 URL 及其可选的元数据。
    Represents a single URL entry in sitemap.xml with its optional metadata.
    
    Attributes:
        loc: 页面 URL（必需）
             Page URL (required)
        lastmod: 最后修改时间（可选）
                 Last modification time (optional)
        changefreq: 更新频率（可选），如 'daily', 'weekly', 'monthly'
                    Change frequency (optional), e.g., 'daily', 'weekly', 'monthly'
        priority: 优先级（可选），范围 0.0-1.0
                  Priority (optional), range 0.0-1.0
    
    Examples:
        >>> entry = SitemapEntry(
        ...     loc='https://example.com/page1',
        ...     lastmod=datetime(2024, 1, 15, 10, 30, 0),
        ...     changefreq='weekly',
        ...     priority=0.8
        ... )
        >>> entry.loc
        'https://example.com/page1'
    """
    loc: str
    lastmod: datetime | None = None
    changefreq: str | None = None
    priority: float | None = None


class SitemapParser:
    """
    Sitemap XML 解析器
    Sitemap XML Parser
    
    解析 sitemap.xml 文件，支持标准 sitemap 格式、sitemap index 格式和 gzip 压缩。
    Parses sitemap.xml files, supporting standard sitemap format, sitemap index format,
    and gzip compression.
    
    Sitemap XML 命名空间:
    - 标准 sitemap: http://www.sitemaps.org/schemas/sitemap/0.9
    
    Examples:
        >>> parser = SitemapParser()
        >>> entries = parser.parse('https://example.com/sitemap.xml')
        >>> for entry in entries:
        ...     print(entry.loc)
        
        >>> # 解析 sitemap index
        >>> sitemap_urls = parser.parse_index('https://example.com/sitemap_index.xml')
        >>> for url in sitemap_urls:
        ...     entries = parser.parse(url)
    """
    
    # Sitemap XML 命名空间
    SITEMAP_NS = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    
    def __init__(self, timeout: int = 30, user_agent: str | None = None):
        """
        初始化 SitemapParser
        Initialize SitemapParser
        
        Args:
            timeout: HTTP 请求超时时间（秒）
                     HTTP request timeout in seconds
            user_agent: 自定义 User-Agent 头
                        Custom User-Agent header
        """
        self.timeout = timeout
        self.user_agent = user_agent or 'PandaWiki-SitemapParser/1.0'
        self._session = requests.Session()
        self._session.headers.update({'User-Agent': self.user_agent})
    
    def parse(self, url: str) -> list[SitemapEntry]:
        """
        解析 sitemap.xml
        Parse sitemap.xml
        
        从给定 URL 获取并解析 sitemap.xml，提取所有页面 URL 及其元数据。
        Fetches and parses sitemap.xml from the given URL, extracting all page URLs
        and their metadata.
        
        Args:
            url: sitemap.xml 的 URL
                 URL of the sitemap.xml
        
        Returns:
            SitemapEntry 列表，包含所有解析出的 URL 条目
            List of SitemapEntry containing all parsed URL entries
        
        Raises:
            SitemapParseError: 当获取或解析失败时
                               When fetching or parsing fails
        
        Examples:
            >>> parser = SitemapParser()
            >>> entries = parser.parse('https://example.com/sitemap.xml')
            >>> len(entries) > 0
            True
        """
        content = self._fetch_content(url)
        xml_content = self._decompress_if_needed(content, url)
        return self._parse_sitemap_xml(xml_content, url)
    
    def parse_index(self, url: str) -> list[str]:
        """
        解析 sitemap index，返回子 sitemap URL 列表
        Parse sitemap index, return list of child sitemap URLs
        
        从给定 URL 获取并解析 sitemap index 文件，提取所有子 sitemap 的 URL。
        Fetches and parses sitemap index file from the given URL, extracting all
        child sitemap URLs.
        
        Args:
            url: sitemap index 的 URL
                 URL of the sitemap index
        
        Returns:
            子 sitemap URL 列表
            List of child sitemap URLs
        
        Raises:
            SitemapParseError: 当获取或解析失败时
                               When fetching or parsing fails
        
        Examples:
            >>> parser = SitemapParser()
            >>> sitemap_urls = parser.parse_index('https://example.com/sitemap_index.xml')
            >>> for url in sitemap_urls:
            ...     print(url)
        """
        content = self._fetch_content(url)
        xml_content = self._decompress_if_needed(content, url)
        return self._parse_sitemap_index_xml(xml_content, url)
    
    def parse_content(self, content: bytes | str, is_gzipped: bool = False) -> list[SitemapEntry]:
        """
        解析 sitemap 内容（不通过 URL 获取）
        Parse sitemap content (without fetching from URL)
        
        直接解析提供的 sitemap 内容，用于测试或已有内容的场景。
        Directly parses the provided sitemap content, useful for testing or
        when content is already available.
        
        Args:
            content: sitemap XML 内容（bytes 或 str）
                     Sitemap XML content (bytes or str)
            is_gzipped: 内容是否为 gzip 压缩
                        Whether the content is gzip compressed
        
        Returns:
            SitemapEntry 列表
            List of SitemapEntry
        
        Raises:
            SitemapParseError: 当解析失败时
                               When parsing fails
        """
        if isinstance(content, str):
            content = content.encode('utf-8')
        
        if is_gzipped:
            xml_content = self._decompress_gzip(content)
        else:
            xml_content = content.decode('utf-8')
        
        return self._parse_sitemap_xml(xml_content, url=None)
    
    def parse_index_content(self, content: bytes | str, is_gzipped: bool = False) -> list[str]:
        """
        解析 sitemap index 内容（不通过 URL 获取）
        Parse sitemap index content (without fetching from URL)
        
        直接解析提供的 sitemap index 内容。
        Directly parses the provided sitemap index content.
        
        Args:
            content: sitemap index XML 内容（bytes 或 str）
                     Sitemap index XML content (bytes or str)
            is_gzipped: 内容是否为 gzip 压缩
                        Whether the content is gzip compressed
        
        Returns:
            子 sitemap URL 列表
            List of child sitemap URLs
        
        Raises:
            SitemapParseError: 当解析失败时
                               When parsing fails
        """
        if isinstance(content, str):
            content = content.encode('utf-8')
        
        if is_gzipped:
            xml_content = self._decompress_gzip(content)
        else:
            xml_content = content.decode('utf-8')
        
        return self._parse_sitemap_index_xml(xml_content, url=None)
    
    def _fetch_content(self, url: str) -> bytes:
        """
        获取 URL 内容
        Fetch URL content
        
        Args:
            url: 要获取的 URL
                 URL to fetch
        
        Returns:
            响应内容（bytes）
            Response content (bytes)
        
        Raises:
            SitemapParseError: 当获取失败时
                               When fetching fails
        """
        try:
            response = self._session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.content
        except requests.exceptions.Timeout:
            raise SitemapParseError(f"Request timed out after {self.timeout} seconds", url)
        except requests.exceptions.ConnectionError as e:
            raise SitemapParseError(f"Connection error: {e}", url)
        except requests.exceptions.HTTPError as e:
            raise SitemapParseError(f"HTTP error: {e}", url)
        except requests.exceptions.RequestException as e:
            raise SitemapParseError(f"Request failed: {e}", url)
    
    def _decompress_if_needed(self, content: bytes, url: str | None = None) -> str:
        """
        处理 gzip 压缩
        Handle gzip compression
        
        检测内容是否为 gzip 压缩，如果是则解压缩。
        Detects if content is gzip compressed and decompresses if so.
        
        Args:
            content: 原始内容（bytes）
                     Raw content (bytes)
            url: 来源 URL（用于错误消息）
                 Source URL (for error messages)
        
        Returns:
            解压后的 XML 字符串
            Decompressed XML string
        
        Raises:
            SitemapParseError: 当解压失败时
                               When decompression fails
        """
        # 检查 gzip 魔数 (1f 8b)
        if len(content) >= 2 and content[0:2] == b'\x1f\x8b':
            return self._decompress_gzip(content, url)
        
        # 尝试直接解码为 UTF-8
        try:
            return content.decode('utf-8')
        except UnicodeDecodeError:
            # 尝试其他编码
            try:
                return content.decode('latin-1')
            except UnicodeDecodeError:
                raise SitemapParseError("Unable to decode content as text", url)
    
    def _decompress_gzip(self, content: bytes, url: str | None = None) -> str:
        """
        解压 gzip 内容
        Decompress gzip content
        
        Args:
            content: gzip 压缩的内容
                     Gzip compressed content
            url: 来源 URL（用于错误消息）
                 Source URL (for error messages)
        
        Returns:
            解压后的字符串
            Decompressed string
        
        Raises:
            SitemapParseError: 当解压失败时
                               When decompression fails
        """
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(content)) as f:
                decompressed = f.read()
            return decompressed.decode('utf-8')
        except gzip.BadGzipFile:
            raise SitemapParseError("Invalid gzip format", url)
        except OSError as e:
            raise SitemapParseError(f"Gzip decompression failed: {e}", url)
        except UnicodeDecodeError:
            raise SitemapParseError("Unable to decode decompressed content as UTF-8", url)
    
    def _parse_sitemap_xml(self, xml_content: str, url: str | None = None) -> list[SitemapEntry]:
        """
        解析 sitemap XML 内容
        Parse sitemap XML content
        
        Args:
            xml_content: XML 字符串
                         XML string
            url: 来源 URL（用于错误消息）
                 Source URL (for error messages)
        
        Returns:
            SitemapEntry 列表
            List of SitemapEntry
        
        Raises:
            SitemapParseError: 当 XML 解析失败时
                               When XML parsing fails
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            raise SitemapParseError(f"Invalid XML: {e}", url)
        
        entries: list[SitemapEntry] = []
        
        # 尝试带命名空间的解析
        url_elements = root.findall('.//sm:url', self.SITEMAP_NS)
        
        # 如果没找到，尝试不带命名空间的解析
        if not url_elements:
            url_elements = root.findall('.//url')
        
        # 如果还是没找到，检查是否是 sitemap index
        if not url_elements:
            sitemap_elements = root.findall('.//sm:sitemap', self.SITEMAP_NS)
            if not sitemap_elements:
                sitemap_elements = root.findall('.//sitemap')
            if sitemap_elements:
                raise SitemapParseError(
                    "This appears to be a sitemap index, not a standard sitemap. "
                    "Use parse_index() method instead.",
                    url
                )
        
        for url_elem in url_elements:
            entry = self._parse_url_element(url_elem, url)
            if entry:
                entries.append(entry)
        
        return entries
    
    def _parse_sitemap_index_xml(self, xml_content: str, url: str | None = None) -> list[str]:
        """
        解析 sitemap index XML 内容
        Parse sitemap index XML content
        
        Args:
            xml_content: XML 字符串
                         XML string
            url: 来源 URL（用于错误消息）
                 Source URL (for error messages)
        
        Returns:
            子 sitemap URL 列表
            List of child sitemap URLs
        
        Raises:
            SitemapParseError: 当 XML 解析失败时
                               When XML parsing fails
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            raise SitemapParseError(f"Invalid XML: {e}", url)
        
        sitemap_urls: list[str] = []
        
        # 尝试带命名空间的解析
        sitemap_elements = root.findall('.//sm:sitemap', self.SITEMAP_NS)
        
        # 如果没找到，尝试不带命名空间的解析
        if not sitemap_elements:
            sitemap_elements = root.findall('.//sitemap')
        
        for sitemap_elem in sitemap_elements:
            loc = self._get_element_text(sitemap_elem, 'loc')
            if loc:
                sitemap_urls.append(loc)
        
        return sitemap_urls
    
    def _parse_url_element(self, url_elem: ET.Element, source_url: str | None = None) -> SitemapEntry | None:
        """
        解析单个 URL 元素
        Parse a single URL element
        
        Args:
            url_elem: URL XML 元素
                      URL XML element
            source_url: 来源 URL（用于错误消息）
                        Source URL (for error messages)
        
        Returns:
            SitemapEntry 或 None（如果 loc 缺失）
            SitemapEntry or None (if loc is missing)
        """
        loc = self._get_element_text(url_elem, 'loc')
        if not loc:
            return None
        
        lastmod = self._parse_lastmod(self._get_element_text(url_elem, 'lastmod'))
        changefreq = self._get_element_text(url_elem, 'changefreq')
        priority = self._parse_priority(self._get_element_text(url_elem, 'priority'))
        
        return SitemapEntry(
            loc=loc,
            lastmod=lastmod,
            changefreq=changefreq,
            priority=priority
        )
    
    def _get_element_text(self, parent: ET.Element, tag: str) -> str | None:
        """
        获取子元素的文本内容
        Get text content of a child element
        
        Args:
            parent: 父元素
                    Parent element
            tag: 子元素标签名
                 Child element tag name
        
        Returns:
            文本内容或 None
            Text content or None
        """
        # 尝试带命名空间
        elem = parent.find(f'sm:{tag}', self.SITEMAP_NS)
        if elem is None:
            # 尝试不带命名空间
            elem = parent.find(tag)
        
        if elem is not None and elem.text:
            return elem.text.strip()
        return None
    
    def _parse_lastmod(self, lastmod_str: str | None) -> datetime | None:
        """
        解析 lastmod 日期字符串
        Parse lastmod date string
        
        支持多种日期格式：
        - ISO 8601 完整格式: 2024-01-15T10:30:00+00:00
        - ISO 8601 无时区: 2024-01-15T10:30:00
        - 仅日期: 2024-01-15
        
        Args:
            lastmod_str: lastmod 字符串
                         lastmod string
        
        Returns:
            datetime 对象或 None
            datetime object or None
        """
        if not lastmod_str:
            return None
        
        # 尝试多种日期格式
        formats = [
            '%Y-%m-%dT%H:%M:%S%z',      # ISO 8601 with timezone
            '%Y-%m-%dT%H:%M:%S.%f%z',   # ISO 8601 with microseconds and timezone
            '%Y-%m-%dT%H:%M:%S',        # ISO 8601 without timezone
            '%Y-%m-%dT%H:%M:%S.%f',     # ISO 8601 with microseconds
            '%Y-%m-%d',                  # Date only
        ]
        
        # 处理 Z 时区标记
        lastmod_str = lastmod_str.replace('Z', '+00:00')
        
        for fmt in formats:
            try:
                return datetime.strptime(lastmod_str, fmt)
            except ValueError:
                continue
        
        # 如果所有格式都失败，返回 None（不抛出异常，保持容错性）
        return None
    
    def _parse_priority(self, priority_str: str | None) -> float | None:
        """
        解析 priority 值
        Parse priority value
        
        Args:
            priority_str: priority 字符串
                          priority string
        
        Returns:
            float 值（0.0-1.0）或 None
            float value (0.0-1.0) or None
        """
        if not priority_str:
            return None
        
        try:
            priority = float(priority_str)
            # 确保在有效范围内
            if 0.0 <= priority <= 1.0:
                return priority
            return None
        except ValueError:
            return None


# =============================================================================
# Crawl Rules Engine
# =============================================================================

@dataclass
class CrawlRules:
    """
    抓取规则配置
    Crawl Rules Configuration
    
    定义 URL 抓取的包含/排除模式规则。支持 glob 模式和正则表达式。
    Defines include/exclude pattern rules for URL crawling. Supports both
    glob patterns and regular expressions.
    
    Attributes:
        include_patterns: 包含模式列表，匹配的 URL 将被抓取
                          List of include patterns, matching URLs will be crawled
        exclude_patterns: 排除模式列表，匹配的 URL 将被跳过（优先级高于 include）
                          List of exclude patterns, matching URLs will be skipped
                          (takes precedence over include)
        use_regex: 是否使用正则表达式模式（默认使用 glob 模式）
                   Whether to use regex patterns (default is glob patterns)
    
    Examples:
        >>> # Glob 模式示例
        >>> rules = CrawlRules(
        ...     include_patterns=['/docs/*', '/blog/*'],
        ...     exclude_patterns=['*/archive/*', '*/tag/*'],
        ...     use_regex=False
        ... )
        
        >>> # Regex 模式示例
        >>> rules = CrawlRules(
        ...     include_patterns=[r'/docs/.*', r'/blog/.*'],
        ...     exclude_patterns=[r'.*/archive/.*', r'.*/tag/.*'],
        ...     use_regex=True
        ... )
    """
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    use_regex: bool = False


class CrawlRuleEngine:
    """
    抓取规则引擎
    Crawl Rule Engine
    
    根据配置的规则判断 URL 是否应该被抓取。支持 glob 和 regex 两种模式。
    Determines whether a URL should be crawled based on configured rules.
    Supports both glob and regex patterns.
    
    规则优先级逻辑:
    Rule Priority Logic:
    1. 如果 URL 匹配任何 exclude_patterns，则不抓取（排除优先）
       If URL matches any exclude_patterns, do not crawl (exclude takes precedence)
    2. 如果配置了 include_patterns 且 URL 不匹配任何，则不抓取
       If include_patterns are configured and URL matches none, do not crawl
    3. 如果没有配置 include_patterns，则抓取所有非排除的 URL
       If no include_patterns are configured, crawl all non-excluded URLs
    
    Attributes:
        rules: 抓取规则配置
               Crawl rules configuration
    
    Examples:
        >>> rules = CrawlRules(
        ...     include_patterns=['/docs/*'],
        ...     exclude_patterns=['*/archive/*']
        ... )
        >>> engine = CrawlRuleEngine(rules)
        >>> engine.should_crawl('https://example.com/docs/guide')
        True
        >>> engine.should_crawl('https://example.com/docs/archive/old')
        False
        >>> engine.should_crawl('https://example.com/blog/post')
        False
    
    Raises:
        ConfigurationError: 当模式无效时（无效的 glob 或 regex 语法）
                            When a pattern is invalid (invalid glob or regex syntax)
    """
    
    def __init__(self, rules: CrawlRules):
        """
        初始化 CrawlRuleEngine
        Initialize CrawlRuleEngine
        
        Args:
            rules: 抓取规则配置
                   Crawl rules configuration
        
        Raises:
            ConfigurationError: 当模式无效时
                                When a pattern is invalid
        """
        self.rules = rules
        self._compiled_include: list[re.Pattern] = []
        self._compiled_exclude: list[re.Pattern] = []
        self._compile_patterns()
    
    def should_crawl(self, url: str) -> bool:
        """
        判断 URL 是否应该抓取
        Determine whether a URL should be crawled
        
        根据配置的 include/exclude 规则判断给定 URL 是否应该被抓取。
        Determines whether the given URL should be crawled based on configured
        include/exclude rules.
        
        Args:
            url: 待检查的 URL
                 URL to check
        
        Returns:
            True 如果应该抓取，False 否则
            True if should crawl, False otherwise
        
        Examples:
            >>> rules = CrawlRules(include_patterns=['/docs/*'])
            >>> engine = CrawlRuleEngine(rules)
            >>> engine.should_crawl('https://example.com/docs/guide')
            True
            >>> engine.should_crawl('https://example.com/blog/post')
            False
        """
        # 规则 1: 排除优先 - 如果匹配任何 exclude 模式，不抓取
        # Rule 1: Exclude takes precedence - if matches any exclude pattern, don't crawl
        if self._matches_any(url, self._compiled_exclude):
            return False
        
        # 规则 2: 如果配置了 include 模式，必须匹配至少一个
        # Rule 2: If include patterns are configured, must match at least one
        if self._compiled_include:
            return self._matches_any(url, self._compiled_include)
        
        # 规则 3: 没有配置 include 模式，抓取所有非排除的 URL
        # Rule 3: No include patterns configured, crawl all non-excluded URLs
        return True
    
    def _compile_patterns(self) -> None:
        """
        编译模式为正则表达式
        Compile patterns to regular expressions
        
        将配置的 glob 或 regex 模式编译为 Python 正则表达式对象。
        Compiles configured glob or regex patterns to Python regex objects.
        
        Raises:
            ConfigurationError: 当模式无效时
                                When a pattern is invalid
        """
        pattern_type = "regex" if self.rules.use_regex else "glob"
        
        # 编译 include 模式
        for pattern in self.rules.include_patterns:
            compiled = self._compile_single_pattern(pattern, pattern_type)
            self._compiled_include.append(compiled)
        
        # 编译 exclude 模式
        for pattern in self.rules.exclude_patterns:
            compiled = self._compile_single_pattern(pattern, pattern_type)
            self._compiled_exclude.append(compiled)
    
    def _compile_single_pattern(self, pattern: str, pattern_type: str) -> re.Pattern:
        """
        编译单个模式
        Compile a single pattern
        
        Args:
            pattern: 要编译的模式
                     Pattern to compile
            pattern_type: 模式类型 ('glob' 或 'regex')
                          Pattern type ('glob' or 'regex')
        
        Returns:
            编译后的正则表达式对象
            Compiled regex pattern object
        
        Raises:
            ConfigurationError: 当模式无效时
                                When the pattern is invalid
        """
        try:
            if pattern_type == "regex":
                # 直接编译正则表达式
                return re.compile(pattern)
            else:
                # 将 glob 模式转换为正则表达式
                regex_pattern = self._glob_to_regex(pattern)
                return re.compile(regex_pattern)
        except re.error as e:
            raise ConfigurationError(
                f"Invalid {pattern_type} pattern: {e}",
                pattern=pattern,
                pattern_type=pattern_type
            )
    
    def _glob_to_regex(self, glob_pattern: str) -> str:
        """
        将 glob 模式转换为正则表达式
        Convert glob pattern to regular expression
        
        支持的 glob 语法:
        Supported glob syntax:
        - * : 匹配任意字符（不包括路径分隔符 /）
              Matches any characters (except path separator /)
        - ** : 匹配任意字符（包括路径分隔符 /）
               Matches any characters (including path separator /)
        - ? : 匹配单个字符
              Matches a single character
        - [seq] : 匹配 seq 中的任意字符
                  Matches any character in seq
        - [!seq] : 匹配不在 seq 中的任意字符
                   Matches any character not in seq
        
        Args:
            glob_pattern: glob 模式字符串
                          Glob pattern string
        
        Returns:
            对应的正则表达式字符串
            Corresponding regex pattern string
        
        Examples:
            >>> engine = CrawlRuleEngine(CrawlRules())
            >>> engine._glob_to_regex('/docs/*')
            '/docs/[^/]*'
            >>> engine._glob_to_regex('/docs/**')
            '/docs/.*'
        """
        # 使用 fnmatch.translate 作为基础，但需要处理 ** 模式
        # Use fnmatch.translate as base, but need to handle ** pattern
        
        # 首先处理 ** 模式（匹配包括 / 的任意字符）
        # First handle ** pattern (matches any characters including /)
        # 临时替换 ** 为占位符，避免被 fnmatch 处理
        placeholder = '\x00DOUBLESTAR\x00'
        pattern_with_placeholder = glob_pattern.replace('**', placeholder)
        
        # 使用 fnmatch.translate 转换基本 glob 模式
        # Use fnmatch.translate to convert basic glob pattern
        regex = fnmatch.translate(pattern_with_placeholder)
        
        # fnmatch.translate 会在末尾添加 \Z，我们需要移除它以支持部分匹配
        # fnmatch.translate adds \Z at the end, we need to remove it for partial matching
        if regex.endswith(r'\Z'):
            regex = regex[:-2]
        
        # 将占位符替换回 .* (匹配任意字符包括 /)
        # Replace placeholder back to .* (matches any characters including /)
        regex = regex.replace(placeholder.replace('\\', '\\\\'), '.*')
        regex = regex.replace(placeholder, '.*')
        
        # fnmatch 将 * 转换为 .* 但我们希望 * 不匹配 /
        # fnmatch converts * to .* but we want * to not match /
        # 由于我们已经处理了 **，现在需要将剩余的 .* 替换为 [^/]*
        # Since we've handled **, now we need to replace remaining .* with [^/]*
        # 但这比较复杂，因为 fnmatch 的输出可能有其他 .* 模式
        # This is complex because fnmatch output may have other .* patterns
        
        # 更简单的方法：手动转换 glob 模式
        # Simpler approach: manually convert glob pattern
        return self._manual_glob_to_regex(glob_pattern)
    
    def _manual_glob_to_regex(self, glob_pattern: str) -> str:
        """
        手动将 glob 模式转换为正则表达式
        Manually convert glob pattern to regular expression
        
        Args:
            glob_pattern: glob 模式字符串
                          Glob pattern string
        
        Returns:
            对应的正则表达式字符串
            Corresponding regex pattern string
        """
        result = []
        i = 0
        n = len(glob_pattern)
        
        while i < n:
            c = glob_pattern[i]
            
            if c == '*':
                # 检查是否是 **
                if i + 1 < n and glob_pattern[i + 1] == '*':
                    # ** 匹配任意字符（包括 /）
                    result.append('.*')
                    i += 2
                else:
                    # * 匹配任意字符（不包括 /）
                    result.append('[^/]*')
                    i += 1
            elif c == '?':
                # ? 匹配单个字符（不包括 /）
                result.append('[^/]')
                i += 1
            elif c == '[':
                # 字符类 [seq] 或 [!seq]
                j = i + 1
                if j < n and glob_pattern[j] == '!':
                    result.append('[^')
                    j += 1
                else:
                    result.append('[')
                
                # 找到匹配的 ]
                while j < n and glob_pattern[j] != ']':
                    if glob_pattern[j] == '\\' and j + 1 < n:
                        result.append(re.escape(glob_pattern[j + 1]))
                        j += 2
                    else:
                        result.append(re.escape(glob_pattern[j]))
                        j += 1
                
                result.append(']')
                i = j + 1
            elif c in r'\^$.|+(){}':
                # 转义正则表达式特殊字符
                result.append('\\' + c)
                i += 1
            else:
                result.append(c)
                i += 1
        
        return ''.join(result)
    
    def _matches_any(self, url: str, patterns: list[re.Pattern]) -> bool:
        """
        检查 URL 是否匹配任何模式
        Check if URL matches any pattern
        
        Args:
            url: 要检查的 URL
                 URL to check
            patterns: 编译后的正则表达式模式列表
                      List of compiled regex patterns
        
        Returns:
            True 如果匹配任何模式，False 否则
            True if matches any pattern, False otherwise
        """
        for pattern in patterns:
            if pattern.search(url):
                return True
        return False


# =============================================================================
# Incremental Crawler
# =============================================================================

import hashlib
import json
from abc import ABC, abstractmethod
from pathlib import Path


@dataclass
class CrawlState:
    """
    爬取状态
    Crawl State
    
    记录单个 URL 的爬取状态，包括最后爬取时间和内容哈希。
    Records the crawl state of a single URL, including last crawl time and content hash.
    
    Attributes:
        url: 页面 URL
             Page URL
        last_crawl: 最后爬取时间（可选）
                    Last crawl time (optional)
        content_hash: 内容哈希值（可选），用于变更检测
                      Content hash (optional), used for change detection
    
    Examples:
        >>> state = CrawlState(
        ...     url='https://example.com/page1',
        ...     last_crawl=datetime(2024, 1, 15, 10, 30, 0),
        ...     content_hash='abc123def456'
        ... )
    """
    url: str
    last_crawl: datetime | None = None
    content_hash: str | None = None


@dataclass
class CrawlStats:
    """
    爬取统计
    Crawl Statistics
    
    记录一次爬取操作的统计信息。
    Records statistics for a crawl operation.
    
    Attributes:
        new_pages: 新页面数量（首次爬取）
                   Number of new pages (first crawl)
        updated_pages: 更新页面数量（内容已变更）
                       Number of updated pages (content changed)
        skipped_pages: 跳过页面数量（无变更）
                       Number of skipped pages (no changes)
        failed_pages: 失败页面数量（爬取出错）
                      Number of failed pages (crawl errors)
    
    Properties:
        total_pages: 总处理页面数
                     Total pages processed
    
    Examples:
        >>> stats = CrawlStats(new_pages=5, updated_pages=3, skipped_pages=10, failed_pages=2)
        >>> stats.total_pages
        20
    """
    new_pages: int = 0
    updated_pages: int = 0
    skipped_pages: int = 0
    failed_pages: int = 0
    
    @property
    def total_pages(self) -> int:
        """
        获取总处理页面数
        Get total pages processed
        
        Returns:
            new_pages + updated_pages + skipped_pages + failed_pages
        """
        return self.new_pages + self.updated_pages + self.skipped_pages + self.failed_pages


@dataclass
class CrawledPage:
    """
    爬取的页面
    Crawled Page
    
    表示成功爬取的页面内容。
    Represents a successfully crawled page content.
    
    Attributes:
        url: 页面 URL
             Page URL
        content: 页面内容
                 Page content
        content_hash: 内容哈希值
                      Content hash
        is_new: 是否为新页面
                Whether this is a new page
        is_updated: 是否为更新的页面
                    Whether this page was updated
    """
    url: str
    content: str
    content_hash: str
    is_new: bool = False
    is_updated: bool = False


class CrawlStateStore(ABC):
    """
    爬取状态存储抽象基类
    Crawl State Store Abstract Base Class
    
    定义爬取状态持久化的接口。
    Defines the interface for crawl state persistence.
    """
    
    @abstractmethod
    def get_state(self, url: str) -> CrawlState | None:
        """
        获取 URL 的爬取状态
        Get crawl state for a URL
        
        Args:
            url: 页面 URL
                 Page URL
        
        Returns:
            CrawlState 或 None（如果不存在）
            CrawlState or None (if not exists)
        """
        pass
    
    @abstractmethod
    def save_state(self, state: CrawlState) -> None:
        """
        保存爬取状态
        Save crawl state
        
        Args:
            state: 要保存的爬取状态
                   Crawl state to save
        """
        pass
    
    @abstractmethod
    def get_all_states(self) -> dict[str, CrawlState]:
        """
        获取所有爬取状态
        Get all crawl states
        
        Returns:
            URL 到 CrawlState 的映射
            Mapping from URL to CrawlState
        """
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """
        清除所有状态
        Clear all states
        """
        pass


class InMemoryCrawlStateStore(CrawlStateStore):
    """
    内存爬取状态存储
    In-Memory Crawl State Store
    
    将爬取状态存储在内存中，适用于测试和临时使用。
    Stores crawl state in memory, suitable for testing and temporary use.
    
    Examples:
        >>> store = InMemoryCrawlStateStore()
        >>> store.save_state(CrawlState(url='https://example.com', last_crawl=datetime.now()))
        >>> state = store.get_state('https://example.com')
    """
    
    def __init__(self):
        self._states: dict[str, CrawlState] = {}
    
    def get_state(self, url: str) -> CrawlState | None:
        return self._states.get(url)
    
    def save_state(self, state: CrawlState) -> None:
        self._states[state.url] = state
    
    def get_all_states(self) -> dict[str, CrawlState]:
        return self._states.copy()
    
    def clear(self) -> None:
        self._states.clear()


class JsonFileCrawlStateStore(CrawlStateStore):
    """
    JSON 文件爬取状态存储
    JSON File Crawl State Store
    
    将爬取状态持久化到 JSON 文件。
    Persists crawl state to a JSON file.
    
    Attributes:
        file_path: JSON 文件路径
                   JSON file path
    
    Examples:
        >>> store = JsonFileCrawlStateStore('data/crawl_state.json')
        >>> store.save_state(CrawlState(url='https://example.com', last_crawl=datetime.now()))
    """
    
    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        self._states: dict[str, CrawlState] = {}
        self._load()
    
    def _load(self) -> None:
        """从文件加载状态"""
        if self.file_path.exists():
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for url, state_data in data.items():
                        last_crawl = None
                        if state_data.get('last_crawl'):
                            last_crawl = datetime.fromisoformat(state_data['last_crawl'])
                        self._states[url] = CrawlState(
                            url=url,
                            last_crawl=last_crawl,
                            content_hash=state_data.get('content_hash')
                        )
            except (json.JSONDecodeError, KeyError, ValueError):
                # 文件损坏或格式错误，使用空状态
                self._states = {}
    
    def _save(self) -> None:
        """保存状态到文件"""
        # 确保目录存在
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {}
        for url, state in self._states.items():
            data[url] = {
                'last_crawl': state.last_crawl.isoformat() if state.last_crawl else None,
                'content_hash': state.content_hash
            }
        
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def get_state(self, url: str) -> CrawlState | None:
        return self._states.get(url)
    
    def save_state(self, state: CrawlState) -> None:
        self._states[state.url] = state
        self._save()
    
    def get_all_states(self) -> dict[str, CrawlState]:
        return self._states.copy()
    
    def clear(self) -> None:
        self._states.clear()
        if self.file_path.exists():
            self.file_path.unlink()


class IncrementalCrawler:
    """
    增量爬虫
    Incremental Crawler
    
    根据 lastmod 时间戳和内容哈希实现增量爬取，只爬取新增或变更的页面。
    Implements incremental crawling based on lastmod timestamps and content hashes,
    only crawling new or changed pages.
    
    增量爬取逻辑:
    Incremental Crawl Logic:
    1. 如果 force_refresh=True，爬取所有页面
       If force_refresh=True, crawl all pages
    2. 如果页面从未被爬取过（无状态），爬取该页面
       If page has never been crawled (no state), crawl it
    3. 如果 sitemap 条目有 lastmod：
       If sitemap entry has lastmod:
       - 如果 lastmod > last_crawl，爬取该页面
         If lastmod > last_crawl, crawl the page
       - 否则跳过
         Otherwise skip
    4. 如果 sitemap 条目没有 lastmod：
       If sitemap entry has no lastmod:
       - 获取页面内容并计算哈希
         Fetch page content and calculate hash
       - 如果哈希与存储的哈希不同，标记为更新
         If hash differs from stored hash, mark as updated
       - 否则跳过
         Otherwise skip
    
    Attributes:
        state_store: 爬取状态存储
                     Crawl state store
        fetcher: 页面内容获取器（可选，用于实际爬取）
                 Page content fetcher (optional, for actual crawling)
    
    Examples:
        >>> store = InMemoryCrawlStateStore()
        >>> crawler = IncrementalCrawler(store)
        >>> entries = [SitemapEntry(loc='https://example.com/page1')]
        >>> pages, stats = crawler.crawl(entries)
    """
    
    def __init__(
        self,
        state_store: CrawlStateStore,
        fetcher: Optional['PageFetcher'] = None
    ):
        """
        初始化增量爬虫
        Initialize Incremental Crawler
        
        Args:
            state_store: 爬取状态存储
                         Crawl state store
            fetcher: 页面内容获取器（可选）
                     Page content fetcher (optional)
        """
        self.state_store = state_store
        self.fetcher = fetcher
    
    def crawl(
        self,
        entries: list[SitemapEntry],
        force_refresh: bool = False
    ) -> tuple[list[CrawledPage], CrawlStats]:
        """
        执行增量爬取
        Execute Incremental Crawl
        
        根据配置的增量逻辑爬取 sitemap 条目列表。
        Crawls the list of sitemap entries based on configured incremental logic.
        
        Args:
            entries: Sitemap 条目列表
                     List of sitemap entries
            force_refresh: 是否强制刷新所有页面（忽略增量逻辑）
                           Whether to force refresh all pages (ignore incremental logic)
        
        Returns:
            (爬取的页面列表, 统计信息)
            (List of crawled pages, statistics)
        
        Examples:
            >>> crawler = IncrementalCrawler(InMemoryCrawlStateStore())
            >>> entries = [SitemapEntry(loc='https://example.com/page1')]
            >>> pages, stats = crawler.crawl(entries)
            >>> stats.total_pages == len(entries)
            True
        """
        stats = CrawlStats()
        crawled_pages: list[CrawledPage] = []
        
        for entry in entries:
            try:
                state = self.state_store.get_state(entry.loc)
                
                # 判断是否需要爬取
                should_crawl, reason = self._should_crawl(entry, state, force_refresh)
                
                if not should_crawl:
                    stats.skipped_pages += 1
                    continue
                
                # 执行爬取
                page = self._fetch_page(entry, state, reason)
                
                if page is None:
                    stats.failed_pages += 1
                    continue
                
                crawled_pages.append(page)
                
                # 更新统计
                if page.is_new:
                    stats.new_pages += 1
                elif page.is_updated:
                    stats.updated_pages += 1
                
                # 更新状态
                new_state = CrawlState(
                    url=entry.loc,
                    last_crawl=datetime.now(),
                    content_hash=page.content_hash
                )
                self.state_store.save_state(new_state)
                
            except Exception:
                stats.failed_pages += 1
        
        return crawled_pages, stats
    
    def _should_crawl(
        self,
        entry: SitemapEntry,
        state: CrawlState | None,
        force_refresh: bool
    ) -> tuple[bool, str]:
        """
        判断是否需要爬取
        Determine Whether to Crawl
        
        根据增量逻辑判断是否需要爬取该页面。
        Determines whether to crawl the page based on incremental logic.
        
        Args:
            entry: Sitemap 条目
                   Sitemap entry
            state: 当前爬取状态（可能为 None）
                   Current crawl state (may be None)
            force_refresh: 是否强制刷新
                           Whether to force refresh
        
        Returns:
            (是否需要爬取, 原因)
            (Whether to crawl, reason)
        """
        # 规则 1: force_refresh=True 时爬取所有页面
        if force_refresh:
            return True, 'force_refresh'
        
        # 规则 2: 从未爬取过的页面
        if state is None:
            return True, 'new_page'
        
        # 规则 3: 有 lastmod 时基于时间戳判断
        if entry.lastmod is not None:
            if state.last_crawl is None:
                return True, 'no_last_crawl'
            
            # 比较时间戳（需要处理时区）
            entry_lastmod = entry.lastmod
            last_crawl = state.last_crawl
            
            # 如果 lastmod 有时区信息而 last_crawl 没有，或反之，需要统一处理
            # 简化处理：移除时区信息进行比较
            if hasattr(entry_lastmod, 'tzinfo') and entry_lastmod.tzinfo is not None:
                entry_lastmod = entry_lastmod.replace(tzinfo=None)
            if hasattr(last_crawl, 'tzinfo') and last_crawl.tzinfo is not None:
                last_crawl = last_crawl.replace(tzinfo=None)
            
            if entry_lastmod > last_crawl:
                return True, 'lastmod_newer'
            else:
                return False, 'lastmod_not_newer'
        
        # 规则 4: 没有 lastmod 时需要通过内容哈希判断
        # 这种情况下需要先获取内容才能判断，所以返回 True 并标记需要哈希检查
        return True, 'check_hash'
    
    def _fetch_page(
        self,
        entry: SitemapEntry,
        state: CrawlState | None,
        reason: str
    ) -> CrawledPage | None:
        """
        获取页面内容
        Fetch Page Content
        
        获取页面内容并创建 CrawledPage 对象。
        Fetches page content and creates a CrawledPage object.
        
        Args:
            entry: Sitemap 条目
                   Sitemap entry
            state: 当前爬取状态
                   Current crawl state
            reason: 爬取原因
                    Crawl reason
        
        Returns:
            CrawledPage 或 None（如果获取失败或内容未变更）
            CrawledPage or None (if fetch failed or content unchanged)
        """
        # 如果没有 fetcher，创建模拟内容（用于测试）
        if self.fetcher is None:
            content = f"Mock content for {entry.loc}"
        else:
            try:
                content = self.fetcher.fetch(entry.loc)
            except Exception:
                return None
        
        # 计算内容哈希
        content_hash = self._compute_hash(content)
        
        # 如果是哈希检查模式，需要比较哈希
        if reason == 'check_hash' and state is not None:
            if state.content_hash == content_hash:
                # 内容未变更，不需要爬取
                return None
        
        # 确定页面状态
        is_new = state is None or reason == 'new_page'
        is_updated = not is_new and (
            reason in ('lastmod_newer', 'check_hash', 'force_refresh', 'no_last_crawl')
        )
        
        return CrawledPage(
            url=entry.loc,
            content=content,
            content_hash=content_hash,
            is_new=is_new,
            is_updated=is_updated
        )
    
    @staticmethod
    def _compute_hash(content: str) -> str:
        """
        计算内容哈希
        Compute Content Hash
        
        使用 SHA-256 计算内容的哈希值。
        Computes the SHA-256 hash of the content.
        
        Args:
            content: 页面内容
                     Page content
        
        Returns:
            哈希值（十六进制字符串）
            Hash value (hexadecimal string)
        """
        return hashlib.sha256(content.encode('utf-8')).hexdigest()


class PageFetcher(ABC):
    """
    页面获取器抽象基类
    Page Fetcher Abstract Base Class
    
    定义页面内容获取的接口。
    Defines the interface for fetching page content.
    """
    
    @abstractmethod
    def fetch(self, url: str) -> str:
        """
        获取页面内容
        Fetch Page Content
        
        Args:
            url: 页面 URL
                 Page URL
        
        Returns:
            页面内容
            Page content
        
        Raises:
            Exception: 获取失败时
                       When fetch fails
        """
        pass


class HttpPageFetcher(PageFetcher):
    """
    HTTP 页面获取器
    HTTP Page Fetcher
    
    通过 HTTP 请求获取页面内容。
    Fetches page content via HTTP requests.
    
    Attributes:
        timeout: 请求超时时间（秒）
                 Request timeout in seconds
        user_agent: User-Agent 头
                    User-Agent header
    """
    
    def __init__(self, timeout: int = 30, user_agent: str | None = None):
        self.timeout = timeout
        self.user_agent = user_agent or 'PandaWiki-Crawler/1.0'
        self._session = requests.Session()
        self._session.headers.update({'User-Agent': self.user_agent})
    
    def fetch(self, url: str) -> str:
        """
        获取页面内容
        Fetch Page Content
        
        Args:
            url: 页面 URL
                 Page URL
        
        Returns:
            页面 HTML 内容
            Page HTML content
        
        Raises:
            requests.RequestException: 请求失败时
                                       When request fails
        """
        response = self._session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.text


# =============================================================================
# HTML to Markdown Converter
# =============================================================================

from bs4 import BeautifulSoup, NavigableString, Tag


class HTMLToMarkdownConverter:
    """
    HTML 转 Markdown 转换器
    HTML to Markdown Converter
    
    将 HTML 内容转换为 Markdown 格式，保留文档结构（标题、列表、表格、代码块、链接），
    同时移除不需要的元素（script, style, nav, footer, header）。
    
    Converts HTML content to Markdown format, preserving document structure
    (headings, lists, tables, code blocks, links) while removing unwanted
    elements (script, style, nav, footer, header).
    
    Attributes:
        remove_tags: 要移除的 HTML 标签列表
                     List of HTML tags to remove
    
    Examples:
        >>> converter = HTMLToMarkdownConverter()
        >>> html = '<h1>Title</h1><p>Hello <strong>World</strong></p>'
        >>> markdown = converter.convert(html)
        >>> print(markdown)
        # Title
        
        Hello **World**
    
    Requirements:
        - 7.1: WHEN importing HTML content, THE Sitemap_Importer SHALL convert it to Markdown format
        - 7.2: THE Sitemap_Importer SHALL preserve document structure including headings, lists, tables, and code blocks
        - 7.3: THE Sitemap_Importer SHALL extract and preserve hyperlinks with their URLs
        - 7.4: THE Sitemap_Importer SHALL remove script, style, and navigation elements from conversion
        - 7.5: THE Sitemap_Importer SHALL handle malformed HTML gracefully without crashing
    """
    
    # 默认要移除的标签
    DEFAULT_REMOVE_TAGS = ['script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript']
    
    def __init__(self, remove_tags: list[str] | None = None):
        """
        初始化 HTMLToMarkdownConverter
        Initialize HTMLToMarkdownConverter
        
        Args:
            remove_tags: 要移除的 HTML 标签列表（可选，默认移除 script, style, nav, footer, header, aside, noscript）
                         List of HTML tags to remove (optional, defaults to script, style, nav, footer, header, aside, noscript)
        """
        self.remove_tags = remove_tags if remove_tags is not None else self.DEFAULT_REMOVE_TAGS.copy()
    
    def convert(self, html: str) -> str:
        """
        将 HTML 转换为 Markdown
        Convert HTML to Markdown
        
        Args:
            html: HTML 内容
                  HTML content
        
        Returns:
            Markdown 格式的文本
            Markdown formatted text
        
        Examples:
            >>> converter = HTMLToMarkdownConverter()
            >>> converter.convert('<h1>Hello</h1>')
            '# Hello'
        """
        if not html or not html.strip():
            return ''
        
        try:
            # 解析 HTML
            soup = BeautifulSoup(html, 'lxml')
            
            # 清理 HTML - 移除不需要的标签
            self._clean_html(soup)
            
            # 获取 body 内容，如果没有 body 则使用整个文档
            body = soup.body if soup.body else soup
            
            # 转换为 Markdown
            markdown = self._convert_element(body)
            
            # 清理多余的空白行
            markdown = self._clean_whitespace(markdown)
            
            return markdown.strip()
            
        except Exception:
            # 处理格式错误的 HTML - 返回纯文本
            # Handle malformed HTML - return plain text
            try:
                soup = BeautifulSoup(html, 'html.parser')
                return soup.get_text(separator='\n', strip=True)
            except Exception:
                return html
    
    def _clean_html(self, soup: BeautifulSoup) -> None:
        """
        清理 HTML，移除不需要的标签
        Clean HTML by removing unwanted tags
        
        Args:
            soup: BeautifulSoup 对象
                  BeautifulSoup object
        """
        for tag_name in self.remove_tags:
            for tag in soup.find_all(tag_name):
                tag.decompose()
        
        # 移除注释
        from bs4 import Comment
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
    
    def _convert_element(self, element: Tag | NavigableString) -> str:
        """
        递归转换 HTML 元素为 Markdown
        Recursively convert HTML element to Markdown
        
        Args:
            element: HTML 元素
                     HTML element
        
        Returns:
            Markdown 文本
            Markdown text
        """
        if isinstance(element, NavigableString):
            text = str(element)
            # 保留有意义的空白，但不保留纯空白节点
            if text.strip():
                return text
            elif text:
                return ' '
            return ''
        
        if not isinstance(element, Tag):
            return ''
        
        tag_name = element.name.lower() if element.name else ''
        
        # 根据标签类型进行转换
        if tag_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            return self._convert_heading(element)
        elif tag_name == 'p':
            return self._convert_paragraph(element)
        elif tag_name in ['strong', 'b']:
            return self._convert_bold(element)
        elif tag_name in ['em', 'i']:
            return self._convert_italic(element)
        elif tag_name == 'a':
            return self._convert_link(element)
        elif tag_name == 'img':
            return self._convert_image(element)
        elif tag_name in ['ul', 'ol']:
            return self._convert_list(element)
        elif tag_name == 'li':
            return self._convert_list_item(element)
        elif tag_name == 'blockquote':
            return self._convert_blockquote(element)
        elif tag_name in ['pre', 'code']:
            return self._convert_code(element)
        elif tag_name == 'table':
            return self._convert_table(element)
        elif tag_name == 'br':
            return '\n'
        elif tag_name == 'hr':
            return '\n---\n'
        elif tag_name in ['div', 'section', 'article', 'main']:
            return self._convert_container(element)
        elif tag_name == 'span':
            return self._convert_children(element)
        else:
            # 默认：递归处理子元素
            return self._convert_children(element)
    
    def _convert_children(self, element: Tag) -> str:
        """
        转换元素的所有子元素
        Convert all children of an element
        
        Args:
            element: 父元素
                     Parent element
        
        Returns:
            子元素的 Markdown 文本
            Markdown text of children
        """
        result = []
        for child in element.children:
            result.append(self._convert_element(child))
        return ''.join(result)
    
    def _convert_heading(self, element: Tag) -> str:
        """
        转换标题标签
        Convert heading tags
        
        Args:
            element: 标题元素 (h1-h6)
                     Heading element (h1-h6)
        
        Returns:
            Markdown 标题
            Markdown heading
        """
        level = int(element.name[1])  # h1 -> 1, h2 -> 2, etc.
        text = self._convert_children(element).strip()
        if text:
            return f"\n{'#' * level} {text}\n"
        return ''
    
    def _convert_paragraph(self, element: Tag) -> str:
        """
        转换段落标签
        Convert paragraph tags
        
        Args:
            element: 段落元素
                     Paragraph element
        
        Returns:
            Markdown 段落
            Markdown paragraph
        """
        text = self._convert_children(element).strip()
        if text:
            return f"\n{text}\n"
        return ''
    
    def _convert_bold(self, element: Tag) -> str:
        """
        转换粗体标签
        Convert bold tags
        
        Args:
            element: 粗体元素 (strong, b)
                     Bold element (strong, b)
        
        Returns:
            Markdown 粗体
            Markdown bold
        """
        text = self._convert_children(element).strip()
        if text:
            return f"**{text}**"
        return ''
    
    def _convert_italic(self, element: Tag) -> str:
        """
        转换斜体标签
        Convert italic tags
        
        Args:
            element: 斜体元素 (em, i)
                     Italic element (em, i)
        
        Returns:
            Markdown 斜体
            Markdown italic
        """
        text = self._convert_children(element).strip()
        if text:
            return f"*{text}*"
        return ''
    
    def _convert_link(self, element: Tag) -> str:
        """
        转换链接标签
        Convert link tags
        
        Args:
            element: 链接元素 (a)
                     Link element (a)
        
        Returns:
            Markdown 链接
            Markdown link
        """
        href = element.get('href', '')
        text = self._convert_children(element).strip()
        
        if not text:
            text = href
        
        if href:
            return f"[{text}]({href})"
        return text
    
    def _convert_image(self, element: Tag) -> str:
        """
        转换图片标签
        Convert image tags
        
        Args:
            element: 图片元素 (img)
                     Image element (img)
        
        Returns:
            Markdown 图片
            Markdown image
        """
        src = element.get('src', '')
        alt = element.get('alt', '')
        
        if src:
            return f"![{alt}]({src})"
        return ''
    
    def _convert_list(self, element: Tag, level: int = 0) -> str:
        """
        转换列表标签
        Convert list tags
        
        Args:
            element: 列表元素 (ul, ol)
                     List element (ul, ol)
            level: 嵌套层级
                   Nesting level
        
        Returns:
            Markdown 列表
            Markdown list
        """
        is_ordered = element.name.lower() == 'ol'
        items = []
        item_num = 1
        
        for child in element.children:
            if isinstance(child, Tag) and child.name.lower() == 'li':
                indent = '  ' * level
                
                # 处理列表项内容
                item_content = []
                nested_list = None
                
                for li_child in child.children:
                    if isinstance(li_child, Tag) and li_child.name.lower() in ['ul', 'ol']:
                        nested_list = li_child
                    else:
                        item_content.append(self._convert_element(li_child))
                
                text = ''.join(item_content).strip()
                
                if is_ordered:
                    prefix = f"{item_num}."
                    item_num += 1
                else:
                    prefix = "-"
                
                if text:
                    items.append(f"{indent}{prefix} {text}")
                
                # 处理嵌套列表
                if nested_list:
                    nested_md = self._convert_list(nested_list, level + 1)
                    if nested_md:
                        items.append(nested_md)
        
        result = '\n'.join(items)
        if result and level == 0:
            return f"\n{result}\n"
        return result
    
    def _convert_list_item(self, element: Tag) -> str:
        """
        转换列表项标签（单独出现时）
        Convert list item tags (when appearing alone)
        
        Args:
            element: 列表项元素 (li)
                     List item element (li)
        
        Returns:
            Markdown 列表项
            Markdown list item
        """
        text = self._convert_children(element).strip()
        if text:
            return f"- {text}"
        return ''
    
    def _convert_blockquote(self, element: Tag) -> str:
        """
        转换引用块标签
        Convert blockquote tags
        
        Args:
            element: 引用块元素 (blockquote)
                     Blockquote element (blockquote)
        
        Returns:
            Markdown 引用块
            Markdown blockquote
        """
        content = self._convert_children(element).strip()
        if content:
            # 为每行添加 > 前缀
            lines = content.split('\n')
            quoted_lines = [f"> {line}" if line.strip() else ">" for line in lines]
            return f"\n{chr(10).join(quoted_lines)}\n"
        return ''
    
    def _convert_code(self, element: Tag) -> str:
        """
        转换代码标签
        Convert code tags
        
        Args:
            element: 代码元素 (pre, code)
                     Code element (pre, code)
        
        Returns:
            Markdown 代码
            Markdown code
        """
        # 检查是否是代码块（pre 标签或 pre > code）
        is_block = element.name.lower() == 'pre'
        
        if is_block:
            # 获取代码内容
            code_elem = element.find('code')
            if code_elem:
                code_text = code_elem.get_text()
                # 尝试获取语言
                lang = ''
                classes = code_elem.get('class', [])
                for cls in classes:
                    if cls.startswith('language-'):
                        lang = cls[9:]
                        break
                    elif cls.startswith('lang-'):
                        lang = cls[5:]
                        break
            else:
                code_text = element.get_text()
                lang = ''
            
            return f"\n```{lang}\n{code_text.strip()}\n```\n"
        else:
            # 行内代码
            code_text = element.get_text()
            if code_text:
                return f"`{code_text}`"
            return ''
    
    def _convert_table(self, element: Tag) -> str:
        """
        转换表格标签
        Convert table tags
        
        Args:
            element: 表格元素 (table)
                     Table element (table)
        
        Returns:
            Markdown 表格
            Markdown table
        """
        rows = []
        header_row = None
        
        # 查找表头
        thead = element.find('thead')
        if thead:
            header_tr = thead.find('tr')
            if header_tr:
                header_cells = []
                for th in header_tr.find_all(['th', 'td']):
                    header_cells.append(self._convert_children(th).strip())
                if header_cells:
                    header_row = header_cells
        
        # 查找表体
        tbody = element.find('tbody')
        body_rows = tbody.find_all('tr') if tbody else element.find_all('tr')
        
        for tr in body_rows:
            # 跳过已处理的表头行
            if thead and tr.parent == thead:
                continue
            
            cells = []
            cell_tags = tr.find_all(['td', 'th'])
            
            # 如果第一行是 th 且没有 thead，作为表头
            if not header_row and cell_tags and cell_tags[0].name == 'th':
                for cell in cell_tags:
                    cells.append(self._convert_children(cell).strip())
                header_row = cells
                continue
            
            for cell in cell_tags:
                cells.append(self._convert_children(cell).strip())
            
            if cells:
                rows.append(cells)
        
        if not header_row and not rows:
            return ''
        
        # 如果没有表头但有数据行，使用第一行作为表头
        if not header_row and rows:
            header_row = rows.pop(0)
        
        # 构建 Markdown 表格
        result = []
        
        if header_row:
            result.append('| ' + ' | '.join(header_row) + ' |')
            result.append('| ' + ' | '.join(['---'] * len(header_row)) + ' |')
        
        for row in rows:
            # 确保行的列数与表头一致
            while len(row) < len(header_row):
                row.append('')
            result.append('| ' + ' | '.join(row[:len(header_row)]) + ' |')
        
        if result:
            return '\n' + '\n'.join(result) + '\n'
        return ''
    
    def _convert_container(self, element: Tag) -> str:
        """
        转换容器标签
        Convert container tags
        
        Args:
            element: 容器元素 (div, section, article, main)
                     Container element (div, section, article, main)
        
        Returns:
            子元素的 Markdown 文本
            Markdown text of children
        """
        content = self._convert_children(element)
        if content.strip():
            return f"\n{content}\n"
        return ''
    
    def _clean_whitespace(self, text: str) -> str:
        """
        清理多余的空白行
        Clean excessive whitespace
        
        Args:
            text: 原始文本
                  Original text
        
        Returns:
            清理后的文本
            Cleaned text
        """
        # 将多个连续空行替换为两个空行
        import re
        text = re.sub(r'\n{3,}', '\n\n', text)
        # 移除行首行尾的空格
        lines = [line.rstrip() for line in text.split('\n')]
        return '\n'.join(lines)


# =============================================================================
# Sitemap Importer - Main Integration Class
# =============================================================================

@dataclass
class SitemapImporterConfig:
    """
    Sitemap 导入器配置
    Sitemap Importer Configuration
    
    整合所有 Sitemap 导入相关的配置选项。
    Consolidates all Sitemap import related configuration options.
    
    Attributes:
        sitemap_url: Sitemap URL（必需）
                     Sitemap URL (required)
        include_patterns: 包含模式列表
                          List of include patterns
        exclude_patterns: 排除模式列表
                          List of exclude patterns
        use_regex: 是否使用正则表达式模式
                   Whether to use regex patterns
        timeout: HTTP 请求超时时间（秒）
                 HTTP request timeout in seconds
        user_agent: 自定义 User-Agent
                    Custom User-Agent
        max_concurrent: 最大并发请求数
                        Maximum concurrent requests
        delay_between_requests: 请求间延迟（秒）
                                Delay between requests in seconds
        force_refresh: 强制刷新所有页面
                       Force refresh all pages
        state_file: 爬取状态文件路径
                    Crawl state file path
        source_type: 来源类型标识
                     Source type identifier
        category: 默认分类
                  Default category
    
    Examples:
        >>> config = SitemapImporterConfig(
        ...     sitemap_url='https://example.com/sitemap.xml',
        ...     include_patterns=['/docs/*', '/blog/*'],
        ...     exclude_patterns=['*/archive/*'],
        ...     timeout=30,
        ...     max_concurrent=5
        ... )
    """
    sitemap_url: str
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    use_regex: bool = False
    timeout: int = 30
    user_agent: str = 'PandaWiki-SitemapImporter/1.0'
    max_concurrent: int = 5
    delay_between_requests: float = 0.5
    force_refresh: bool = False
    state_file: str | None = None
    source_type: str = 'sitemap'
    category: str = ''


@dataclass
class ImportResult:
    """
    导入结果
    Import Result
    
    记录 Sitemap 导入操作的结果统计。
    Records statistics of a Sitemap import operation.
    
    Attributes:
        total_urls: 总 URL 数量
                    Total number of URLs
        filtered_urls: 过滤后的 URL 数量
                       Number of URLs after filtering
        crawled_urls: 成功爬取的 URL 数量
                      Number of successfully crawled URLs
        skipped_urls: 跳过的 URL 数量（未变更）
                      Number of skipped URLs (unchanged)
        failed_urls: 失败的 URL 数量
                     Number of failed URLs
        articles_added: 添加到知识库的文章数量
                        Number of articles added to knowledge base
        errors: 错误列表
                List of errors
        duration_seconds: 导入耗时（秒）
                          Import duration in seconds
    
    Examples:
        >>> result = ImportResult(
        ...     total_urls=100,
        ...     filtered_urls=80,
        ...     crawled_urls=75,
        ...     skipped_urls=20,
        ...     failed_urls=5,
        ...     articles_added=75
        ... )
        >>> result.success_rate
        0.9375
    """
    total_urls: int = 0
    filtered_urls: int = 0
    crawled_urls: int = 0
    skipped_urls: int = 0
    failed_urls: int = 0
    articles_added: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    
    @property
    def success_rate(self) -> float:
        """
        计算成功率
        Calculate success rate
        
        Returns:
            成功率（0.0-1.0）
            Success rate (0.0-1.0)
        """
        if self.filtered_urls == 0:
            return 0.0
        return self.crawled_urls / self.filtered_urls


class SitemapImporter:
    """
    Sitemap 导入器
    Sitemap Importer
    
    整合 SitemapParser、CrawlRuleEngine、IncrementalCrawler 和 HTMLToMarkdownConverter，
    提供完整的 Sitemap 导入功能。
    
    Integrates SitemapParser, CrawlRuleEngine, IncrementalCrawler, and HTMLToMarkdownConverter
    to provide complete Sitemap import functionality.
    
    主要功能:
    Main Features:
    1. 解析 Sitemap XML（支持 index 和 gzip）
       Parse Sitemap XML (supports index and gzip)
    2. 根据规则过滤 URL
       Filter URLs based on rules
    3. 增量爬取页面内容
       Incrementally crawl page content
    4. 将 HTML 转换为 Markdown
       Convert HTML to Markdown
    5. 生成文章数据供知识库使用
       Generate article data for knowledge base
    
    Attributes:
        config: 导入器配置
                Importer configuration
        parser: Sitemap 解析器
                Sitemap parser
        rule_engine: 抓取规则引擎
                     Crawl rule engine
        crawler: 增量爬虫
                 Incremental crawler
        converter: HTML 转 Markdown 转换器
                   HTML to Markdown converter
    
    Examples:
        >>> config = SitemapImporterConfig(
        ...     sitemap_url='https://example.com/sitemap.xml',
        ...     include_patterns=['/docs/*']
        ... )
        >>> importer = SitemapImporter(config)
        >>> result = importer.import_from_sitemap()
        >>> print(f"Imported {result.articles_added} articles")
        
        >>> # 获取文章数据（不直接添加到知识库）
        >>> articles = importer.fetch_articles()
        >>> for article in articles:
        ...     print(article['title'])
    
    Requirements:
        - 5.1: Parse and extract all page URLs from sitemap
        - 6.1: Support incremental crawling
        - 7.1: Convert HTML to Markdown
        - 8.1: Support include/exclude patterns
    """
    
    def __init__(
        self,
        config: SitemapImporterConfig | dict,
        state_store: CrawlStateStore | None = None
    ):
        """
        初始化 SitemapImporter
        Initialize SitemapImporter
        
        Args:
            config: 导入器配置（SitemapImporterConfig 或字典）
                    Importer configuration (SitemapImporterConfig or dict)
            state_store: 爬取状态存储（可选，用于依赖注入）
                         Crawl state store (optional, for dependency injection)
        
        Raises:
            ConfigurationError: 当配置无效时
                                When configuration is invalid
        
        Examples:
            >>> config = SitemapImporterConfig(
            ...     sitemap_url='https://example.com/sitemap.xml'
            ... )
            >>> importer = SitemapImporter(config)
            
            >>> # 使用字典配置
            >>> importer = SitemapImporter({
            ...     'sitemap_url': 'https://example.com/sitemap.xml',
            ...     'include_patterns': ['/docs/*']
            ... })
        """
        # 解析配置
        if isinstance(config, dict):
            self.config = SitemapImporterConfig(
                sitemap_url=config.get('sitemap_url', ''),
                include_patterns=config.get('include_patterns', []),
                exclude_patterns=config.get('exclude_patterns', []),
                use_regex=config.get('use_regex', False),
                timeout=config.get('timeout', 30),
                user_agent=config.get('user_agent', 'PandaWiki-SitemapImporter/1.0'),
                max_concurrent=config.get('max_concurrent', 5),
                delay_between_requests=config.get('delay_between_requests', 0.5),
                force_refresh=config.get('force_refresh', False),
                state_file=config.get('state_file'),
                source_type=config.get('source_type', 'sitemap'),
                category=config.get('category', '')
            )
        else:
            self.config = config
        
        # 验证配置
        if not self.config.sitemap_url:
            raise ConfigurationError("sitemap_url is required")
        
        # 初始化组件
        self.parser = SitemapParser(
            timeout=self.config.timeout,
            user_agent=self.config.user_agent
        )
        
        # 初始化规则引擎
        rules = CrawlRules(
            include_patterns=self.config.include_patterns,
            exclude_patterns=self.config.exclude_patterns,
            use_regex=self.config.use_regex
        )
        self.rule_engine = CrawlRuleEngine(rules)
        
        # 初始化状态存储
        if state_store:
            self._state_store = state_store
        elif self.config.state_file:
            self._state_store = FileCrawlStateStore(self.config.state_file)
        else:
            self._state_store = InMemoryCrawlStateStore()
        
        # 初始化增量爬虫
        self.crawler = IncrementalCrawler(
            state_store=self._state_store
        )
        
        # 初始化 HTML 转换器
        self.converter = HTMLToMarkdownConverter()
    
    def import_from_sitemap(
        self,
        knowledge_base=None
    ) -> ImportResult:
        """
        从 Sitemap 导入内容到知识库
        Import content from Sitemap to knowledge base
        
        完整的导入流程：
        Complete import workflow:
        1. 解析 Sitemap 获取 URL 列表
        2. 根据规则过滤 URL
        3. 增量爬取页面内容
        4. 转换 HTML 为 Markdown
        5. 添加到知识库
        
        Args:
            knowledge_base: 知识库实例（可选）
                            Knowledge base instance (optional)
                            如果提供，将自动调用 add_articles()
                            If provided, will automatically call add_articles()
        
        Returns:
            ImportResult 包含导入统计信息
            ImportResult containing import statistics
        
        Raises:
            SitemapParseError: 当 Sitemap 解析失败时
                               When Sitemap parsing fails
        
        Examples:
            >>> importer = SitemapImporter(config)
            >>> result = importer.import_from_sitemap(knowledge_base)
            >>> print(f"Added {result.articles_added} articles")
            >>> print(f"Success rate: {result.success_rate:.1%}")
        """
        import time
        start_time = time.time()
        
        result = ImportResult()
        
        try:
            # 1. 解析 Sitemap
            entries = self._parse_sitemap()
            result.total_urls = len(entries)
            
            # 2. 过滤 URL
            filtered_entries = self._filter_entries(entries)
            result.filtered_urls = len(filtered_entries)
            
            # 3. 爬取并转换
            articles = []
            for entry in filtered_entries:
                try:
                    article = self._crawl_and_convert(entry)
                    if article:
                        if article.get('_skipped'):
                            result.skipped_urls += 1
                        else:
                            articles.append(article)
                            result.crawled_urls += 1
                    else:
                        result.failed_urls += 1
                except Exception as e:
                    result.failed_urls += 1
                    result.errors.append(f"Failed to crawl {entry.loc}: {e}")
            
            # 4. 添加到知识库
            if knowledge_base and articles:
                try:
                    added = knowledge_base.add_articles(articles)
                    result.articles_added = added
                except Exception as e:
                    result.errors.append(f"Failed to add articles to knowledge base: {e}")
            else:
                result.articles_added = len(articles)
            
        except SitemapParseError as e:
            result.errors.append(str(e))
            raise
        except Exception as e:
            result.errors.append(f"Unexpected error: {e}")
        
        result.duration_seconds = time.time() - start_time
        return result
    
    def fetch_articles(self) -> list[dict]:
        """
        获取文章数据（不添加到知识库）
        Fetch article data (without adding to knowledge base)
        
        执行解析、过滤、爬取和转换流程，返回文章数据列表。
        Executes parsing, filtering, crawling, and conversion workflow,
        returns list of article data.
        
        Returns:
            文章数据列表，每篇文章包含：
            List of article data, each article contains:
            - id: 文章 ID（基于 URL hash）
            - title: 标题
            - content: Markdown 内容
            - url: 原文链接
            - source_type: 来源类型
            - published_date: 发布日期（如果有）
            - category: 分类
        
        Examples:
            >>> importer = SitemapImporter(config)
            >>> articles = importer.fetch_articles()
            >>> for article in articles:
            ...     print(f"{article['title']}: {len(article['content'])} chars")
        """
        # 1. 解析 Sitemap
        entries = self._parse_sitemap()
        
        # 2. 过滤 URL
        filtered_entries = self._filter_entries(entries)
        
        # 3. 爬取并转换
        articles = []
        for entry in filtered_entries:
            try:
                article = self._crawl_and_convert(entry)
                if article and not article.get('_skipped'):
                    articles.append(article)
            except Exception:
                continue
        
        return articles
    
    def get_filtered_urls(self) -> list[str]:
        """
        获取过滤后的 URL 列表
        Get filtered URL list
        
        解析 Sitemap 并应用规则过滤，返回符合条件的 URL 列表。
        Parses Sitemap and applies rule filtering, returns list of matching URLs.
        
        Returns:
            过滤后的 URL 列表
            List of filtered URLs
        
        Examples:
            >>> importer = SitemapImporter(config)
            >>> urls = importer.get_filtered_urls()
            >>> print(f"Found {len(urls)} matching URLs")
        """
        entries = self._parse_sitemap()
        filtered_entries = self._filter_entries(entries)
        return [entry.loc for entry in filtered_entries]
    
    def _parse_sitemap(self) -> list[SitemapEntry]:
        """
        解析 Sitemap（支持 index 格式）
        Parse Sitemap (supports index format)
        
        Returns:
            SitemapEntry 列表
            List of SitemapEntry
        """
        all_entries = []
        
        try:
            # 首先尝试作为普通 sitemap 解析
            entries = self.parser.parse(self.config.sitemap_url)
            all_entries.extend(entries)
        except SitemapParseError as e:
            # 如果提示是 sitemap index，尝试解析 index
            if "sitemap index" in str(e).lower():
                sitemap_urls = self.parser.parse_index(self.config.sitemap_url)
                for sitemap_url in sitemap_urls:
                    try:
                        entries = self.parser.parse(sitemap_url)
                        all_entries.extend(entries)
                    except SitemapParseError:
                        continue
            else:
                raise
        
        return all_entries
    
    def _filter_entries(self, entries: list[SitemapEntry]) -> list[SitemapEntry]:
        """
        根据规则过滤 URL
        Filter URLs based on rules
        
        Args:
            entries: 原始 SitemapEntry 列表
                     Original list of SitemapEntry
        
        Returns:
            过滤后的 SitemapEntry 列表
            Filtered list of SitemapEntry
        """
        return [
            entry for entry in entries
            if self.rule_engine.should_crawl(entry.loc)
        ]
    
    def _crawl_and_convert(self, entry: SitemapEntry) -> dict | None:
        """
        爬取页面并转换为文章数据
        Crawl page and convert to article data
        
        Args:
            entry: Sitemap 条目
                   Sitemap entry
        
        Returns:
            文章数据字典，如果失败则返回 None
            Article data dict, or None if failed
        """
        # 使用增量爬虫获取内容
        crawl_result = self.crawler.crawl(
            entry.loc,
            lastmod=entry.lastmod,
            force=self.config.force_refresh
        )
        
        if crawl_result is None:
            return None
        
        # 检查是否跳过（未变更）
        if crawl_result.get('skipped'):
            return {'_skipped': True}
        
        html_content = crawl_result.get('content', '')
        if not html_content:
            return None
        
        # 转换 HTML 为 Markdown
        markdown_content = self.converter.convert(html_content)
        if not markdown_content or not markdown_content.strip():
            return None
        
        # 提取标题
        title = self._extract_title(html_content, entry.loc)
        
        # 生成文章 ID
        article_id = self._generate_id(entry.loc)
        
        # 构建文章数据
        return {
            'id': article_id,
            'title': title,
            'content': markdown_content,
            'url': entry.loc,
            'source_type': self.config.source_type,
            'published_date': entry.lastmod.isoformat() if entry.lastmod else '',
            'category': self.config.category
        }
    
    def _extract_title(self, html_content: str, url: str) -> str:
        """
        从 HTML 中提取标题
        Extract title from HTML
        
        Args:
            html_content: HTML 内容
                          HTML content
            url: 页面 URL（作为后备标题）
                 Page URL (as fallback title)
        
        Returns:
            页面标题
            Page title
        """
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 尝试从 <title> 标签获取
            title_tag = soup.find('title')
            if title_tag and title_tag.get_text().strip():
                return title_tag.get_text().strip()
            
            # 尝试从 <h1> 标签获取
            h1_tag = soup.find('h1')
            if h1_tag and h1_tag.get_text().strip():
                return h1_tag.get_text().strip()
            
            # 尝试从 og:title 获取
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                return og_title.get('content').strip()
            
        except Exception:
            pass
        
        # 使用 URL 作为后备标题
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path.rstrip('/')
        if path:
            return path.split('/')[-1].replace('-', ' ').replace('_', ' ').title()
        return parsed.netloc
    
    def _generate_id(self, url: str) -> str:
        """
        根据 URL 生成唯一 ID
        Generate unique ID from URL
        
        Args:
            url: 页面 URL
                 Page URL
        
        Returns:
            唯一 ID（URL 的 hash）
            Unique ID (hash of URL)
        """
        import hashlib
        return hashlib.md5(url.encode()).hexdigest()[:16]
    
    def get_crawl_stats(self) -> CrawlStats:
        """
        获取爬取统计信息
        Get crawl statistics
        
        Returns:
            CrawlStats 对象
            CrawlStats object
        """
        return self.crawler.get_stats()
    
    def reset_state(self) -> None:
        """
        重置爬取状态
        Reset crawl state
        
        清除所有已保存的爬取状态，下次爬取将重新获取所有页面。
        Clears all saved crawl state, next crawl will re-fetch all pages.
        """
        self._state_store.clear()


# =============================================================================
# File-based Crawl State Store
# =============================================================================

class FileCrawlStateStore(CrawlStateStore):
    """
    基于文件的爬取状态存储
    File-based Crawl State Store
    
    将爬取状态持久化到 JSON 文件。
    Persists crawl state to a JSON file.
    
    Attributes:
        file_path: 状态文件路径
                   State file path
    
    Examples:
        >>> store = FileCrawlStateStore('data/crawl_state.json')
        >>> store.save(CrawlState(url='https://example.com', content_hash='abc123'))
        >>> state = store.get('https://example.com')
    """
    
    def __init__(self, file_path: str):
        """
        初始化 FileCrawlStateStore
        Initialize FileCrawlStateStore
        
        Args:
            file_path: 状态文件路径
                       State file path
        """
        import json
        import os
        
        self.file_path = file_path
        self._states: dict[str, CrawlState] = {}
        self._json = json
        self._os = os
        
        # 加载现有状态
        self._load()
    
    def _load(self) -> None:
        """加载状态文件"""
        if self._os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    data = self._json.load(f)
                    for url, state_data in data.items():
                        self._states[url] = CrawlState(
                            url=state_data['url'],
                            content_hash=state_data.get('content_hash'),
                            last_crawl=datetime.fromisoformat(state_data['last_crawl'])
                            if state_data.get('last_crawl') else None
                        )
            except Exception:
                self._states = {}
    
    def _save_to_file(self) -> None:
        """保存状态到文件"""
        # 确保目录存在
        dir_path = self._os.path.dirname(self.file_path)
        if dir_path and not self._os.path.exists(dir_path):
            self._os.makedirs(dir_path, exist_ok=True)
        
        data = {}
        for url, state in self._states.items():
            data[url] = {
                'url': state.url,
                'content_hash': state.content_hash,
                'last_crawl': state.last_crawl.isoformat() if state.last_crawl else None
            }
        
        with open(self.file_path, 'w', encoding='utf-8') as f:
            self._json.dump(data, f, ensure_ascii=False, indent=2)
    
    def get_state(self, url: str) -> CrawlState | None:
        """获取 URL 的爬取状态"""
        return self._states.get(url)
    
    def save_state(self, state: CrawlState) -> None:
        """保存爬取状态"""
        self._states[state.url] = state
        self._save_to_file()
    
    def get_all_states(self) -> dict[str, CrawlState]:
        """获取所有爬取状态"""
        return self._states.copy()
    
    def get(self, url: str) -> CrawlState | None:
        """获取 URL 的爬取状态（别名）"""
        return self.get_state(url)
    
    def save(self, state: CrawlState) -> None:
        """保存爬取状态（别名）"""
        self.save_state(state)
    
    def delete(self, url: str) -> None:
        """删除 URL 的爬取状态"""
        if url in self._states:
            del self._states[url]
            self._save_to_file()
    
    def get_all(self) -> list[CrawlState]:
        """获取所有爬取状态列表"""
        return list(self._states.values())
    
    def clear(self) -> None:
        """清除所有状态"""
        self._states.clear()
        if self._os.path.exists(self.file_path):
            self._os.remove(self.file_path)
