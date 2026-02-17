#!/usr/bin/env python3
"""
飞书多维表格初始化脚本
Feishu Bitable Setup Script

用于创建多维表格和数据表，并输出配置信息。
Creates Bitable and data table, outputs configuration info.

使用方法 Usage:
    python scripts/setup_bitable.py
    
    # 指定表格名称
    python scripts/setup_bitable.py --name "我的文章库"
"""

import argparse
import logging
import sys
from pathlib import Path

# 将项目根目录添加到Python路径
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from src.config import load_config
from src.bots.feishu_bitable import FeishuBitable

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description='飞书多维表格初始化工具')
    parser.add_argument(
        '--name', '-n',
        type=str,
        default='文章聚合器',
        help='多维表格名称 (默认: 文章聚合器)'
    )
    parser.add_argument(
        '--table-name', '-t',
        type=str,
        default='文章列表',
        help='数据表名称 (默认: 文章列表)'
    )
    parser.add_argument(
        '--config', '-c',
        type=str,
        default='config.yaml',
        help='配置文件路径 (默认: config.yaml)'
    )
    return parser.parse_args()


def main():
    args = parse_args()
    
    print(f"\n{'='*60}")
    print("飞书多维表格初始化工具")
    print(f"{'='*60}\n")
    
    # 加载配置
    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"❌ 加载配置失败: {e}")
        return 1
    
    # 获取飞书配置
    bitable_config = config.get('feishu_bitable', {})
    
    if not bitable_config.get('app_id') or not bitable_config.get('app_secret'):
        print("❌ 缺少飞书应用配置，请在 .env 文件中设置:")
        print("   FEISHU_APP_ID=your_app_id")
        print("   FEISHU_APP_SECRET=your_app_secret")
        return 1
    
    # 检查是否已有配置
    existing_app_token = bitable_config.get('app_token')
    existing_table_id = bitable_config.get('table_id')
    
    if existing_app_token and existing_table_id:
        print("✅ 已有多维表格配置:")
        print(f"   app_token: {existing_app_token}")
        print(f"   table_id: {existing_table_id}")
        print("\n如需重新创建，请先清空 .env 中的 FEISHU_BITABLE_APP_TOKEN 和 FEISHU_BITABLE_TABLE_ID")
        return 0
    
    # 初始化客户端
    try:
        client = FeishuBitable(bitable_config)
        print("✅ 飞书客户端初始化成功")
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        return 1
    
    # 测试获取 token
    try:
        token = client._get_access_token()
        print(f"✅ 获取 access_token 成功: {token[:20]}...")
    except Exception as e:
        print(f"❌ 获取 access_token 失败: {e}")
        print("\n请检查:")
        print("1. app_id 和 app_secret 是否正确")
        print("2. 应用是否已发布")
        print("3. 应用是否有多维表格权限")
        return 1
    
    # 创建多维表格
    print(f"\n正在创建多维表格: {args.name}")
    try:
        app_token = client.create_bitable(args.name)
        print(f"✅ 多维表格创建成功: {app_token}")
    except Exception as e:
        print(f"❌ 创建多维表格失败: {e}")
        return 1
    
    # 创建数据表
    print(f"\n正在创建数据表: {args.table_name}")
    try:
        table_id = client.create_table(args.table_name)
        print(f"✅ 数据表创建成功: {table_id}")
    except Exception as e:
        print(f"❌ 创建数据表失败: {e}")
        return 1
    
    # 输出配置信息
    print(f"\n{'='*60}")
    print("🎉 初始化完成！请将以下配置添加到 .env 文件:")
    print(f"{'='*60}")
    print(f"\nFEISHU_BITABLE_APP_TOKEN={app_token}")
    print(f"FEISHU_BITABLE_TABLE_ID={table_id}")
    print(f"\n{'='*60}")
    print(f"多维表格链接: https://feishu.cn/base/{app_token}")
    print(f"{'='*60}\n")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
