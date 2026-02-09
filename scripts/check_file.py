"""Check test file."""
with open('tests/test_fetchers/test_sitemap_importer.py', 'rb') as f:
    content = f.read()
    print(f'File size: {len(content)} bytes')
    print(f'First 200 bytes: {content[:200]}')
    print(f'Has BOM: {content.startswith(b"\\xef\\xbb\\xbf")}')
    
# Try to import and list classes
import sys
sys.path.insert(0, '.')
import importlib.util
spec = importlib.util.spec_from_file_location("test_module", "tests/test_fetchers/test_sitemap_importer.py")
module = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(module)
    print("Module loaded successfully")
    # List test classes
    for name in dir(module):
        if name.startswith('Test'):
            print(f"Found test class: {name}")
except Exception as e:
    print(f"Error loading module: {e}")
