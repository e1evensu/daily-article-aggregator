"""
ContentProcessor - 内容处理器
Content Processor Module

获取文章HTML内容并转换为Markdown格式。
Fetches article HTML content and converts to Markdown format.

需求 3.1: 获取文章的HTML内容
需求 3.2: 将HTML转换为Markdown格式
需求 3.3: 如果文章内容超过最大长度限制，截断内容并添加省略标记
需求 3.4: 获取文章内容失败时记录错误并跳过该文章
需求 3.5: 支持通过代理获取文章内容
"""

import logging
import os
from io import BytesIO
from typing import Optional

import requests
from markitdown import MarkItDown

# 配置日志
logger = logging.getLogger(__name__)


def truncate_content(content: str, max_length: int, marker: str = "...[内容已截断]") -> str:
    """
    截断内容到指定最大长度，并添加省略标记。
    Truncate content to specified max length and add ellipsis marker.
    
    此函数是独立的纯函数，便于属性测试。
    This is a standalone pure function for easy property testing.
    
    Args:
        content: 原始内容
                 Original content
        max_length: 最大长度限制（包含省略标记）
                    Maximum length limit (including marker)
        marker: 省略标记，默认为 "...[内容已截断]"
                Ellipsis marker, defaults to "...[内容已截断]"
    
    Returns:
        截断后的内容。如果原内容不超过限制，返回原内容。
        Truncated content. Returns original if within limit.
    
    Examples:
        >>> truncate_content("Hello World", 5, "...")
        'He...'
        >>> truncate_content("Hi", 10, "...")
        'Hi'
    
    **验证: 需求 3.3**
    """
    if not content:
        return content
    
    if max_length <= 0:
        return ""
    
    # 如果内容长度不超过限制，直接返回
    if len(content) <= max_length:
        return content
    
    # 计算截断位置：需要为省略标记留出空间
    marker_len = len(marker)
    
    # 如果最大长度小于等于标记长度，只返回标记的前max_length个字符
    if max_length <= marker_len:
        return marker[:max_length]
    
    # 截断内容并添加省略标记
    truncate_at = max_length - marker_len
    return content[:truncate_at] + marker


