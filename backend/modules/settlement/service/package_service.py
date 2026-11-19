"""结汇资料包：按“批次 → 出口合同号”把销售合同（形式发票）、提单与报关单打成 zip，附文件清单。

资料未齐时拒绝打包。报关单取 NS 报关资料的归档原件（PDF 或 xls），未归档或读不到时在文件清单中注明。
"""

import io
import re
import zipfile

from backend.core.errors import ApiError

from ..policy.amount_policy import money
from ..policy.route_policy import HK_TRANSIT
from .document_service import load


def safe_name(value):
    """去掉路径分隔符等不适合文件名的字符。"""
    return re.sub(r'[\\/:*?"<>|\s]+', "_", str(value)).strip("_.") or "未命名"


class PackageService:
    def __init__(self, engine, store, reader, documents=None):
        self.engine, self.store, self.reader = engine, store, reader
        self.documents = documents

    def build(self, batch_id):
        """返回 (zip 文件名, zip 字节)。"""
        with self.engine.connect() as connection:
            batch, items = (
                self.documents.load(connection, batch_id) if self.documents else load(connection, batch_id)
            )
            direct = batch.get("document_kind") == "direct"
            if batch["route"] != HK_TRANSIT and not direct:
                raise ApiError(409, "仅香港中转批次需要资料包")
            if batch["status"] == "cancelled":
                raise ApiError(409, "批次已作废，不能下载资料包")
            state = self.reader.state(connection, batch, items)
        if state["issues"]:
            raise ApiError(409, "资料未齐，不能打包：" + "；".join(state["issues"][:3]))
        direct = batch.get("document_kind") == "direct"
        root = (
            safe_name(f"直接收汇_{batch['id']}_{batch['currency']}{money(batch['declared_total'])}")
            if direct
            else safe_name(
                f"{batch['received_on']}_{batch['batch_no']}_{batch['currency']}{money(batch['declared_total'])}"
            )
        )
        listing = [
            f"直接收汇报关单 {batch['id']}" if direct else f"结汇批次 {batch['batch_no']}",
            f"境外收货人：{batch['consignee']}",
            f"报关合计：{batch['currency']} {money(batch['declared_total'])}"
            if direct
            else f"香港到账日期：{batch['received_on']}　报关合计：{batch['currency']} {money(batch['declared_total'])}",
            "",
        ]
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for contract in state["contracts"]:
                folder = f"{root}/{safe_name(contract['contract_no'])}"
                listing.append(
                    f"[{contract['contract_no']}] 报关单：{'、'.join(contract['declaration_nos'])}　"
                    f"合同金额：{contract['currency']} {money(contract['amount'])}"
                )
                name = f"销售合同（形式发票）{safe_name(contract['contract_no'])}.pdf"
                archive.writestr(f"{folder}/{name}", self.store.read(contract["file_id"], "pdf"))
                listing.append(
                    f"  {name}" + (f"（{contract['stamp_note']}）" if contract["stamp_note"] else "")
                )
                numbers = set(contract["declaration_nos"])
                for bill in state["bills"]:
                    if numbers & set(bill["declaration_nos"] or []):
                        name = f"提单{safe_name(bill['bl_no'])}.pdf"
                        archive.writestr(f"{folder}/{name}", self.store.read(bill["file_id"], "pdf"))
                        listing.append(
                            f"  {name}　{bill['port_of_loading']} → {bill['port_of_discharge']}　"
                            f"装船日期 {bill['on_board_date']}"
                        )
                for row in state["declaration_files"]:
                    if row["declaration_no"] in numbers:
                        listing.extend(self._declaration(archive, folder, row))
                listing.append("")
            archive.writestr(f"{root}/文件清单.txt", "\r\n".join(listing))
        return f"{root}.zip", buffer.getvalue()

    def _declaration(self, archive, folder, row):
        """把一张报关单的归档文件写入 zip，返回文件清单中的各行。"""
        number = safe_name(row["declaration_no"])
        if row["status"] != "archived":
            return [f"  报关单 {row['declaration_no']}：{row['label']}，未放入，需另行准备"]
        lines = []
        for index, file in enumerate(row["files"], 1):
            content, reason = self.reader.declaration_files.read(file)
            if content is None:
                lines.append(f"  报关单 {row['declaration_no']}：{reason}，未放入，需另行准备")
                continue
            suffix = f"_{index}" if len(row["files"]) > 1 else ""
            extension = ".pdf" if str(file["filename"]).lower().endswith(".pdf") else ".xls"
            name = f"报关单{number}{suffix}{extension}"
            archive.writestr(f"{folder}/{name}", content)
            lines.append(f"  {name}")
        return lines
