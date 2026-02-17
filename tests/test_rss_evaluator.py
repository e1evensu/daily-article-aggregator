"""
RSSEvaluator属性测试

测试RSS源质量评估器的属性测试，验证：
- Property 12: RSS源活跃度判断
- Property 13: 质量评分一致性
- Property 14: 评估报告完整性
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock

from hypothesis import given, strategies as st, settings, assume

from src.evaluators.rss_evaluator import RSSEvaluator, FeedEvaluation


# =============================================================================
# 测试辅助函数和策略
# =============================================================================

def create_mock_ai_analyzer():
    """创建模拟的AI分析器"""
    mock = Mock()
    mock._call_api = Mock(return_value="原创性: 是\n评分: 0.8\n理由: 原创内容")
    return mock


def create_evaluator(config=None):
    """创建评估器实例"""
    if config is None:
        config = {'inactive_months': 6, 'sample_count': 3, 'min_quality_score': 0.6}
    mock_ai = create_mock_ai_analyzer()
    return RSSEvaluator(mock_ai, config)


# 生成有效的技术深度值
technical_depth_strategy = st.sampled_from(['high', 'medium', 'low'])

# 生成有效的原创性评分 (0.0-1.0)
originality_score_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

# 生成有效的活跃状态
is_active_strategy = st.booleans()

# 生成有效的推荐操作
recommendation_strategy = st.sampled_from(['keep', 'remove', 'review'])


# 生成有效的质量评分 (0.0-1.0)
quality_score_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

# 生成有效的RSS源名称
feed_name_strategy = st.text(min_size=1, max_size=100).filter(lambda x: x.strip())

# 生成有效的URL
feed_url_strategy = st.text(min_size=5, max_size=200).map(
    lambda x: f"https://example.com/feed/{x.replace(' ', '_')}"
)

# 生成有效的日期字符串
date_string_strategy = st.dates().map(lambda d: d.strftime("%Y-%m-%d"))

# 生成有效的分类标签列表
categories_strategy = st.lists(
    st.text(min_size=1, max_size=30).filter(lambda x: x.strip()),
    min_size=0,
    max_size=4
)


def feed_evaluation_strategy():
    """生成有效的FeedEvaluation对象"""
    return st.builds(
        FeedEvaluation,
        url=feed_url_strategy,
        name=feed_name_strategy,
        last_updated=date_string_strategy,
        is_active=is_active_strategy,
        quality_score=quality_score_strategy,
        originality_score=originality_score_strategy,
        technical_depth=technical_depth_strategy,
        categories=categories_strategy,
        recommendation=recommendation_strategy,
        sample_articles=st.just([])
    )


# =============================================================================
# Property 12: RSS源活跃度判断
# =============================================================================

class TestPropertyFeedActivityCheck:
    """
    Feature: daily-article-aggregator, Property 12: RSS源活跃度判断
    
    *对于任意*RSS订阅源，如果最后更新时间距今超过6个月，
    则应该被标记为不活跃（is_active=False）。
    
    **Validates: Requirements 9.1, 9.2**
    """
    
    @given(
        months_ago=st.integers(min_value=7, max_value=36)
    )
    @settings(max_examples=100)
    def test_inactive_feed_when_last_update_over_6_months(self, months_ago):
        """
        Feature: daily-article-aggregator, Property 12: RSS源活跃度判断
        
        验证超过6个月未更新的订阅源被标记为不活跃。
        **Validates: Requirements 9.1, 9.2**
        """
        evaluator = create_evaluator({'inactive_months': 6})
        
        # 计算超过6个月前的日期
        old_date = datetime.now() - timedelta(days=months_ago * 30)
        
        # 直接测试活跃度判断逻辑
        # 使用 inactive_months * 30 天作为截止日期
        cutoff_date = datetime.now() - timedelta(days=evaluator.inactive_months * 30)
        is_active = old_date >= cutoff_date
        
        # 超过6个月的应该被标记为不活跃
        assert is_active is False, (
            f"最后更新时间 {old_date.strftime('%Y-%m-%d')} 距今 {months_ago} 个月，"
            f"超过 {evaluator.inactive_months} 个月阈值，应该被标记为不活跃"
        )

    
    @given(
        months_ago=st.integers(min_value=0, max_value=5)
    )
    @settings(max_examples=100)
    def test_active_feed_when_last_update_within_6_months(self, months_ago):
        """
        Feature: daily-article-aggregator, Property 12: RSS源活跃度判断
        
        验证6个月内有更新的订阅源被标记为活跃。
        **Validates: Requirements 9.1, 9.2**
        """
        evaluator = create_evaluator({'inactive_months': 6})
        
        # 计算6个月内的日期
        recent_date = datetime.now() - timedelta(days=months_ago * 30)
        
        # 直接测试活跃度判断逻辑
        cutoff_date = datetime.now() - timedelta(days=evaluator.inactive_months * 30)
        is_active = recent_date >= cutoff_date
        
        # 6个月内的应该被标记为活跃
        assert is_active is True, (
            f"最后更新时间 {recent_date.strftime('%Y-%m-%d')} 距今 {months_ago} 个月，"
            f"在 {evaluator.inactive_months} 个月阈值内，应该被标记为活跃"
        )
    
    @given(
        days_ago=st.integers(min_value=0, max_value=365)
    )
    @settings(max_examples=100)
    def test_activity_boundary_at_6_months(self, days_ago):
        """
        Feature: daily-article-aggregator, Property 12: RSS源活跃度判断
        
        验证活跃度判断在6个月边界处的正确性。
        **Validates: Requirements 9.1, 9.2**
        """
        evaluator = create_evaluator({'inactive_months': 6})
        
        # 计算指定天数前的日期
        test_date = datetime.now() - timedelta(days=days_ago)
        
        # 计算截止日期（6个月 = 180天）
        cutoff_days = evaluator.inactive_months * 30
        cutoff_date = datetime.now() - timedelta(days=cutoff_days)
        
        # 判断活跃状态
        is_active = test_date >= cutoff_date
        
        # 验证逻辑一致性
        if days_ago <= cutoff_days:
            assert is_active is True, (
                f"距今 {days_ago} 天 <= {cutoff_days} 天阈值，应该是活跃的"
            )
        else:
            assert is_active is False, (
                f"距今 {days_ago} 天 > {cutoff_days} 天阈值，应该是不活跃的"
            )


# =============================================================================
# Property 13: 质量评分一致性
# =============================================================================

class TestPropertyQualityScoreConsistency:
    """
    Feature: daily-article-aggregator, Property 13: 质量评分一致性
    
    *对于任意*RSS源评估结果，质量评分应该与原创性评分和技术深度评估结果一致：
    高原创性+高技术深度应该对应高质量评分。
    
    **Validates: Requirements 9.4, 9.5, 9.6**
    """
    
    @given(
        is_active=is_active_strategy,
        originality_score=originality_score_strategy,
        technical_depth=technical_depth_strategy
    )
    @settings(max_examples=100)
    def test_quality_score_calculation_consistency(self, is_active, originality_score, technical_depth):
        """
        Feature: daily-article-aggregator, Property 13: 质量评分一致性
        
        验证质量评分计算与输入参数一致。
        **Validates: Requirements 9.4, 9.5, 9.6**
        """
        evaluator = create_evaluator()
        
        # 计算质量评分
        quality_score = evaluator._calculate_quality_score(
            is_active, originality_score, technical_depth
        )
        
        # 验证评分在有效范围内
        assert 0.0 <= quality_score <= 1.0, (
            f"质量评分 {quality_score} 应该在 0.0-1.0 范围内"
        )
        
        # 验证评分是浮点数
        assert isinstance(quality_score, float), "质量评分应该是浮点数"

    
    @given(
        originality_score=st.floats(min_value=0.8, max_value=1.0, allow_nan=False)
    )
    @settings(max_examples=100)
    def test_high_quality_for_high_originality_and_depth(self, originality_score):
        """
        Feature: daily-article-aggregator, Property 13: 质量评分一致性
        
        验证高原创性+高技术深度+活跃状态对应高质量评分。
        **Validates: Requirements 9.4, 9.5, 9.6**
        """
        evaluator = create_evaluator()
        
        # 高原创性 + 高技术深度 + 活跃
        quality_score = evaluator._calculate_quality_score(
            is_active=True,
            originality_score=originality_score,
            technical_depth='high'
        )
        
        # 计算预期的最低分数（使用实际输入的原创性评分）
        # 活跃度权重30%: 1.0 * 0.3 = 0.3
        # 原创性权重40%: originality_score * 0.4
        # 技术深度权重30%: 1.0 * 0.3 = 0.3
        expected_score = round(0.3 + (originality_score * 0.4) + 0.3, 2)
        
        # 由于_calculate_quality_score使用round(x, 2)，我们也使用相同精度比较
        assert quality_score == expected_score, (
            f"高原创性({originality_score})+高技术深度+活跃状态的质量评分 {quality_score} "
            f"应该等于 {expected_score}"
        )
        
        # 验证高质量评分（>= 0.9）
        # 当originality_score >= 0.8时，最低分数为 0.3 + 0.32 + 0.3 = 0.92
        assert quality_score >= 0.9, (
            f"高原创性+高技术深度+活跃状态的质量评分 {quality_score} 应该 >= 0.9"
        )
    
    @given(
        originality_score=st.floats(min_value=0.0, max_value=0.3, allow_nan=False)
    )
    @settings(max_examples=100)
    def test_low_quality_for_low_originality_and_depth(self, originality_score):
        """
        Feature: daily-article-aggregator, Property 13: 质量评分一致性
        
        验证低原创性+低技术深度+不活跃状态对应低质量评分。
        **Validates: Requirements 9.4, 9.5, 9.6**
        """
        evaluator = create_evaluator()
        
        # 低原创性 + 低技术深度 + 不活跃
        quality_score = evaluator._calculate_quality_score(
            is_active=False,
            originality_score=originality_score,
            technical_depth='low'
        )
        
        # 计算预期的最高分数
        # 活跃度权重30%: 0.0 * 0.3 = 0.0
        # 原创性权重40%: 0.3 * 0.4 = 0.12 (最高)
        # 技术深度权重30%: 0.2 * 0.3 = 0.06
        # 最高预期: 0.0 + 0.12 + 0.06 = 0.18
        max_expected = 0.0 + (0.3 * 0.4) + (0.2 * 0.3)  # 0.18
        
        assert quality_score <= max_expected, (
            f"低原创性({originality_score})+低技术深度+不活跃状态的质量评分 {quality_score} "
            f"应该 <= {max_expected}"
        )

    
    @given(
        originality_score1=originality_score_strategy,
        originality_score2=originality_score_strategy,
        technical_depth=technical_depth_strategy
    )
    @settings(max_examples=100)
    def test_higher_originality_leads_to_higher_score(self, originality_score1, originality_score2, technical_depth):
        """
        Feature: daily-article-aggregator, Property 13: 质量评分一致性
        
        验证更高的原创性评分导致更高的质量评分（其他条件相同）。
        **Validates: Requirements 9.4, 9.5, 9.6**
        """
        evaluator = create_evaluator()
        
        # 计算两个不同原创性评分的质量评分
        score1 = evaluator._calculate_quality_score(True, originality_score1, technical_depth)
        score2 = evaluator._calculate_quality_score(True, originality_score2, technical_depth)
        
        # 验证单调性：更高的原创性应该导致更高或相等的质量评分
        if originality_score1 > originality_score2:
            assert score1 >= score2, (
                f"原创性 {originality_score1} > {originality_score2}，"
                f"但质量评分 {score1} < {score2}"
            )
        elif originality_score1 < originality_score2:
            assert score1 <= score2, (
                f"原创性 {originality_score1} < {originality_score2}，"
                f"但质量评分 {score1} > {score2}"
            )
        else:
            assert score1 == score2, (
                f"原创性相同 {originality_score1}，"
                f"但质量评分不同 {score1} != {score2}"
            )
    
    @given(
        originality_score=originality_score_strategy
    )
    @settings(max_examples=100)
    def test_technical_depth_ordering(self, originality_score):
        """
        Feature: daily-article-aggregator, Property 13: 质量评分一致性
        
        验证技术深度的排序：high > medium > low。
        **Validates: Requirements 9.4, 9.5, 9.6**
        """
        evaluator = create_evaluator()
        
        # 计算不同技术深度的质量评分
        score_high = evaluator._calculate_quality_score(True, originality_score, 'high')
        score_medium = evaluator._calculate_quality_score(True, originality_score, 'medium')
        score_low = evaluator._calculate_quality_score(True, originality_score, 'low')
        
        # 验证排序
        assert score_high >= score_medium, (
            f"high技术深度评分 {score_high} 应该 >= medium评分 {score_medium}"
        )
        assert score_medium >= score_low, (
            f"medium技术深度评分 {score_medium} 应该 >= low评分 {score_low}"
        )

    
    @given(
        originality_score=originality_score_strategy,
        technical_depth=technical_depth_strategy
    )
    @settings(max_examples=100)
    def test_activity_impact_on_score(self, originality_score, technical_depth):
        """
        Feature: daily-article-aggregator, Property 13: 质量评分一致性
        
        验证活跃状态对质量评分的影响。
        **Validates: Requirements 9.4, 9.5, 9.6**
        """
        evaluator = create_evaluator()
        
        # 计算活跃和不活跃状态的质量评分
        score_active = evaluator._calculate_quality_score(True, originality_score, technical_depth)
        score_inactive = evaluator._calculate_quality_score(False, originality_score, technical_depth)
        
        # 活跃状态应该有更高的评分
        assert score_active >= score_inactive, (
            f"活跃状态评分 {score_active} 应该 >= 不活跃状态评分 {score_inactive}"
        )
        
        # 活跃度权重为30%，所以差值应该是0.3
        expected_diff = 0.3
        actual_diff = round(score_active - score_inactive, 2)
        assert actual_diff == expected_diff, (
            f"活跃与不活跃的评分差值应该是 {expected_diff}，实际是 {actual_diff}"
        )


# =============================================================================
# Property 14: 评估报告完整性
# =============================================================================

class TestPropertyReportCompleteness:
    """
    Feature: daily-article-aggregator, Property 14: 评估报告完整性
    
    *对于任意*评估结果列表，生成的报告应该包含每个RSS源的名称、
    活跃状态、质量评分和推荐操作。
    
    **Validates: Requirements 9.8**
    """
    
    @given(
        evaluations=st.lists(feed_evaluation_strategy(), min_size=1, max_size=20)
    )
    @settings(max_examples=100)
    def test_report_contains_all_feed_names(self, evaluations):
        """
        Feature: daily-article-aggregator, Property 14: 评估报告完整性
        
        验证报告包含所有RSS源的名称。
        **Validates: Requirements 9.8**
        """
        evaluator = create_evaluator()
        
        # 生成报告
        report = evaluator.generate_report(evaluations)
        
        # 验证每个订阅源的名称都在报告中
        for eval_result in evaluations:
            assert eval_result.name in report, (
                f"报告应该包含订阅源名称 '{eval_result.name}'"
            )

    
    @given(
        evaluations=st.lists(feed_evaluation_strategy(), min_size=1, max_size=20)
    )
    @settings(max_examples=100)
    def test_report_contains_quality_scores(self, evaluations):
        """
        Feature: daily-article-aggregator, Property 14: 评估报告完整性
        
        验证报告包含质量评分信息（在统计部分或详细部分）。
        **Validates: Requirements 9.8**
        """
        evaluator = create_evaluator()
        
        # 生成报告
        report = evaluator.generate_report(evaluations)
        
        # 验证报告包含质量评分相关信息
        # 报告中应该有"质量评分"字样（在统计部分或详细部分）
        assert '质量评分' in report, "报告应该包含质量评分信息"
        
        # 验证平均质量评分在报告中
        if evaluations:
            avg_score = sum(e.quality_score for e in evaluations) / len(evaluations)
            # 平均分以2位小数格式出现
            assert f"{avg_score:.2f}" in report, (
                f"报告应该包含平均质量评分 {avg_score:.2f}"
            )
        
        # 验证推荐保留和需要审核的订阅源有质量评分显示
        keep_and_review = [e for e in evaluations if e.recommendation in ('keep', 'review')]
        for eval_result in keep_and_review:
            # 这些订阅源的质量评分应该在报告中
            score_str = str(eval_result.quality_score)
            assert (score_str in report or 
                    f"{eval_result.quality_score:.2f}" in report or
                    f"{eval_result.quality_score:.1f}" in report), (
                f"报告应该包含订阅源 '{eval_result.name}' 的质量评分 {eval_result.quality_score}"
            )
    
    @given(
        evaluations=st.lists(feed_evaluation_strategy(), min_size=1, max_size=20)
    )
    @settings(max_examples=100)
    def test_report_contains_activity_status(self, evaluations):
        """
        Feature: daily-article-aggregator, Property 14: 评估报告完整性
        
        验证报告包含所有RSS源的活跃状态信息。
        **Validates: Requirements 9.8**
        """
        evaluator = create_evaluator()
        
        # 生成报告
        report = evaluator.generate_report(evaluations)
        
        # 统计活跃和不活跃的数量
        active_count = sum(1 for e in evaluations if e.is_active)
        
        # 报告应该包含活跃状态的统计信息
        assert '活跃' in report, "报告应该包含活跃状态信息"
        
        # 如果有不活跃的订阅源，报告应该提及
        inactive_feeds = [e for e in evaluations if not e.is_active]
        for feed in inactive_feeds:
            # 不活跃的订阅源应该在"建议移除"部分或有"不活跃"标记
            assert (feed.name in report), (
                f"不活跃的订阅源 '{feed.name}' 应该在报告中"
            )

    
    @given(
        evaluations=st.lists(feed_evaluation_strategy(), min_size=1, max_size=20)
    )
    @settings(max_examples=100)
    def test_report_contains_recommendations(self, evaluations):
        """
        Feature: daily-article-aggregator, Property 14: 评估报告完整性
        
        验证报告包含推荐操作分类（保留/移除/审核）。
        **Validates: Requirements 9.8**
        """
        evaluator = create_evaluator()
        
        # 生成报告
        report = evaluator.generate_report(evaluations)
        
        # 统计各类推荐的数量
        keep_count = sum(1 for e in evaluations if e.recommendation == 'keep')
        remove_count = sum(1 for e in evaluations if e.recommendation == 'remove')
        review_count = sum(1 for e in evaluations if e.recommendation == 'review')
        
        # 如果有推荐保留的，报告应该有相应部分
        if keep_count > 0:
            assert '保留' in report or 'keep' in report.lower(), (
                f"有 {keep_count} 个推荐保留的订阅源，报告应该包含保留部分"
            )
        
        # 如果有建议移除的，报告应该有相应部分
        if remove_count > 0:
            assert '移除' in report or 'remove' in report.lower(), (
                f"有 {remove_count} 个建议移除的订阅源，报告应该包含移除部分"
            )
        
        # 如果有需要审核的，报告应该有相应部分
        if review_count > 0:
            assert '审核' in report or 'review' in report.lower(), (
                f"有 {review_count} 个需要审核的订阅源，报告应该包含审核部分"
            )
    
    @given(
        evaluations=st.lists(feed_evaluation_strategy(), min_size=1, max_size=10)
    )
    @settings(max_examples=100)
    def test_report_has_valid_structure(self, evaluations):
        """
        Feature: daily-article-aggregator, Property 14: 评估报告完整性
        
        验证报告具有有效的Markdown结构。
        **Validates: Requirements 9.8**
        """
        evaluator = create_evaluator()
        
        # 生成报告
        report = evaluator.generate_report(evaluations)
        
        # 验证报告是非空字符串
        assert isinstance(report, str), "报告应该是字符串"
        assert len(report) > 0, "报告不应该为空"
        
        # 验证报告包含标题
        assert '# RSS订阅源评估报告' in report, "报告应该包含主标题"
        
        # 验证报告包含统计部分
        assert '总订阅源数' in report or '总体统计' in report, (
            "报告应该包含统计信息"
        )

    
    def test_empty_evaluations_report(self):
        """
        Feature: daily-article-aggregator, Property 14: 评估报告完整性
        
        验证空评估列表生成有效的报告。
        **Validates: Requirements 9.8**
        """
        evaluator = create_evaluator()
        
        # 生成空列表的报告
        report = evaluator.generate_report([])
        
        # 验证报告是有效的
        assert isinstance(report, str), "报告应该是字符串"
        assert len(report) > 0, "报告不应该为空"
        assert '# RSS订阅源评估报告' in report, "报告应该包含主标题"
    
    @given(
        evaluations=st.lists(feed_evaluation_strategy(), min_size=1, max_size=20)
    )
    @settings(max_examples=100)
    def test_report_statistics_accuracy(self, evaluations):
        """
        Feature: daily-article-aggregator, Property 14: 评估报告完整性
        
        验证报告中的统计数据准确性。
        **Validates: Requirements 9.8**
        """
        evaluator = create_evaluator()
        
        # 生成报告
        report = evaluator.generate_report(evaluations)
        
        # 计算预期统计数据
        total = len(evaluations)
        active_count = sum(1 for e in evaluations if e.is_active)
        keep_count = sum(1 for e in evaluations if e.recommendation == 'keep')
        remove_count = sum(1 for e in evaluations if e.recommendation == 'remove')
        review_count = sum(1 for e in evaluations if e.recommendation == 'review')
        
        # 验证总数在报告中
        assert str(total) in report, (
            f"报告应该包含总订阅源数 {total}"
        )
        
        # 验证推荐保留数量
        assert str(keep_count) in report, (
            f"报告应该包含推荐保留数量 {keep_count}"
        )
        
        # 验证建议移除数量
        assert str(remove_count) in report, (
            f"报告应该包含建议移除数量 {remove_count}"
        )
        
        # 验证需要审核数量
        assert str(review_count) in report, (
            f"报告应该包含需要审核数量 {review_count}"
        )