class ContentProcessor:
    """
    内容处理器：获取HTML并转换为Markdown
    Content Processor: Fetch HTML and convert to Markdown
    
    支持两种获取模式：
    1. 普通HTTP请求（使用requests库）
    2. Playwright无头浏览器（用于反爬网站）
    
    Supports two fetch modes:
    1. Regular HTTP requests (using requests library)
    2. Playwright headless browser (for anti-scraping sites)
    """
    
    # 默认配置
    DEFAULT_MAX_CONTENT_LENGTH = 50000  # 默认最大内容长度
    DEFAULT_TRUNCATION_MARKER = "...[内容已截断]"
    DEFAULT_TIMEOUT = 30  # 默认超时时间（秒）
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    
    def __init__(self, config: dict):
        """
        初始化处理器
        Initialize processor
        
        Args:
            config: 配置字典，包含以下可选键：
                    Config dict with optional keys:
                    - proxy: 代理URL (e.g., "http://127.0.0.1:7890")
                    - max_content_length: 最大内容长度
                    - truncation_marker: 截断标记
                    - timeout: 请求超时时间（秒）
                    - user_agent: 自定义User-Agent
                    - playwright_always: 是否总是使用Playwright
                    - playwright_headless: Playwright是否使用无头模式
                    - playwright_timeout: Playwright超时时间（毫秒）
        """
        self.config = config or {}
        
        # 代理配置
        self.proxy = self.config.get('proxy') or os.environ.get('HTTP_PROXY') or os.environ.get('HTTPS_PROXY')
        
        # 内容处理配置
        self.max_content_length = self.config.get('max_content_length', self.DEFAULT_MAX_CONTENT_LENGTH)
        self.truncation_marker = self.config.get('truncation_marker', self.DEFAULT_TRUNCATION_MARKER)
        self.timeout = self.config.get('timeout', self.DEFAULT_TIMEOUT)
        self.user_agent = self.config.get('user_agent', self.DEFAULT_USER_AGENT)
        
        # Playwright配置
        self._playwright_always = self._get_bool_config('playwright_always', 'PLAYWRIGHT_ALWAYS', False)
        self._playwright_headless = self._get_bool_config('playwright_headless', 'PLAYWRIGHT_HEADLESS', True)
        self._playwright_timeout = self._get_int_config('playwright_timeout', 'PLAYWRIGHT_TIMEOUT', 30000)
        
        # 初始化MarkItDown转换器
        self._markitdown = MarkItDown()
        
        # Playwright实例（延迟初始化）
        self._playwright = None
        self._browser = None
    
    def _get_bool_config(self, config_key: str, env_key: str, default: bool) -> bool:
        """从配置或环境变量获取布尔值"""
        if config_key in self.config:
            value = self.config[config_key]
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ('true', '1', 'yes')
        
        env_value = os.environ.get(env_key)
        if env_value:
            return env_value.lower() in ('true', '1', 'yes')
        
        return default
    
    def _get_int_config(self, config_key: str, env_key: str, default: int) -> int:
        """从配置或环境变量获取整数值"""
        if config_key in self.config:
            try:
                return int(self.config[config_key])
            except (ValueError, TypeError):
                pass
        
        env_value = os.environ.get(env_key)
        if env_value:
            try:
                return int(env_value)
            except ValueError:
                pass
        
        return default
    
    def _get_proxies(self) -> dict | None:
        """获取requests库使用的代理配置"""
        if not self.proxy:
            return None
        return {
            'http': self.proxy,
            'https': self.proxy
        }
    
    def _get_headers(self) -> dict:
        """获取HTTP请求头"""
        return {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
    
    def _fetch_with_requests(self, url: str) -> str | None:
        """
        使用requests库获取HTML内容
        Fetch HTML content using requests library
        
        Args:
            url: 文章URL
        
        Returns:
            HTML内容，失败返回None
        """
        try:
            response = requests.get(
                url,
                headers=self._get_headers(),
                proxies=self._get_proxies(),
                timeout=self.timeout,
                allow_redirects=True
            )
            response.raise_for_status()
            return response.text
        except requests.exceptions.Timeout:
            logger.warning(f"请求超时: {url}")
            return None
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else 'unknown'
            logger.warning(f"HTTP错误 {status_code}: {url}")
            # 返回None以触发Playwright回退
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"请求失败: {url}, 错误: {e}")
            return None
    
    def _init_playwright(self):
        """
        初始化Playwright浏览器
        Initialize Playwright browser
        """
        if self._browser is not None:
            return
        
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self._playwright_headless
            )
            logger.info("Playwright浏览器已初始化")
        except Exception as e:
            logger.error(f"Playwright初始化失败: {e}")
            raise
    
    def _fetch_with_playwright(self, url: str) -> str | None:
        """
        使用Playwright获取HTML内容（用于反爬网站）
        Fetch HTML content using Playwright (for anti-scraping sites)
        
        Args:
            url: 文章URL
        
        Returns:
            HTML内容，失败返回None
        """
        try:
            self._init_playwright()
            
            # 创建新的浏览器上下文
            context_options = {
                'user_agent': self.user_agent
            }
            
            # 配置代理
            if self.proxy:
                context_options['proxy'] = {'server': self.proxy}
            
            context = self._browser.new_context(**context_options)
            page = context.new_page()
            
            try:
                # 导航到页面
                page.goto(url, timeout=self._playwright_timeout, wait_until='domcontentloaded')
                
                # 等待页面加载完成
                page.wait_for_load_state('networkidle', timeout=self._playwright_timeout)
                
                # 获取HTML内容
                html = page.content()
                return html
            finally:
                page.close()
                context.close()
                
        except Exception as e:
            logger.error(f"Playwright获取失败: {url}, 错误: {e}")
            return None
    
    def fetch_html(self, url: str) -> str | None:
        """
        获取文章HTML内容
        Fetch article HTML content
        
        实现回退机制：
        1. 如果配置了playwright_always，直接使用Playwright
        2. 否则先尝试普通HTTP请求
        3. 如果失败（403, 503, 超时等），回退到Playwright
        
        Implements fallback mechanism:
        1. If playwright_always is configured, use Playwright directly
        2. Otherwise try regular HTTP request first
        3. If failed (403, 503, timeout, etc.), fallback to Playwright
        
        Args:
            url: 文章URL
                 Article URL
        
        Returns:
            HTML内容，失败返回None
            HTML content, returns None on failure
        
        **验证: 需求 3.1, 3.4, 3.5**
        """
        if not url:
            logger.warning("URL为空")
            return None
        
        # 如果配置了总是使用Playwright
        if self._playwright_always:
            logger.debug(f"使用Playwright获取: {url}")
            return self._fetch_with_playwright(url)
        
        # 先尝试普通HTTP请求
        logger.debug(f"使用requests获取: {url}")
        html = self._fetch_with_requests(url)
        
        if html is not None:
            return html
        
        # 回退到Playwright
        logger.info(f"回退到Playwright获取: {url}")
        return self._fetch_with_playwright(url)
    
    def html_to_markdown(self, html: str) -> str | None:
        """
        将HTML转换为Markdown
        Convert HTML to Markdown
        
        使用markitdown库进行转换。
        Uses markitdown library for conversion.
        
        Args:
            html: HTML内容
                  HTML content
        
        Returns:
            Markdown内容，失败返回None
            Markdown content, returns None on failure
        
        **验证: 需求 3.2**
        """
        if not html:
            logger.warning("HTML内容为空")
            return None
        
        try:
            # markitdown需要文件对象或URL，我们使用BytesIO模拟文件
            html_bytes = html.encode('utf-8')
            html_file = BytesIO(html_bytes)
            
            # 使用markitdown转换
            result = self._markitdown.convert_stream(html_file, file_extension='.html')
            
            if result and result.text_content:
                return result.text_content.strip()
            
            logger.warning("Markdown转换结果为空")
            return None
            
        except Exception as e:
            logger.error(f"HTML转Markdown失败: {e}")
            return None
    
    def process_article(self, url: str) -> str | None:
        """
        处理文章：获取HTML并转换为Markdown
        Process article: fetch HTML and convert to Markdown
        
        完整的处理流程：
        1. 获取HTML内容
        2. 转换为Markdown
        3. 如果超过最大长度，截断内容
        
        Complete processing flow:
        1. Fetch HTML content
        2. Convert to Markdown
        3. Truncate if exceeds max length
        
        Args:
            url: 文章URL
                 Article URL
        
        Returns:
            处理后的Markdown内容，失败返回None
            Processed Markdown content, returns None on failure
        
        **验证: 需求 3.1, 3.2, 3.3, 3.4, 3.5**
        """
        # 获取HTML
        html = self.fetch_html(url)
        if html is None:
            logger.error(f"获取文章内容失败: {url}")
            return None
        
        # 转换为Markdown
        markdown = self.html_to_markdown(html)
        if markdown is None:
            logger.error(f"HTML转Markdown失败: {url}")
            return None
        
        # 截断内容（如果需要）
        if self.max_content_length > 0 and len(markdown) > self.max_content_length:
            logger.info(f"内容超过限制({len(markdown)} > {self.max_content_length})，进行截断: {url}")
            markdown = truncate_content(markdown, self.max_content_length, self.truncation_marker)
        
        return markdown
    
    def close(self):
        """
        关闭Playwright浏览器和资源
        Close Playwright browser and resources
        """
        if self._browser:
            try:
                self._browser.close()
            except Exception as e:
                logger.warning(f"关闭浏览器失败: {e}")
            self._browser = None
        
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception as e:
                logger.warning(f"停止Playwright失败: {e}")
            self._playwright = None
    
    def __enter__(self):
        """支持上下文管理器"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出时关闭资源"""
        self.close()
        return False
