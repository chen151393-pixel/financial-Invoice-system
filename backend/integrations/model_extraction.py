"""识别模型适配：把一段文字或一张图片交给外部模型，取回一个 JSON 对象。

只负责传输与响应格式，不包含任何业务字段或校验；提示词由调用方（业务模块）提供。
换模型或换厂商只改配置：凡提供 OpenAI 兼容接口（`POST {base_url}/chat/completions`）的服务
共用 OpenAICompatibleExtractor。接口格式不同的厂商在本文件新增一个同样带 extract 方法的类，
并在 create_extractor 中登记。

失败（网络、超时、非 2xx、返回内容不是 JSON 对象）一律返回 None，由调用方退回本地规则；
日志只记录状态，不记录密钥、提示词或单据内容。
"""

import base64
import json
import logging

import httpx

logger = logging.getLogger(__name__)

KINDS = ("openai_compatible",)
MAX_RESPONSE_BYTES = 1024 * 1024


class OpenAICompatibleExtractor:
    def __init__(self, base_url, api_key, model, *, timeout=30, transport=None):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.client = httpx.Client(
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def extract(self, instructions, *, text=None, image_jpeg=None):
        """instructions：系统提示词；text 与 image_jpeg 二选一。返回 JSON 对象（dict）或 None。"""
        if image_jpeg is not None:
            data = base64.b64encode(image_jpeg).decode()
            content = [
                {"type": "text", "text": "Extract the fields from this document image."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}},
            ]
        elif text:
            content = text
        else:
            return None
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": content},
            ],
            "response_format": {"type": "json_object"},
        }
        try:
            # 单次请求，不自动重试：识别失败只是退回人工填写，不值得拖慢上传
            response = self.client.post(self.url, json=body)
        except httpx.HTTPError as error:
            logger.warning("识别模型请求失败：%s", type(error).__name__)
            return None
        if not response.is_success or len(response.content) > MAX_RESPONSE_BYTES:
            logger.warning("识别模型返回异常：HTTP %s", response.status_code)
            return None
        try:
            answer = json.loads(response.json()["choices"][0]["message"]["content"])
        except (ValueError, KeyError, IndexError, TypeError):
            logger.warning("识别模型返回的不是约定的 JSON")
            return None
        return answer if isinstance(answer, dict) else None


def create_extractor(kind, *, base_url, api_key, model, timeout=30):
    """按配置返回识别模型适配器；kind 为空或 rules 时返回 None（不调用任何模型）。"""
    if kind == "openai_compatible":
        return OpenAICompatibleExtractor(base_url, api_key, model, timeout=timeout)
    return None
