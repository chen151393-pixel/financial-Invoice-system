"""提单扫描件识别：取第一页的扫描图像，去掉彩色底纹后交给本机 tesseract，返回带坐标的文字。

tesseract 是服务器上的可选组件（SETTLEMENT_OCR_COMMAND）；未安装、超时或图像无法读取时返回空列表，
由人工填写提单字段。识别在数据库事务之外进行。
"""

import io
import shutil
import subprocess

from PIL import Image, ImageChops
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from .bill_ocr_cells import refine_cells
from .bill_ocr_refine import refine_bl

# 整页版面分别按“单一文本块”和“稀疏文字”两种方式识别，结果一致的字段才采用
PAGE_MODES = ("6", "11")
MIN_SIDE = 1000
MAX_SIDE = 4000
TIMEOUT_SECONDS = 40
# 三个颜色通道取最大值后的二值化阈值：彩色水印与底纹变白，黑色文字保留
INK_THRESHOLD = 150


def scan_image(content):
    """第一页中最大的图像（彩色原样），按页面旋转角转正；不是扫描件时返回 None。"""
    try:
        page = PdfReader(io.BytesIO(content)).pages[0]
        images = [item.image for item in page.images]
        rotation = int(page.get("/Rotate") or 0)
    except (
        PyPdfError,
        ValueError,
        KeyError,
        IndexError,
        OSError,
        RecursionError,
        Image.DecompressionBombError,
    ):
        return None
    images = [image for image in images if image is not None and min(image.size) >= MIN_SIDE]
    if not images:
        return None
    image = max(images, key=lambda item: item.size[0] * item.size[1]).convert("RGB")
    if rotation % 360:
        image = image.rotate(-rotation, expand=True)
    if max(image.size) > MAX_SIDE:
        image.thumbnail((MAX_SIDE, MAX_SIDE))
    return image


def page_image(content):
    """scan_image 去掉彩色底纹后的黑白图像，供 tesseract 识别；不是扫描件时返回 None。"""
    image = scan_image(content)
    if image is None:
        return None
    red, green, blue = image.split()
    brightest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    return brightest.point(lambda value: 255 if value > INK_THRESHOLD else 0)


def words_from_tsv(output):
    """tesseract TSV 中的词（level 5）转为 {text, left, top, right, bottom}。"""
    words = []
    for line in output.splitlines()[1:]:
        cells = line.split("\t")
        if len(cells) != 12 or cells[0] != "5" or not cells[11].strip():
            continue
        left, top, width, height = (int(cell) for cell in cells[6:10])
        words.append(
            {"text": cells[11], "left": left, "top": top, "right": left + width, "bottom": top + height}
        )
    return words


class BillOcr:
    def __init__(self, command="tesseract"):
        self.command = shutil.which(command) if command else None

    @property
    def available(self):
        return bool(self.command)

    def readings(self, content):
        """同一页按各识别方式得到的文字列表；无法识别时返回空列表。"""
        if not self.command:
            return []
        image = page_image(content)
        if image is None:
            return []
        readings = [self._read_words(image, mode) for mode in PAGE_MODES]
        if any(words is None for words in readings):
            return []
        readings = refine_bl(image, readings, self.command)
        return refine_cells(image, readings, lambda crop, mode: self._read_words(crop, mode, timeout=10))

    def _read_words(self, image, mode, *, timeout=TIMEOUT_SECONDS):
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        try:
            done = subprocess.run(  # noqa: S603 命令来自部署配置，参数固定，不经过 shell
                [self.command, "stdin", "stdout", "--psm", mode, "-l", "eng", "tsv"],
                input=buffer.getvalue(),
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if done.returncode != 0:
            return None
        return words_from_tsv(done.stdout.decode("utf-8", "replace"))
