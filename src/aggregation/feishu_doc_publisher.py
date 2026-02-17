"""
飞书文档发布器模块

负责将综述发布到飞书文档。
支持 Markdown 到飞书块的转换，以及本地备份功能。

使用飞书文档 API 流程：
1. POST /docx/v1/documents - 创建空文档（只有标题）
2. 获取文档的根 block_id（document_id 即为根 block_id）
3. POST /docx/v1/documents/:document_id/blocks/:block_id/children - 添加内容块

Requirements:
- 4.1: 将综述发布到飞书文档
- 4.2: 支持 Markdown 格式转换为飞书块
- 4.3: 支持标题层级、代码块、超链接、列表格式
- 4.4: 添加元数据（生成时间、文章数量、话题关键词）
- 4.5: API 失败时保存本地备份
- 4.6: 返回发布结果（成功/失败、文档链接）
"""

import json
import logging
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from src.aggregation.models import Synthesis, PublishResult

logger = logging.getLogger(__name__)

# 飞书文档块类型常量
BLOCK_TYPE_PAGE = 1
BLOCK_TYPE_TEXT = 2
BLOCK_TYPE_HEADING1 = 3
BLOCK_TYPE_HEADING2 = 4
BLOCK_TYPE_HEADING3 = 5
BLOCK_TYPE_HEADING4 = 6
BLOCK_TYPE_HEADING5 = 7
BLOCK_TYPE_HEADING6 = 8
BLOCK_TYPE_HEADING7 = 9
BLOCK_TYPE_HEADING8 = 10
BLOCK_TYPE_HEADING9 = 11
BLOCK_TYPE_BULLET = 12
BLOCK_TYPE_ORDERED = 13
BLOCK_TYPE_CODE = 14
BLOCK_TYPE_QUOTE = 15
BLOCK_TYPE_DIVIDER = 22


