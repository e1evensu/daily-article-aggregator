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

        logger.info(f"开始处理PDF: {pdf_url}")
        start_time = time.time()

        try:
            # 0. 处理纯 arXiv ID（如 2501.12345）转换为 URL
            cleaned_url = pdf_url.strip()
            # 检查是否是纯 arXiv ID（如 2501.12345 或 arxiv:2501.12345）
            import re
            if re.match(r'^\d{4}\.\d{4,5}$', cleaned_url):
                # 转换为 arXiv URL
                cleaned_url = f"https://arxiv.org/abs/{cleaned_url}"
                logger.info(f"已将 arXiv ID 转换为 URL: {cleaned_url}")
            elif cleaned_url.startswith('arxiv:'):
                arxiv_id = cleaned_url[6:].strip()
                cleaned_url = f"https://arxiv.org/abs/{arxiv_id}"
                logger.info(f"已将 arXiv ID 转换为 URL: {cleaned_url}")

            # 1. 下载PDF
            pdf_path = self._download_pdf(cleaned_url)
            if not pdf_path:
                return {
                    'success': False,
                    'message': '下载PDF失败'
                }

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
