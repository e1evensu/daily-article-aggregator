#!/usr/bin/env python3
"""
测试飞书推送功能

Usage:
    python scripts/test_feishu_push.py
    python scripts/test_feishu_push.py --count 5  # 测试推送5篇文章
"""

import argparse
import logging
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import load_config
from src.bots.feishu_bot import FeishuBot
from src.repository import ArticleRepository

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_webhook_connection(webhook_url: str) -> bool:
    """测试 Webhook 连接"""
    logger.info("测试 Webhook 连接...")
    
    try:
        bot = FeishuBot(webhook_url)
        success = bot.send_text("🔔 测试消息：飞书 Webhook 连接正常！")
        
        if success:
            logger.info("✅ Webhook 连接测试成功")
        else:
            logger.error("❌ Webhook 连接测试失败")
        
        return success
    except Exception as e:
        logger.error(f"❌ Webhook 连接测试异常: {e}")
        return False


def test_push_articles(webhook_url: str, articles: list[dict]) -> bool:
    """测试推送文章"""
    logger.info(f"测试推送 {len(articles)} 篇文章...")
    
    try:
        bot = FeishuBot(webhook_url)
        success = bot.push_articles(articles, batch_size=10)
        
        if success:
            logger.info("✅ 文章推送测试成功")
        else:
            logger.error("❌ 文章推送测试失败")
        
        return success
    except Exception as e:
        logger.error(f"❌ 文章推送测试异常: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='测试飞书推送功能')
    parser.add_argument(
        '--config', '-c',
        default='config.yaml',
        help='配置文件路径 (默认: config.yaml)'
    )
    parser.add_argument(
        '--count', '-n',
        type=int,
        default=3,
        help='测试推送的文章数量 (默认: 3)'
    )
    parser.add_argument(
        '--from-db',
        action='store_true',
        help='从数据库获取未推送的文章进行测试'
    )
    
    args = parser.parse_args()
    
    # 加载配置
    logger.info(f"加载配置: {args.config}")
    config = load_config(args.config)
    
    # 获取 Webhook URL
    feishu_config = config.get('feishu', {})
    webhook_url = feishu_config.get('webhook_url', '')
    
    if not webhook_url:
        logger.error("❌ 未配置飞书 Webhook URL")
        logger.info("请在 config.yaml 或 .env 中设置 FEISHU_WEBHOOK_URL")
        return
    
    logger.info(f"Webhook URL: {webhook_url[:50]}...")
    
    # 测试 1: Webhook 连接
    print("\n" + "=" * 50)
    print("测试 1: Webhook 连接")
    print("=" * 50)
    
    if not test_webhook_connection(webhook_url):
        logger.error("Webhook 连接失败，请检查 URL 是否正确")
        return
    
    # 测试 2: 推送文章
    print("\n" + "=" * 50)
    print("测试 2: 推送文章")
    print("=" * 50)
    
    if args.from_db:
        # 从数据库获取文章
        db_config = config.get('database', {})
        db_path = db_config.get('path', 'data/articles.db')
        
        if not Path(db_path).exists():
            logger.error(f"数据库文件不存在: {db_path}")
            return
        
        repo = ArticleRepository(db_path)
        articles = repo.get_unpushed_articles()[:args.count]
        repo.close()
        
        if not articles:
            logger.warning("数据库中没有未推送的文章")
            # 使用测试数据
            articles = _get_test_articles(args.count)
    else:
        # 使用测试数据
        articles = _get_test_articles(args.count)
    
    logger.info(f"准备推送 {len(articles)} 篇文章")
    test_push_articles(webhook_url, articles)
    
    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)


def _get_test_articles(count: int) -> list[dict]:
    """生成测试文章数据"""
    articles = []
    for i in range(1, count + 1):
        articles.append({
            'title': f'测试文章 {i}: 这是一篇用于测试飞书推送功能的文章',
            'url': f'https://example.com/article/{i}',
            'source': '测试来源',
            'category': '测试分类',
            'zh_summary': f'这是测试文章 {i} 的中文摘要，用于验证飞书推送功能是否正常工作。',
        })
    return articles


if __name__ == '__main__':
    main()
