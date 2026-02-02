"""
飞书Webhook机器人模块

实现飞书Webhook消息推送功能，支持文本消息和富文本消息。
"""

import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)


def format_article_list(articles: list[dict]) -> str:
    """
    格式化文章列表为消息文本（独立函数，用于属性测试）
    
    Args:
        articles: 文章列表，每篇文章应包含title和url字段
        
    Returns:
        格式化后的消息文本，每篇文章占一行，格式为"标题: URL"
        
    Note:
        - 空列表返回空字符串
        - 缺少title或url的文章会被跳过
        - 如果文章有summary或zh_summary字段，会添加摘要信息
    """
    if not articles:
        return ""
    
    lines = []
    for i, article in enumerate(articles, 1):
        title = article.get('title', '').strip()
        url = article.get('url', '').strip()
        
        # 跳过缺少必要字段的文章
        if not title or not url:
            continue
        
        # 基本格式：序号. 标题
        line = f"{i}. {title}"
        lines.append(line)
        
        # 添加链接
        lines.append(f"   链接: {url}")
        
        # 添加摘要（优先使用中文摘要）
        zh_summary = article.get('zh_summary', '').strip()
        summary = article.get('summary', '').strip()
        
        if zh_summary:
            lines.append(f"   摘要: {zh_summary}")
        elif summary:
            lines.append(f"   摘要: {summary}")
        
        # 添加分类（如果有）
        category = article.get('category', '').strip()
        if category:
            lines.append(f"   分类: {category}")
        
        # 文章之间添加空行
        lines.append("")
    
    return "\n".join(lines).strip()


