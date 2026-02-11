#!/usr/bin/env python
"""
知识库问答服务器启动脚本

初始化所有 QA 组件并启动飞书事件服务器。

Usage:
    python scripts/run_qa_server.py [--host HOST] [--port PORT] [--debug]

Options:
    --host HOST   监听地址（默认 0.0.0.0）
    --port PORT   监听端口（默认 8080）
    --debug       启用调试模式

Requirements: 2.1
"""

# SQLite 版本兼容性补丁 - ChromaDB 需要 SQLite >= 3.35.0
try:
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

import argparse
import logging
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

from src.config import load_config
from src.qa.event_server import FeishuEventServer
from src.qa.qa_engine import QAEngine
from src.qa.knowledge_base import KnowledgeBase
from src.qa.embedding_service import EmbeddingService
from src.qa.context_manager import ContextManager
from src.qa.query_processor import QueryProcessor
from src.qa.rate_limiter import RateLimiter
from src.qa.config import (
    EventServerConfig,
    QAConfig,
    RateLimitConfig,
    QAEngineConfig
)
from src.bots.feishu_bot import FeishuAppBot
from src.analyzers.ai_analyzer import AIAnalyzer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_qa_components(config: dict) -> dict:
    """
    创建所有 QA 组件
    
    Args:
        config: 配置字典
    
    Returns:
        组件字典
    """
    qa_config = config.get("knowledge_qa", {})
    
    # 创建知识库
    logger.info("初始化知识库...")
    kb_config = {
        "chroma_path": qa_config.get("chroma", {}).get("path", "data/chroma_db"),
        "collection_name": qa_config.get("chroma", {}).get("collection_name", "knowledge_articles"),
        "chunk_size": qa_config.get("chunking", {}).get("chunk_size", 500),
        "chunk_overlap": qa_config.get("chunking", {}).get("chunk_overlap", 50),
    }
    knowledge_base = KnowledgeBase(kb_config)
    
    # 创建并设置 Embedding 服务
    logger.info("初始化 Embedding 服务...")
    embedding_service = EmbeddingService(qa_config.get("embedding", {}))
    knowledge_base.set_embedding_service(embedding_service)
    
    kb_stats = knowledge_base.get_stats()
    logger.info(f"知识库已加载: {kb_stats['total_documents']} 个文档")
    
    # 创建上下文管理器
    logger.info("初始化上下文管理器...")
    ctx_config = qa_config.get("context_manager", {})
    context_manager = ContextManager(
        max_history=ctx_config.get("max_history", 5),
        ttl_minutes=ctx_config.get("ttl_minutes", 30)
    )
    
    # 创建查询处理器
    logger.info("初始化查询处理器...")
    query_processor = QueryProcessor()
    
    # 创建频率限制器
    logger.info("初始化频率限制器...")
    rl_config = RateLimitConfig.from_dict(qa_config.get("rate_limit", {}))
    rate_limiter = RateLimiter(rl_config)
    
    # 创建 AI 分析器（复用现有配置）
    logger.info("初始化 AI 分析器...")
    ai_config = config.get("ai", {})
    ai_analyzer = AIAnalyzer(ai_config)
    
    # 创建 QA 引擎
    logger.info("初始化问答引擎...")
    engine_config = QAEngineConfig.from_dict(qa_config.get("qa_engine", {}))
    qa_engine = QAEngine(
        knowledge_base=knowledge_base,
        context_manager=context_manager,
        query_processor=query_processor,
        ai_analyzer=ai_analyzer,
        config=engine_config
    )
    
    return {
        "knowledge_base": knowledge_base,
        "context_manager": context_manager,
        "query_processor": query_processor,
        "rate_limiter": rate_limiter,
        "qa_engine": qa_engine
    }


def create_feishu_bot() -> FeishuAppBot | None:
    """
    创建飞书应用机器人
    
    Returns:
        FeishuAppBot 实例，如果配置不完整则返回 None
    """
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    
    if not app_id or not app_secret:
        logger.warning(
            "飞书应用凭证未配置 (FEISHU_APP_ID, FEISHU_APP_SECRET)，"
            "将无法发送回复消息"
        )
        return None
    
    logger.info("初始化飞书应用机器人...")
    return FeishuAppBot(app_id=app_id, app_secret=app_secret)


def run_server(
    host: str = "0.0.0.0",
    port: int = 8080,
    debug: bool = False
) -> None:
    """
    运行问答服务器
    
    Args:
        host: 监听地址
        port: 监听端口
        debug: 是否启用调试模式
    """
    logger.info("=" * 60)
    logger.info("知识库问答服务器")
    logger.info("=" * 60)
    
    # 加载配置
    config = load_config()
    
    # 创建 QA 组件
    components = create_qa_components(config)
    
    # 创建飞书机器人
    feishu_bot = create_feishu_bot()
    
    # 获取事件服务器配置
    verification_token = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
    encrypt_key = os.getenv("FEISHU_ENCRYPT_KEY", "")
    
    if not verification_token:
        logger.warning(
            "飞书验证 Token 未配置 (FEISHU_VERIFICATION_TOKEN)，"
            "将跳过请求验证"
        )
    
    # 创建事件服务器
    logger.info("初始化事件服务器...")
    server_config = EventServerConfig(
        host=host,
        port=port,
        verification_token=verification_token,
        encrypt_key=encrypt_key
    )
    
    server = FeishuEventServer(
        config=server_config,
        qa_engine=components["qa_engine"],
        feishu_bot=feishu_bot,
        rate_limiter=components["rate_limiter"]
    )
    
    # 打印服务器信息
    logger.info("=" * 60)
    logger.info(f"服务器地址: http://{host}:{port}")
    logger.info(f"事件回调: http://{host}:{port}/webhook/event")
    logger.info(f"健康检查: http://{host}:{port}/health")
    logger.info(f"调试模式: {'启用' if debug else '禁用'}")
    logger.info(f"QA 引擎: 已启用")
    logger.info(f"飞书机器人: {'已启用' if feishu_bot else '未配置'}")
    logger.info(f"频率限制: 已启用")
    logger.info("=" * 60)
    logger.info("按 Ctrl+C 停止服务器")
    
    # 启动服务器（阻塞模式）
    try:
        server.run(debug=debug)
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭服务器...")
        server.stop()
        logger.info("服务器已停止")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="启动知识库问答服务器",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="监听地址（默认 0.0.0.0）"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="监听端口（默认 8080）"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试模式"
    )
    
    args = parser.parse_args()
    
    try:
        run_server(
            host=args.host,
            port=args.port,
            debug=args.debug
        )
    except Exception as e:
        logger.error(f"服务器启动失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
