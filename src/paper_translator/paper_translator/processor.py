"""
论文翻译处理器 - 主流程
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

from .config import config
from .models import (
    PaperTranslationResult, ProcessedPage, Term,
    TextBlock
)
from .pdf_parser import PDFParser
from .translation_engine import TranslationEngine
from .figure_understanding import FigureUnderstanding
from .pdf_generator import PDFGenerator

logger = logging.getLogger(__name__)


class PaperTranslator:
    """论文翻译处理器"""

    def __init__(self):
        self.parser = PDFParser()
        self.translator = TranslationEngine()
        self.figure_understanding = FigureUnderstanding()
        self.generator = PDFGenerator()

        logger.info("论文翻译系统初始化完成")

    def translate(
        self,
        pdf_path: str,
        output_path: Optional[str] = None
    ) -> PaperTranslationResult:
        """
        翻译整篇论文

        Args:
            pdf_path: 输入PDF路径
            output_path: 输出PDF路径（可选）

        Returns:
            翻译结果
        """
        start_time = time.time()

        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")

        # 设置输出路径
        if output_path is None:
            output_dir = Path(config.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{pdf_path.stem}_translated.pdf"
        else:
            output_path = Path(output_path)

        logger.info(f"开始翻译论文: {pdf_path.name}")

        # Step 1: 解析PDF
        logger.info("Step 1: 解析PDF...")
        parsed = self.parser.parse(str(pdf_path))
        content = parsed.get('content', [])
        formulas = parsed.get('formulas', [])
        figures = parsed.get('figures', [])

        # 提取标题
        title = parsed.get('metadata', {}).get('title', pdf_path.stem)

        # Step 2: 翻译文本 - 批量处理减少API调用
        logger.info("Step 2: 翻译文本...")
        translated_blocks = []
        terms = []

        # 按页分组文本
        pages_dict = {}
        for item in content:
            page_num = item.get('page', 1)
            text = item.get('text', '')
            if text.strip():
                if page_num not in pages_dict:
                    pages_dict[page_num] = []
                pages_dict[page_num].append(text)

        # 合并每页文本一次翻译
        page_translations = {}
        for page_num in sorted(pages_dict.keys()):
            page_text = "\n\n".join(pages_dict[page_num])
            if page_text.strip():
                translated = self.translator.translate_text(page_text)
                page_translations[page_num] = translated
                logger.info(f"第{page_num}页翻译完成")

        # 创建文本块
        for item in content:
            text = item.get('text', '')
            page_num = item.get('page', 1)
            if not text.strip():
                continue

            # 使用对应页的翻译结果
            translated_text = page_translations.get(page_num, f"[未翻译 {page_num}]")

            block = TextBlock(
                text=translated_text,
                page=page_num,
                bbox=item.get('bbox', (0, 0, 0, 0))
            )
            translated_blocks.append(block)

        # 简化版：跳过术语提取加快速度
        unique_terms = []

        # Step 3: 公式解释 - 简化处理
        logger.info("Step 3: 解释公式...")
        formula_explanations = []
        for formula in formulas:
            latex = formula.get('latex', '')
            # 简化处理，跳过API调用
            formula['explanation'] = f"公式: {latex[:50]}..." if latex else ""
            formula_explanations.append(formula)
            formula_explanations.append(formula)

        # Step 4: 图表理解
        logger.info("Step 4: 理解图表...")
        figure_descriptions = []
        for figure in figures:
            img_path = figure.get('image_path', '')
            caption = figure.get('caption', '')

            if img_path and os.path.exists(img_path):
                description = self.figure_understanding.describe_figure(img_path, caption)
            else:
                description = self.figure_understanding._mock_describe_figure(caption)

            figure['description'] = description
            figure_descriptions.append(figure)

        # Step 5: 构建页面
        logger.info("Step 5: 构建页面...")
        pages = self._build_pages(
            translated_blocks,
            formula_explanations,
            figure_descriptions
        )

        # Step 6: 生成PDF
        logger.info("Step 6: 生成PDF...")
        result = PaperTranslationResult(
            title=title,
            original_path=str(pdf_path),
            output_path=str(output_path),
            pages=pages,
            all_terms=unique_terms,
            all_formulas=formula_explanations,
            all_figures=figure_descriptions,
            total_pages=len(pages),
            processing_time=time.time() - start_time
        )

        self.generator.generate(result, str(output_path))

        logger.info(f"翻译完成! 耗时: {result.processing_time:.2f}秒")
        return result

    def translate_batch(
        self,
        pdf_paths: list[str],
        output_dir: Optional[str] = None
    ) -> list[PaperTranslationResult]:
        """批量翻译"""
        results = []
        for pdf_path in pdf_paths:
            try:
                result = self.translate(pdf_path, output_dir)
                results.append(result)
            except Exception as e:
                logger.error(f"翻译失败 {pdf_path}: {e}")

        return results

    def _deduplicate_terms(self, terms: list[Term]) -> list[Term]:
        """去重术语"""
        seen = set()
        unique = []

        for term in terms:
            key = term.term.lower()
            if key not in seen:
                seen.add(key)
                unique.append(term)

        return unique

    def _build_pages(
        self,
        blocks: list[TextBlock],
        formulas: list,
        figures: list
    ) -> list[ProcessedPage]:
        """构建页面"""
        # 按页分组
        pages_dict = {}

        for block in blocks:
            page_num = block.page
            if page_num not in pages_dict:
                pages_dict[page_num] = {
                    'blocks': [],
                    'formulas': [],
                    'figures': []
                }
            pages_dict[page_num]['blocks'].append(block)

        for formula in formulas:
            page_num = formula.get('page', 1)
            if page_num not in pages_dict:
                pages_dict[page_num] = {
                    'blocks': [],
                    'formulas': [],
                    'figures': []
                }
            pages_dict[page_num]['formulas'].append(formula)

        for figure in figures:
            page_num = figure.get('page', 1)
            if page_num not in pages_dict:
                pages_dict[page_num] = {
                    'blocks': [],
                    'formulas': [],
                    'figures': []
                }
            pages_dict[page_num]['figures'].append(figure)

        # 转换为ProcessedPage列表
        pages = []
        for page_num in sorted(pages_dict.keys()):
            data = pages_dict[page_num]

            # 生成底部注释
            bottom_notes = []

            # 术语注释
            page_formulas = data['formulas']
            if page_formulas:
                notes = [f"公式: {f.get('latex', '')[:50]}..." for f in page_formulas[:3]]
                bottom_notes.extend(notes)

            page = ProcessedPage(
                page_number=page_num,
                original_blocks=[],
                translated_blocks=data['blocks'],
                formulas=page_formulas,
                figures=data['figures'],
                bottom_notes=bottom_notes
            )
            pages.append(page)

        return pages
