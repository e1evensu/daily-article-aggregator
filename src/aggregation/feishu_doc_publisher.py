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
        filename = f"synthesis_{synthesis.topic_id}_{timestamp}.md"
        filepath = self.backup_dir / filename
        
        content = f"""# {synthesis.title}

**生成时间**: {synthesis.generated_at.isoformat() if synthesis.generated_at else 'N/A'}
**话题 ID**: {synthesis.topic_id}

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
                synthesis_id=synthesis.synthesis_id,
                document_url=doc_url,
                published_at=datetime.now()
            )
        
        # 发布失败，保存本地备份
        backup_path = self.save_local_backup(synthesis)
        
        return PublishResult(
            success=False,
            synthesis_id=synthesis.synthesis_id,
            document_url=None,
            error_message=f"发布失败，已保存本地备份: {backup_path}",
            published_at=datetime.now()
        )
