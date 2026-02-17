"""
翻译引擎 - 支持 DeepSeek 和 MiniMax (Anthropic格式) API
"""

import json
import logging
import re
from typing import Optional

import openai
import requests

from .config import config
from .models import Term

logger = logging.getLogger(__name__)


class TranslationEngine:
    """翻译引擎"""

    def __init__(self):
        self._client = None
        self._provider = config.translation_provider
        self._init_client()

    def _init_client(self):
        """初始化API客户端"""
        if self._provider == 'minimax':
            self._init_minimax()
        else:
            self._init_deepseek()

    def _init_deepseek(self):
        """初始化DeepSeek客户端"""
        api_key = config.deepseek_api_key
        if not api_key:
            logger.warning("未配置DEEPSEEK_API_KEY，将使用模拟翻译")
            return

        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=config.deepseek_base_url
        )
        logger.info("翻译引擎初始化完成 (DeepSeek)")

    def _init_minimax(self):
        """初始化MiniMax客户端 (Anthropic格式)"""
        api_key = config.minimax_api_key
        if not api_key:
            logger.warning("未配置MINIMAX_API_KEY，将使用模拟翻译")
            return

        self._client = True
        logger.info("翻译引擎初始化完成 (MiniMax)")

    def _extract_json_from_markdown(self, text: str) -> str:
        """从markdown代码块中提取JSON"""
        # 匹配 ```json ... ``` 或 ``` ... ```
        pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
        return text.strip()

    def _call_minimax(self, prompt: str, max_tokens: int = 2000) -> str:
        """调用 MiniMax API (Anthropic格式)"""
        headers = {
            "x-api-key": config.minimax_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }

        payload = {
            "model": config.minimax_model,
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }

        response = requests.post(
            f"{config.minimax_base_url}/v1/messages",
            headers=headers,
            json=payload,
            timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            for block in result.get('content', []):
                if block.get('type') == 'text':
                    return block.get('text', '')
            return ''
        else:
            raise Exception(f"MiniMax API error: {response.status_code} - {response.text}")

    def _call_deepseek(self, messages: list, temperature: float = 0.3, response_format: dict = None) -> str:
        """调用 DeepSeek API (OpenAI格式)"""
        kwargs = {
            "model": config.deepseek_model,
            "messages": messages,
            "temperature": temperature
        }
        if response_format:
            kwargs["response_format"] = response_format
        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    def translate_text(self, text: str, style: str = "academic") -> str:
        """翻译文本"""
        if not self._client:
            return self._mock_translate(text)

        style_instruction = {
            "academic": "使用学术风格，保持专业术语的准确性，句式严谨",
            "casual": "使用通俗易懂的语言，适当解释专业概念"
        }.get(style, "使用学术风格")

        prompt = f"""你是一个专业的学术论文翻译助手。请将以下英文论文内容翻译成中文。
{style_instruction}

要求：
1. 保持专业术语的准确性，首次出现时在括号内保留英文原文
2. 保持公式和变量的原样
3. 保持原有格式（段落、标点）
4. 翻译要通顺自然，符合中文阅读习惯

原文：
{text}"""

        try:
            if self._provider == 'minimax':
                return self._call_minimax(prompt, max_tokens=2000)
            else:
                messages = [{"role": "user", "content": prompt}]
                return self._call_deepseek(messages, temperature=0.3)
        except Exception as e:
            logger.error(f"翻译失败: {e}")
            return self._mock_translate(text)

    def translate_batch(self, texts: list, style: str = "academic") -> list:
        """批量翻译"""
        return [self.translate_text(t, style) for t in texts]

    def explain_formula(self, latex: str, context: str = "") -> str:
        """解释公式"""
        if not self._client:
            return self._mock_explain_formula(latex)

        prompt = f"""你是一个专业的AI/机器学习论文助手。请解释以下数学公式：

公式：{latex}

上下文：{context}

请用通俗易懂的语言解释这个公式，包括：
1. 公式中每个变量的含义
2. 公式的整体作用和意义
3. 在机器学习/深度学习中的直观理解

注意：避免过于专业的数学语言，用通俗的比喻帮助理解。"""

        try:
            if self._provider == 'minimax':
                return self._call_minimax(prompt, max_tokens=1000)
            else:
                messages = [{"role": "user", "content": prompt}]
                return self._call_deepseek(messages, temperature=0.3)
        except Exception as e:
            logger.error(f"公式解释失败: {e}")
            return self._mock_explain_formula(latex)

    def extract_terms(self, text: str, max_terms: int = 10) -> list:
        """提取并解释术语"""
        if not self._client:
            return self._mock_extract_terms(text, max_terms)

        prompt = f"""从以下AI/机器学习论文中提取关键专业术语，并给出简洁的中文解释。

要求：
1. 选择最重要、最常见的术语（最多{max_terms}个）
2. 解释要简洁明了（30字以内）
3. 返回JSON数组格式

文本：
{text[:3000]}...

格式示例：
[
  {{"term": "Transformer", "translation": "Transformer是一种...", "explanation": "一种基于注意力机制的神经网络架构"}},
  {{"term": "Attention", "translation": "注意力机制", "explanation": "让模型聚焦于关键信息"}}
]"""

        try:
            if self._provider == 'minimax':
                result = self._call_minimax(prompt, max_tokens=1500)
                # 从markdown代码块中提取JSON
                result = self._extract_json_from_markdown(result)
            else:
                messages = [{"role": "user", "content": prompt}]
                result = self._call_deepseek(messages, temperature=0.3, response_format={"type": "json_object"})

            terms_data = json.loads(result)

            terms = []
            if isinstance(terms_data, dict):
                for key, value in terms_data.items():
                    if isinstance(value, list):
                        terms_data = value
                        break
                else:
                    terms_data = []

            for item in terms_data:
                if isinstance(item, dict):
                    terms.append(Term(
                        term=item.get('term', ''),
                        translation=item.get('translation', ''),
                        explanation=item.get('explanation', '')
                    ))
            return terms
        except Exception as e:
            logger.error(f"术语提取失败: {e}")
            return self._mock_extract_terms(text, max_terms)

    def _mock_translate(self, text: str) -> str:
        """模拟翻译（无API时使用）"""
        return f"[译] {text[:200]}..."

    def _mock_explain_formula(self, latex: str) -> str:
        """模拟公式解释"""
        return f"公式 {latex} 是一个数学表达式，用于表示..."

    def _mock_extract_terms(self, text: str, max_terms: int) -> list:
        """模拟术语提取"""
        common_terms = [
            ("Transformer", "Transformer", "一种基于自注意力机制的神经网络架构"),
            ("Attention", "注意力机制", "让模型聚焦于输入的关键部分"),
            ("Neural Network", "神经网络", "受人脑启发的计算模型"),
            ("Deep Learning", "深度学习", "使用多层神经网络的机器学习方法"),
            ("Model", "模型", "从数据中学习得到的数学表示"),
        ]
        return [
            Term(term=t[0], translation=t[1], explanation=t[2])
            for t in common_terms[:max_terms]
        ]
