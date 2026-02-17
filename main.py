#!/usr/bin/env python3
"""
每日文章聚合器 - 主程序入口
Daily Article Aggregator - Main Entry Point

# SQLite 版本兼容性补丁 - ChromaDB 需要 SQLite >= 3.35.0
try:
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

支持三种运行模式：
1. 定时调度模式（默认）：每天在配置的时间自动执行任务
2. 单次执行模式（--once）：立即执行一次任务后退出
3. RSS评估模式（--evaluate）：评估RSS订阅源质量

使用方法 Usage:
    # 启动定时调度
    python main.py
    
    # 单次执行
    python main.py --once
    
    # 评估RSS源
    python main.py --evaluate --opml feeds.opml
    
    # 使用自定义配置
    python main.py --config my_config.yaml --once

需求 7.5: 支持命令行参数控制
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# 确保项目根目录在Python路径中
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from src.config import load_config
from src.scheduler import Scheduler

# Import new components for advanced features
try:
    from src.fetchers.dblp_fetcher import DBLPFetcher
    from src.fetchers.nvd_fetcher import NVDFetcher
    from src.fetchers.kev_fetcher import KEVFetcher
    from src.fetchers.huggingface_fetcher import HuggingFaceFetcher
    from src.fetchers.pwc_fetcher import PWCFetcher
    from src.fetchers.blog_fetcher import BlogFetcher
    from src.filters.vulnerability_filter import VulnerabilityFilter
    from src.scoring.priority_scorer import PriorityScorer
    from src.pushers.tiered_pusher import TieredPusher
    ADVANCED_FEATURES_AVAILABLE = True
except ImportError:
    ADVANCED_FEATURES_AVAILABLE = False


# 配置日志格式
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


def setup_logging(verbose: bool = False) -> None:
    """
    配置日志系统
    Setup logging system
    
    Args:
        verbose: 是否启用详细日志（DEBUG级别）
                 Whether to enable verbose logging (DEBUG level)
    """
    level = logging.DEBUG if verbose else logging.INFO
    
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # 降低第三方库的日志级别
    # Reduce log level for third-party libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('openai').setLevel(logging.WARNING)
    logging.getLogger('schedule').setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数
    Parse command line arguments
    
    Returns:
        解析后的参数命名空间
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description='每日文章聚合器 - 自动化内容聚合和分析系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
运行模式 Modes:
  默认模式    启动定时调度，每天在配置的时间自动执行任务
  --once      单次执行模式，立即执行一次任务后退出
  --evaluate  RSS评估模式，评估订阅源质量并生成报告

示例 Examples:
  # 启动定时调度（每天在config.yaml中配置的时间执行）
  python main.py
  
  # 立即执行一次任务
  python main.py --once
  
  # 评估RSS订阅源质量
  python main.py --evaluate --opml feeds.opml
  
  # 使用自定义配置文件
  python main.py --config my_config.yaml --once
  
  # 启用详细日志
  python main.py --once --verbose
        """
    )
    
    # 运行模式参数
    mode_group = parser.add_argument_group('运行模式 Mode Options')
    mode_group.add_argument(
        '--once', '-1',
        action='store_true',
        help='单次执行模式：立即执行一次任务后退出 / Run task once and exit'
    )
    mode_group.add_argument(
        '--evaluate', '-e',
        action='store_true',
        help='RSS评估模式：评估订阅源质量 / Run RSS feed evaluation mode'
    )
    mode_group.add_argument(
        '--checkpoint-status',
        action='store_true',
        help='查看断点续传状态 / Show checkpoint status'
    )
    mode_group.add_argument(
        '--clear-checkpoint',
        action='store_true',
        help='清除断点续传检查点 / Clear checkpoint files'
    )
    
    # 配置参数
    config_group = parser.add_argument_group('配置选项 Config Options')
    config_group.add_argument(
        '--config', '-c',
        type=str,
        default='config.yaml',
        help='配置文件路径 (默认: config.yaml) / Config file path (default: config.yaml)'
    )
    config_group.add_argument(
        '--env',
        type=str,
        default=None,
        help='.env文件路径 (默认: 自动查找) / .env file path (default: auto-discover)'
    )
    
    # 评估模式参数
    eval_group = parser.add_argument_group('评估模式选项 Evaluation Options (仅用于 --evaluate)')
    eval_group.add_argument(
        '--opml',
        type=str,
        default=None,
        help='OPML文件路径 (默认: 从配置文件读取) / OPML file path (default: from config)'
    )
    eval_group.add_argument(
        '--output', '-O',
        type=str,
        default='reports',
        help='评估报告输出目录 (默认: reports) / Output directory for reports (default: reports)'
    )
    eval_group.add_argument(
        '--min-score',
        type=float,
        default=0.6,
        help='最低质量评分阈值 (默认: 0.6) / Minimum quality score threshold (default: 0.6)'
    )
    
    # 通用参数
    general_group = parser.add_argument_group('通用选项 General Options')
    general_group.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='启用详细日志输出 / Enable verbose logging'
    )
    
    return parser.parse_args()


