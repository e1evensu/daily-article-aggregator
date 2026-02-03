#!/usr/bin/env python3
"""
手动同步数据库文章到飞书多维表格
Manual sync articles from database to Feishu Bitable
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import logging
from src.bots.feishu_bitable import FeishuBitable
from src.config import load_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    # 加载配置
    config = load_config("config.yaml")
    
    # 初始化 Bitable
    bitable_config = config.get('feishu_bitable', {})
    if not bitable_config.get('enabled'):
        logger.error("Feishu Bitable 未启用，请在 config.yaml 中设置 feishu_bitable.enabled: true")
        return
    
    if not bitable_config.get('app_id') or not bitable_config.get('app_secret'):
        logger.error("缺少 FEISHU_APP_ID 或 FEISHU_APP_SECRET")
        return
    
    bitable = FeishuBitable(bitable_config)
    
    # 如果没有 app_token 和 table_id，先创建
    if not bitable.app_token or not bitable.table_id:
        logger.info("首次运行，创建多维表格...")
        app_token, table_id = bitable.setup()
        logger.info(f"创建成功！请将以下配置添加到 .env 文件：")
        logger.info(f"FEISHU_BITABLE_APP_TOKEN={app_token}")
        logger.info(f"FEISHU_BITABLE_TABLE_ID={table_id}")
    
    # 连接数据库
    db_path = config.get('database', {}).get('path', 'data/articles.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # 获取所有文章
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM articles ORDER BY fetched_at DESC")
    rows = cursor.fetchall()
    
    logger.info(f"数据库中共有 {len(rows)} 篇文章")
    
    # 转换为字典列表
    articles = []
    for row in rows:
        articles.append({
            'id': row['id'],
            'title': row['title'],
            'url': row['url'],
            'source': row['source'],
            'source_type': row['source_type'],
            'published_date': row['published_date'],
            'fetched_at': row['fetched_at'],
            'content': row['content'],
            'summary': row['summary'],
            'zh_summary': row['zh_summary'],
            'category': row['category'],
            'is_pushed': bool(row['is_pushed']),
        })
    
    conn.close()
    
    # 批量同步到 Bitable
    if articles:
        logger.info(f"开始同步 {len(articles)} 篇文章到飞书多维表格...")
        success_count = bitable.batch_add_records(articles)
        logger.info(f"同步完成，成功 {success_count} 篇")
    else:
        logger.info("没有文章需要同步")


if __name__ == "__main__":
    main()
