"""Script to fix the duplicated test file."""
import re

with open('tests/test_fetchers/test_sitemap_importer.py', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')
print(f'Total lines: {len(lines)}')

# Find the first occurrence of TestCrawlRuleEngineEdgeCases and its end
in_class = False
class_end_line = 0
for i, line in enumerate(lines):
    if 'class TestCrawlRuleEngineEdgeCases:' in line:
        if not in_class:
            in_class = True
            print(f'Found TestCrawlRuleEngineEdgeCases at line {i+1}')
    elif in_class and line.startswith('class ') or (in_class and line.startswith('# ===') and i > 0):
        class_end_line = i
        print(f'Class ends at line {class_end_line}')
        break

# Find the actual end of the test_overlapping_patterns method
for i in range(class_end_line, 0, -1):
    if 'is False' in lines[i] and 'internal/secret' in lines[i]:
        class_end_line = i + 1
        print(f'Adjusted end to line {class_end_line}')
        break

# Keep only the original content
clean_lines = lines[:class_end_line]
clean_content = '\n'.join(clean_lines)

print(f'Clean content has {len(clean_lines)} lines')
print('Last 5 lines:')
for line in clean_lines[-5:]:
    print(f'  {line}')

# Write back
with open('tests/test_fetchers/test_sitemap_importer.py', 'w', encoding='utf-8') as f:
    f.write(clean_content)

print('File cleaned!')