def run_scheduled_mode(config: dict, logger: logging.Logger) -> int:
    """
    运行定时调度模式
    Run scheduled mode
    
    Args:
        config: 配置字典
        logger: 日志记录器
    
    Returns:
        退出码
    """
    logger.info("启动定时调度模式...")
    logger.info(f"任务将在每天 {config.get('schedule', {}).get('time', '09:00')} 执行")
    
    try:
        scheduler = Scheduler(config)
        scheduler.start()
        return 0
    except KeyboardInterrupt:
        logger.info("用户中断，程序退出")
        return 0
    except Exception as e:
        logger.error(f"调度器运行失败: {e}", exc_info=True)
        return 1


def show_checkpoint_status(config: dict, logger: logging.Logger) -> int:
    """
    显示断点续传状态
    Show checkpoint status
    
    Args:
        config: 配置字典
        logger: 日志记录器
    
    Returns:
        退出码
    """
    try:
        from src.utils.checkpoint import CheckpointManager
    except ImportError:
        print("错误: 断点续传模块不可用")
        return 1
    
    checkpoint_config = config.get('checkpoint', {})
    checkpoint_dir = checkpoint_config.get('dir', 'data/checkpoints')
    
    manager = CheckpointManager(checkpoint_dir=checkpoint_dir)
    
    # 加载检查点
    fetch_cp = manager.load_fetch_checkpoint()
    process_cp = manager.load_process_checkpoint()
    
    print(f"\n{'='*60}")
    print("断点续传状态")
    print(f"{'='*60}")
    print(f"检查点目录: {checkpoint_dir}")
    print()
    
    if fetch_cp:
        print("📥 抓取阶段检查点:")
        print(f"   ID: {fetch_cp.checkpoint_id}")
        print(f"   创建时间: {fetch_cp.created_at}")
        print(f"   更新时间: {fetch_cp.updated_at}")
        print(f"   状态: {fetch_cp.phase}")
        print(f"   进度: {len(fetch_cp.completed_feeds)}/{fetch_cp.total_feeds} 个订阅源")
        print(f"   失败: {len(fetch_cp.failed_feeds)} 个订阅源")
        total_articles = sum(len(a) for a in fetch_cp.fetched_articles.values())
        print(f"   已抓取文章: {total_articles} 篇")
    else:
        print("📥 抓取阶段检查点: 无")
    
    print()
    
    if process_cp:
        print("⚙️  处理阶段检查点:")
        print(f"   ID: {process_cp.checkpoint_id}")
        print(f"   创建时间: {process_cp.created_at}")
        print(f"   更新时间: {process_cp.updated_at}")
        print(f"   状态: {process_cp.phase}")
        print(f"   进度: {len(process_cp.processed_urls)}/{process_cp.total_articles} 篇文章")
        print(f"   失败: {len(process_cp.failed_urls)} 篇文章")
    else:
        print("⚙️  处理阶段检查点: 无")
    
    print(f"\n{'='*60}\n")
    
    return 0


