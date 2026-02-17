"""
知识 RSS 生成器模块

负责生成自建知识库的 RSS 订阅源。
将综述文档转换为 RSS 2.0 格式，支持条目限制和增量更新。

Requirements:
- 5.1: 生成 RSS 2.0 格式的订阅源
- 5.2: 每个综述作为一个 RSS 条目
- 5.3: 包含标题、摘要、链接、发布时间
- 5.4: 支持条目数量限制
- 5.5: 支持增量更新（加载现有条目）
- 5.6: 保存到文件
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any
from email.utils import formatdate
import time

from src.aggregation.models import Synthesis, RSSItem

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_MAX_ITEMS = 100
DEFAULT_FEED_TITLE = "知识聚合 RSS"
DEFAULT_FEED_DESCRIPTION = "自动聚合的技术知识综述"
DEFAULT_FEED_LINK = "https://example.com/knowledge-feed"


class KnowledgeRSSGenerator:
    """
    知识 RSS 生成器
    
    生成自建知识库的 RSS 订阅源。
    
    Attributes:
        output_path: RSS 文件输出路径
        max_items: 最大条目数量
        feed_title: RSS 标题
        feed_description: RSS 描述
        feed_link: RSS 链接
    """
    
    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化 RSS 生成器
        
        Args:
            config: 配置字典，包含：
                - output_path: RSS 文件输出路径
                - max_items: 最大条目数量
                - feed_title: RSS 标题
                - feed_description: RSS 描述
                - feed_link: RSS 链接
        """
        config = config or {}
        
        self.output_path = Path(config.get('output_path', 'data/knowledge_feed.xml'))
        self.max_items = config.get('max_items', DEFAULT_MAX_ITEMS)
        self.feed_title = config.get('feed_title', DEFAULT_FEED_TITLE)
        self.feed_description = config.get('feed_description', DEFAULT_FEED_DESCRIPTION)
        self.feed_link = config.get('feed_link', DEFAULT_FEED_LINK)
        
        # 确保输出目录存在
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 内存中的条目列表
        self._items: list[RSSItem] = []
        
        logger.info(f"KnowledgeRSSGenerator 初始化完成，输出路径: {self.output_path}")
    
    def add_item(self, item: RSSItem):
        """
        添加 RSS 条目
        
        Args:
            item: RSS 条目
        
        Requirements:
            - 5.2: 每个综述作为一个 RSS 条目
        """
        # 检查是否已存在相同 ID 的条目
        existing_ids = {i.item_id for i in self._items}
        if item.item_id in existing_ids:
            logger.debug(f"条目已存在，跳过: {item.item_id}")
            return
        
        self._items.append(item)
        logger.debug(f"添加 RSS 条目: {item.title}")
    
    def add_synthesis(self, synthesis: Synthesis, doc_url: str | None = None):
        """
        从综述添加 RSS 条目
        
        Args:
            synthesis: 综述对象
            doc_url: 文档 URL（可选）
        
        Requirements:
            - 5.2: 每个综述作为一个 RSS 条目
            - 5.3: 包含标题、摘要、链接、发布时间
        """
        # 生成摘要（取前 500 字符）
        description = synthesis.content[:500] if synthesis.content else ""
        if len(synthesis.content) > 500:
            description += "..."
        
        item = RSSItem(
            item_id=synthesis.id,
            title=synthesis.title,
            link=doc_url or self.feed_link,
            description=description,
            pub_date=synthesis.generated_at or datetime.now(),
            categories=synthesis.key_points[:5] if synthesis.key_points else []
        )
        
        self.add_item(item)
    
    def generate_feed(self) -> str:
        """
        生成 RSS 2.0 XML
        
        Returns:
            RSS XML 字符串
        
        Requirements:
            - 5.1: 生成 RSS 2.0 格式的订阅源
            - 5.4: 支持条目数量限制
        """
        # 创建根元素
        rss = ET.Element('rss', version='2.0')
        channel = ET.SubElement(rss, 'channel')
        
        # 添加频道信息
        ET.SubElement(channel, 'title').text = self.feed_title
        ET.SubElement(channel, 'link').text = self.feed_link
        ET.SubElement(channel, 'description').text = self.feed_description
        ET.SubElement(channel, 'language').text = 'zh-CN'
        ET.SubElement(channel, 'lastBuildDate').text = formatdate(time.time())
        ET.SubElement(channel, 'generator').text = 'KnowledgeRSSGenerator'
        
        # 按发布时间排序（最新的在前）
        sorted_items = sorted(
            self._items, 
            key=lambda x: x.pub_date or datetime.min, 
            reverse=True
        )
        
        # 限制条目数量
        limited_items = sorted_items[:self.max_items]
        
        # 添加条目
        for item in limited_items:
            item_elem = ET.SubElement(channel, 'item')
            
            ET.SubElement(item_elem, 'title').text = item.title
            ET.SubElement(item_elem, 'link').text = item.link
            ET.SubElement(item_elem, 'description').text = item.description
            ET.SubElement(item_elem, 'guid', isPermaLink='false').text = item.item_id
            
            if item.pub_date:
                pub_timestamp = item.pub_date.timestamp()
                ET.SubElement(item_elem, 'pubDate').text = formatdate(pub_timestamp)
            
            # 添加分类
            for category in item.categories:
                ET.SubElement(item_elem, 'category').text = category
        
        # 生成 XML 字符串
        xml_str = ET.tostring(rss, encoding='unicode', method='xml')
        
        # 添加 XML 声明
        xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
        
        return xml_declaration + xml_str
    
    def save_feed(self, path: str | Path | None = None) -> str:
        """
        保存 RSS 到文件
        
        Args:
            path: 输出路径（可选，默认使用配置的路径）
        
        Returns:
            保存的文件路径
        
        Requirements:
            - 5.6: 保存到文件
        """
        output_path = Path(path) if path else self.output_path
        
        # 生成 RSS
        xml_content = self.generate_feed()
        
        # 写入文件
        output_path.write_text(xml_content, encoding='utf-8')
        
        logger.info(f"RSS 已保存: {output_path} ({len(self._items)} 条目)")
        
        return str(output_path)
    
    def load_existing_items(self, path: str | Path | None = None) -> int:
        """
        加载现有 RSS 条目
        
        Args:
            path: RSS 文件路径（可选，默认使用配置的路径）
        
        Returns:
            加载的条目数量
        
        Requirements:
            - 5.5: 支持增量更新（加载现有条目）
        """
        input_path = Path(path) if path else self.output_path
        
        if not input_path.exists():
            logger.debug(f"RSS 文件不存在: {input_path}")
            return 0
        
        try:
            tree = ET.parse(input_path)
            root = tree.getroot()
            
            channel = root.find('channel')
            if channel is None:
                logger.warning("RSS 文件格式错误：未找到 channel 元素")
                return 0
            
            loaded_count = 0
            for item_elem in channel.findall('item'):
                try:
                    title = item_elem.findtext('title', '')
                    link = item_elem.findtext('link', '')
                    description = item_elem.findtext('description', '')
                    guid = item_elem.findtext('guid', '')
                    pub_date_str = item_elem.findtext('pubDate', '')
                    
                    # 解析发布时间
                    pub_date = None
                    if pub_date_str:
                        try:
                            from email.utils import parsedate_to_datetime
                            pub_date = parsedate_to_datetime(pub_date_str)
                        except Exception:
                            pass
                    
                    # 解析分类
                    categories = [
                        cat.text for cat in item_elem.findall('category') 
                        if cat.text
                    ]
                    
                    item = RSSItem(
                        item_id=guid or f"item_{loaded_count}",
                        title=title,
                        link=link,
                        description=description,
                        pub_date=pub_date,
                        categories=categories
                    )
                    
                    self.add_item(item)
                    loaded_count += 1
                    
                except Exception as e:
                    logger.warning(f"解析 RSS 条目失败: {e}")
                    continue
            
            logger.info(f"从 {input_path} 加载了 {loaded_count} 个条目")
            return loaded_count
            
        except ET.ParseError as e:
            logger.error(f"解析 RSS 文件失败: {e}")
            return 0
        except Exception as e:
            logger.error(f"加载 RSS 文件时发生错误: {e}")
            return 0
    
    def get_items(self) -> list[RSSItem]:
        """
        获取所有条目
        
        Returns:
            RSS 条目列表
        """
        return self._items.copy()
    
    def clear_items(self):
        """清除所有条目"""
        self._items.clear()
        logger.debug("RSS 条目已清除")