class FeishuDocPublisher:
    """
    飞书文档发布器
    
    将综述发布到飞书文档，支持 Markdown 转换和本地备份。
    
    Attributes:
        app_id: 飞书应用 ID
        app_secret: 飞书应用密钥
        folder_token: 目标文件夹 Token
        backup_dir: 本地备份目录
    """
    
    BASE_URL = "https://open.feishu.cn/open-apis"
    
    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化飞书文档发布器
        
        Args:
            config: 配置字典，包含：
                - app_id: 飞书应用 ID
                - app_secret: 飞书应用密钥
                - folder_token: 目标文件夹 Token
                - backup_dir: 本地备份目录
        """
        config = config or {}
        
        self.app_id = config.get('app_id', '')
        self.app_secret = config.get('app_secret', '')
        self.folder_token = config.get('folder_token', '')
        self.backup_dir = Path(config.get('backup_dir', 'data/doc_backups'))
        
        # 确保备份目录存在
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None
        
        logger.info("FeishuDocPublisher 初始化完成")
    
    def _get_access_token(self) -> str | None:
        """
        获取飞书访问令牌
        
        Returns:
            访问令牌，失败返回 None
        """
        if not self.app_id or not self.app_secret:
            logger.warning("飞书应用凭证未配置")
            return None
        
        # 检查缓存的 token 是否有效
        if self._access_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at:
                return self._access_token
        
        try:
            url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
            response = requests.post(
                url,
                json={
                    "app_id": self.app_id,
                    "app_secret": self.app_secret
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0:
                    self._access_token = data.get('tenant_access_token')
                    expire_seconds = data.get('expire', 7200) - 300
                    self._token_expires_at = datetime.now() + timedelta(seconds=expire_seconds)
                    return self._access_token
                else:
                    logger.error(f"获取飞书 token 失败: {data.get('msg')}")
            else:
                logger.error(f"获取飞书 token 请求失败: {response.status_code}")
            
            return None
        except Exception as e:
            logger.error(f"获取飞书 token 时发生错误: {e}")
            return None
    
    def _get_headers(self) -> dict | None:
        """获取带授权的请求头"""
        token = self._get_access_token()
        if not token:
            return None
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    
    # ==================== 块创建辅助方法 ====================
    
    def _create_text_element(self, text: str, link: str | None = None) -> dict:
        """创建文本元素"""
        element = {
            "text_run": {
                "content": text,
                "text_element_style": {}
            }
        }
        if link:
            element["text_run"]["text_element_style"]["link"] = {"url": link}
        return element
    
    def _create_text_block(self, text: str) -> dict:
        """创建文本块"""
        return {
            "block_type": BLOCK_TYPE_TEXT,
            "text": {
                "elements": [self._create_text_element(text)],
                "style": {}
            }
        }
    
    def _create_heading_block(self, text: str, level: int = 2) -> dict:
        """创建标题块"""
        heading_types = {
            1: BLOCK_TYPE_HEADING1, 2: BLOCK_TYPE_HEADING2,
            3: BLOCK_TYPE_HEADING3, 4: BLOCK_TYPE_HEADING4,
            5: BLOCK_TYPE_HEADING5, 6: BLOCK_TYPE_HEADING6,
            7: BLOCK_TYPE_HEADING7, 8: BLOCK_TYPE_HEADING8,
            9: BLOCK_TYPE_HEADING9,
        }
        block_type = heading_types.get(min(level, 9), BLOCK_TYPE_HEADING2)
        heading_key = f"heading{min(level, 9)}"
        
        return {
            "block_type": block_type,
            heading_key: {
                "elements": [self._create_text_element(text)],
                "style": {}
            }
        }
    
    def _create_bullet_block(self, elements: list[dict]) -> dict:
        """创建无序列表项块"""
        return {
            "block_type": BLOCK_TYPE_BULLET,
            "bullet": {
                "elements": elements,
                "style": {}
            }
        }
    
    def _create_ordered_block(self, elements: list[dict]) -> dict:
        """创建有序列表项块"""
        return {
            "block_type": BLOCK_TYPE_ORDERED,
            "ordered": {
                "elements": elements,
                "style": {}
            }
        }
    
    def _create_code_block(self, code: str, language: str = "text") -> dict:
        """创建代码块"""
        lang_map = {
            "python": 49, "javascript": 22, "typescript": 67,
            "java": 21, "go": 18, "rust": 54, "c": 7, "cpp": 8,
            "shell": 57, "bash": 4, "sql": 59, "json": 23,
            "yaml": 73, "xml": 72, "html": 19, "css": 10, "text": 66,
        }
        lang_code = lang_map.get(language.lower(), 66)
        
        return {
            "block_type": BLOCK_TYPE_CODE,
            "code": {
                "elements": [self._create_text_element(code)],
                "style": {"language": lang_code}
            }
        }
    
    def _create_quote_block(self, text: str) -> dict:
        """创建引用块"""
        return {
            "block_type": BLOCK_TYPE_QUOTE,
            "quote": {
                "elements": [self._create_text_element(text)],
                "style": {}
            }
        }
    
    def _create_divider_block(self) -> dict:
        """创建分割线块"""
        return {"block_type": BLOCK_TYPE_DIVIDER, "divider": {}}
    
    def _create_rich_text_block(self, elements: list[dict]) -> dict:
        """创建富文本块"""
        return {
            "block_type": BLOCK_TYPE_TEXT,
            "text": {"elements": elements, "style": {}}
        }

    
    # ==================== Markdown 转换 ====================
    
    def _parse_inline_elements(self, text: str) -> list[dict]:
        """解析行内元素（链接等）"""
        elements = []
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        
        last_end = 0
        for match in re.finditer(link_pattern, text):
            if match.start() > last_end:
                plain_text = text[last_end:match.start()]
                if plain_text:
                    elements.append(self._create_text_element(plain_text))
            
            link_text = match.group(1)
            link_url = match.group(2)
            elements.append(self._create_text_element(link_text, link_url))
            last_end = match.end()
        
        if last_end < len(text):
            remaining = text[last_end:]
            if remaining:
                elements.append(self._create_text_element(remaining))
        
        if not elements:
            elements.append(self._create_text_element(text))
        
        return elements
    
    def convert_to_feishu_blocks(self, markdown: str) -> list[dict]:
        """
        将 Markdown 转换为飞书块格式
        
        Args:
            markdown: Markdown 文本
        
        Returns:
            飞书块列表
        """
        blocks = []
        lines = markdown.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # 空行 - 跳过
            if not line.strip():
                i += 1
                continue
            
            # 标题 (# ## ### etc.)
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if heading_match:
                level = len(heading_match.group(1))
                text = heading_match.group(2)
                blocks.append(self._create_heading_block(text, level))
                i += 1
                continue
            
            # 代码块 (```)
            if line.startswith('```'):
                language = line[3:].strip() or "text"
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].startswith('```'):
                    code_lines.append(lines[i])
                    i += 1
                i += 1  # 跳过结束的 ```
                blocks.append(self._create_code_block("\n".join(code_lines), language))
                continue
            
            # 引用块 (>)
            if line.startswith('>'):
                quote_text = line[1:].strip()
                blocks.append(self._create_quote_block(quote_text))
                i += 1
                continue
            
            # 分割线 (--- or ***)
            if re.match(r'^[-*]{3,}$', line.strip()):
                blocks.append(self._create_divider_block())
                i += 1
                continue
            
            # 无序列表 (- or *)
            if re.match(r'^[-*]\s+', line):
                item_text = re.sub(r'^[-*]\s+', '', line)
                elements = self._parse_inline_elements(item_text)
                blocks.append(self._create_bullet_block(elements))
                i += 1
                continue
            
            # 有序列表 (1. 2. etc.)
            if re.match(r'^\d+\.\s+', line):
                item_text = re.sub(r'^\d+\.\s+', '', line)
                elements = self._parse_inline_elements(item_text)
                blocks.append(self._create_ordered_block(elements))
                i += 1
                continue
            
            # 普通段落
            elements = self._parse_inline_elements(line)
            blocks.append(self._create_rich_text_block(elements))
            i += 1
        
        return blocks

    
    # ==================== 文档 API 操作 ====================
    
    def _create_empty_document(self, title: str) -> tuple[str | None, str | None]:
        """
        创建空文档
        
        Args:
            title: 文档标题
        
        Returns:
            (document_id, 错误信息)
        """
        headers = self._get_headers()
        if not headers:
            return None, "无法获取访问令牌"
        
        try:
            url = f"{self.BASE_URL}/docx/v1/documents"
            payload = {"title": title}
            if self.folder_token:
                payload["folder_token"] = self.folder_token
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code != 200:
                return None, f"HTTP {response.status_code}: {response.text}"
            
            data = response.json()
            if data.get('code') != 0:
                return None, f"API 错误: {data.get('msg')}"
            
            document_id = data.get('data', {}).get('document', {}).get('document_id')
            if not document_id:
                return None, "未返回 document_id"
            
            logger.info(f"创建空文档成功: {document_id}")
            return document_id, None
            
        except Exception as e:
            return None, f"请求异常: {e}"
    
    def _add_blocks_to_document(
        self, 
        document_id: str, 
        blocks: list[dict],
        batch_size: int = 50
    ) -> tuple[bool, str | None]:
        """
        向文档添加内容块
        
        Args:
            document_id: 文档 ID（同时也是根 block_id）
            blocks: 要添加的块列表
            batch_size: 每批添加的块数量
        
        Returns:
            (成功标志, 错误信息)
        """
        if not blocks:
            return True, None
        
        headers = self._get_headers()
        if not headers:
            return False, "无法获取访问令牌"
        
        # 文档的根 block_id 就是 document_id
        block_id = document_id
        url = f"{self.BASE_URL}/docx/v1/documents/{document_id}/blocks/{block_id}/children"
        
        try:
            # 分批添加块
            for i in range(0, len(blocks), batch_size):
                batch = blocks[i:i + batch_size]
                
                payload = {
                    "children": batch,
                    "index": -1  # 追加到末尾
                }
                
                response = requests.post(
                    url, 
                    headers=headers, 
                    json=payload, 
                    timeout=60
                )
                
                if response.status_code != 200:
                    logger.error(f"添加块失败: HTTP {response.status_code}")
                    logger.error(f"响应: {response.text}")
                    return False, f"HTTP {response.status_code}: {response.text}"
                
                data = response.json()
                if data.get('code') != 0:
                    logger.error(f"添加块 API 错误: {data.get('msg')}")
                    return False, f"API 错误: {data.get('msg')}"
                
                logger.debug(f"成功添加 {len(batch)} 个块")
            
            logger.info(f"成功添加 {len(blocks)} 个块到文档")
            return True, None
            
        except Exception as e:
            logger.error(f"添加块时发生异常: {e}")
            return False, f"请求异常: {e}"
    
    def create_document(
        self, 
        title: str, 
        blocks: list[dict]
    ) -> tuple[bool, str | None]:
        """
        创建飞书文档并添加内容
        
        Args:
            title: 文档标题
            blocks: 飞书块列表
        
        Returns:
            (成功标志, 文档 URL 或 None)
        """
        # 步骤 1: 创建空文档
        document_id, error = self._create_empty_document(title)
        if not document_id:
            logger.error(f"创建文档失败: {error}")
            return False, None
        
        # 步骤 2: 添加内容块
        if blocks:
            success, error = self._add_blocks_to_document(document_id, blocks)
            if not success:
                logger.warning(f"添加内容块失败: {error}，但文档已创建")
                # 文档已创建，返回 URL（内容可能不完整）
        
        doc_url = f"https://feishu.cn/docx/{document_id}"
        logger.info(f"文档创建完成: {doc_url}")
        return True, doc_url

    
    # ==================== 备份和发布 ====================
    
    def save_local_backup(self, synthesis: Synthesis) -> str:
        """
        保存本地备份
        
        Args:
            synthesis: 综述对象
        
        Returns:
            备份文件路径
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"synthesis_{synthesis.cluster_id}_{timestamp}.md"
        filepath = self.backup_dir / filename

        content = f"""# {synthesis.title}

**生成时间**: {synthesis.generated_at.isoformat() if synthesis.generated_at else 'N/A'}
**话题 ID**: {synthesis.cluster_id}

---

{synthesis.content}

---

## 参考来源

"""
        for i, ref in enumerate(synthesis.references, 1):
            title = ref.get('title', '未知标题')
            url = ref.get('url', '')
            source = ref.get('source', '')
            content += f"{i}. [{title}]({url}) - {source}\n"
        
        filepath.write_text(content, encoding='utf-8')
        logger.info(f"本地备份已保存: {filepath}")
        return str(filepath)
    
    def publish(self, synthesis: Synthesis) -> PublishResult:
        """
        发布综述到飞书文档
        
        Args:
            synthesis: 综述对象
        
        Returns:
            PublishResult 对象
        """
        # 添加元数据到内容
        gen_time = synthesis.generated_at.isoformat() if synthesis.generated_at else datetime.now().isoformat()
        keywords = ', '.join(synthesis.key_points[:5]) if synthesis.key_points else 'N/A'
        
        metadata = f"""> **生成时间**: {gen_time}
> **文章数量**: {len(synthesis.references)}
> **关键词**: {keywords}

"""
        full_content = metadata + synthesis.content
        
        # 添加参考来源
        if synthesis.references:
            full_content += "\n\n---\n\n## 参考来源\n\n"
            for i, ref in enumerate(synthesis.references, 1):
                title = ref.get('title', '未知标题')
                url = ref.get('url', '')
                source = ref.get('source', '')
                full_content += f"{i}. [{title}]({url})"
                if source:
                    full_content += f" - {source}"
                full_content += "\n"
        
        # 转换为飞书块
        blocks = self.convert_to_feishu_blocks(full_content)
        
        # 尝试发布
        success, doc_url = self.create_document(synthesis.title, blocks)
        
        if success and doc_url:
            return PublishResult(
                success=True,
                synthesis_id=synthesis.id,
                document_url=doc_url,
                published_at=datetime.now()
            )
        
        # 发布失败，保存本地备份
        backup_path = self.save_local_backup(synthesis)
        
        return PublishResult(
            success=False,
            synthesis_id=synthesis.id,
            document_url=None,
            error_message=f"发布失败，已保存本地备份: {backup_path}",
            published_at=datetime.now()
        )

    # ==================== 日报相关常量和辅助方法 ====================

    # 分类关键词映射
    CATEGORY_KEYWORDS = {
        "AI/ML": ["ai", "artificial intelligence", "machine learning", "llm", "deep learning",
                  "神经网络", "机器学习", "深度学习", "大语言模型", "gpt", "chatgpt", "claude",
                  "transformer", "langchain", "aigc", "生成式ai", "人工智能"],
        "安全": ["security", "privacy", "vulnerability", "encryption", "hack", "attack",
                "安全", "隐私", "漏洞", "加密", "黑客", "威胁", "cve", "渗透", "恶意软件"],
        "工程": ["software engineering", "architecture", "programming", "system design",
                "软件工程", "架构", "编程", "系统设计", "开发", "代码", "algorithm",
                "database", "distributed", "微服务", "kubernetes", "devops", "云原生"],
        "工具/开源": ["tool", "open source", "framework", "library", "开发工具", "开源",
                    "github", "vscode", " IDE", "terminal", "效率", " productivity"],
        "观点/杂谈": ["opinion", "perspective", "thought", "analysis", "趋势", "观察",
                    "行业", "观点", "思考", "评论", "review", "展望", "未来"],
    }

    # 分类显示名称
    CATEGORY_NAMES = {
        "AI/ML": "AI/ML",
        "安全": "安全",
        "工程": "工程",
        "工具/开源": "工具/开源",
        "观点/杂谈": "观点/杂谈",
        "其他": "其他",
    }

    def _classify_article(self, article: dict | Any) -> str:
        """
        根据文章内容分类

        Args:
            article: 文章对象（dict 或 Article）

        Returns:
            分类名称
        """
        # 获取文章标题和摘要
        if hasattr(article, 'title'):
            title = article.title.lower()
            summary = getattr(article, 'summary', '') or ''
            if hasattr(summary, 'lower'):
                summary = summary.lower()
        else:
            title = str(article.get('title', '')).lower()
            summary = str(article.get('summary', '')).lower()

        text = f"{title} {summary}".lower()

        # 匹配分类
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    return category

        return "其他"

    def _get_all_keywords(self, articles: list) -> list[str]:
        """从所有文章中提取关键词"""
        all_keywords = []
        for article in articles:
            if hasattr(article, 'keywords'):
                kw_list = article.keywords
            else:
                kw_list = article.get('keywords', [])
            all_keywords.extend(kw_list)
        return all_keywords

    def _generate_trend_summary(self, articles: list, categories: dict) -> str:
        """
        生成宏观趋势总结

        Args:
            articles: 文章列表
            categories: 分类统计

        Returns:
            3-5句话的趋势总结
        """
        total = len(articles)
        category_counts = {cat: len(arts) for cat, arts in categories.items()}

        # 获取最热门的分类
        top_cats = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)

        sentences = []

        # 基础统计
        sentences.append(f"今日共收录 {total} 篇优质技术文章，涵盖六大领域。")

        # 热门分类
        if top_cats:
            top_cat_name = self.CATEGORY_NAMES.get(top_cats[0][0], top_cats[0][0])
            sentences.append(f"{top_cat_name} 领域持续火热，占据今日文章的 {top_cats[0][1] * 100 // total}%。")

        # 趋势洞察
        if "AI/ML" in category_counts and category_counts["AI/ML"] > 0:
            sentences.append("AI 领域继续保持高速发展态势，多项重磅研究和应用值得关注。")

        # 安全态势
        if "安全" in category_counts and category_counts["安全"] > 0:
            sentences.append(f"安全领域有 {category_counts['安全']} 篇新文章，安全威胁形势依然严峻。")

        # 工程实践
        if "工程" in category_counts and category_counts["工程"] > 0:
            sentences.append("工程实践类文章丰富，软件架构和系统设计仍是业界关注焦点。")

        return " ".join(sentences[:5])  # 最多5句

    def _generate_ascii_pie_chart(self, data: dict[str, int], width: int = 40) -> str:
        """
        生成 ASCII 饼图

        Args:
            data: 数据字典 {label: count}
            width: 图表宽度

        Returns:
            ASCII 饼图字符串
        """
        total = sum(data.values())
        if total == 0:
            return "No data"

        # 按值排序
        sorted_data = sorted(data.items(), key=lambda x: x[1], reverse=True)

        # 饼图字符
        chars = ['█', '▓', '▒', '░', '◙', '◘', '◧', '◨', '◫', '◱']

        lines = []
        lines.append("  饼图分布 (Pie Chart)")
        lines.append("  " + "─" * (width - 4))

        current = 0
        max_label_len = max(len(str(k)) for k in data.keys()) if data else 0

        for i, (label, value) in enumerate(sorted_data):
            percentage = value / total
            bar_len = int(percentage * (width - max_label_len - 15))
            bar = chars[i % len(chars)] * bar_len
            pct_str = f"{percentage * 100:.1f}%"
            lines.append(f"  {label:<{max_label_len}} │ {bar} {pct_str}")

        lines.append("  " + "─" * (width - 4))
        return "\n".join(lines)

    def _generate_ascii_bar_chart(self, data: dict[str, int], max_width: int = 30) -> str:
        """
        生成 ASCII 柱状图

        Args:
            data: 数据字典 {label: count}
            max_width: 最大条形宽度

        Returns:
            ASCII 柱状图字符串
        """
        if not data:
            return "No data"

        # 按值排序
        sorted_data = sorted(data.items(), key=lambda x: x[1], reverse=True)
        max_value = max(data.values())
        max_label_len = max(len(str(k)) for k in data.keys())

        lines = []
        lines.append("  柱状图分布 (Bar Chart)")
        lines.append("  " + "─" * (max_label_len + max_width + 8))

        for label, value in sorted_data:
            bar_len = int((value / max_value) * max_width) if max_value > 0 else 0
            bar = "▓" * bar_len
            lines.append(f"  {label:<{max_label_len}} │{bar} {value}")

        lines.append("  " + "─" * (max_label_len + max_width + 8))
        return "\n".join(lines)

    def _generate_tag_cloud(self, keywords: list[str], max_tags: int = 20) -> str:
        """
        生成标签云

        Args:
            keywords: 关键词列表
            max_tags: 最大标签数

        Returns:
            标签云字符串
        """
        if not keywords:
            return "No keywords"

        # 统计词频
        counter = Counter(keywords)
        top_keywords = counter.most_common(max_tags)

        if not top_keywords:
            return "No keywords"

        max_count = top_keywords[0][1]

        lines = []
        lines.append("  热门标签 (Tag Cloud)")
        lines.append("  " + "─" * 30)

        # 分行显示，每行几个标签
        current_line = "  "
        for i, (word, count) in enumerate(top_keywords):
            # 计算字体大小指示
            if max_count > 0:
                size_ratio = count / max_count
                if size_ratio > 0.8:
                    indicator = "●●●"
                elif size_ratio > 0.5:
                    indicator = "●●○"
                elif size_ratio > 0.3:
                    indicator = "●○○"
                else:
                    indicator = "○○○"
            else:
                indicator = "●○○"

            tag = f"{word}({indicator}{count})"
            if len(current_line) + len(tag) + 2 > 50:
                lines.append(current_line)
                current_line = "  " + tag
            else:
                current_line += tag + "  "

        if current_line.strip():
            lines.append(current_line)

        lines.append("  " + "─" * 30)
        lines.append("  图例: ●●●高  ●●○中  ●○○低")
        return "\n".join(lines)

    def _create_table_block(self, rows: list[list[str]]) -> dict:
        """
        创建表格块

        Args:
            rows: 表格行列表，每行是单元格列表

        Returns:
            飞书表格块
        """
        if not rows:
            return {}

        # 第一行作为表头
        header_row = rows[0]
        cell_count = len(header_row)

        # 构建表格块结构
        table_cells = []
        for row in rows:
            cells = []
            for cell in row[:cell_count]:
                cells.append({
                    "cell": {
                        "elements": [self._create_text_element(str(cell))],
                        "style": {}
                    }
                })
            table_cells.append({"cells": cells})

        return {
            "block_type": 10,  # TABLE 类型
            "table": {
                "rows": table_cells,
                "style": {}
            }
        }

    def _select_top_articles(self, articles: list, top_n: int = 3) -> list:
        """
        选择 Top N 篇必读文章

        Args:
            articles: 文章列表
            top_n: 选择数量

        Returns:
            选中的文章列表
        """
        # 简单策略：优先选择有英文标题的文章，然后按标题长度排序
        scored_articles = []

        for article in articles:
            if hasattr(article, 'title'):
                title = article.title
            else:
                title = str(article.get('title', ''))

            # 评分：优先选择包含英文的文章
            score = 0
            if any(c.isalpha() and ord(c) < 128 for c in title):
                score += 10

            # 标题长度适中得分更高
            if 30 <= len(title) <= 100:
                score += 5

            scored_articles.append((score, article))

        # 按分数降序排序
        scored_articles.sort(key=lambda x: x[0], reverse=True)

        return [article for score, article in scored_articles[:top_n]]

    def _generate_digest_blocks(self, articles: list, config: dict) -> list[dict]:
        """
        生成日报的所有飞书块

        Args:
            articles: 文章列表
            config: 配置字典

        Returns:
            飞书块列表
        """
        blocks = []

        # ========== 今日看点 ==========
        blocks.append(self._create_heading_block("今日看点", 2))

        # 按分类统计
        categories = {cat: [] for cat in self.CATEGORY_NAMES.keys()}
        for article in articles:
            cat = self._classify_article(article)
            categories[cat].append(article)

        # 生成趋势总结
        trend_summary = self._generate_trend_summary(articles, categories)
        blocks.append(self._create_quote_block(trend_summary))
        blocks.append(self._create_divider_block())

        # ========== 今日必读 ==========
        blocks.append(self._create_heading_block("今日必读", 2))

        top_articles = self._select_top_articles(articles, 3)
        for i, article in enumerate(top_articles, 1):
            if hasattr(article, 'title'):
                title = article.title
                summary = getattr(article, 'summary', '') or ''
                url = getattr(article, 'url', '') or ''
                keywords = getattr(article, 'keywords', []) or []
            else:
                title = str(article.get('title', ''))
                summary = str(article.get('summary', ''))
                url = str(article.get('url', ''))
                keywords = article.get('keywords', []) or []

            # 标题
            blocks.append(self._create_text_block(f"#{i} {title}"))

            # 摘要
            if summary:
                blocks.append(self._create_quote_block(summary[:200] + "..." if len(summary) > 200 else summary))

            # 推荐理由
            reason = f"推荐理由: 本文探讨了核心技术趋势，具有较高的学习和参考价值。"
            blocks.append(self._create_text_block(reason))

            # 关键词
            if keywords:
                kw_str = "关键词: " + ", ".join(keywords[:5])
                blocks.append(self._create_text_block(kw_str))

            # 链接
            if url:
                blocks.append(self._create_text_block(f"阅读原文: [点击访问]({url})"))

            blocks.append(self._create_divider_block())

        # ========== 数据概览 ==========
        blocks.append(self._create_heading_block("数据概览", 2))

        # 统计表格
        blocks.append(self._create_heading_block("分类统计", 3))
        category_stats = {self.CATEGORY_NAMES.get(cat, cat): len(arts) for cat, arts in categories.items()}
        table_rows = [["分类", "数量", "占比"]]  # 表头
        total_articles = len(articles)
        for cat, count in sorted(category_stats.items(), key=lambda x: x[1], reverse=True):
            pct = f"{count * 100 // total_articles}%" if total_articles > 0 else "0%"
            table_rows.append([cat, str(count), pct])

        blocks.append(self._create_table_block(table_rows))
        blocks.append(self._create_divider_block())

        # ASCII 饼图
        blocks.append(self._create_code_block(
            self._generate_ascii_pie_chart(category_stats),
            "text"
        ))
        blocks.append(self._create_divider_block())

        # ASCII 柱状图
        blocks.append(self._create_code_block(
            self._generate_ascii_bar_chart(category_stats),
            "text"
        ))
        blocks.append(self._create_divider_block())

        # 标签云
        all_keywords = self._get_all_keywords(articles)
        blocks.append(self._create_code_block(
            self._generate_tag_cloud(all_keywords),
            "text"
        ))
        blocks.append(self._create_divider_block())

        # ========== 分类文章列表 ==========
        blocks.append(self._create_heading_block("分类文章列表", 2))

        for cat_name, cat_key in [("AI/ML", "AI/ML"), ("安全", "安全"), ("工程", "工程"),
                                   ("工具/开源", "工具/开源"), ("观点/杂谈", "观点/杂谈"), ("其他", "其他")]:
            cat_articles = categories.get(cat_key, [])
            if not cat_articles:
                continue

            blocks.append(self._create_heading_block(cat_name, 3))

            for j, article in enumerate(cat_articles[:10], 1):  # 每类最多显示10篇
                if hasattr(article, 'title'):
                    title = article.title
                    url = getattr(article, 'url', '') or ''
                else:
                    title = str(article.get('title', ''))
                    url = str(article.get('url', ''))

                # 使用链接文本
                if url:
                    elements = [
                        self._create_text_element(f"{j}. "),
                        self._create_text_element(title, url)
                    ]
                    blocks.append(self._create_rich_text_block(elements))
                else:
                    blocks.append(self._create_text_block(f"{j}. {title}"))

            blocks.append(self._create_divider_block())

        # ========== 元数据 ==========
        blocks.append(self._create_heading_block("关于本日报", 3))
        blocks.append(self._create_text_block(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
        blocks.append(self._create_text_block(f"文章总数: {len(articles)}"))
        blocks.append(self._create_text_block(f"数据来源: 技术文章聚合系统"))

        return blocks

    def publish_daily_digest(self, articles: list, config: dict) -> PublishResult:
        """
        发布结构化日报到飞书文档

        Args:
            articles: 文章列表（dict 或 Article 对象列表）
            config: 配置字典，包含：
                - title: 日报标题（可选，默认按日期生成）
                - folder_token: 目标文件夹 Token（可选）

        Returns:
            PublishResult 对象，包含 document_url
        """
        if not articles:
            return PublishResult(
                success=False,
                synthesis_id="daily_digest",
                document_url=None,
                error_message="没有文章可发布"
            )

        # 生成标题
        title = config.get('title', f"技术日报 {datetime.now().strftime('%Y-%m-%d')}")

        # 如果配置中指定了 folder_token，临时覆盖
        original_folder_token = self.folder_token
        if 'folder_token' in config:
            self.folder_token = config.get('folder_token', '')

        try:
            # 生成飞书块
            blocks = self._generate_digest_blocks(articles, config)

            # 创建文档
            success, doc_url = self.create_document(title, blocks)

            if success and doc_url:
                return PublishResult(
                    success=True,
                    synthesis_id="daily_digest",
                    document_url=doc_url,
                    published_at=datetime.now()
                )
            else:
                # 保存本地备份
                backup_path = self._save_digest_backup(articles, title)
                return PublishResult(
                    success=False,
                    synthesis_id="daily_digest",
                    document_url=None,
                    error_message=f"发布失败，已保存本地备份: {backup_path}",
                    published_at=datetime.now()
                )
        finally:
            # 恢复原始 folder_token
            self.folder_token = original_folder_token

    def _save_digest_backup(self, articles: list, title: str) -> str:
        """
        保存日报本地备份

        Args:
            articles: 文章列表
            title: 日报标题

        Returns:
            备份文件路径
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"daily_digest_{timestamp}.md"
        filepath = self.backup_dir / filename

        content = f"# {title}\n\n"
        content += f"**生成时间**: {datetime.now().isoformat()}\n"
        content += f"**文章数量**: {len(articles)}\n\n"
        content += "---\n\n"

        # 按分类组织
        categories = {cat: [] for cat in self.CATEGORY_NAMES.keys()}
        for article in articles:
            cat = self._classify_article(article)
            categories[cat].append(article)

        for cat_name in self.CATEGORY_NAMES.keys():
            cat_articles = categories.get(cat_name, [])
            if cat_articles:
                content += f"## {cat_name}\n\n"
                for i, article in enumerate(cat_articles, 1):
                    if hasattr(article, 'title'):
                        title = article.title
                        url = getattr(article, 'url', '')
                    else:
                        title = str(article.get('title', ''))
                        url = str(article.get('url', ''))
                    content += f"{i}. [{title}]({url})\n"
                content += "\n"

        filepath.write_text(content, encoding='utf-8')
        logger.info(f"日报本地备份已保存: {filepath}")
        return str(filepath)
