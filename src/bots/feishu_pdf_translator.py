"""
PDF翻译飞书服务

处理飞书消息中的PDF链接，自动下载并翻译，然后发回飞书。
"""

import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Optional
import urllib.request

import requests

from src.paper_translator.paper_translator.processor import PaperTranslator
from src.paper_translator.paper_translator.config import config as pdf_config

logger = logging.getLogger(__name__)


class FeishuPDFTranslationService:
    """飞书PDF翻译服务"""

    # 支持的PDF URL模式
    PDF_URL_PATTERNS = [
        r'https?://[^\s]+\.pdf',
        r'https?://[^\s]+/paper/[^\s]+\.pdf',
        r'https?://[^\s]+/pdf/[^\s]+\.pdf',
        r'https?://arxiv\.org/pdf/[^\s]+\.pdf',
    ]

    def __init__(self, config: dict):
        self.config = config
        self.enabled = config.get('enabled', False)

        # 创建输入输出目录
        self.input_dir = Path(config.get('input_dir', 'data/papers/input'))
        self.output_dir = Path(config.get('output_dir', 'data/papers/output'))
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 初始化翻译器
        if self.enabled:
            self._init_translator()

        # 飞书配置
        self.feishu_config = config.get('feishu', {})

        # 缓存翻译文本的对象（用于网页翻译）
        self._text_translator = None

    def _get_text_translator(self):
        """获取文本翻译器（用于网页翻译）"""
        if self._text_translator is None:
            from src.paper_translator.paper_translator.translation_engine import TranslationEngine
            # 使用与 PDF 翻译相同的配置
            provider = 'minimax'
            self._text_translator = TranslationEngine(
                provider=provider,
                api_key=self.config.get('minimax', {}).get('api_key'),
                base_url=self.config.get('minimax', {}).get('base_url'),
                model=self.config.get('minimax', {}).get('model', 'MiniMax-Text-01')
            )
        return self._text_translator

        logger.info(f"FeishuPDFTranslationService initialized: enabled={self.enabled}")

    def _init_translator(self):
        """初始化翻译器"""
        # 配置论文翻译系统
        pdf_config._config['deepseek_api_key'] = self.config.get('deepseek', {}).get('api_key', '')
        pdf_config._config['deepseek_base_url'] = self.config.get('deepseek', {}).get('base_url', 'https://api.deepseek.com')
        pdf_config._config['deepseek_model'] = self.config.get('deepseek', {}).get('model', 'deepseek-chat')
        pdf_config._config['siliconflow_api_key'] = self.config.get('siliconflow', {}).get('api_key', '')
        pdf_config._config['output_dir'] = str(self.output_dir)

        self.translator = PaperTranslator()
        logger.info("PDF Translator initialized")

    def is_pdf_url(self, text: str) -> bool:
        """检查文本是否包含PDF链接"""
        for pattern in self.PDF_URL_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def extract_pdf_url(self, text: str) -> Optional[str]:
        """从文本中提取PDF链接"""
        for pattern in self.PDF_URL_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return None

    def process_pdf_link(
        self,
        pdf_url: str,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        feishu_client: Optional[object] = None
    ) -> dict:
        """
        处理PDF链接

        Args:
            pdf_url: PDF文件URL
            user_id: 用户ID（用于通知）
            chat_id: 群聊ID
            feishu_client: 飞书客户端（用于发送消息）

        Returns:
            处理结果字典
        """
        if not self.enabled:
            return {
                'success': False,
                'message': 'PDF翻译服务未启用'
            }

        logger.info(f"开始处理: {pdf_url}")
        start_time = time.time()

        try:
            # 0. 处理输入，判断是 PDF 还是网页
            cleaned_url = pdf_url.strip()

            # 检查是否是纯 arXiv ID（如 2501.12345）
            import re
            if re.match(r'^\d{4}\.\d{4,5}$', cleaned_url):
                # 转换为 arXiv PDF URL
                cleaned_url = f"https://arxiv.org/pdf/{cleaned_url}.pdf"
                logger.info(f"已将 arXiv ID 转换为 PDF URL: {cleaned_url}")
            elif cleaned_url.startswith('arxiv:'):
                arxiv_id = cleaned_url[6:].strip()
                cleaned_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                logger.info(f"已将 arXiv ID 转换为 PDF URL: {cleaned_url}")
            elif cleaned_url.startswith('http://') or cleaned_url.startswith('https://'):
                # 是 HTTP URL，检查是 PDF 还是网页
                if '.pdf' in cleaned_url.lower() or '/pdf/' in cleaned_url.lower():
                    # PDF URL
                    pass
                else:
                    # 网页 URL，使用网页翻译
                    logger.info(f"检测为网页 URL，使用网页翻译: {cleaned_url}")
                    return self._translate_webpage(cleaned_url)

            # 1. 下载PDF
            pdf_path = self._download_pdf(cleaned_url)
            if not pdf_path:
                # 下载失败，尝试作为网页处理
                logger.info("PDF 下载失败，尝试作为网页处理")
                return self._translate_webpage(cleaned_url)

            logger.info(f"PDF下载成功: {pdf_path}")

            # 2. 翻译PDF
            result = self.translator.translate(str(pdf_path))

            # 3. 发送结果到飞书
            if feishu_client:
                self._send_to_feishu(
                    feishu_client,
                    chat_id,
                    user_id,
                    result
                )

            processing_time = time.time() - start_time

            return {
                'success': True,
                'message': '翻译完成',
                'output_path': result.output_path,
                'processing_time': processing_time,
                'stats': {
                    'pages': result.total_pages,
                    'terms': len(result.all_terms),
                    'formulas': len(result.all_formulas),
                    'figures': len(result.all_figures)
                }
            }

        except Exception as e:
            logger.error(f"PDF翻译失败: {e}")
            return {
                'success': False,
                'message': f'翻译失败: {str(e)}'
            }

    def _download_pdf(self, url: str) -> Optional[Path]:
        """下载PDF文件"""
        try:
            # 生成唯一文件名
            filename = f"{uuid.uuid4().hex[:8]}.pdf"
            output_path = self.input_dir / filename

            # 下载文件
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            request = urllib.request.Request(url, headers=headers)

            with urllib.request.urlopen(request, timeout=60) as response:
                with open(output_path, 'wb') as f:
                    f.write(response.read())

            return output_path

        except Exception as e:
            logger.error(f"下载PDF失败: {e}")
            return None

    def _fetch_webpage(self, url: str) -> Optional[dict]:
        """获取网页内容"""
        try:
            from bs4 import BeautifulSoup

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            }

            response = requests.get(url, headers=headers, timeout=30)
            response.encoding = response.apparent_encoding or 'utf-8'

            soup = BeautifulSoup(response.text, 'html.parser')

            # 移除脚本和样式
            for script in soup(['script', 'style', 'nav', 'footer', 'header']):
                script.decompose()

            # 获取标题
            title = soup.title.string if soup.title else ''
            if not title:
                title = soup.find('h1')
                title = title.get_text(strip=True) if title else url

            # 获取主要内容
            content = soup.find('article') or soup.find('main') or soup.find('div', class_=lambda x: x and 'content' in x.lower())
            if content:
                text = content.get_text(separator='\n', strip=True)
            else:
                text = soup.get_text(separator='\n', strip=True)

            # 限制文本长度
            max_length = 50000
            if len(text) > max_length:
                text = text[:max_length] + '\n\n... [内容已截断]'

            logger.info(f"网页获取成功: {url}, 标题: {title}, 内容长度: {len(text)}")
            return {
                'title': title,
                'content': text,
                'url': url
            }

        except Exception as e:
            logger.error(f"获取网页失败: {e}")
            return None

    def _translate_webpage(self, url: str) -> dict:
        """翻译网页内容"""
        logger.info(f"开始翻译网页: {url}")

        # 获取网页内容
        webpage = self._fetch_webpage(url)
        if not webpage:
            return {
                'success': False,
                'message': '获取网页内容失败'
            }

        # 翻译标题
        translator = self._get_text_translator()
        try:
            title_translated = translator.translate_text(
                f"请翻译以下标题为中文：{webpage['title']}",
                style="casual"
            )
            # 提取翻译后的标题
            if '翻译：' in title_translated:
                title_translated = title_translated.split('翻译：')[-1].strip()
        except Exception as e:
            logger.warning(f"标题翻译失败: {e}")
            title_translated = webpage['title']

        # 翻译内容（分段处理）
        content = webpage['content']
        max_chunk = 8000
        chunks = [content[i:i+max_chunk] for i in range(0, len(content), max_chunk)]

        translated_chunks = []
        for i, chunk in enumerate(chunks):
            logger.info(f"翻译网页内容 chunk {i+1}/{len(chunks)}")
            try:
                translated = translator.translate_text(
                    f"请将以下内容翻译成中文，保持原文格式：\n\n{chunk}",
                    style="casual"
                )
                translated_chunks.append(translated)
            except Exception as e:
                logger.warning(f"内容翻译失败 chunk {i+1}: {e}")
                translated_chunks.append(chunk)

        translated_content = '\n\n'.join(translated_chunks)

        return {
            'success': True,
            'message': '网页翻译完成',
            'title': webpage['title'],
            'title_translated': title_translated,
            'content': translated_content,
            'url': url
        }

    def _send_to_feishu(
        self,
        feishu_client,
        chat_id: Optional[str],
        user_id: Optional[str],
        result
    ):
        """发送翻译结果到飞书"""
        try:
            # 构建消息内容
            message = f"✅ 论文翻译完成！\n\n"
            message += f"📄 标题: {result.title}\n"
            message += f"📊 页数: {result.total_pages}\n"
            message += f"📖 术语数: {len(result.all_terms)}\n"
            message += f"🔢 公式数: {len(result.all_formulas)}\n"
            message += f"🖼️ 图表数: {len(result.all_figures)}\n"
            message += f"⏱️ 处理时间: {result.processing_time:.1f}秒\n\n"

            if result.output_path:
                # 上传文件到飞书
                file_url = self._upload_file_to_feishu(feishu_client, result.output_path)
                if file_url:
                    message += f"📥 下载翻译后的PDF: {file_url}"

            # 发送到群聊
            if chat_id and hasattr(feishu_client, 'send_message'):
                feishu_client.send_message(chat_id, message)
            elif user_id and hasattr(feishu_client, 'send_dm'):
                feishu_client.send_dm(user_id, message)

        except Exception as e:
            logger.error(f"发送飞书消息失败: {e}")

    def _upload_file_to_feishu(self, feishu_client, file_path: str) -> Optional[str]:
        """上传文件到飞书并返回下载链接"""
        try:
            # 飞书文件上传API
            upload_url = "https://open.feishu.cn/open-apis/drive/v1/files/upload_all"

            with open(file_path, 'rb') as f:
                files = {'file': (Path(file_path).name, f, 'application/pdf')}
                data = {
                    'parent_node': 'root',
                    'file_type': 'pdf'
                }
                headers = {
                    'Authorization': f'Bearer {feishu_client.access_token}'
                } if hasattr(feishu_client, 'access_token') else {}

                response = requests.post(
                    upload_url,
                    files=files,
                    data=data,
                    headers=headers,
                    timeout=60
                )

            if response.status_code == 200:
                result = response.json()
                if result.get('code') == 0:
                    return result.get('data', {}).get('download_url')

        except Exception as e:
            logger.error(f"上传文件到飞书失败: {e}")

        return None
