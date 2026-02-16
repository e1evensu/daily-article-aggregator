"""
数据模型定义
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Formula:
    """公式数据"""
    latex: str                      # LaTeX源码
    page: int                       # 所在页码
    bbox: tuple                    # 位置坐标 (x0, y0, x1, y1)
    context: str = ""                # 上下文文本


@dataclass
class Figure:
    """图表数据"""
    image_path: str                 # 图片路径
    caption: str                   # 图注
    page: int                      # 所在页码
    bbox: tuple                   # 位置坐标


@dataclass
class TextBlock:
    """文本块"""
    text: str                      # 文本内容
    page: int                      # 页码
    bbox: tuple                   # 位置坐标
    is_heading: bool = False       # 是否为标题
    heading_level: int = 0        # 标题级别


@dataclass
class Term:
    """术语"""
    term: str                      # 英文术语
    translation: str               # 中文翻译
    explanation: str               # 解释说明
    first_appeared_page: int = 0  # 首次出现页码


@dataclass
class TranslationResult:
    """翻译结果"""
    original_text: str             # 原文
    translated_text: str           # 译文
    terms: list[Term] = field(default_factory=list)      # 术语列表
    formulas: list[Formula] = field(default_factory=list)  # 公式列表
    figures: list[Figure] = field(default_factory=list)   # 图表列表


@dataclass
class ProcessedPage:
    """处理后的页面"""
    page_number: int
    original_blocks: list[TextBlock]
    translated_blocks: list[TextBlock]
    formulas: list[Formula]
    figures: list[Figure]
    bottom_notes: list[str] = field(default_factory=list)   # 底部注释


@dataclass
class PaperTranslationResult:
    """整篇论文的翻译结果"""
    title: str
    original_path: str
    output_path: str

    pages: list[ProcessedPage] = field(default_factory=list)

    # 汇总信息
    all_terms: list[Term] = field(default_factory=list)
    all_formulas: list[Formula] = field(default_factory=list)
    all_figures: list[Figure] = field(default_factory=list)

    # 翻译统计
    total_pages: int = 0
    total_words: int = 0
    processing_time: float = 0.0
