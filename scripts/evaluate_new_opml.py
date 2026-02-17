#!/usr/bin/env python3
"""
单独评估新OPML文件并合并到现有报告

用法:
    python scripts/evaluate_new_opml.py rss/hn-popular-blogs-2025.opml
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_config
from src.analyzers.ai_analyzer import AIAnalyzer
from src.evaluators.rss_evaluator import RSSEvaluator, FeedEvaluation


def load_existing_checkpoint(checkpoint_path: str) -> list[dict]:
    """加载现有检查点"""
    if Path(checkpoint_path).exists():
        with open(checkpoint_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('evaluations', [])
    return []


def save_merged_checkpoint(checkpoint_path: str, evaluations: list[dict]):
    """保存合并后的检查点"""
    # 确保目录存在
    Path(checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
    checkpoint_data = {
        'timestamp': datetime.now().isoformat(),
        'count': len(evaluations),
        'evaluations': evaluations
    }
    with open(checkpoint_path, 'w', encoding='utf-8') as f:
        json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
    print(f"✅ 检查点已保存: {len(evaluations)} 个评估结果")


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/evaluate_new_opml.py <opml_file>")
        print("示例: python scripts/evaluate_new_opml.py rss/hn-popular-blogs-2025.opml")
        sys.exit(1)
    
    opml_path = sys.argv[1]
    if not Path(opml_path).exists():
        print(f"❌ 文件不存在: {opml_path}")
        sys.exit(1)
    
    print(f"📂 评估OPML: {opml_path}")
    print("=" * 60)
    
    # 加载配置
    config = load_config("config.yaml")
    
    # 初始化AI分析器
    ai_config = config.get('ai', {})
    ai_analyzer = AIAnalyzer(ai_config)
    
    # 初始化评估器
    evaluator = RSSEvaluator(ai_analyzer, config)
    
    # 检查点路径
    checkpoint_path = "reports/evaluation_checkpoint.json"
    report_path = "reports/evaluation_report.md"
    filtered_opml_path = "reports/filtered_feeds.opml"
    
    # 加载现有评估结果
    existing_evals = load_existing_checkpoint(checkpoint_path)
    existing_urls = {e['url'] for e in existing_evals}
    print(f"📊 现有评估结果: {len(existing_evals)} 个")
    
    # 评估新OPML（只评估不在现有结果中的）
    print(f"\n🔍 开始评估新订阅源...")
    new_evaluations = evaluator.evaluate_all_feeds(
        opml_path,
        checkpoint_path=None,  # 不使用断点，直接评估
        concurrency=3,
        feed_timeout=60
    )
    
    # 过滤出真正新的评估结果
    truly_new = []
    for eval_obj in new_evaluations:
        if eval_obj.url not in existing_urls:
            truly_new.append({
                'url': eval_obj.url,
                'name': eval_obj.name,
                'last_updated': eval_obj.last_updated,
                'is_active': eval_obj.is_active,
                'quality_score': eval_obj.quality_score,
                'originality_score': eval_obj.originality_score,
                'technical_depth': eval_obj.technical_depth,
                'categories': eval_obj.categories,
                'recommendation': eval_obj.recommendation,
                'sample_articles': eval_obj.sample_articles,
                'failure_reason': eval_obj.failure_reason
            })
    
    print(f"\n✨ 新增评估: {len(truly_new)} 个")
    
    # 合并结果
    merged_evals = existing_evals + truly_new
    
    # 保存合并后的检查点
    save_merged_checkpoint(checkpoint_path, merged_evals)
    
    # 转换为FeedEvaluation对象用于生成报告
    all_feed_evals = []
    for e in merged_evals:
        all_feed_evals.append(FeedEvaluation(
            url=e['url'],
            name=e['name'],
            last_updated=e.get('last_updated', ''),
            is_active=e.get('is_active', False),
            quality_score=e.get('quality_score', 0.0),
            originality_score=e.get('originality_score', 0.0),
            technical_depth=e.get('technical_depth', 'medium'),
            categories=e.get('categories', []),
            recommendation=e.get('recommendation', 'review'),
            sample_articles=e.get('sample_articles', []),
            failure_reason=e.get('failure_reason', '')
        ))
    
    # 生成合并后的报告
    report = evaluator.generate_report(all_feed_evals)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"📝 报告已更新: {report_path}")
    
    # 导出筛选后的OPML
    kept_count = evaluator.export_filtered_opml(all_feed_evals, filtered_opml_path)
    print(f"📤 筛选OPML已更新: {filtered_opml_path} ({kept_count} 个)")
    
    # 统计
    print("\n" + "=" * 60)
    print("📊 合并后统计:")
    print(f"   总订阅源: {len(merged_evals)}")
    print(f"   推荐保留: {sum(1 for e in merged_evals if e.get('recommendation') == 'keep')}")
    print(f"   建议移除: {sum(1 for e in merged_evals if e.get('recommendation') == 'remove')}")
    print(f"   需要审核: {sum(1 for e in merged_evals if e.get('recommendation') == 'review')}")


if __name__ == "__main__":
    main()
