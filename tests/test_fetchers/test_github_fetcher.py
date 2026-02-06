"""
GitHub Fetcher 测试
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from src.fetchers.github_fetcher import GitHubFetcher


@pytest.fixture
def fetcher():
    """创建 GitHub fetcher"""
    config = {
        'topics': ['security', 'ai'],
        'min_stars': 100,
        'days_back': 7,
        'max_results': 10,
        'timeout': 10,
    }
    return GitHubFetcher(config)


class TestGitHubFetcher:
    """GitHub Fetcher 测试"""
    
    def test_init(self, fetcher):
        """测试初始化"""
        assert fetcher.topics == ['security', 'ai']
        assert fetcher.min_stars == 100
        assert fetcher.days_back == 7
        assert fetcher.source_type == 'github'
        assert fetcher.source_name == 'GitHub'
    
    def test_headers_without_token(self, fetcher):
        """测试无 token 的请求头"""
        headers = fetcher._headers
        assert 'Authorization' not in headers
        assert 'Accept' in headers
    
    def test_headers_with_token(self):
        """测试有 token 的请求头"""
        fetcher = GitHubFetcher({'token': 'test_token'})
        headers = fetcher._headers
        assert headers['Authorization'] == 'token test_token'
    
    @patch('src.fetchers.github_fetcher.requests.get')
    def test_search_by_topic(self, mock_get, fetcher):
        """测试按话题搜索"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'items': [
                {
                    'full_name': 'owner/repo1',
                    'html_url': 'https://github.com/owner/repo1',
                    'description': 'A security tool',
                    'stargazers_count': 500,
                    'forks_count': 100,
                    'language': 'Python',
                    'topics': ['security', 'tool'],
                    'created_at': '2024-01-01T00:00:00Z',
                    'pushed_at': datetime.now().isoformat() + 'Z',
                }
            ]
        }
        mock_get.return_value = mock_response
        
        projects = fetcher._search_by_topic('security')
        
        assert len(projects) == 1
        assert projects[0]['repo_full_name'] == 'owner/repo1'
        assert projects[0]['stars'] == 500
        assert projects[0]['source_type'] == 'github'
    
    @patch('src.fetchers.github_fetcher.requests.get')
    def test_fetch_deduplication(self, mock_get, fetcher):
        """测试去重"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'items': [
                {
                    'full_name': 'owner/same-repo',
                    'html_url': 'https://github.com/owner/same-repo',
                    'description': 'Same repo',
                    'stargazers_count': 200,
                    'forks_count': 50,
                    'language': 'Go',
                    'topics': ['security', 'ai'],
                    'created_at': '2024-01-01T00:00:00Z',
                    'pushed_at': datetime.now().isoformat() + 'Z',
                }
            ]
        }
        mock_get.return_value = mock_response
        
        projects = fetcher.fetch()
        
        # 同一个 repo 应该只出现一次（即使在多个话题中都搜到）
        repo_names = [p['repo_full_name'] for p in projects]
        assert len(repo_names) == len(set(repo_names))
    
    def test_should_push_first_time(self, fetcher):
        """测试首次发现项目应该推送"""
        project = {
            'repo_full_name': 'new/project',
            'stars': 100,
            'latest_release': {'tag_name': 'v1.0.0'},
        }
        
        assert fetcher._should_push(project) is True
        assert 'new/project' in fetcher._pushed_versions
    
    def test_should_push_no_update(self, fetcher):
        """测试无更新不应该推送"""
        project = {
            'repo_full_name': 'existing/project',
            'stars': 100,
            'latest_release': {'tag_name': 'v1.0.0'},
        }
        
        # 首次推送
        fetcher._should_push(project)
        
        # 再次检查，无更新
        assert fetcher._should_push(project) is False
    
    def test_should_push_new_release(self, fetcher):
        """测试新版本应该推送"""
        project = {
            'repo_full_name': 'release/project',
            'stars': 100,
            'latest_release': {'tag_name': 'v1.0.0'},
        }
        
        # 首次推送
        fetcher._should_push(project)
        
        # 新版本
        project['latest_release'] = {'tag_name': 'v2.0.0'}
        assert fetcher._should_push(project) is True
        assert 'update_reason' in project
        assert 'v2.0.0' in project['update_reason']
    
    def test_should_push_star_growth(self, fetcher):
        """测试星数大幅增长应该推送"""
        project = {
            'repo_full_name': 'growing/project',
            'stars': 100,
            'latest_release': {'tag_name': 'v1.0.0'},
        }
        
        # 首次推送
        fetcher._should_push(project)
        
        # 星数增长超过 20%
        project['stars'] = 150
        assert fetcher._should_push(project) is True
        assert 'update_reason' in project
        assert '增长' in project['update_reason']
    
    def test_should_push_small_star_growth(self, fetcher):
        """测试星数小幅增长不应该推送"""
        project = {
            'repo_full_name': 'stable/project',
            'stars': 100,
            'latest_release': {'tag_name': 'v1.0.0'},
        }
        
        # 首次推送
        fetcher._should_push(project)
        
        # 星数小幅增长（< 20%）
        project['stars'] = 110
        assert fetcher._should_push(project) is False
    
    def test_load_and_get_pushed_versions(self, fetcher):
        """测试加载和获取已推送版本"""
        data = {
            'owner/repo1': {'stars': 100, 'release': 'v1.0'},
            'owner/repo2': {'stars': 200, 'release': 'v2.0'},
        }
        
        fetcher.load_pushed_versions(data)
        
        assert fetcher.get_pushed_versions() == data
    
    def test_parse_repo(self, fetcher):
        """测试解析仓库信息"""
        item = {
            'full_name': 'test/repo',
            'html_url': 'https://github.com/test/repo',
            'description': 'A test repository',
            'stargazers_count': 1000,
            'forks_count': 200,
            'language': 'Python',
            'topics': ['ai', 'ml'],
            'created_at': '2024-01-01T00:00:00Z',
            'pushed_at': '2024-02-01T00:00:00Z',
        }
        
        project = fetcher._parse_repo(item, 'ai')
        
        assert project['title'] == '[GitHub] test/repo'
        assert project['url'] == 'https://github.com/test/repo'
        assert project['stars'] == 1000
        assert project['forks'] == 200
        assert project['language'] == 'Python'
        assert project['source_type'] == 'github'
        assert project['search_topic'] == 'ai'
    
    def test_build_content(self, fetcher):
        """测试构建内容"""
        item = {
            'full_name': 'test/repo',
            'description': 'A great tool',
            'stargazers_count': 5000,
            'forks_count': 1000,
            'language': 'Rust',
            'topics': ['security', 'tool', 'cli'],
        }
        release = {
            'tag_name': 'v3.0.0',
            'published_at': '2024-02-01T00:00:00Z',
        }
        
        content = fetcher._build_content(item, release)
        
        assert 'test/repo' in content
        assert '5,000' in content  # Stars formatted
        assert 'Rust' in content
        assert 'v3.0.0' in content
        assert 'security' in content
