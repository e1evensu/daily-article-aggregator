#!/usr/bin/env python3
"""
修复数据库中缺失 content 和 zh_summary 的文章
Fix articles with missing content and zh_summary in database

对于 NVD/KEV 等数据源的文章，重新从标题中提取描述信息，
然后调用 AI 分析生成摘要。
"""

import sys
import os
import logging

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.config import load_config
from src.repository import ArticleRepository
from src.analyzers.ai_analyzer import AIAnalyzer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def extract_description_from_title(title: str) -> str:
    """从标题中提取描述（CVE 标题格式：CVE-XXXX-XXXX: description）"""
    if ':' in title:
        parts = title.split(':', 1)
        if len(parts) > 1:
            return parts[1].strip()
    return title


def main():
    # 加载配置
    config = load_config("config.yaml")
    
    # 连接数据库
    db_path = config.get('database', {}).get('path', 'data/articles.db')
    repo = ArticleRepository(db_path)
    
    # 初始化 AI 分析器
    ai_config = config.get('ai', {})
    ai_analyzer = None
    if ai_config.get('enabled', True):
        try:
            ai_analyzer = AIAnalyzer(ai_config)
            logger.info("AI 分析器初始化成功")
        except Exception as e:
            logger.error(f"AI 分析器初始化失败: {e}")
            return
    
    # 获取所有未推送且缺少 zh_summary 的文章
    conn = repo._get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, title, url, source_type, content, summary, zh_summary 
        FROM articles 
        WHERE is_pushed = 0 AND (zh_summary IS NULL OR zh_summary = '')
        ORDER BY fetched_at DESC
    """)
    rows = cursor.fetchall()
    
    logger.info(f"找到 {len(rows)} 篇缺少 zh_summary 的文章")
    
    if not rows:
        logger.info("没有需要修复的文章")
        repo.close()
        return
    
    # 处理每篇文章
    fixed_count = 0
    error_count = 0
    
    for row in rows:
        article_id = row['id']
        title = row['title']
        source_type = row['source_type']
        content = row['content'] or ''
        
        logger.info(f"处理文章 {article_id}: {title[:50]}...")
        
        try:
            # 如果没有 content，从标题中提取描述
            if not content:
                content = extract_description_from_title(title)
                logger.info(f"  从标题提取内容: {content[:50]}...")
            
            if not content:
                logger.warning(f"  无法获取内容，跳过")
                continue
            
            # 调用 AI 分析
            if ai_analyzer:
                analysis_result = ai_analyzer.analyze_article(title, content)
                summary = analysis_result.get('summary', '')
                category = analysis_result.get('category', '其他')
                zh_summary = analysis_result.get('zh_summary', '')
                
                # 更新数据库
                cursor.execute("""
                    UPDATE articles 
                    SET content = ?, summary = ?, category = ?, zh_summary = ?
                    WHERE id = ?
                """, (content, summary, category, zh_summary, article_id))
                conn.commit()
                
                fixed_count += 1
                logger.info(f"  ✓ 已更新: zh_summary={zh_summary[:50]}...")
            
        except Exception as e:
            error_count += 1
            logger.error(f"  ✗ 处理失败: {e}")
            continue
    
    logger.info(f"\n=== 修复完成 ===")
    logger.info(f"成功修复: {fixed_count} 篇")
    logger.info(f"处理失败: {error_count} 篇")
    
    repo.close()


if __name__ == "__main__":
    main()
