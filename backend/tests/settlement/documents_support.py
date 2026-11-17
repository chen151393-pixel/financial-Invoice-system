"""结汇资料测试辅助：生成提单 PDF、印章图片，并把一个批次的资料补齐。"""

import base64
import io

from backend.modules.settlement.dto.bill_dto import UploadBillRequest
from backend.modules.settlement.dto.contract_dto import GenerateContractsRequest
from backend.modules.settlement.dto.party_dto import SavePartyRequest, UploadStampRequest
from backend.modules.settlement.service.bill_service import BillService
from backend.modules.settlement.service.contract_service import ContractService
from backend.modules.settlement.service.declaration_files import DeclarationFiles
from backend.modules.settlement.service.document_reader import DocumentReader
from backend.modules.settlement.service.document_service import DocumentService
from backend.modules.settlement.service.document_store import DocumentStore
from backend.modules.settlement.service.package_service import PackageService
from backend.modules.settlement.service.party_service import PartyService
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas

HK = "HONGKONG VISION DIGITAL PRINTING CO., LIMITED"
SELLER = "上海绎视数码科技有限公司"
BILL_LINES = (
    "BILL OF LADING",
    "B/L NO: EGLV142503975412",
    "PORT OF LOADING: YANTIAN, CHINA",
    "PORT OF DISCHARGE: LOS ANGELES, CA",
    "ON BOARD DATE: JUN 15 2026",
)


def encoded(content):
    return base64.b64encode(content).decode()


def bill_pdf(lines=BILL_LINES):
    buffer = io.BytesIO()
    # invariant：相同内容生成相同字节，便于验证重复上传
    page = canvas.Canvas(buffer, invariant=1)
    for index, line in enumerate(lines):
        page.drawString(60, 780 - index * 24, line)
    page.save()
    return buffer.getvalue()


def scanned_bill_pdf(lines=()):
    """只有一张整页图像、没有文字层的提单（模拟扫描件）。lines：[(x, y, 文字)]，300dpi A4 像素坐标。"""
    image = Image.new("RGB", (2480, 3508), "white")
    draw = ImageDraw.Draw(image)
    # 彩色底纹：识别前应被去掉
    draw.rectangle((100, 200, 2380, 900), fill=(205, 235, 215))
    for x, y, text in lines:
        draw.text((x, y), text, fill="black", font=ImageFont.load_default(size=30))
    buffer = io.BytesIO()
    image.save(buffer, "PDF", resolution=300)
    return buffer.getvalue()


def stamp_png():
    buffer = io.BytesIO()
    Image.new("RGBA", (40, 40), (200, 0, 0, 160)).save(buffer, "PNG")
    return buffer.getvalue()


class Documents:
    """一组共用同一资料目录的结汇资料服务。"""

    def __init__(self, engine, root, ocr=None):
        # 报关单归档目录（模拟共享盘）；与结汇资料目录分开
        self.archive = root / "archive"
        self.archive.mkdir(exist_ok=True)
        # 资料放在独立子目录，不与测试数据库文件混放
        self.store = DocumentStore(root / "documents")
        self.reader = DocumentReader(lead_days=28, declaration_files=DeclarationFiles(self.archive))
        self.views = DocumentService(engine, self.reader)
        self.bills = BillService(engine, self.store, self.views, ocr)
        self.contracts = ContractService(engine, self.store, self.reader, self.views)
        self.packages = PackageService(engine, self.store, self.reader)
        self.parties = PartyService(engine, self.store)

    def party(self, name, name_en, *, stamp=True):
        saved = self.parties.save(
            SavePartyRequest(name=name, nameEn=name_en, addressEn="1 Test Road", nameCn=name), "finance-user"
        )
        if stamp:
            body = UploadStampRequest(fileName="stamp.png", content=encoded(stamp_png()))
            saved = self.parties.upload_stamp(saved.id, body, "finance-user")
        return saved

    def upload(self, batch_id, content=None, numbers=()):
        body = UploadBillRequest(
            fileName="提单.pdf", content=encoded(content or bill_pdf()), declarationNos=list(numbers)
        )
        return self.bills.upload(batch_id, body, "finance-user")

    def generate(self, batch_id, seller_id):
        body = GenerateContractsRequest(
            sellerPartyId=seller_id, paymentTermsCn="100% 预付", paymentTermsEn="100% in advance"
        )
        return self.contracts.generate(batch_id, body, "finance-user")


def complete_documents(engine, root, batch_id):
    """维护双方抬头、上传提单并生成销售合同，使批次资料齐全。"""
    documents = Documents(engine, root)
    documents.party(HK, HK)
    seller = documents.party(SELLER, "SHANGHAI VISION DIGITAL PRINTING CO.,LTD.")
    documents.upload(batch_id)
    view = documents.generate(batch_id, seller.id)
    assert view.complete, view.issues
    return documents
