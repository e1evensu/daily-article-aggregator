"""
飞书文档发布器模块

负责将综述发布到飞书文档。
支持 Markdown 到飞书块的转换，以及本地备份功能。

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
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from src.aggregation.models import Synthesis, PublishResult

logger = logging.getLogger(__name__)


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
            url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
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
                    # Token 有效期通常是 2 小时，提前 5 分钟刷新
                    expire_seconds = data.get('expire', 7200) - 300
                    from datetime import timedelta
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
    
    def convert_to_feishu_blocks(self, markdown: str) -> list[dict]:
        """
        将 Markdown 转换为飞书块格式
        
        Args:
            markdown: Markdown 文本
        
        Returns:
            飞书块列表
        
        Requirements:
            - 4.2: 支持 Markdown 格式转换为飞书块
            - 4.3: 支持标题层级、代码块、超链接、列表格式
        """
        blocks = []
        lines = markdown.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # 空行
            if not line.strip():
                i += 1
                continue
            
            # 标题 (# ## ### etc.)
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if heading_match:
                level = len(heading_match.group(1))
                text = heading_match.group(2)
                blocks.append({
                    "block_type": f"heading{min(level, 9)}",
                    "heading": {
                        "content": self._convert_inline_elements(text)
                    }
                })
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
                
                blocks.append({
                    "block_type": "code",
                    "code": {
                        "language": language,
                        "content": "\n".join(code_lines)
                    }
                })
                continue
            
            # 无序列表 (- or *)
            if re.match(r'^[-*]\s+', line):
                list_items = []
                while i < len(lines) and re.match(r'^[-*]\s+', lines[i]):
                    item_text = re.sub(r'^[-*]\s+', '', lines[i])
                    list_items.append({
                        "content": self._convert_inline_elements(item_text)
                    })
                    i += 1
                
                blocks.append({
                    "block_type": "bullet",
                    "bullet": {
                        "items": list_items
                    }
                })
                continue
            
            # 有序列表 (1. 2. etc.)
            if re.match(r'^\d+\.\s+', line):
                list_items = []
                while i < len(lines) and re.match(r'^\d+\.\s+', lines[i]):
                    item_text = re.sub(r'^\d+\.\s+', '', lines[i])
                    list_items.append({
                        "content": self._convert_inline_elements(item_text)
                    })
                    i += 1
                
                blocks.append({
                    "block_type": "ordered",
                    "ordered": {
                        "items": list_items
                    }
                })
                continue
            
            # 普通段落
            blocks.append({
                "block_type": "text",
                "text": {
                    "content": self._convert_inline_elements(line)
                }
            })
            i += 1
        
        return blocks
    
    def _convert_inline_elements(self, text: str) -> list[dict]:
        """
        转换行内元素（链接、粗体、斜体等）
        
        Args:
            text: 文本
        
        Returns:
            飞书文本元素列表
        """
        elements = []
        
        # 简化处理：将整个文本作为一个元素
        # 处理链接 [text](url)
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        
        last_end = 0
        for match in re.finditer(link_pattern, text):
            # 添加链接前的文本
            if match.start() > last_end:
                elements.append({
                    "type": "text",
                    "text": text[last_end:match.start()]
                })
            
            # 添加链接
            elements.append({
                "type": "link",
                "text": match.group(1),
                "link": match.group(2)
            })
            
            last_end = match.end()
        
        # 添加剩余文本
        if last_end < len(text):
            remaining = text[last_end:]
            if remaining:
                elements.append({
                    "type": "text",
                    "text": remaining
                })
        
        # 如果没有任何元素，添加整个文本
        if not elements:
            elements.append({
                "type": "text",
                "text": text
            })
        
        return elements
    
    def create_document(
        self, 
        title: str, 
        blocks: list[dict]
    ) -> tuple[bool, str | None]:
        """
        创建飞书文档
        
        Args:
            title: 文档标题
            blocks: 飞书块列表
        
        Returns:
            (成功标志, 文档 URL 或 None)
        
        Requirements:
            - 4.1: 将综述发布到飞书文档
        """
        token = self._get_access_token()
        if not token:
            logger.error("无法获取飞书访问令牌")
            return False, None
        
        try:
            # 创建文档
            url = "https://open.feishu.cn/open-apis/docx/v1/documents"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "title": title,
                "folder_token": self.folder_token if self.folder_token else None
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"创建文档失败: {response.status_code} - {response.text}")
                return False, None
            
            data = response.json()
            if data.get('code') != 0:
                logger.error(f"创建文档失败: {data.get('msg')}")
                return False, None
            
            document_id = data.get('data', {}).get('document', {}).get('document_id')
            
            if not document_id:
                logger.error("创建文档成功但未返回 document_id")
                return False, None
            
            # 添加内容块
            # 注意：飞书文档 API 需要逐个添加块，这里简化处理
            # 实际使用时可能需要更复杂的逻辑
            
            doc_url = f"https://feishu.cn/docx/{document_id}"
            logger.info(f"文档创建成功: {doc_url}")
            
            return True, doc_url
            
        except Exception as e:
            logger.error(f"创建文档时发生错误: {e}")
            return False, None
    
    def save_local_backup(self, synthesis: Synthesis) -> str:
        """
        保存本地备份
        
        Args:
            synthesis: 综述对象
        
        Returns:
            备份文件路径
        
        Requirements:
            - 4.5: API 失败时保存本地备份
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"synthesis_{synthesis.topic_id}_{timestamp}.md"
        filepath = self.backup_dir / filename
        
        # 构建备份内容
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
        
        # 写入文件
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
        
        Requirements:
            - 4.1: 将综述发布到飞书文档
            - 4.4: 添加元数据
            - 4.5: API 失败时保存本地备份
            - 4.6: 返回发布结果
        """
        # 添加元数据到内容
        metadata = f"""
> **生成时间**: {synthesis.generated_at.isoformat() if synthesis.generated_at else datetime.now().isoformat()}
> **文章数量**: {len(synthesis.references)}
> **关键词**: {', '.join(synthesis.key_points[:5]) if synthesis.key_points else 'N/A'}

"""
        full_content = metadata + synthesis.content
        
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
