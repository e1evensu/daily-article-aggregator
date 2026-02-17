#!/usr/bin/env python3
"""
RSS订阅源评估独立脚本
RSS Feed Evaluation Standalone Script

用于评估OPML文件中的RSS订阅源质量，生成评估报告和筛选后的OPML文件。
Evaluates RSS feed quality from OPML file, generates evaluation report and filtered OPML.

使用方法 Usage:
    python scripts/evaluate_feeds.py --opml feeds.opml --output reports/ --min-score 0.5

需求 9.8: 输出评估报告，包含推荐保留和建议移除的RSS源列表
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# 将项目根目录添加到Python路径
# Add project root to Python path
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from src.config import load_config
from src.analyzers.ai_analyzer import AIAnalyzer
from src.evaluators.rss_evaluator import RSSEvaluator


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数
    Parse command line arguments
    
    Returns:
        解析后的参数命名空间
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description='RSS订阅源质量评估工具 - 评估OPML文件中的订阅源质量',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例 Examples:
  # 使用默认参数评估feeds.opml
  python scripts/evaluate_feeds.py --opml feeds.opml
  
  # 指定输出目录和最低评分阈值
  python scripts/evaluate_feeds.py --opml feeds.opml --output reports/ --min-score 0.5
  
  # 自定义输出文件名
  python scripts/evaluate_feeds.py --opml feeds.opml --report my_report.md --filtered-opml my_feeds.opml
        """
    )
    
    parser.add_argument(
        '--opml', '-o',
        type=str,
        required=True,
        help='OPML文件路径 (必需) / Path to OPML file (required)'
    )
    
    parser.add_argument(
        '--output', '-O',
        type=str,
        default='.',
        help='输出目录路径 (默认: 当前目录) / Output directory path (default: current directory)'
    )
    
    parser.add_argument(
        '--min-score',
        type=float,
        default=0.6,
        help='最低质量评分阈值 (默认: 0.6) / Minimum quality score threshold (default: 0.6)'
    )
    
    parser.add_argument(
        '--report',
        type=str,
        default='evaluation_report.md',
        help='评估报告文件名 (默认: evaluation_report.md) / Report filename (default: evaluation_report.md)'
    )
    
    parser.add_argument(
        '--filtered-opml',
        type=str,
        default='filtered_feeds.opml',
        help='筛选后的OPML文件名 (默认: filtered_feeds.opml) / Filtered OPML filename (default: filtered_feeds.opml)'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default='config.yaml',
        help='配置文件路径 (默认: config.yaml) / Config file path (default: config.yaml)'
    )
    
    parser.add_argument(
        '--env',
        type=str,
        default=None,
        help='.env文件路径 (默认: 自动查找) / .env file path (default: auto-discover)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='启用详细日志输出 / Enable verbose logging'
    )
    
    parser.add_argument(
        '--checkpoint',
        type=str,
        default='evaluation_checkpoint.json',
        help='检查点文件名，用于断点续传 (默认: evaluation_checkpoint.json) / Checkpoint filename for resume (default: evaluation_checkpoint.json)'
    )
    
    parser.add_argument(
        '--concurrency', '-c',
        type=int,
        default=5,
        help='并发数 (默认: 5) / Number of concurrent workers (default: 5)'
    )
    
    parser.add_argument(
        '--timeout', '-t',
        type=int,
        default=60,
        help='单个源评估超时时间（秒）(默认: 60) / Timeout per feed in seconds (default: 60)'
    )
    
    return parser.parse_args()