class FeishuBot:
    """
    飞书Webhook机器人
    
    通过飞书Webhook API发送消息到飞书群。
    支持发送文本消息和富文本消息。
    
    Attributes:
        webhook_url: 飞书Webhook URL
        proxy: 代理URL（可选）
        timeout: 请求超时时间（秒）
    """
    
    def __init__(self, webhook_url: str, proxy: Optional[str] = None, timeout: int = 30):
        """
        初始化飞书机器人
        
        Args:
            webhook_url: 飞书Webhook URL
            proxy: 代理URL（可选），格式如 "http://proxy:port"
            timeout: 请求超时时间（秒），默认30秒
            
        Raises:
            ValueError: 如果webhook_url为空
        """
        if not webhook_url or not webhook_url.strip():
            raise ValueError("webhook_url不能为空")
        
        self.webhook_url = webhook_url.strip()
        self.proxy = proxy.strip() if proxy else None
        self.timeout = timeout
        
        # 配置代理
        self._proxies = None
        if self.proxy:
            self._proxies = {
                'http': self.proxy,
                'https': self.proxy,
            }
    
    def _send_request(self, payload: dict) -> bool:
        """
        发送HTTP请求到Webhook
        
        Args:
            payload: 请求体JSON数据
            
        Returns:
            是否发送成功
        """
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                proxies=self._proxies,
                timeout=self.timeout,
                headers={'Content-Type': 'application/json'}
            )
            
            # 检查HTTP状态码
            if response.status_code != 200:
                logger.error(
                    f"飞书Webhook请求失败: HTTP {response.status_code}, "
                    f"响应: {response.text}"
                )
                return False
            
            # 检查飞书API响应
            result = response.json()
            if result.get('code') != 0 and result.get('StatusCode') != 0:
                # 飞书API可能返回code或StatusCode
                error_msg = result.get('msg') or result.get('StatusMessage') or '未知错误'
                logger.error(f"飞书Webhook API错误: {error_msg}")
                return False
            
            logger.info("飞书消息发送成功")
            return True
            
        except requests.exceptions.Timeout:
            logger.error(f"飞书Webhook请求超时: {self.timeout}秒")
            return False
        except requests.exceptions.ConnectionError as e:
            logger.error(f"飞书Webhook连接错误: {e}")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"飞书Webhook请求异常: {e}")
            return False
        except ValueError as e:
            # JSON解析错误
            logger.error(f"飞书Webhook响应解析错误: {e}")
            return False
    
    def send_text(self, text: str) -> bool:
        """
        发送文本消息
        
        Args:
            text: 消息文本内容
            
        Returns:
            是否发送成功
            
        Note:
            空文本会返回False并记录警告
        """
        if not text or not text.strip():
            logger.warning("尝试发送空文本消息")
            return False
        
        payload = {
            "msg_type": "text",
            "content": {
                "text": text
            }
        }
        
        logger.debug(f"发送文本消息: {text[:100]}...")
        return self._send_request(payload)
    
    def send_rich_text(self, title: str, content: list) -> bool:
        """
        发送富文本消息
        
        Args:
            title: 消息标题
            content: 富文本内容，格式为飞书富文本格式的二维数组
                    每个元素是一行，每行包含多个内容块
                    内容块格式: {"tag": "text", "text": "内容"} 或
                              {"tag": "a", "text": "链接文字", "href": "URL"}
            
        Returns:
            是否发送成功
            
        Example:
            content = [
                [{"tag": "text", "text": "这是第一行"}],
                [{"tag": "a", "text": "点击链接", "href": "https://example.com"}]
            ]
        """
        if not title and not content:
            logger.warning("尝试发送空富文本消息")
            return False
        
        payload = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": title or "",
                        "content": content or []
                    }
                }
            }
        }
        
        logger.debug(f"发送富文本消息: {title}")
        return self._send_request(payload)
    
    def format_articles(self, articles: list[dict]) -> str:
        """
        格式化文章列表为消息文本
        
        Args:
            articles: 文章列表，每篇文章应包含title和url字段
            
        Returns:
            格式化后的消息文本
            
        Note:
            这是对独立函数format_article_list的封装，
            便于在类实例上调用
        """
        return format_article_list(articles)
    
    def _build_rich_text_content(self, articles: list[dict]) -> list:
        """
        构建富文本消息内容
        
        Args:
            articles: 文章列表
            
        Returns:
            飞书富文本格式的内容数组
        """
        content = []
        
        for i, article in enumerate(articles, 1):
            title = article.get('title', '').strip()
            url = article.get('url', '').strip()
            
            if not title or not url:
                continue
            
            # 文章标题行（带链接）
            title_line = [
                {"tag": "text", "text": f"{i}. "},
                {"tag": "a", "text": title, "href": url}
            ]
            content.append(title_line)
            
            # 摘要行（优先中文摘要）
            zh_summary = article.get('zh_summary', '').strip()
            summary = article.get('summary', '').strip()
            
            if zh_summary:
                summary_line = [{"tag": "text", "text": f"   摘要: {zh_summary}"}]
                content.append(summary_line)
            elif summary:
                summary_line = [{"tag": "text", "text": f"   摘要: {summary}"}]
                content.append(summary_line)
            
            # 分类行
            category = article.get('category', '').strip()
            if category:
                category_line = [{"tag": "text", "text": f"   分类: {category}"}]
                content.append(category_line)
            
            # 空行分隔
            content.append([{"tag": "text", "text": ""}])
        
        return content
    
    def push_articles(self, articles: list[dict]) -> bool:
        """
        推送文章到飞书
        
        Args:
            articles: 文章列表，每篇文章应包含title和url字段
            
        Returns:
            是否推送成功
            
        Note:
            - 空列表会返回True（无需推送）
            - 使用富文本格式发送，标题为"📚 今日文章推荐"
        """
        if not articles:
            logger.info("没有文章需要推送")
            return True
        
        # 过滤有效文章
        valid_articles = [
            a for a in articles 
            if a.get('title', '').strip() and a.get('url', '').strip()
        ]
        
        if not valid_articles:
            logger.warning("所有文章都缺少必要字段（title或url）")
            return False
        
        # 构建富文本内容
        title = f"📚 今日文章推荐 ({len(valid_articles)}篇)"
        content = self._build_rich_text_content(valid_articles)
        
        logger.info(f"推送 {len(valid_articles)} 篇文章到飞书")
        return self.send_rich_text(title, content)
