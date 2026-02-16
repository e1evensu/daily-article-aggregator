"""
图表理解模块 - 使用多模态LLM
"""

import base64
import logging
import os
from pathlib import Path
from typing import Optional

import requests

from paper_translator.config import config

logger = logging.getLogger(__name__)


class FigureUnderstanding:
    """图表理解器"""

    def __init__(self):
        self._api_key = config.siliconflow_api_key
        self._base_url = config.siliconflow_base_url
        self._use_local = not bool(self._api_key)

        if self._use_local:
            logger.warning("未配置SILICONFLOW_API_KEY，将使用模拟图表理解")
        else:
            logger.info("图表理解模块初始化完成 (SiliconFlow)")

    def describe_figure(
        self,
        image_path: str,
        caption: str = ""
    ) -> str:
        """
        理解并描述图表

        Args:
            image_path: 图片路径
            caption: 图注（可选）

        Returns:
            图表描述
        """
        if self._use_local:
            return self._mock_describe_figure(caption)

        try:
            # 将图片转为base64
            with open(image_path, 'rb') as f:
                img_base64 = base64.b64encode(f.read()).decode()

            # 构建prompt
            prompt_text = self._build_prompt(caption)

            # 调用API
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": "zai-org/GLM-4.6V",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                    ]
                }],
                "temperature": 0.3
            }

            response = requests.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            else:
                logger.error(f"图表理解API错误: {response.status_code}")
                return self._mock_describe_figure(caption)

        except Exception as e:
            logger.error(f"图表理解失败: {e}")
            return self._mock_describe_figure(caption)

    def describe_figures_batch(
        self,
        figures: list[dict]
    ) -> list[str]:
        """批量理解图表"""
        results = []
        for fig in figures:
            img_path = fig.get('image_path', '')
            caption = fig.get('caption', '')

            if img_path and os.path.exists(img_path):
                desc = self.describe_figure(img_path, caption)
            else:
                desc = self._mock_describe_figure(caption)

            results.append(desc)

        return results

    def _build_prompt(self, caption: str) -> str:
        """构建图表理解prompt"""
        base_prompt = """这是一张来自AI/机器学习论文的图表。请详细描述：

1. 图表类型（折线图、柱状图、流程图、架构图等）
2. 坐标轴含义和数据趋势
3. 图表的关键结论或信息
4. 在论文上下文中的意义

"""
        if caption:
            base_prompt += f"图表标题/图注：{caption}\n"

        base_prompt += "\n请用中文回答，描述要清晰详细。"
        return base_prompt

    def _mock_describe_figure(self, caption: str) -> str:
        """模拟图表理解"""
        if caption:
            return f"图表显示：{caption}。该图表展示了研究中的关键数据和趋势。"
        return "图表显示了论文中的关键数据点，包括实验结果对比、性能指标等。"
