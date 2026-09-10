"""视觉大模型调用客户端（CommOCR pipeline.call_model 移植）。

OpenAI 兼容 chat.completions + image_url(base64)；与 llm_engine 的纯文本路线并列。
"""
from __future__ import annotations

import base64

from openai import OpenAI

from command_shared.ocr_render import encode_image_to_base64

DEFAULT_TIMEOUT = 300
DEFAULT_MAX_RETRIES = 1


def make_vl_client(api_key: str, base_url: str, timeout: int = DEFAULT_TIMEOUT,
                   max_retries: int = DEFAULT_MAX_RETRIES) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=base_url or None,
                  timeout=timeout, max_retries=max_retries)


def call_vl(client: OpenAI, prompt: str, image_bytes: bytes, model: str,
            image_format: str = "jpeg") -> str:
    """单图视觉问答 → 模型文本应答。图像经 base64 data URL 送出。"""
    data_url = (
        f"data:image/{image_format};base64,"
        + encode_image_to_base64(image_bytes)
    )
    response = client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return response.choices[0].message.content or ""
