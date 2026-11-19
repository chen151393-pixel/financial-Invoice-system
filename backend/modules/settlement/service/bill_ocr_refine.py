"""对整页识别有歧义的提单号局部放大复识；两次一致才替换原词。"""

import io
import re
import subprocess

from PIL import Image, ImageOps

from ..policy.bill_layout_policy import agreed, bl_value_words, parse_words


def refine_bl(image, readings, command):
    if agreed([parse_words(words) for words in readings])["bl_no"]:
        return readings
    targets = bl_value_words(readings)
    if not targets:
        return readings
    # 以已定位的文字框裁剪，少量留边，避免把表格线带入单行识别。
    box = (
        max(0, min(word["left"] for word in targets) - 3),
        max(0, min(word["top"] for word in targets) - 3),
        min(image.width, max(word["right"] for word in targets) + 3),
        min(image.height, max(word["bottom"] for word in targets) + 3),
    )
    crop = image.crop(box)
    values = []
    for mode, scale in (("6", 2), ("7", 3)):
        enlarged = crop.resize((crop.width * scale, crop.height * scale), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        ImageOps.expand(enlarged, border=20, fill="white").save(buffer, "PNG")
        try:
            done = subprocess.run(  # noqa: S603 命令来自部署配置，参数固定，不经过 shell
                [
                    command,
                    "stdin",
                    "stdout",
                    "--psm",
                    mode,
                    "-l",
                    "eng",
                    "-c",
                    "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                ],
                input=buffer.getvalue(),
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return readings
        value = done.stdout.decode("utf-8", "replace").strip()
        if done.returncode or not re.fullmatch(r"[A-Z0-9]{8,20}", value):
            return readings
        if not any(char.isdigit() for char in value):
            return readings
        values.append(value)
    if len(set(values)) != 1:
        return readings
    return [
        [dict(word, text=values[0]) if word is target else word for word in words]
        for words, target in zip(readings, targets, strict=True)
    ]
