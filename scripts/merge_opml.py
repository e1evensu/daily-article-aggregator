zai#!/usr/bin/env python3
"""
OPML 文件合并去重脚本
Merge and deduplicate multiple OPML files

用法:
    python scripts/merge_opml.py --input rss/ --output merged_feeds.opml
"""

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime


def parse_opml(file_path: str) -> list[dict]:
    """解析 OPML 文件，提取所有订阅源"""
    feeds = []
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        for outline in root.iter('outline'):
            xml_url = outline.get('xmlUrl')
            if xml_url:
                feeds.append({
                    'title': outline.get('title') or outline.get('text') or '',
                    'xml_url': xml_url,
                    'html_url': outline.get('htmlUrl') or '',
                    'type': outline.get('type') or 'rss',
                    'source_file': file_path
                })
    except Exception as e:
        print(f"解析 {file_path} 失败: {e}")
    
    return feeds


def merge_and_dedupe(input_dir: str, output_file: str) -> tuple[int, int, int]:
    """
    合并目录下所有 OPML 文件并去重
    
    Returns:
        (总数, 去重后数量, 重复数量)
    """
    input_path = Path(input_dir)
    all_feeds = []
    
    # 收集所有 OPML 文件中的订阅源
    opml_files = list(input_path.glob('*.opml'))
    print(f"找到 {len(opml_files)} 个 OPML 文件")
    
    for opml_file in opml_files:
        feeds = parse_opml(str(opml_file))
        print(f"  {opml_file.name}: {len(feeds)} 个订阅源")
        all_feeds.extend(feeds)
    
    total = len(all_feeds)
    
    # 基于 URL 去重（保留第一个出现的）
    seen_urls = set()
    unique_feeds = []
    
    for feed in all_feeds:
        url = feed['xml_url'].lower().strip()
        if url not in seen_urls:
            seen_urls.add(url)
            unique_feeds.append(feed)
    
    unique_count = len(unique_feeds)
    duplicate_count = total - unique_count
    
    # 生成合并后的 OPML
    opml = ET.Element('opml', version='2.0')
    
    head = ET.SubElement(opml, 'head')
    ET.SubElement(head, 'title').text = 'Merged RSS Feeds'
    ET.SubElement(head, 'dateCreated').text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
    
    body = ET.SubElement(opml, 'body')
    
    for feed in unique_feeds:
        ET.SubElement(body, 'outline',
            type=feed['type'],
            text=feed['title'],
            title=feed['title'],
            xmlUrl=feed['xml_url'],
            htmlUrl=feed['html_url']
        )
    
    # 写入文件
    tree = ET.ElementTree(opml)
    ET.indent(tree, space='  ')
    tree.write(output_file, encoding='utf-8', xml_declaration=True)
    
    return total, unique_count, duplicate_count


def main():
    parser = argparse.ArgumentParser(description='合并并去重多个 OPML 文件')
    parser.add_argument('--input', '-i', default='rss/', help='OPML 文件目录 (默认: rss/)')
    parser.add_argument('--output', '-o', default='merged_feeds.opml', help='输出文件 (默认: merged_feeds.opml)')
    
    args = parser.parse_args()
    
    print(f"\n{'='*50}")
    print("OPML 合并去重工具")
    print(f"{'='*50}")
    print(f"输入目录: {args.input}")
    print(f"输出文件: {args.output}")
    print(f"{'='*50}\n")
    
    total, unique, duplicates = merge_and_dedupe(args.input, args.output)
    
    print(f"\n{'='*50}")
    print("完成!")
    print(f"{'='*50}")
    print(f"总订阅源: {total}")
    print(f"去重后: {unique}")
    print(f"移除重复: {duplicates}")
    print(f"输出文件: {args.output}")
    print(f"{'='*50}\n")


if __name__ == '__main__':
    main()