def clear_checkpoint(config: dict, logger: logging.Logger) -> int:
    """
    清除断点续传检查点
    Clear checkpoint files
    
    Args:
        config: 配置字典
        logger: 日志记录器
    
    Returns:
        退出码
    """
    try:
        from src.utils.checkpoint import CheckpointManager
    except ImportError:
        print("错误: 断点续传模块不可用")
        return 1
    
    checkpoint_config = config.get('checkpoint', {})
    checkpoint_dir = checkpoint_config.get('dir', 'data/checkpoints')
    
    manager = CheckpointManager(checkpoint_dir=checkpoint_dir)
    manager.clear_checkpoints()
    
    print("✓ 断点续传检查点已清除")
    logger.info("断点续传检查点已清除")
    
    return 0


def run_once_mode(config: dict, logger: logging.Logger) -> int:
    """
    运行单次执行模式
    Run once mode
    
    Args:
        config: 配置字典
        logger: 日志记录器
    
    Returns:
        退出码
    """
    logger.info("启动单次执行模式...")
    
    try:
        scheduler = Scheduler(config)
        scheduler.run_once()
        logger.info("任务执行完成")
        return 0
    except Exception as e:
        logger.error(f"任务执行失败: {e}", exc_info=True)
        return 1


def run_evaluate_mode(config: dict, args: argparse.Namespace, logger: logging.Logger) -> int:
    """
    运行RSS评估模式
    Run RSS evaluation mode
    
    Args:
        config: 配置字典
        args: 命令行参数
        logger: 日志记录器
    
    Returns:
        退出码
    """
    logger.info("启动RSS评估模式...")
    
    # 延迟导入评估相关模块
    from src.analyzers.ai_analyzer import AIAnalyzer
    from src.evaluators.rss_evaluator import RSSEvaluator
    
    # 确定OPML文件路径
    opml_path = args.opml
    if not opml_path:
        # 从配置文件读取
        opml_path = config.get('sources', {}).get('rss', {}).get('opml_path', 'feeds.opml')
    
    opml_file = Path(opml_path)
    if not opml_file.exists():
        logger.error(f"OPML文件不存在: {opml_path}")
        print(f"错误: OPML文件不存在: {opml_path}", file=sys.stderr)
        return 1
    
    # 创建输出目录
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 检查AI配置
    ai_config = config.get('ai', {})
    if not ai_config.get('api_key'):
        logger.warning("未配置AI API密钥，评估功能可能受限")
        print("警告: 未配置AI API密钥 (OPENAI_API_KEY)，评估功能可能受限", file=sys.stderr)
    
    try:
        # 初始化AI分析器
        ai_analyzer = AIAnalyzer(ai_config)
        logger.info("AI分析器初始化成功")
        
        # 初始化RSS评估器
        evaluator_config = {
            'min_quality_score': args.min_score,
            'proxy': config.get('proxy', {}).get('url') if config.get('proxy', {}).get('enabled') else None,
            'timeout': ai_config.get('timeout', 30)
        }
        evaluator = RSSEvaluator(ai_analyzer, evaluator_config)
        logger.info("RSS评估器初始化成功")
        
    except Exception as e:
        logger.error(f"初始化评估器失败: {e}")
        print(f"错误: 初始化评估器失败: {e}", file=sys.stderr)
        return 1
    
    # 打印评估信息
    print(f"\n{'='*60}")
    print(f"RSS订阅源质量评估")
    print(f"{'='*60}")
    print(f"OPML文件: {opml_file.resolve()}")
    print(f"最低评分阈值: {args.min_score}")
    print(f"输出目录: {output_dir.resolve()}")
    print(f"{'='*60}\n")
    
    try:
        # 执行评估
        evaluations = evaluator.evaluate_all_feeds(str(opml_path))
        
        if not evaluations:
            logger.warning("没有获取到任何评估结果")
            print("警告: 没有获取到任何评估结果", file=sys.stderr)
            return 1
        
        # 生成评估报告
        report_path = output_dir / 'evaluation_report.md'
        report = evaluator.generate_report(evaluations)
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        logger.info(f"评估报告已保存: {report_path}")
        print(f"✓ 评估报告已保存: {report_path}")
        
        # 导出筛选后的OPML
        filtered_opml_path = output_dir / 'filtered_feeds.opml'
        kept_count = evaluator.export_filtered_opml(
            evaluations,
            str(filtered_opml_path),
            min_score=args.min_score
        )
        logger.info(f"筛选后的OPML已保存: {filtered_opml_path}")
        print(f"✓ 筛选后的OPML已保存: {filtered_opml_path}")
        
        # 打印摘要统计
        total = len(evaluations)
        active_count = sum(1 for e in evaluations if e.is_active)
        keep_count = sum(1 for e in evaluations if e.recommendation == 'keep')
        remove_count = sum(1 for e in evaluations if e.recommendation == 'remove')
        review_count = sum(1 for e in evaluations if e.recommendation == 'review')
        avg_score = sum(e.quality_score for e in evaluations) / total if total > 0 else 0
        
        print(f"\n{'='*60}")
        print(f"评估完成 - 摘要统计")
        print(f"{'='*60}")
        print(f"总订阅源数: {total}")
        print(f"活跃订阅源: {active_count} ({active_count/total*100:.1f}%)" if total > 0 else "活跃订阅源: 0")
        print(f"平均质量评分: {avg_score:.2f}")
        print(f"")
        print(f"推荐操作:")
        print(f"  ✅ 保留: {keep_count}")
        print(f"  ⚠️  审核: {review_count}")
        print(f"  ❌ 移除: {remove_count}")
        print(f"")
        print(f"筛选后保留: {kept_count} 个订阅源 (评分 >= {args.min_score})")
        print(f"{'='*60}\n")
        
        logger.info(f"评估完成: 总计 {total} 个订阅源, 保留 {kept_count} 个")
        return 0
        
    except Exception as e:
        logger.error(f"评估过程出错: {e}", exc_info=True)
        print(f"错误: 评估过程出错: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """
    主函数
    Main function
    
    Returns:
        退出码：0表示成功，非0表示失败
        Exit code: 0 for success, non-zero for failure
    
    **验证: 需求 7.5**
    """
    # 解析命令行参数
    args = parse_args()
    
    # 配置日志
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    # 切换到项目根目录（确保相对路径正确）
    os.chdir(project_root)
    logger.debug(f"工作目录: {project_root}")
    
    # 验证配置文件存在
    config_path = Path(args.config)
    if not config_path.exists():
        logger.error(f"配置文件不存在: {args.config}")
        print(f"错误: 配置文件不存在: {args.config}", file=sys.stderr)
        return 1
    
    # 加载配置
    try:
        config = load_config(str(config_path), args.env)
        logger.info(f"已加载配置文件: {config_path}")
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        print(f"错误: 加载配置文件失败: {e}", file=sys.stderr)
        return 1
    
    # 根据运行模式执行相应逻辑
    if args.checkpoint_status:
        # 查看断点状态
        return show_checkpoint_status(config, logger)
    elif args.clear_checkpoint:
        # 清除断点
        return clear_checkpoint(config, logger)
    elif args.evaluate:
        # RSS评估模式
        return run_evaluate_mode(config, args, logger)
    elif args.once:
        # 单次执行模式
        return run_once_mode(config, logger)
    else:
        # 定时调度模式（默认）
        return run_scheduled_mode(config, logger)


if __name__ == '__main__':
    sys.exit(main())
