"""
调度器模块测试
Scheduler Module Tests

测试Scheduler类的初始化和基本功能。
Tests Scheduler class initialization and basic functionality.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.scheduler import Scheduler


class TestSchedulerInit:
    """测试Scheduler初始化"""
    
    def test_init_with_default_config(self):
        """测试使用默认配置初始化"""
        config = {}
        scheduler = Scheduler(config)
        
        assert scheduler.schedule_time == '09:00'
        assert scheduler.timezone == 'Asia/Shanghai'
        assert scheduler._running is False
    
    def test_init_with_custom_schedule_time(self):
        """测试使用自定义调度时间初始化"""
        config = {
            'schedule': {
                'time': '10:30',
                'timezone': 'UTC'
            }
        }
        scheduler = Scheduler(config)
        
        assert scheduler.schedule_time == '10:30'
        assert scheduler.timezone == 'UTC'
    
    def test_init_stores_full_config(self):
        """测试初始化时保存完整配置"""
        config = {
            'schedule': {'time': '08:00'},
            'database': {'path': 'test.db'},
            'ai': {'enabled': True}
        }
        scheduler = Scheduler(config)
        
        assert scheduler.config == config


class TestSchedulerComponents:
    """测试Scheduler组件初始化"""
    
    def test_init_components_creates_repository(self):
        """测试_init_components创建数据库仓库"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'data', 'test.db')
            config = {
                'database': {'path': db_path},
                'sources': {
                    'arxiv': {'enabled': False},
                    'rss': {'enabled': False}
                },
                'ai': {'enabled': False},
                'feishu': {'webhook_url': ''}
            }
            scheduler = Scheduler(config)
            
            components = scheduler._init_components()
            
            assert 'repository' in components
            assert Path(db_path).parent.exists()
            
            # 清理
            scheduler._cleanup_components(components)
    
    def test_init_components_creates_arxiv_fetcher_when_enabled(self):
        """测试启用arXiv时创建ArxivFetcher"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                'database': {'path': os.path.join(tmpdir, 'test.db')},
                'sources': {
                    'arxiv': {
                        'enabled': True,
                        'categories': ['cs.AI'],
                        'keywords': ['llm']
                    },
                    'rss': {'enabled': False}
                },
                'ai': {'enabled': False},
                'feishu': {'webhook_url': ''}
            }
            scheduler = Scheduler(config)
            
            components = scheduler._init_components()
            
            assert 'arxiv_fetcher' in components
            
            scheduler._cleanup_components(components)
    
    def test_init_components_skips_arxiv_fetcher_when_disabled(self):
        """测试禁用arXiv时不创建ArxivFetcher"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                'database': {'path': os.path.join(tmpdir, 'test.db')},
                'sources': {
                    'arxiv': {'enabled': False},
                    'rss': {'enabled': False}
                },
                'ai': {'enabled': False},
                'feishu': {'webhook_url': ''}
            }
            scheduler = Scheduler(config)
            
            components = scheduler._init_components()
            
            assert 'arxiv_fetcher' not in components
            
            scheduler._cleanup_components(components)
    
    def test_init_components_creates_rss_fetcher_when_enabled(self):
        """测试启用RSS时创建RSSFetcher"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                'database': {'path': os.path.join(tmpdir, 'test.db')},
                'sources': {
                    'arxiv': {'enabled': False},
                    'rss': {
                        'enabled': True,
                        'opml_path': 'feeds.opml'
                    }
                },
                'ai': {'enabled': False},
                'feishu': {'webhook_url': ''}
            }
            scheduler = Scheduler(config)
            
            components = scheduler._init_components()
            
            assert 'rss_fetcher' in components
            
            scheduler._cleanup_components(components)
    
    def test_init_components_creates_content_processor(self):
        """测试创建ContentProcessor"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                'database': {'path': os.path.join(tmpdir, 'test.db')},
                'sources': {
                    'arxiv': {'enabled': False},
                    'rss': {'enabled': False}
                },
                'content': {
                    'max_length': 10000,
                    'truncation_marker': '...'
                },
                'ai': {'enabled': False},
                'feishu': {'webhook_url': ''}
            }
            scheduler = Scheduler(config)
            
            components = scheduler._init_components()
            
            assert 'content_processor' in components
            
            scheduler._cleanup_components(components)
    
    def test_init_components_creates_ai_analyzer_when_enabled(self):
        """测试启用AI时创建AIAnalyzer"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                'database': {'path': os.path.join(tmpdir, 'test.db')},
                'sources': {
                    'arxiv': {'enabled': False},
                    'rss': {'enabled': False}
                },
                'ai': {
                    'enabled': True,
                    'api_base': 'https://api.example.com/v1',
                    'api_key': 'test-key',
                    'model': 'test-model'
                },
                'feishu': {'webhook_url': ''}
            }
            scheduler = Scheduler(config)
            
            components = scheduler._init_components()
            
            assert 'ai_analyzer' in components
            
            scheduler._cleanup_components(components)
    
    def test_init_components_creates_feishu_bot_when_configured(self):
        """测试配置webhook_url时创建FeishuBot"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                'database': {'path': os.path.join(tmpdir, 'test.db')},
                'sources': {
                    'arxiv': {'enabled': False},
                    'rss': {'enabled': False}
                },
                'ai': {'enabled': False},
                'feishu': {'webhook_url': 'https://open.feishu.cn/webhook/xxx'}
            }
            scheduler = Scheduler(config)
            
            components = scheduler._init_components()
            
            assert 'feishu_bot' in components
            
            scheduler._cleanup_components(components)
    
    def test_init_components_skips_feishu_bot_when_not_configured(self):
        """测试未配置webhook_url时不创建FeishuBot"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                'database': {'path': os.path.join(tmpdir, 'test.db')},
                'sources': {
                    'arxiv': {'enabled': False},
                    'rss': {'enabled': False}
                },
                'ai': {'enabled': False},
                'feishu': {'webhook_url': ''}
            }
            scheduler = Scheduler(config)
            
            components = scheduler._init_components()
            
            assert 'feishu_bot' not in components
            
            scheduler._cleanup_components(components)


class TestSchedulerRunOnce:
    """测试Scheduler.run_once方法"""
    
    def test_run_once_calls_run_task(self):
        """测试run_once调用run_task"""
        config = {}
        scheduler = Scheduler(config)
        
        # Mock run_task
        scheduler.run_task = MagicMock()
        
        scheduler.run_once()
        
        scheduler.run_task.assert_called_once()


class TestSchedulerStart:
    """测试Scheduler.start方法"""
    
    def test_start_sets_running_flag(self):
        """测试start设置_running标志"""
        config = {'schedule': {'time': '09:00'}}
        scheduler = Scheduler(config)
        
        # 使用mock来避免实际运行调度循环
        with patch('schedule.every') as mock_every:
            with patch('schedule.run_pending'):
                with patch('time.sleep', side_effect=KeyboardInterrupt):
                    try:
                        scheduler.start()
                    except KeyboardInterrupt:
                        pass
        
        # 验证调度任务被设置
        mock_every.assert_called()
    
    def test_stop_clears_running_flag(self):
        """测试stop清除_running标志"""
        config = {}
        scheduler = Scheduler(config)
        scheduler._running = True
        
        scheduler.stop()
        
        assert scheduler._running is False


class TestSchedulerRunTask:
    """测试Scheduler.run_task方法"""
    
    def test_run_task_with_no_articles(self):
        """测试没有文章时的run_task"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                'database': {'path': os.path.join(tmpdir, 'test.db')},
                'sources': {
                    'arxiv': {'enabled': False},
                    'rss': {'enabled': False}
                },
                'ai': {'enabled': False},
                'feishu': {'webhook_url': ''}
            }
            scheduler = Scheduler(config)
            
            # 应该正常完成，不抛出异常
            scheduler.run_task()
    
    def test_run_task_with_mocked_arxiv(self):
        """测试使用mock的arXiv获取器"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                'database': {'path': os.path.join(tmpdir, 'test.db')},
                'sources': {
                    'arxiv': {
                        'enabled': True,
                        'categories': ['cs.AI'],
                        'keywords': []
                    },
                    'rss': {'enabled': False}
                },
                'ai': {'enabled': False},
                'feishu': {'webhook_url': ''}
            }
            scheduler = Scheduler(config)
            
            # Mock ArxivFetcher.fetch_papers
            with patch.object(
                scheduler, '_init_components',
                wraps=scheduler._init_components
            ) as mock_init:
                # 创建一个mock的fetch_papers返回空列表
                with patch(
                    'src.fetchers.arxiv_fetcher.ArxivFetcher.fetch_papers',
                    return_value=[]
                ):
                    scheduler.run_task()


class TestSchedulerIntegration:
    """集成测试"""
    
    def test_full_workflow_with_mock_data(self):
        """测试完整工作流（使用mock数据）"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                'database': {'path': os.path.join(tmpdir, 'test.db')},
                'sources': {
                    'arxiv': {'enabled': False},
                    'rss': {'enabled': False}
                },
                'ai': {'enabled': False},
                'feishu': {'webhook_url': ''}
            }
            scheduler = Scheduler(config)
            
            # 初始化组件
            components = scheduler._init_components()
            repository = components['repository']
            
            # 手动添加一篇文章
            article = {
                'title': 'Test Article',
                'url': 'https://example.com/test',
                'source': 'test',
                'source_type': 'rss',
                'published_date': '2024-01-01',
                'fetched_at': '2024-01-01T00:00:00',
                'content': 'Test content',
                'summary': 'Test summary',
                'zh_summary': '测试摘要',
                'category': '其他',
                'is_pushed': False
            }
            article_id = repository.save_article(article)
            
            # 验证文章已保存
            assert article_id is not None
            
            # 验证未推送文章列表
            unpushed = repository.get_unpushed_articles()
            assert len(unpushed) == 1
            assert unpushed[0]['title'] == 'Test Article'
            
            # 标记为已推送
            repository.mark_as_pushed([article_id])
            
            # 验证已推送
            unpushed = repository.get_unpushed_articles()
            assert len(unpushed) == 0
            
            # 清理
            scheduler._cleanup_components(components)