def main() -> int:
    """
    主函数
    Main function
    
    Returns:
        退出码：0表示成功，非0表示失败
        Exit code: 0 for success, non-zero for failure
    """
    # 解析命令行参数
    args = parse_args()
    
    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("启用详细日志模式")
    
    # 切换到项目根目录（确保相对路径正确）
    os.chdir(project_root)
    logger.info(f"工作目录: {project_root}")
    
    # 验证OPML文件存在
    opml_path = Path(args.opml)
    if not opml_path.exists():
        logger.error(f"OPML文件不存在: {args.opml}")
        print(f"错误: OPML文件不存在: {args.opml}", file=sys.stderr)
        return 1
    
    # 创建输出目录
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"输出目录: {output_dir.resolve()}")
    
    # 加载配置
    config_path = Path(args.config)
    if not config_path.exists():
        logger.error(f"配置文件不存在: {args.config}")
        print(f"错误: 配置文件不存在: {args.config}", file=sys.stderr)
        return 1
    
    try:
        config = load_config(str(config_path), args.env)
        logger.info(f"已加载配置文件: {config_path}")
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        print(f"错误: 加载配置文件失败: {e}", file=sys.stderr)
        return 1
    
    # 检查AI配置
    ai_config = config.get('ai', {})
    if not ai_config.get('api_key'):
        logger.warning("未配置AI API密钥，评估功能可能受限")
        print("警告: 未配置AI API密钥 (OPENAI_API_KEY)，评估功能可能受限", file=sys.stderr)
    
    # 初始化AI分析器
    try:
        ai_analyzer = AIAnalyzer(ai_config)
        logger.info("AI分析器初始化成功")
    except Exception as e:
        logger.error(f"初始化AI分析器失败: {e}")
        print(f"错误: 初始化AI分析器失败: {e}", file=sys.stderr)
        return 1
    
    # 初始化RSS评估器
    evaluator_config = {
        'min_quality_score': args.min_score,
        'proxy': config.get('proxy', {}).get('url') if config.get('proxy', {}).get('enabled') else None,
        'timeout': ai_config.get('timeout', 30)
    }
    
    try:
        evaluator = RSSEvaluator(ai_analyzer, evaluator_config)
        logger.info("RSS评估器初始化成功")
    except Exception as e:
        logger.error(f"初始化RSS评估器失败: {e}")
        print(f"错误: 初始化RSS评估器失败: {e}", file=sys.stderr)
        return 1
    
    # 开始评估
    print(f"\n{'='*60}")
    print(f"RSS订阅源质量评估")
    print(f"{'='*60}")
    print(f"OPML文件: {opml_path.resolve()}")
    print(f"最低评分阈值: {args.min_score}")
    print(f"输出目录: {output_dir.resolve()}")
    print(f"{'='*60}\n")
    
    logger.info(f"开始评估OPML文件: {opml_path}")
    
    # 检查点文件路径
    checkpoint_path = output_dir / args.checkpoint
    print(f"检查点文件: {checkpoint_path}")
    print(f"并发数: {args.concurrency}, 单源超时: {args.timeout}s")
    print(f"(支持断点续传，中断后重新运行会从上次位置继续)")
    print(f"{'='*60}\n")
    
    try:
        evaluations = evaluator.evaluate_all_feeds(
            str(opml_path), 
            str(checkpoint_path),
            concurrency=args.concurrency,
            feed_timeout=args.timeout
        )
    except Exception as e:
        logger.error(f"评估过程出错: {e}")
        print(f"错误: 评估过程出错: {e}", file=sys.stderr)
        return 1
    
    if not evaluations:
        logger.warning("没有获取到任何评估结果")
        print("警告: 没有获取到任何评估结果", file=sys.stderr)
        return 1
    
    # 生成评估报告
    report_path = output_dir / args.report
    try:
        report = evaluator.generate_report(evaluations)
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        logger.info(f"评估报告已保存: {report_path}")
        print(f"✓ 评估报告已保存: {report_path}")
    except Exception as e:
        logger.error(f"保存评估报告失败: {e}")
        print(f"错误: 保存评估报告失败: {e}", file=sys.stderr)
        return 1
    
    # 导出筛选后的OPML
    filtered_opml_path = output_dir / args.filtered_opml
    try:
        kept_count = evaluator.export_filtered_opml(
            evaluations, 
            str(filtered_opml_path), 
            min_score=args.min_score
        )
        logger.info(f"筛选后的OPML已保存: {filtered_opml_path}")
        print(f"✓ 筛选后的OPML已保存: {filtered_opml_path}")
    except Exception as e:
        logger.error(f"导出筛选后的OPML失败: {e}")
        print(f"错误: 导出筛选后的OPML失败: {e}", file=sys.stderr)
        return 1
    
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


if __name__ == '__main__':
    sys.exit(main())
