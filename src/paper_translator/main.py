"""
论文翻译系统 - 主入口
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from paper_translator.config import config
from paper_translator.processor import PaperTranslator

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def setup_env():
    """加载环境变量"""
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        with open(env_file, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='论文翻译系统 - 保留格式，添加术语和公式解释'
    )

    parser.add_argument(
        'input',
        nargs='?',
        help='输入PDF文件路径'
    )

    parser.add_argument(
        '-o', '--output',
        help='输出PDF文件路径'
    )

    parser.add_argument(
        '-c', '--config',
        default='config.yaml',
        help='配置文件路径'
    )

    parser.add_argument(
        '-d', '--directory',
        help='输入目录（批量处理）'
    )

    parser.add_argument(
        '--list',
        action='store_true',
        help='列出输入目录中的PDF文件'
    )

    args = parser.parse_args()

    # 加载配置
    config_path = Path(args.config)
    if config_path.exists():
        config.load_from_yaml(str(config_path))

    # 检查API配置
    if not config.deepseek_api_key:
        logger.warning("未配置DEEPSEEK_API_KEY，将使用模拟翻译模式")
        logger.warning("请在.env文件中设置 DEEPSEEK_API_KEY")

    # 处理输入
    translator = PaperTranslator()

    # 列出文件
    if args.list:
        input_dir = Path(config.input_dir)
        if input_dir.exists():
            pdf_files = list(input_dir.glob('*.pdf'))
            logger.info(f"输入目录 {input_dir} 中的PDF文件：")
            for f in pdf_files:
                print(f"  - {f.name}")
        else:
            logger.warning(f"输入目录不存在: {input_dir}")
        return

    # 批量处理目录
    if args.directory:
        input_dir = Path(args.directory)
        pdf_files = list(input_dir.glob('*.pdf'))

        if not pdf_files:
            logger.warning(f"目录中没有PDF文件: {input_dir}")
            return

        logger.info(f"开始批量处理 {len(pdf_files)} 个文件...")

        for pdf_file in pdf_files:
            try:
                logger.info(f"\n处理: {pdf_file.name}")
                result = translator.translate(str(pdf_file))
                logger.info(f"完成: {result.output_path}")
            except Exception as e:
                logger.error(f"处理失败: {pdf_file.name}, 错误: {e}")

        logger.info("批量处理完成!")
        return

    # 单文件处理
    if args.input:
        input_arg = args.input

        # 检查是否是URL
        if input_arg.startswith('http://') or input_arg.startswith('https://'):
            # 下载PDF
            logger.info(f"检测到URL，正在下载: {input_arg}")
            import urllib.request
            import uuid
            input_dir = Path(config.input_dir)
            input_dir.mkdir(parents=True, exist_ok=True)
            local_path = input_dir / f"{uuid.uuid4().hex[:8]}.pdf"

            try:
                urllib.request.urlretrieve(input_arg, local_path)
                logger.info(f"下载完成: {local_path}")
                input_arg = str(local_path)
            except Exception as e:
                logger.error(f"下载失败: {e}")
                sys.exit(1)

        pdf_path = Path(input_arg)
        if not pdf_path.exists():
            logger.error(f"文件不存在: {pdf_path}")
            sys.exit(1)

        try:
            result = translator.translate(
                str(pdf_path),
                args.output
            )
            logger.info(f"\n翻译完成!")
            logger.info(f"输出文件: {result.output_path}")
            logger.info(f"耗时: {result.processing_time:.2f}秒")
            logger.info(f"页数: {result.total_pages}")
            logger.info(f"术语数: {len(result.all_terms)}")
            logger.info(f"公式数: {len(result.all_formulas)}")
            logger.info(f"图表数: {len(result.all_figures)}")

        except Exception as e:
            logger.error(f"翻译失败: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == '__main__':
    setup_env()
    main()
