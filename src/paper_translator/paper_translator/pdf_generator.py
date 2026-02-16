"""
PDF生成模块

生成带注释的PDF：
1. 保留原文格式
2. 添加底部注释
3. 生成术语表附录
"""

import logging
import os
from pathlib import Path
from typing import Optional
from datetime import datetime

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak,
    Table, TableStyle, Image as RLImage
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.fonts import addMapping

from .models import (
    ProcessedPage, PaperTranslationResult, Term
)

logger = logging.getLogger(__name__)

# 尝试注册中文字体
def _register_chinese_fonts():
    """注册中文字体"""
    try:
        # 尝试使用系统自带的中文字体
        import platform
        system = platform.system()

        font_paths = []
        if system == 'Windows':
            font_paths = [
                'C:/Windows/Fonts/simhei.ttf',   # 黑体
                'C:/Windows/Fonts/simsun.ttc',   # 宋体
                'C:/Windows/Fonts/msyh.ttc',     # 微软雅黑
            ]
        elif system == 'Linux':
            font_paths = [
                '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
                '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
                '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
            ]
        elif system == 'Darwin':
            font_paths = [
                '/System/Library/Fonts/PingFang.ttc',
                '/System/Library/Fonts/STHeiti Light.ttc',
            ]

        for font_path in font_paths:
            if os.path.exists(font_path):
                font_name = 'ChineseFont'
                pdfmetrics.registerFont(TTFont(font_name, font_path))
                addMapping('ChineseFont', 0, 0, font_name)
                addMapping('ChineseFont', 0, 1, font_name)
                addMapping('ChineseFont', 1, 0, font_name)
                logger.info(f"注册中文字体: {font_path}")
                return font_name

        logger.warning("未找到中文字体，将使用默认字体")
        return 'Helvetica'
    except Exception as e:
        logger.warning(f"字体注册失败: {e}")
        return 'Helvetica'

# 全局字体名称
CHINESE_FONT = _register_chinese_fonts()


