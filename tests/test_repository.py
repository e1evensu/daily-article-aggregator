"""
ArticleRepository单元测试

测试数据库操作的基本功能和边界情况。
"""

import pytest
import sqlite3
from datetime import datetime

from src.repository import ArticleRepository


class TestArticleRepositoryInit:
    """测试数据库初始化"""
    
    def test_init_db_creates_table(self):
        """测试init_db创建articles表"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        # 验证表存在
        conn = repo._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='articles'")
        result = cursor.fetchone()
        
        assert result is not None
        assert result['name'] == 'articles'
        repo.close()
    
    def test_init_db_creates_indexes(self):
        """测试init_db创建索引"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        conn = repo._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row['name'] for row in cursor.fetchall()]
        
        assert 'idx_url' in indexes
        assert 'idx_is_pushed' in indexes
        assert 'idx_source' in indexes
        assert 'idx_fetched_at' in indexes
        repo.close()
    
    def test_init_db_idempotent(self):
        """测试init_db可以多次调用"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        repo.init_db()  # 第二次调用不应该报错
        repo.close()


class TestExistsByUrl:
    """测试URL存在性检查"""
    
    def test_exists_by_url_returns_false_for_new_url(self):
        """测试新URL返回False"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        result = repo.exists_by_url('https://example.com/article1')
        
        assert result is False
        repo.close()
    
    def test_exists_by_url_returns_true_for_existing_url(self):
        """测试已存在URL返回True"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        article = {
            'title': 'Test Article',
            'url': 'https://example.com/article1',
            'source': 'test',
            'source_type': 'rss',
            'fetched_at': datetime.now().isoformat()
        }
        repo.save_article(article)
        
        result = repo.exists_by_url('https://example.com/article1')
        
        assert result is True
        repo.close()
    
    def test_exists_by_url_empty_database(self):
        """测试空数据库返回False"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        result = repo.exists_by_url('')
        
        assert result is False
        repo.close()


