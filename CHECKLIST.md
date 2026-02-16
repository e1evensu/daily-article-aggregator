# 开发规范 - Python 3.9 兼容性

## 禁止使用 Python 3.10+ 语法

### 类型注解
- ❌ 禁止: `str | None`
- ✅ 必须: `Optional[str]`

- ❌ 禁止: `dict[str, Any]`
- ✅ 必须: `Dict[str, Any]`

- ❌ 禁止: `list[int]`
- ✅ 必须: `List[int]`

### Import 要求
所有使用类型注解的文件必须导入:
```python
from typing import Any, Optional, Union, List, Dict
```

## 代码提交前检查清单

- [ ] 搜索项目中所有 `|: ` 模式，确保没有使用 `str | None` 等语法
- [ ] 检查所有 `typing import` 是否包含 `List, Dict`
- [ ] 用 Python 3.9 测试: `python -c "from src.xxx import xxx"`
