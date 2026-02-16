"""
PDF解析模块

使用MinerU解析PDF，提取文本、公式、图表等信息
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from paper_translator.models import Formula, Figure, TextBlock

logger = logging.getLogger(__name__)


class PDFParser:
    """PDF解析器 - 使用MinerU"""

    def __init__(self):
        self._mineru_available = None

    def _check_mineru(self) -> bool:
        """检查MinerU是否可用"""
        if self._mineru_available is not None:
            return self._mineru_available

        try:
            import magicoder
            self._mineru_available = True
            logger.info("MinerU 已安装")
            return True
        except ImportError:
            self._mineru_available = False
            logger.warning("MinerU 未安装，将使用备用解析方案")
            return False

    def parse(self, pdf_path: str) -> dict:
        """
        解析PDF文件

        Args:
            pdf_path: PDF文件路径

        Returns:
            解析结果字典，包含:
            - content: 文本内容
            - formulas: 公式列表
            - figures: 图表列表
            - layout: 布局信息
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")

        logger.info(f"开始解析PDF: {pdf_path.name}")

        if self._check_mineru():
            return self._parse_with_mineru(pdf_path)
        else:
            return self._parse_with_fallback(pdf_path)

    def _parse_with_mineru(self, pdf_path: Path) -> dict:
        """使用MinerU解析"""
        try:
            # MinerU 解析
            from magicoder import PDF2JSON

            # 创建临时输出目录
            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir) / "output"

                # 调用MinerU解析
                pdf2json = PDF2JSON()
                result = pdf2json.extract(str(pdf_path), str(output_dir))

                # 读取解析结果
                middle_json = output_dir / "middle.json"
                if middle_json.exists():
                    with open(middle_json, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    return self._convert_mineru_result(data)

            # 如果MinerU方式失败，使用备用方案
            raise Exception("MinerU解析失败")

        except Exception as e:
            logger.warning(f"MinerU解析失败: {e}，使用备用方案")
            return self._parse_with_fallback(pdf_path)

    def _parse_with_fallback(self, pdf_path: Path) -> dict:
        """备用解析方案 - 使用pdfplumber"""
        try:
            import pdfplumber
        except ImportError:
            logger.error("请安装pdfplumber: pip install pdfplumber")
            raise

        result = {
            'content': [],
            'formulas': [],
            'figures': [],
            'layout': [],
            'metadata': {}
        }

        with pdfplumber.open(pdf_path) as pdf:
            result['metadata'] = {
                'title': pdf.metadata.get('Title', ''),
                'author': pdf.metadata.get('Author', ''),
                'pages': len(pdf.pages)
            }

            for page_num, page in enumerate(pdf.pages, 1):
                # 提取文本
                text = page.extract_text()
                if text:
                    result['content'].append({
                        'page': page_num,
                        'text': text,
                    })

                # 提取表格
                tables = page.extract_tables()
                if tables:
                    logger.info(f"第{page_num}页发现 {len(tables)} 个表格")

                # 提取图片
                images = page.images
                if images:
                    logger.info(f"第{page_num}页发现 {len(images)} 张图片")

        return result

    def _convert_mineru_result(self, data: dict) -> dict:
        """转换MinerU结果为统一格式"""
        result = {
            'content': [],
            'formulas': [],
            'figures': [],
            'layout': [],
            'metadata': data.get('metadata', {})
        }

        # 提取文本块
        for item in data.get('content', []):
            page_num = item.get('page_num', 1)

            if item.get('type') == 'text':
                result['content'].append({
                    'page': page_num,
                    'text': item.get('text', ''),
                    'bbox': item.get('bbox', (0, 0, 0, 0)),
                    'is_heading': item.get('is_heading', False),
                    'heading_level': item.get('heading_level', 0),
                })

            elif item.get('type') == 'formula':
                result['formulas'].append({
                    'page': page_num,
                    'latex': item.get('text', ''),
                    'bbox': item.get('bbox', (0, 0, 0, 0)),
                    'context': '',
                })

            elif item.get('type') in ['figure', 'image']:
                result['figures'].append({
                    'page': page_num,
                    'caption': item.get('caption', ''),
                    'image_path': item.get('image_path', ''),
                    'bbox': item.get('bbox', (0, 0, 0, 0)),
                })

        return result

    def extract_text_only(self, pdf_path: str) -> str:
        """仅提取文本（简单模式）"""
        result = self.parse(pdf_path)
        texts = []
        for item in result.get('content', []):
            texts.append(item.get('text', ''))
        return '\n\n'.join(texts)