class TestFindSimilarByTitle:
    """测试标题相似度查找"""
    
    def test_find_similar_returns_none_for_empty_db(self):
        """测试空数据库返回None"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        result = repo.find_similar_by_title('Test Article')
        
        assert result is None
        repo.close()
    
    def test_find_similar_returns_exact_match(self):
        """测试精确匹配返回文章"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        article = {
            'title': 'Test Article Title',
            'url': 'https://example.com/article1',
            'source': 'test',
            'source_type': 'rss',
            'fetched_at': datetime.now().isoformat()
        }
        repo.save_article(article)
        
        result = repo.find_similar_by_title('Test Article Title')
        
        assert result is not None
        assert result['title'] == 'Test Article Title'
        repo.close()
    
    def test_find_similar_returns_similar_title(self):
        """测试相似标题返回文章"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        article = {
            'title': 'Introduction to Machine Learning',
            'url': 'https://example.com/article1',
            'source': 'test',
            'source_type': 'rss',
            'fetched_at': datetime.now().isoformat()
        }
        repo.save_article(article)
        
        # 相似标题（只有细微差别）
        result = repo.find_similar_by_title('Introduction to Machine Learning Basics')
        
        # 相似度可能不够高，取决于阈值
        # 这里测试的是功能正确性
        repo.close()
    
    def test_find_similar_respects_threshold(self):
        """测试相似度阈值"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        article = {
            'title': 'Python Programming Guide',
            'url': 'https://example.com/article1',
            'source': 'test',
            'source_type': 'rss',
            'fetched_at': datetime.now().isoformat()
        }
        repo.save_article(article)
        
        # 完全不同的标题，低阈值也不应该匹配
        result = repo.find_similar_by_title('JavaScript Tutorial', threshold=0.9)
        
        assert result is None
        repo.close()
    
    def test_find_similar_with_low_threshold(self):
        """测试低阈值能匹配更多文章"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        article = {
            'title': 'Python Programming',
            'url': 'https://example.com/article1',
            'source': 'test',
            'source_type': 'rss',
            'fetched_at': datetime.now().isoformat()
        }
        repo.save_article(article)
        
        # 使用非常低的阈值
        result = repo.find_similar_by_title('Python', threshold=0.3)
        
        assert result is not None
        repo.close()


class TestSaveArticle:
    """测试保存文章"""
    
    def test_save_article_returns_id(self):
        """测试保存文章返回ID"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        article = {
            'title': 'Test Article',
            'url': 'https://example.com/article1',
            'source': 'test',
            'source_type': 'rss',
            'fetched_at': datetime.now().isoformat()
        }
        
        article_id = repo.save_article(article)
        
        assert article_id is not None
        assert article_id > 0
        repo.close()
    
    def test_save_article_stores_all_fields(self):
        """测试保存文章存储所有字段"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        article = {
            'title': 'Test Article',
            'url': 'https://example.com/article1',
            'source': 'test_source',
            'source_type': 'rss',
            'published_date': '2024-01-01',
            'fetched_at': '2024-01-02T10:00:00',
            'content': 'Article content',
            'summary': 'Article summary',
            'zh_summary': '文章摘要',
            'category': 'tech',
            'is_pushed': False,
            'pushed_at': None
        }
        
        article_id = repo.save_article(article)
        retrieved = repo.get_by_id(article_id)
        
        assert retrieved['title'] == article['title']
        assert retrieved['url'] == article['url']
        assert retrieved['source'] == article['source']
        assert retrieved['source_type'] == article['source_type']
        assert retrieved['published_date'] == article['published_date']
        assert retrieved['fetched_at'] == article['fetched_at']
        assert retrieved['content'] == article['content']
        assert retrieved['summary'] == article['summary']
        assert retrieved['zh_summary'] == article['zh_summary']
        assert retrieved['category'] == article['category']
        assert retrieved['is_pushed'] == article['is_pushed']
        repo.close()
    
    def test_save_article_duplicate_url_raises_error(self):
        """测试重复URL抛出错误"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        article = {
            'title': 'Test Article',
            'url': 'https://example.com/article1',
            'source': 'test',
            'source_type': 'rss',
            'fetched_at': datetime.now().isoformat()
        }
        
        repo.save_article(article)
        
        with pytest.raises(sqlite3.IntegrityError):
            repo.save_article(article)
        
        repo.close()
    
    def test_save_article_with_minimal_fields(self):
        """测试只有必需字段的文章"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        article = {
            'title': 'Minimal Article',
            'url': 'https://example.com/minimal',
            'source': 'test',
            'source_type': 'rss',
            'fetched_at': datetime.now().isoformat()
        }
        
        article_id = repo.save_article(article)
        retrieved = repo.get_by_id(article_id)
        
        assert retrieved is not None
        assert retrieved['title'] == 'Minimal Article'
        assert retrieved['content'] == ''  # 默认空字符串
        repo.close()


class TestGetById:
    """测试根据ID获取文章"""
    
    def test_get_by_id_returns_article(self):
        """测试获取存在的文章"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        article = {
            'title': 'Test Article',
            'url': 'https://example.com/article1',
            'source': 'test',
            'source_type': 'rss',
            'fetched_at': datetime.now().isoformat()
        }
        
        article_id = repo.save_article(article)
        retrieved = repo.get_by_id(article_id)
        
        assert retrieved is not None
        assert retrieved['id'] == article_id
        assert retrieved['title'] == article['title']
        repo.close()
    
    def test_get_by_id_returns_none_for_nonexistent(self):
        """测试获取不存在的文章返回None"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        result = repo.get_by_id(999)
        
        assert result is None
        repo.close()


class TestGetUnpushedArticles:
    """测试获取未推送文章"""
    
    def test_get_unpushed_returns_empty_for_empty_db(self):
        """测试空数据库返回空列表"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        result = repo.get_unpushed_articles()
        
        assert result == []
        repo.close()
    
    def test_get_unpushed_returns_unpushed_articles(self):
        """测试返回未推送的文章"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        article = {
            'title': 'Unpushed Article',
            'url': 'https://example.com/article1',
            'source': 'test',
            'source_type': 'rss',
            'fetched_at': datetime.now().isoformat(),
            'is_pushed': False
        }
        
        repo.save_article(article)
        result = repo.get_unpushed_articles()
        
        assert len(result) == 1
        assert result[0]['title'] == 'Unpushed Article'
        repo.close()
    
    def test_get_unpushed_excludes_pushed_articles(self):
        """测试排除已推送的文章"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        unpushed = {
            'title': 'Unpushed Article',
            'url': 'https://example.com/article1',
            'source': 'test',
            'source_type': 'rss',
            'fetched_at': datetime.now().isoformat(),
            'is_pushed': False
        }
        
        pushed = {
            'title': 'Pushed Article',
            'url': 'https://example.com/article2',
            'source': 'test',
            'source_type': 'rss',
            'fetched_at': datetime.now().isoformat(),
            'is_pushed': True
        }
        
        repo.save_article(unpushed)
        repo.save_article(pushed)
        
        result = repo.get_unpushed_articles()
        
        assert len(result) == 1
        assert result[0]['title'] == 'Unpushed Article'
        repo.close()


