"""LLM Provider 抽象层。

统一封装不同 LLM 后端（Anthropic-compatible / OpenAI-compatible / 中转）。
后续切换到 DeepSeek / Qwen / cc 等只需改环境变量，不修改业务代码。

环境变量:
  ANTHROPIC_BASE_URL     — API endpoint (默认 https://api.anthropic.com)
  ANTHROPIC_AUTH_TOKEN   — API key / auth token
  ANTHROPIC_MODEL        — 默认 model name (默认 claude-opus-4-7)
"""

import os
from dataclasses import dataclass
from typing import Optional
import anthropic


@dataclass
class LLMConfig:
    provider: str        # "anthropic" | "openai" | "deepseek" | ...
    base_url: str        # API endpoint
    api_key: str         # auth token
    model: str           # model name

    @classmethod
    def from_env(cls, model: Optional[str] = None) -> "LLMConfig":
        """从环境变量构造配置。"""
        base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        api_key = os.getenv("ANTHROPIC_AUTH_TOKEN", "")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_AUTH_TOKEN 环境变量未设置。"
                "请设置后重试: export ANTHROPIC_AUTH_TOKEN=your-token"
            )
        default_model = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-7")
        return cls(
            provider="anthropic",
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            model=model or default_model,
        )


class LLMProvider:
    """LLM 调用抽象。

    当前实现：Anthropic-compatible API（支持 DeepSeek 等兼容端点）。
    后续扩展：provider="openai" 时使用 OpenAI SDK。
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        if config.provider == "anthropic":
            self._client = anthropic.Anthropic(
                base_url=config.base_url,
                api_key=config.api_key,
            )
        else:
            raise ValueError(f"不支持的 provider: {config.provider}")

    @property
    def model(self) -> str:
        return self.config.model

    @property
    def base_url(self) -> str:
        return self.config.base_url

    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
    ) -> str:
        """发送消息，返回文本响应。自动过滤 ThinkingBlock，只取 TextBlock。"""
        response = self._client.messages.create(
            model=self.config.model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            thinking={"type": "disabled"},
        )
        # 过滤 TextBlock（兼容 DeepSeek thinking 模式返回的 ThinkingBlock）
        for block in response.content:
            if hasattr(block, "text"):
                return block.text.strip()
        # 回退：某些 provider 可能不支持 thinking 参数，重试一次
        response = self._client.messages.create(
            model=self.config.model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        for block in response.content:
            if hasattr(block, "text"):
                return block.text.strip()
        raise RuntimeError("响应中没有 TextBlock")
