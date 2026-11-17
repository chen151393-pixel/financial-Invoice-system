"""结汇资料包：按“批次 → 出口合同号”把销售合同与提单 PDF 打成 zip，附文件清单。资料未齐时拒绝打包。"""

import io
import re
import zipfile

from backend.core.errors import ApiError

from ..policy.amount_policy import money
from ..policy.route_policy import HK_TRANSIT
from .document_service import NOT_INCLUDED, load


def safe_name(value):
    """去掉路径分隔符等不适合文件名的字符。"""
    return re.sub(r'[\\/:*?"<>|\s]+', "_", str(value)).strip("_.") or "未命名"


class PackageService:
    def __init__(self, engine, store, reader):
        self.engine, self.store, self.reader = engine, store, reader

    def build(self, batch_id):
        """返回 (zip 文件名, zip 字节)。"""
        with self.engine.connect() as connection:
            batch, items = load(connection, batch_id)
            if batch["route"] != HK_TRANSIT:
                raise ApiError(409, "仅香港中转批次需要资料包")
            if batch["status"] == "cancelled":
                raise ApiError(409, "批次已作废，不能下载资料包")
            state = self.reader.state(connection, batch, items)
        if state["issues"]:
            raise ApiError(409, "资料未齐，不能打包：" + "；".join(state["issues"][:3]))
        root = safe_name(
            f"{batch['received_on']}_{batch['batch_no']}_{batch['currency']}{money(batch['declared_total'])}"
        )
        listing = [
            f"结汇批次 {batch['batch_no']}",
            f"境外收货人：{batch['consignee']}",
            f"香港到账日期：{batch['received_on']}　报关合计：{batch['currency']} {money(batch['declared_total'])}",
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
                name = f"销售合同{safe_name(contract['contract_no'])}.pdf"
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
                listing.append("")
            listing.append("未纳入本资料包、需另行准备：" + "、".join(NOT_INCLUDED))
            archive.writestr(f"{root}/文件清单.txt", "\r\n".join(listing))
        return f"{root}.zip", buffer.getvalue()
