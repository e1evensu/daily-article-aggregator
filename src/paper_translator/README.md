# 论文翻译系统

将英文PDF论文翻译成中文，保留原格式，并添加术语解释、公式说明和图表描述。

## 功能特性

- **PDF解析** - 提取文本、公式、图表
- **文本翻译** - 使用DeepSeek API翻译，保持学术风格
- **术语解释** - 自动提取并解释专业术语
- **公式说明** - 解释LaTeX公式的含义
- **图表理解** - 使用多模态LLM理解图表内容
- **PDF生成** - 保留原格式，添加底部注释和术语表附录

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置API

复制 `.env.example` 为 `.env`，填入API密钥：

```bash
cp .env.example .env
```

需要配置：
- **DEEPSEEK_API_KEY** - 翻译和公式解释（必需）
  - 申请地址: https://platform.deepseek.com/
- **SILICONFLOW_API_KEY** - 图表理解（可选）
  - 申请地址: https://siliconflow.cn/

### 3. 使用方法

```bash
# 翻译单个PDF
python main.py input_papers/paper.pdf

# 指定输出路径
python main.py input_papers/paper.pdf -o output/translated.pdf

# 批量处理目录
python main.py -d input_papers/

# 列出输入目录中的PDF
python main.py --list
```

## 输出格式

生成的PDF包含：

1. **标题页** - 论文标题和翻译信息
2. **正文翻译** - 中文译文
3. **底部注释** - 术语和公式引用
4. **附录1：术语表** - 所有专业术语及解释
5. **附录2：公式解释** - 公式的直观理解
6. **附录3：图表说明** - 图表的详细描述

## 成本估算

| 功能 | API | 成本(每篇15页) |
|------|-----|---------------|
| 文本翻译 | DeepSeek | ¥0.02 |
| 公式解释 | DeepSeek | ¥0.01 |
| 图表理解 | SiliconFlow | ¥0.02 |
| **合计** | | **¥0.05** |

## 目录结构

```
paper-translator/
├── config.yaml          # 配置文件
├── main.py              # 主入口
├── requirements.txt     # 依赖
├── .env.example         # 环境变量示例
├── README.md            # 说明文档
├── paper_translator/    # 核心模块
│   ├── __init__.py
│   ├── config.py        # 配置管理
│   ├── models.py        # 数据模型
│   ├── pdf_parser.py   # PDF解析
│   ├── translation_engine.py  # 翻译引擎
│   ├── figure_understanding.py # 图表理解
│   ├── pdf_generator.py # PDF生成
│   └── processor.py     # 主处理器
└── input_papers/        # 输入目录
    └── translated_papers/  # 输出目录
```

## 对接爬虫系统

可以将翻译系统集成到你的爬虫系统中：

```python
from paper_translator.processor import PaperTranslator

translator = PaperTranslator()

# 爬虫获取PDF后
pdf_path = "/path/to/paper.pdf"
result = translator.translate(pdf_path)

print(f"翻译完成: {result.output_path}")
```

## 注意事项

1. **API密钥** - 必须配置DeepSeek API才能正常翻译
2. **MinerU** - 可选安装，提升PDF解析精度
3. **图表理解** - 需要SiliconFlow API，未配置时使用模拟输出
4. **版权** - 仅用于学习和研究
