"""提单交给识别模型：有文字层的发文字，扫描件发第一页图像；返回校验后的字段。

模型适配器由 app.py 按配置注入（backend/integrations/model_extraction.py），本文件不关心是哪家模型。
调用在数据库事务之外进行；模型未返回可用结果时返回 None，由调用方沿用本地规则的结果。
"""

import io

from ..policy.bill_model_policy import INSTRUCTIONS, clean
from .bill_ocr import scan_image

# 发给模型的图像长边上限：A4 约 190dpi，足够辨认提单文字，又不至于请求过大
MODEL_IMAGE_SIDE = 2200


class BillModelReader:
    def __init__(self, extractor):
        self.extractor = extractor

    def read(self, content, text):
        """content：提单 PDF 字节；text：已提取的文字层（扫描件为空）。"""
        if text.strip():
            answer = self.extractor.extract(INSTRUCTIONS, text=text)
        else:
            # 发原始彩色图像：去底纹的二值化是为 tesseract 准备的，可能抹掉浅色文字
            image = scan_image(content)
            if image is None:
                return None
            image.thumbnail((MODEL_IMAGE_SIDE, MODEL_IMAGE_SIDE))
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=85)
            answer = self.extractor.extract(INSTRUCTIONS, image_jpeg=buffer.getvalue())
        return clean(answer) if answer is not None else None