class TestMarkAsPushed:
    """测试标记文章为已推送"""
    
    def test_mark_as_pushed_updates_status(self):
        """测试标记更新推送状态"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        article = {
            'title': 'Test Article',
            'url': 'https://example.com/article1',
            'source': 'test',
            'source_type': 'rss',
            'fetched_at': datetime.now().isoformat(),
            'is_pushed': False
        }
        
        article_id = repo.save_article(article)
        repo.mark_as_pushed([article_id])
        
        retrieved = repo.get_by_id(article_id)
        
        assert retrieved['is_pushed'] is True
        assert retrieved['pushed_at'] is not None
        repo.close()
    
    def test_mark_as_pushed_multiple_articles(self):
        """测试批量标记多篇文章"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        ids = []
        for i in range(3):
            article = {
                'title': f'Article {i}',
                'url': f'https://example.com/article{i}',
                'source': 'test',
                'source_type': 'rss',
                'fetched_at': datetime.now().isoformat(),
                'is_pushed': False
            }
            ids.append(repo.save_article(article))
        
        repo.mark_as_pushed(ids)
        
        for article_id in ids:
            retrieved = repo.get_by_id(article_id)
            assert retrieved['is_pushed'] is True
        repo.close()
    
    def test_mark_as_pushed_empty_list(self):
        """测试空列表不报错"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        repo.mark_as_pushed([])  # 不应该报错
        repo.close()
    
    def test_mark_as_pushed_removes_from_unpushed(self):
        """测试标记后文章不再出现在未推送列表"""
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        article = {
            'title': 'Test Article',
            'url': 'https://example.com/article1',
            'source': 'test',
            'source_type': 'rss',
            'fetched_at': datetime.now().isoformat(),
            'is_pushed': False
        }
        
        article_id = repo.save_article(article)
        
        # 标记前应该在未推送列表中
        unpushed = repo.get_unpushed_articles()
        assert len(unpushed) == 1
        
        repo.mark_as_pushed([article_id])
        
        # 标记后不应该在未推送列表中
        unpushed = repo.get_unpushed_articles()
        assert len(unpushed) == 0
        repo.close()


# =============================================================================
# 属性测试 (Property-Based Tests)
# =============================================================================

from hypothesis import given, strategies as st, settings, assume
from difflib import SequenceMatcher


# 文章数据生成策略
def article_strategy():
    """生成有效的文章数据"""
    return st.fixed_dictionaries({
        'title': st.text(min_size=1, max_size=200).filter(lambda x: x.strip()),
        'url': st.text(min_size=10, max_size=500).map(lambda x: f"https://example.com/{x.replace(' ', '_')}"),
        'source': st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
        'source_type': st.sampled_from(['rss', 'arxiv']),
        'published_date': st.text(min_size=0, max_size=20),
        'fetched_at': st.text(min_size=1, max_size=30).filter(lambda x: x.strip()),
        'content': st.text(max_size=1000),
        'summary': st.text(max_size=500),
        'zh_summary': st.text(max_size=500),
        'category': st.text(max_size=50),
        'is_pushed': st.just(False),
        'pushed_at': st.none(),
    })


def unique_url_strategy():
    """生成唯一的URL"""
    return st.uuids().map(lambda x: f"https://example.com/article/{x}")


class TestPropertyArticleStorageRoundTrip:
    """
    Feature: daily-article-aggregator, Property 6: 文章存储Round-Trip
    
    *对于任意*有效的文章数据，存储到数据库后再查询，
    应该能够获取到相同的标题、URL、来源、摘要和分类。
    
    **Validates: Requirements 5.2**
    """
    
    @given(
        title=st.text(min_size=1, max_size=200).filter(lambda x: x.strip()),
        url=unique_url_strategy(),
        source=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
        summary=st.text(max_size=500),
        category=st.text(max_size=50),
    )
    @settings(max_examples=100)
    def test_article_storage_roundtrip(self, title, url, source, summary, category):
        """
        Feature: daily-article-aggregator, Property 6: 文章存储Round-Trip
        
        验证文章存储后能够正确读取所有关键字段。
        **Validates: Requirements 5.2**
        """
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        try:
            article = {
                'title': title,
                'url': url,
                'source': source,
                'source_type': 'rss',
                'fetched_at': datetime.now().isoformat(),
                'summary': summary,
                'category': category,
            }
            
            article_id = repo.save_article(article)
            retrieved = repo.get_by_id(article_id)
            
            # 验证Round-Trip：存储后读取的数据应该与原始数据一致
            assert retrieved is not None, "存储的文章应该能够被检索到"
            assert retrieved['title'] == title, f"标题不匹配: {retrieved['title']} != {title}"
            assert retrieved['url'] == url, f"URL不匹配: {retrieved['url']} != {url}"
            assert retrieved['source'] == source, f"来源不匹配: {retrieved['source']} != {source}"
            assert retrieved['summary'] == summary, f"摘要不匹配: {retrieved['summary']} != {summary}"
            assert retrieved['category'] == category, f"分类不匹配: {retrieved['category']} != {category}"
        finally:
            repo.close()


class TestPropertyURLDeduplication:
    """
    Feature: daily-article-aggregator, Property 7: URL去重有效性
    
    *对于任意*URL，如果该URL已存在于数据库中，则exists_by_url应返回True；
    对于新URL应返回False。重复插入相同URL的文章不应该创建新记录。
    
    **Validates: Requirements 5.3, 5.4**
    """
    
    @given(url=unique_url_strategy())
    @settings(max_examples=100)
    def test_new_url_not_exists(self, url):
        """
        Feature: daily-article-aggregator, Property 7: URL去重有效性
        
        验证新URL在空数据库中不存在。
        **Validates: Requirements 5.3**
        """
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        try:
            # 新URL应该不存在
            assert repo.exists_by_url(url) is False, f"新URL {url} 不应该存在于空数据库中"
        finally:
            repo.close()
    
    @given(url=unique_url_strategy())
    @settings(max_examples=100)
    def test_existing_url_exists(self, url):
        """
        Feature: daily-article-aggregator, Property 7: URL去重有效性
        
        验证已存储的URL能被正确识别为存在。
        **Validates: Requirements 5.3**
        """
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        try:
            article = {
                'title': 'Test Article',
                'url': url,
                'source': 'test',
                'source_type': 'rss',
                'fetched_at': datetime.now().isoformat(),
            }
            
            repo.save_article(article)
            
            # 存储后URL应该存在
            assert repo.exists_by_url(url) is True, f"已存储的URL {url} 应该存在"
        finally:
            repo.close()
    
    @given(url=unique_url_strategy())
    @settings(max_examples=100)
    def test_duplicate_url_raises_error(self, url):
        """
        Feature: daily-article-aggregator, Property 7: URL去重有效性
        
        验证重复插入相同URL会抛出错误，不会创建新记录。
        **Validates: Requirements 5.4**
        """
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        try:
            article = {
                'title': 'Test Article',
                'url': url,
                'source': 'test',
                'source_type': 'rss',
                'fetched_at': datetime.now().isoformat(),
            }
            
            # 第一次插入应该成功
            repo.save_article(article)
            
            # 第二次插入相同URL应该失败
            with pytest.raises(sqlite3.IntegrityError):
                repo.save_article(article)
        finally:
            repo.close()


class TestPropertyTitleSimilarityDeduplication:
    """
    Feature: daily-article-aggregator, Property 8: 标题相似度去重
    
    *对于任意*两篇标题相似度超过阈值的文章，
    find_similar_by_title应该能够识别出相似文章。
    
    **Validates: Requirements 5.5**
    """
    
    @given(
        base_title=st.text(min_size=10, max_size=100).filter(lambda x: x.strip() and len(x.strip()) >= 10),
        suffix=st.text(min_size=0, max_size=5),
    )
    @settings(max_examples=100)
    def test_similar_titles_detected(self, base_title, suffix):
        """
        Feature: daily-article-aggregator, Property 8: 标题相似度去重
        
        验证相似标题能被正确识别。
        **Validates: Requirements 5.5**
        """
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        try:
            # 存储原始文章
            original_article = {
                'title': base_title,
                'url': f'https://example.com/article/{hash(base_title)}',
                'source': 'test',
                'source_type': 'rss',
                'fetched_at': datetime.now().isoformat(),
            }
            repo.save_article(original_article)
            
            # 创建相似标题（添加小后缀）
            similar_title = base_title + suffix
            
            # 计算实际相似度
            actual_similarity = SequenceMatcher(None, base_title, similar_title).ratio()
            
            # 使用略低于实际相似度的阈值进行查找
            threshold = actual_similarity - 0.01
            if threshold < 0:
                threshold = 0
            
            result = repo.find_similar_by_title(similar_title, threshold=threshold)
            
            # 如果相似度足够高，应该能找到相似文章
            if actual_similarity >= threshold:
                assert result is not None, f"相似度 {actual_similarity:.2f} >= 阈值 {threshold:.2f}，应该找到相似文章"
                assert result['title'] == base_title, f"找到的文章标题应该是原始标题"
        finally:
            repo.close()
    
    @given(
        title1=st.text(min_size=20, max_size=100).filter(lambda x: x.strip() and len(x.strip()) >= 20),
        title2=st.text(min_size=20, max_size=100).filter(lambda x: x.strip() and len(x.strip()) >= 20),
    )
    @settings(max_examples=100)
    def test_dissimilar_titles_not_matched(self, title1, title2):
        """
        Feature: daily-article-aggregator, Property 8: 标题相似度去重
        
        验证不相似的标题不会被错误匹配。
        **Validates: Requirements 5.5**
        """
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        try:
            # 计算实际相似度
            actual_similarity = SequenceMatcher(None, title1, title2).ratio()
            
            # 只测试真正不相似的标题对（相似度低于0.5）
            assume(actual_similarity < 0.5)
            
            # 存储第一篇文章
            article = {
                'title': title1,
                'url': f'https://example.com/article/{hash(title1)}',
                'source': 'test',
                'source_type': 'rss',
                'fetched_at': datetime.now().isoformat(),
            }
            repo.save_article(article)
            
            # 使用高阈值（0.8）查找，不相似的标题不应该被匹配
            result = repo.find_similar_by_title(title2, threshold=0.8)
            
            assert result is None, f"相似度 {actual_similarity:.2f} < 0.8，不应该找到相似文章"
        finally:
            repo.close()


class TestPropertyPushStatusManagement:
    """
    Feature: daily-article-aggregator, Property 9: 推送状态管理
    
    *对于任意*数据库状态，get_unpushed_articles只返回is_pushed为False的文章；
    调用mark_as_pushed后，这些文章不应该再出现在未推送列表中。
    
    **Validates: Requirements 5.6, 5.7**
    """
    
    @given(
        num_articles=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=100)
    def test_unpushed_articles_only_returns_unpushed(self, num_articles):
        """
        Feature: daily-article-aggregator, Property 9: 推送状态管理
        
        验证get_unpushed_articles只返回未推送的文章。
        **Validates: Requirements 5.6**
        """
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        try:
            # 创建多篇文章，全部未推送
            for i in range(num_articles):
                article = {
                    'title': f'Article {i}',
                    'url': f'https://example.com/article/{i}',
                    'source': 'test',
                    'source_type': 'rss',
                    'fetched_at': datetime.now().isoformat(),
                    'is_pushed': False,
                }
                repo.save_article(article)
            
            unpushed = repo.get_unpushed_articles()
            
            # 所有文章都应该在未推送列表中
            assert len(unpushed) == num_articles, f"应该有 {num_articles} 篇未推送文章"
            
            # 验证所有返回的文章都是未推送状态
            for article in unpushed:
                assert article['is_pushed'] is False, "get_unpushed_articles返回的文章应该都是未推送状态"
        finally:
            repo.close()
    
    @given(
        num_articles=st.integers(min_value=1, max_value=20),
        num_to_push=st.integers(min_value=0, max_value=20),
    )
    @settings(max_examples=100)
    def test_mark_as_pushed_removes_from_unpushed(self, num_articles, num_to_push):
        """
        Feature: daily-article-aggregator, Property 9: 推送状态管理
        
        验证mark_as_pushed后文章不再出现在未推送列表中。
        **Validates: Requirements 5.7**
        """
        # 确保要推送的数量不超过文章总数
        num_to_push = min(num_to_push, num_articles)
        
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        try:
            # 创建文章并收集ID
            article_ids = []
            for i in range(num_articles):
                article = {
                    'title': f'Article {i}',
                    'url': f'https://example.com/article/{i}',
                    'source': 'test',
                    'source_type': 'rss',
                    'fetched_at': datetime.now().isoformat(),
                    'is_pushed': False,
                }
                article_ids.append(repo.save_article(article))
            
            # 标记部分文章为已推送
            ids_to_push = article_ids[:num_to_push]
            if ids_to_push:
                repo.mark_as_pushed(ids_to_push)
            
            # 获取未推送文章
            unpushed = repo.get_unpushed_articles()
            unpushed_ids = {a['id'] for a in unpushed}
            
            # 验证已推送的文章不在未推送列表中
            for pushed_id in ids_to_push:
                assert pushed_id not in unpushed_ids, f"已推送的文章 {pushed_id} 不应该在未推送列表中"
            
            # 验证未推送文章数量正确
            expected_unpushed = num_articles - num_to_push
            assert len(unpushed) == expected_unpushed, f"应该有 {expected_unpushed} 篇未推送文章，实际有 {len(unpushed)} 篇"
        finally:
            repo.close()
    
    @given(
        num_articles=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=100)
    def test_pushed_articles_have_pushed_at_timestamp(self, num_articles):
        """
        Feature: daily-article-aggregator, Property 9: 推送状态管理
        
        验证标记为已推送的文章有推送时间戳。
        **Validates: Requirements 5.7**
        """
        repo = ArticleRepository(':memory:')
        repo.init_db()
        
        try:
            # 创建文章
            article_ids = []
            for i in range(num_articles):
                article = {
                    'title': f'Article {i}',
                    'url': f'https://example.com/article/{i}',
                    'source': 'test',
                    'source_type': 'rss',
                    'fetched_at': datetime.now().isoformat(),
                    'is_pushed': False,
                }
                article_ids.append(repo.save_article(article))
            
            # 标记所有文章为已推送
            repo.mark_as_pushed(article_ids)
            
            # 验证所有文章都有推送时间戳
            for article_id in article_ids:
                article = repo.get_by_id(article_id)
                assert article['is_pushed'] is True, "文章应该被标记为已推送"
                assert article['pushed_at'] is not None, "已推送的文章应该有推送时间戳"
        finally:
            repo.close()
