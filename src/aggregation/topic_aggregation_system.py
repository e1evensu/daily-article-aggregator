"""
话题聚合系统主类

整合所有组件，实现完整的话题聚合流程：
1. 质量过滤
2. 话题聚类
3. 综述生成
4. 飞书文档发布
5. RSS 生成

Requirements:
- 6.1: 整合所有组件
- 6.2: 实现完整处理流程
- 6.3: 复用现有的 RSS 抓取器和去重工具
- 6.4: 支持配置化
- 6.5: 支持独立运行和作为调度器任务运行
"""

import logging
from datetime import datetime
from typing import Any

from src.models import Article
from src.aggregation.models import TopicCluster, Synthesis, FilterResult, PublishResult
from src.aggregation.quality_filter import QualityFilter
from src.aggregation.aggregation_engine import AggregationEngine
from src.aggregation.synthesis_generator import SynthesisGenerator
from src.aggregation.feishu_doc_publisher import FeishuDocPublisher
from src.aggregation.knowledge_rss_generator import KnowledgeRSSGenerator

logger = logging.getLogger(__name__)


class TopicAggregationSystem:
    """
    话题聚合系统
    
    整合所有组件，实现完整的话题聚合流程。
    
    Attributes:
        quality_filter: 质量过滤器
        aggregation_engine: 聚合引擎
        synthesis_generator: 综述生成器
        doc_publisher: 飞书文档发布器
        rss_generator: RSS 生成器
    """
    
    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化话题聚合系统
        
        Args:
            config: 配置字典，包含各组件的配置
        """
        config = config or {}
        
        # 获取各组件配置
        filter_config = config.get('quality_filter', {})
        engine_config = config.get('aggregation_engine', {})
        synthesis_config = config.get('synthesis_generator', {})
        publisher_config = config.get('doc_publisher', {})
        rss_config = config.get('rss_generator', {})
        
        # 共享 AI 配置
        ai_config = config.get('ai', {})
        if ai_config:
            engine_config['ai_config'] = ai_config
            synthesis_config.update({
                'api_base': ai_config.get('api_base'),
                'api_key': ai_config.get('api_key'),
                'model': ai_config.get('model'),
            })
        
        # 初始化组件
        self.quality_filter = QualityFilter(filter_config)
        self.aggregation_engine = AggregationEngine(engine_config)
        self.synthesis_generator = SynthesisGenerator(synthesis_config)
        self.doc_publisher = FeishuDocPublisher(publisher_config)
        self.rss_generator = KnowledgeRSSGenerator(rss_config)
        
        # 加载现有 RSS 条目
        self.rss_generator.load_existing_items()
        
        logger.info("TopicAggregationSystem 初始化完成")
    
    def run(
        self, 
        articles: list[Article],
        publish_to_feishu: bool = True,
        generate_rss: bool = True
    ) -> dict[str, Any]:
        """
        执行完整的话题聚合流程
        
        Args:
            articles: 文章列表
            publish_to_feishu: 是否发布到飞书文档
            generate_rss: 是否生成 RSS
        
        Returns:
            处理结果字典，包含：
            - filter_results: 过滤结果列表
            - clusters: 话题聚类列表
            - pending_clusters: 待整合的聚类列表
            - syntheses: 生成的综述列表
            - publish_results: 发布结果列表
            - rss_path: RSS 文件路径（如果生成）
        
        Requirements:
            - 6.2: 实现完整处理流程
        """
        result = {
            'filter_results': [],
            'clusters': [],
            'pending_clusters': [],
            'syntheses': [],
            'publish_results': [],
            'rss_path': None,
            'stats': {
                'total_articles': len(articles),
                'filtered_articles': 0,
                'passed_articles': 0,
                'clusters_count': 0,
                'pending_clusters_count': 0,
                'syntheses_count': 0,
                'published_count': 0,
            }
        }
        
        if not articles:
            logger.warning("没有文章需要处理")
            return result
        
        logger.info(f"开始处理 {len(articles)} 篇文章")
        
        # 步骤 1: 质量过滤
        logger.info("步骤 1: 质量过滤")
        filter_result = self.quality_filter.filter_articles(articles)
        result['filter_results'] = filter_result

        passed_articles = filter_result.passed
        result['stats']['filtered_articles'] = len(articles) - len(passed_articles)
        result['stats']['passed_articles'] = len(passed_articles)
        
        logger.info(
            f"过滤完成: {len(passed_articles)}/{len(articles)} 篇文章通过"
        )
        
        if not passed_articles:
            logger.warning("所有文章都被过滤，无需继续处理")
            return result
        
        # 步骤 2: 话题聚类
        logger.info("步骤 2: 话题聚类")
        clusters = self.aggregation_engine.cluster_articles(passed_articles)
        result['clusters'] = clusters
        result['stats']['clusters_count'] = len(clusters)
        
        logger.info(f"聚类完成: {len(clusters)} 个话题")
        
        # 步骤 3: 获取待整合的聚类
        logger.info("步骤 3: 获取待整合聚类")
        pending_clusters = self.aggregation_engine.get_pending_clusters(clusters)
        result['pending_clusters'] = pending_clusters
        result['stats']['pending_clusters_count'] = len(pending_clusters)
        
        logger.info(f"待整合聚类: {len(pending_clusters)} 个")
        
        if not pending_clusters:
            logger.info("没有达到聚合阈值的话题")
            # 仍然生成 RSS（保留现有条目）
            if generate_rss:
                result['rss_path'] = self.rss_generator.save_feed()
            return result
        
        # 步骤 4: 生成综述
        logger.info("步骤 4: 生成综述")
        syntheses = []
        for cluster in pending_clusters:
            try:
                synthesis = self.synthesis_generator.generate_synthesis(cluster)
                syntheses.append(synthesis)
                logger.info(f"生成综述: {synthesis.title}")
            except Exception as e:
                logger.error(f"生成综述失败: {e}")
        
        result['syntheses'] = syntheses
        result['stats']['syntheses_count'] = len(syntheses)
        
        # 步骤 5: 发布到飞书文档
        if publish_to_feishu and syntheses:
            logger.info("步骤 5: 发布到飞书文档")
            publish_results = []
            for synthesis in syntheses:
                try:
                    pub_result = self.doc_publisher.publish(synthesis)
                    publish_results.append(pub_result)
                    
                    if pub_result.success:
                        logger.info(f"发布成功: {pub_result.document_url}")
                        result['stats']['published_count'] += 1
                        
                        # 添加到 RSS
                        if generate_rss:
                            self.rss_generator.add_synthesis(
                                synthesis, 
                                pub_result.document_url
                            )
                    else:
                        logger.warning(f"发布失败: {pub_result.error_message}")
                        
                        # 即使发布失败，也添加到 RSS（使用本地备份链接）
                        if generate_rss:
                            self.rss_generator.add_synthesis(synthesis)
                            
                except Exception as e:
                    logger.error(f"发布综述时发生错误: {e}")
            
            result['publish_results'] = publish_results
        elif generate_rss and syntheses:
            # 不发布到飞书，但仍然添加到 RSS
            for synthesis in syntheses:
                self.rss_generator.add_synthesis(synthesis)
        
        # 步骤 6: 保存 RSS
        if generate_rss:
            logger.info("步骤 6: 保存 RSS")
            result['rss_path'] = self.rss_generator.save_feed()
        
        logger.info(
            f"处理完成: "
            f"过滤 {result['stats']['filtered_articles']} 篇, "
            f"聚类 {result['stats']['clusters_count']} 个, "
            f"综述 {result['stats']['syntheses_count']} 篇, "
            f"发布 {result['stats']['published_count']} 篇"
        )
        
        return result
    
    def run_incremental(
        self, 
        new_articles: list[Article],
        existing_clusters: list[TopicCluster] | None = None
    ) -> dict[str, Any]:
        """
        增量处理新文章
        
        将新文章与现有聚类合并，只处理新增的内容。
        
        Args:
            new_articles: 新文章列表
            existing_clusters: 现有聚类列表（可选）
        
        Returns:
            处理结果字典
        """
        # 简化实现：直接调用 run 方法
        # 实际使用时可以实现更复杂的增量逻辑
        return self.run(new_articles)
    
    def get_stats(self) -> dict[str, Any]:
        """
        获取系统统计信息
        
        Returns:
            统计信息字典
        """
        return {
            'rss_items_count': len(self.rss_generator.get_items()),
            'blacklist_domains': list(self.quality_filter.blacklist_domains),
            'trusted_sources': list(self.quality_filter.trusted_sources),
            'similarity_threshold': self.aggregation_engine.similarity_threshold,
            'aggregation_threshold': self.aggregation_engine.aggregation_threshold,
        }