class PDFGenerator:
    """PDF生成器"""

    def __init__(self):
        self._styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """设置自定义样式"""
        # 正文样式 - 先创建，因为它会被其他样式引用
        self._styles.add(ParagraphStyle(
            name='ChineseNormal',
            fontName=CHINESE_FONT,
            fontSize=10,
            leading=14,
            alignment=TA_LEFT,
        ))

        # 标题样式
        self._styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self._styles['Heading1'],
            fontSize=18,
            fontName=CHINESE_FONT,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=12,
        ))

        # 章节标题样式
        self._styles.add(ParagraphStyle(
            name='SectionTitle',
            parent=self._styles['Heading2'],
            fontName=CHINESE_FONT,
            fontSize=14,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=8,
            borderPadding=5,
        ))

        # 术语样式
        self._styles.add(ParagraphStyle(
            name='Term',
            parent=self._styles['ChineseNormal'],
            fontName=CHINESE_FONT,
            fontSize=10,
            textColor=colors.HexColor('#2980b9'),
            spaceAfter=3,
        ))

        # 注释样式
        self._styles.add(ParagraphStyle(
            name='Note',
            parent=self._styles['ChineseNormal'],
            fontName=CHINESE_FONT,
            fontSize=9,
            textColor=colors.HexColor('#7f8c8d'),
            spaceAfter=3,
        ))

    def generate(
        self,
        result: PaperTranslationResult,
        output_path: str
    ) -> str:
        """
        生成带注释的PDF

        Args:
            result: 翻译结果
            output_path: 输出路径

        Returns:
            生成的PDF路径
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"开始生成PDF: {output_path}")

        # 创建PDF文档
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72,
        )

        # 构建故事
        story = []

        # 1. 标题页
        story.extend(self._build_title_page(result))

        # 2. 原文页面（简化版：每页原文+译文对照+底部注释）
        story.extend(self._build_content_pages(result))

        # 3. 术语表附录
        story.extend(self._build_glossary_page(result.all_terms))

        # 4. 公式解释附录
        if result.all_formulas:
            story.extend(self._build_formula_appendix(result.all_formulas))

        # 5. 图表说明附录
        if result.all_figures:
            story.extend(self._build_figure_appendix(result.all_figures))

        # 生成PDF
        doc.build(story)

        logger.info(f"PDF生成完成: {output_path}")
        return str(output_path)

    def _build_title_page(self, result: PaperTranslationResult):
        """构建标题页"""
        story = []

        # 标题
        title = Paragraph(
            f"论文翻译：{result.title}",
            self._styles['CustomTitle']
        )
        story.append(title)
        story.append(Spacer(1, 0.3 * inch))

        # 副标题
        subtitle = Paragraph(
            "含专业术语解释、公式说明、图表描述",
            self._styles['ChineseNormal']
        )
        story.append(subtitle)
        story.append(Spacer(1, 0.5 * inch))

        # 元信息
        meta = f"""
        <br/>
        原文路径：{result.original_path}<br/>
        翻译时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}<br/>
        页数：{result.total_pages}<br/>
        """
        story.append(Paragraph(meta, self._styles['ChineseNormal']))
        story.append(PageBreak())

        return story

    def _build_content_pages(self, result: PaperTranslationResult):
        """构建内容页面"""
        story = []

        story.append(Paragraph("正文翻译", self._styles['SectionTitle']))
        story.append(Spacer(1, 0.2 * inch))

        # 简化处理：输出翻译后的文本
        for i, page in enumerate(result.pages):
            # 页码
            story.append(Paragraph(
                f"<b>第 {page.page_number} 页</b>",
                self._styles['Term']
            ))

            # 翻译后的文本
            for block in page.translated_blocks:
                story.append(Paragraph(block.text, self._styles['ChineseNormal']))
                story.append(Spacer(1, 0.1 * inch))

            # 底部注释
            if page.bottom_notes:
                story.append(Spacer(1, 0.2 * inch))
                story.append(Paragraph("<b>注释：</b>", self._styles['Term']))
                for note in page.bottom_notes:
                    story.append(Paragraph(note, self._styles['Note']))

            story.append(PageBreak())

        return story

    def _build_glossary_page(self, terms: list[Term]):
        """构建术语表"""
        story = []

        story.append(PageBreak())
        story.append(Paragraph("附录1：专业术语表", self._styles['SectionTitle']))
        story.append(Spacer(1, 0.2 * inch))

        if not terms:
            story.append(Paragraph("无术语记录", self._styles['ChineseNormal']))
            return story

        # 术语表格
        data = [['英文术语', '中文翻译', '解释']]

        for term in terms:
            data.append([
                term.term,
                term.translation,
                term.explanation
            ])

        table = Table(data, colWidths=[1.5*inch, 1.5*inch, 3*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))

        story.append(table)

        return story

    def _build_formula_appendix(self, formulas: list):
        """构建公式解释附录"""
        story = []

        story.append(PageBreak())
        story.append(Paragraph("附录2：公式解释", self._styles['SectionTitle']))
        story.append(Spacer(1, 0.2 * inch))

        for i, formula in enumerate(formulas, 1):
            # 公式
            story.append(Paragraph(
                f"<b>公式 {i}</b>: <code>{formula.get('latex', '')}</code>",
                self._styles['Term']
            ))
            story.append(Spacer(1, 0.1 * inch))

            # 解释
            explanation = formula.get('explanation', '暂无解释')
            story.append(Paragraph(explanation, self._styles['ChineseNormal']))
            story.append(Spacer(1, 0.2 * inch))

        return story

    def _build_figure_appendix(self, figures: list):
        """构建图表说明附录"""
        story = []

        story.append(PageBreak())
        story.append(Paragraph("附录3：图表说明", self._styles['SectionTitle']))
        story.append(Spacer(1, 0.2 * inch))

        for i, figure in enumerate(figures, 1):
            # 图注
            caption = figure.get('caption', f'图 {i}')
            story.append(Paragraph(f"<b>{caption}</b>", self._styles['Term']))
            story.append(Spacer(1, 0.1 * inch))

            # 描述
            description = figure.get('description', '暂无描述')
            story.append(Paragraph(description, self._styles['ChineseNormal']))
            story.append(Spacer(1, 0.2 * inch))

        return story
