#!/usr/bin/env python3
"""
并发优化脚本：加速 AI 漏洞分析
- 添加线程池并发处理
- 进度日志
"""

import re

# 1. 优化 vulnerability_filter.py
vuln_file = "/opt/daily-article-aggregator/src/filters/vulnerability_filter.py"
with open(vuln_file, "r") as f:
    vuln_content = f.read()

# 添加并发导入
old_imports = """import logging
import requests
import re
from typing import Any, Callable, TypeVar, List, Tuple"""

new_imports = """import logging
import requests
import re
from typing import Any, Callable, TypeVar, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import time"""

if old_imports in vuln_content:
    vuln_content = vuln_content.replace(old_imports, new_imports)

# 优化 filter_vulnerabilities 方法，添加并发
old_filter_vulns = '''    def filter_vulnerabilities(
        self, 
        vulnerabilities: list[dict[str, Any]]
    ) -> list[VulnerabilityFilterResult]:
        """
        批量过滤漏洞
        Filter vulnerabilities in batch
        
        Args:
            vulnerabilities: 漏洞列表
        
        Returns:
            过滤结果列表
        """
        results: list[VulnerabilityFilterResult] = []
        
        for vuln in vulnerabilities:
            result = self.filter_single(vuln)
            results.append(result)
        
        # 统计
        passed_count = sum(1 for r in results if r.passed)
        filtered_count = len(results) - passed_count
        logger.info(
            f"VulnerabilityFilter: {passed_count} passed, {filtered_count} filtered"
        )
        
        return results'''

new_filter_vulns = '''    def filter_vulnerabilities(
        self,
        vulnerabilities: list[dict[str, Any]]
    ) -> list[VulnerabilityFilterResult]:
        """
        批量过滤漏洞（并发优化版）
        Filter vulnerabilities in batch with concurrent optimization

        Args:
            vulnerabilities: 漏洞列表

        Returns:
            过滤结果列表
        """
        results: list[VulnerabilityFilterResult] = []
        total = len(vulnerabilities)

        # 使用线程池并发处理（加速 AI 分析）
        max_workers = min(10, total)  # 最多10个并发线程
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_vuln = {
                executor.submit(self.filter_single, vuln): vuln
                for vuln in vulnerabilities
            }

            # 收集结果并显示进度
            completed = 0
            for future in as_completed(future_to_vuln):
                try:
                    result = future.result()
                    results.append(result)
                    completed += 1

                    # 每10个或完成时打印进度
                    if completed % 10 == 0 or completed == total:
                        elapsed = time.time() - start_time
                        speed = completed / elapsed if elapsed > 0 else 0
                        logger.info(
                            f"漏洞过滤进度: {completed}/{total} ({completed/total*100:.1f}%) - "
                            f"速度: {speed:.1f}个/秒"
                        )
                except Exception as e:
                    vuln = future_to_vuln[future]
                    logger.error(f"Error filtering vulnerability {vuln.get('id', 'unknown')}: {e}")

        # 统计
        passed_count = sum(1 for r in results if r.passed)
        filtered_count = len(results) - passed_count
        elapsed = time.time() - start_time
        logger.info(
            f"VulnerabilityFilter: {passed_count} passed, {filtered_count} filtered - "
            f"耗时: {elapsed:.1f}秒"
        )

        return results'''

if old_filter_vulns in vuln_content:
    vuln_content = vuln_content.replace(old_filter_vulns, new_filter_vulns)
    print("✓ vulnerability_filter.py 并发优化")
else:
    print("⚠ vulnerability_filter.py 已经优化过或格式不同")

with open(vuln_file, "w") as f:
    f.write(vuln_content)

print("\n优化内容:")
print("1. 线程池并发：最多10个线程同时分析漏洞")
print("2. 进度日志：每10个漏洞显示进度和速度")
print("3. 性能统计：显示总耗时")
print("\n预期性能提升：")
print("- 从 15-20 分钟 → 2-3 分钟")
print("- 速度提升约 5-10倍")
