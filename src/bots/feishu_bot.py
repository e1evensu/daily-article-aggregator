"""
飞书机器人模块

实现飞书消息推送功能：
1. Webhook 机器人：通过 Webhook URL 发送消息到群
2. 应用机器人：通过 app_id/app_secret 主动发送消息给用户
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import requests

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
    
    def push_articles(self, articles: list[dict], batch_size: int = 10) -> bool:
        """
        推送文章到飞书（支持分批推送）
        
        Args:
            articles: 文章列表，每篇文章应包含title和url字段
            batch_size: 每批推送的文章数量，默认10篇
            
        Returns:
            是否全部推送成功
            
        Note:
            - 空列表会返回True（无需推送）
            - 文章数量超过 batch_size 时会分批推送
            - 每批之间间隔1秒，避免触发频率限制
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
        
        total_count = len(valid_articles)
        logger.info(f"准备推送 {total_count} 篇文章到飞书（每批 {batch_size} 篇）")
        
        # 分批推送
        all_success = True
        batch_num = 0
        
        for i in range(0, total_count, batch_size):
            batch_num += 1
            batch = valid_articles[i:i + batch_size]
            batch_start = i + 1
            batch_end = min(i + batch_size, total_count)
            
            # 构建富文本内容
            title = f"📚 今日文章推荐 ({batch_start}-{batch_end}/{total_count}篇)"
            content = self._build_rich_text_content_simple(batch)
            
            logger.info(f"推送第 {batch_num} 批: {len(batch)} 篇文章")
            success = self.send_rich_text(title, content)
            
            if not success:
                logger.error(f"第 {batch_num} 批推送失败")
                all_success = False
            
            # 批次之间间隔，避免触发频率限制
            if i + batch_size < total_count:
                time.sleep(1)
        
        if all_success:
            logger.info(f"全部 {total_count} 篇文章推送成功")
        else:
            logger.warning(f"部分批次推送失败，请检查日志")
        
        return all_success
    
    def _build_rich_text_content_simple(self, articles: list[dict]) -> list:
        """
        构建简化版富文本消息内容（不含摘要，减少消息长度）
        
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
            
            # 截断过长的标题
            if len(title) > 80:
                title = title[:77] + "..."
            
            # 文章标题行（带链接）
            title_line = [
                {"tag": "text", "text": f"{i}. "},
                {"tag": "a", "text": title, "href": url}
            ]
            content.append(title_line)
            
            # 分类行（简短信息）
            category = article.get('category', '').strip()
            source = article.get('source', '').strip()
            if category or source:
                info_parts = []
                if category:
                    info_parts.append(f"[{category}]")
                if source:
                    # 截断过长的来源名
                    if len(source) > 30:
                        source = source[:27] + "..."
                    info_parts.append(source)
                info_line = [{"tag": "text", "text": f"   {' '.join(info_parts)}"}]
                content.append(info_line)
        
        return content



class FeishuAppBot:
    """
    飞书应用机器人
    
    通过飞书应用凭证（app_id/app_secret）发送消息。
    支持发送消息给用户、群组，以及创建文档等高级功能。
    
    Attributes:
        app_id: 飞书应用 ID
        app_secret: 飞书应用密钥
        timeout: 请求超时时间（秒）
    """
    
    BASE_URL = "https://open.feishu.cn/open-apis"
    
    def __init__(
        self, 
        app_id: str, 
        app_secret: str, 
        timeout: int = 30
    ):
        """
        初始化飞书应用机器人
        
        Args:
            app_id: 飞书应用 ID
            app_secret: 飞书应用密钥
            timeout: 请求超时时间（秒），默认30秒
            
        Raises:
            ValueError: 如果 app_id 或 app_secret 为空
        """
        if not app_id or not app_id.strip():
            raise ValueError("app_id 不能为空")
        if not app_secret or not app_secret.strip():
            raise ValueError("app_secret 不能为空")
        
        self.app_id = app_id.strip()
        self.app_secret = app_secret.strip()
        self.timeout = timeout
        
        # Token 缓存
        self._tenant_access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
    
    def get_tenant_access_token(self) -> Optional[str]:
        """
        获取 tenant_access_token
        
        飞书应用的访问令牌，用于调用各种 API。
        会自动缓存 token，在过期前 5 分钟刷新。
        
        Returns:
            tenant_access_token，失败返回 None
        """
        # 检查缓存的 token 是否有效
        if self._tenant_access_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at:
                return self._tenant_access_token
        
        try:
            url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
            response = requests.post(
                url,
                json={
                    "app_id": self.app_id,
                    "app_secret": self.app_secret
                },
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code != 200:
                logger.error(
                    f"获取 tenant_access_token 失败: HTTP {response.status_code}"
                )
                return None
            
            data = response.json()
            if data.get('code') != 0:
                logger.error(
                    f"获取 tenant_access_token 失败: {data.get('msg')}"
                )
                return None
            
            self._tenant_access_token = data.get('tenant_access_token')
            # Token 有效期通常是 2 小时，提前 5 分钟刷新
            expire_seconds = data.get('expire', 7200) - 300
            self._token_expires_at = datetime.now() + timedelta(seconds=expire_seconds)
            
            logger.debug("tenant_access_token 获取成功")
            return self._tenant_access_token
            
        except requests.exceptions.Timeout:
            logger.error(f"获取 tenant_access_token 超时: {self.timeout}秒")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"获取 tenant_access_token 请求异常: {e}")
            return None
        except Exception as e:
            logger.error(f"获取 tenant_access_token 时发生错误: {e}")
            return None
    
    def _get_headers(self) -> Optional[dict]:
        """
        获取带有授权的请求头
        
        Returns:
            请求头字典，获取 token 失败返回 None
        """
        token = self.get_tenant_access_token()
        if not token:
            return None
        
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def send_message_to_user(
        self, 
        user_id: str, 
        msg_type: str, 
        content: dict,
        receive_id_type: str = "open_id"
    ) -> bool:
        """
        发送消息给用户
        
        Args:
            user_id: 用户 ID（open_id、user_id 或 union_id）
            msg_type: 消息类型（text、post、interactive 等）
            content: 消息内容
            receive_id_type: 接收者 ID 类型，默认 open_id
                可选值: open_id, user_id, union_id, email, chat_id
            
        Returns:
            是否发送成功
        """
        headers = self._get_headers()
        if not headers:
            logger.error("无法获取访问令牌，发送消息失败")
            return False
        
        try:
            url = f"{self.BASE_URL}/im/v1/messages"
            params = {"receive_id_type": receive_id_type}
            
            payload = {
                "receive_id": user_id,
                "msg_type": msg_type,
                "content": content if isinstance(content, str) else json.dumps(content)
            }
            
            response = requests.post(
                url,
                params=params,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                logger.error(
                    f"发送消息失败: HTTP {response.status_code}, "
                    f"响应: {response.text}"
                )
                return False
            
            data = response.json()
            if data.get('code') != 0:
                logger.error(f"发送消息失败: {data.get('msg')}")
                return False
            
            logger.info(f"消息发送成功: {user_id}")
            return True
            
        except requests.exceptions.Timeout:
            logger.error(f"发送消息超时: {self.timeout}秒")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"发送消息请求异常: {e}")
            return False
        except Exception as e:
            logger.error(f"发送消息时发生错误: {e}")
            return False
    
    def send_text_to_user(self, user_id: str, text: str) -> bool:
        """
        发送文本消息给用户
        
        Args:
            user_id: 用户 open_id
            text: 消息文本
            
        Returns:
            是否发送成功
        """
        if not text or not text.strip():
            logger.warning("尝试发送空文本消息")
            return False
        
        content = {"text": text}
        return self.send_message_to_user(user_id, "text", content)
    
    def send_message_to_chat(
        self, 
        chat_id: str, 
        msg_type: str, 
        content: dict
    ) -> bool:
        """
        发送消息到群聊
        
        Args:
            chat_id: 群聊 ID
            msg_type: 消息类型
            content: 消息内容
            
        Returns:
            是否发送成功
        """
        return self.send_message_to_user(
            chat_id, 
            msg_type, 
            content, 
            receive_id_type="chat_id"
        )
    
    def send_rich_text_to_user(
        self, 
        user_id: str, 
        title: str, 
        content: list
    ) -> bool:
        """
        发送富文本消息给用户
        
        Args:
            user_id: 用户 open_id
            title: 消息标题
            content: 富文本内容（飞书格式）
            
        Returns:
            是否发送成功
        """
        post_content = {
            "zh_cn": {
                "title": title,
                "content": content
            }
        }
        return self.send_message_to_user(user_id, "post", post_content)
    
    def push_articles_to_user(
        self, 
        user_id: str, 
        articles: list[dict]
    ) -> bool:
        """
        推送文章列表给用户
        
        Args:
            user_id: 用户 open_id
            articles: 文章列表
            
        Returns:
            是否推送成功
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
            logger.warning("所有文章都缺少必要字段")
            return False
        
        # 构建富文本内容
        content = []
        for i, article in enumerate(valid_articles, 1):
            title = article.get('title', '').strip()
            url = article.get('url', '').strip()
            
            # 文章标题行（带链接）
            title_line = [
                {"tag": "text", "text": f"{i}. "},
                {"tag": "a", "text": title, "href": url}
            ]
            content.append(title_line)
            
            # 摘要行
            zh_summary = article.get('zh_summary', '').strip()
            summary = article.get('summary', '').strip()
            
            if zh_summary:
                content.append([{"tag": "text", "text": f"   摘要: {zh_summary}"}])
            elif summary:
                content.append([{"tag": "text", "text": f"   摘要: {summary}"}])
            
            # 空行分隔
            content.append([{"tag": "text", "text": ""}])
        
        title = f"📚 今日文章推荐 ({len(valid_articles)}篇)"
        return self.send_rich_text_to_user(user_id, title, content)


# 需要导入 json 模块
import json
