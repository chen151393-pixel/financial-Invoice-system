"""Excel预览和整批原子导入，保存前重新解析并复核来源冲突。"""

import hashlib
import hmac
import re
import secrets
import time
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from . import dao
from .entity import load_tables
from .mapper import image_storage_values, storage_values
from .parser import digest, number, parse_file
from .vo import decimal_text, invoice_detail_view, invoice_row, result


class InvoiceService:
    def __init__(self, engine):
        self.engine = engine
        self.secret = secrets.token_bytes(32)

    def _engine(self):
        if self.engine is None:
            raise ApiError(503, "独立MySQL业务库尚未配置")
        if self.engine.dialect.name != "mysql":
            raise ApiError(503, "发票导入需要MySQL业务库")
        return self.engine

    def configuration(self):
        try:
            with self._engine().connect() as connection:
                load_tables(connection)
            return {"allowed": True, "reason": "可导入柠檬云导出的进项XLS或XLSX文件", "maxBytes": 4194304}
        except ApiError as error:
            return {"allowed": False, "reason": error.message, "maxBytes": 4194304}
        except SQLAlchemyError:
            return {
                "allowed": False,
                "reason": "无法读取发票两表，请检查业务数据库及迁移",
                "maxBytes": 4194304,
            }

    def list_invoices(self, query, owner):
        tenant = hashlib.sha256(owner.encode()).hexdigest()
        try:
            with self._engine().connect() as connection, connection.begin():
                head, lines = load_tables(connection)
                total, amounts, records = dao.invoice_list(connection, head, lines, tenant, query)
                return {
                    "total": total,
                    "page": query.page,
                    "pageSize": query.page_size,
                    "hasPrevious": query.page > 1,
                    "hasNext": query.page * query.page_size < total,
                    "rows": [invoice_row(row) for row in records],
                    "amounts": [
                        {
                            "currency": row["currency_code"],
                            "count": row["count"],
                            "net": decimal_text(row["net"]),
                            "tax": decimal_text(row["tax"]),
                            "gross": decimal_text(row["gross"]),
                        }
                        for row in amounts
                    ],
                }
        except SQLAlchemyError:
            raise ApiError(503, "发票查询失败，请检查业务数据库连接及表结构") from None

    def invoice_detail(self, invoice_id, owner):
        tenant = hashlib.sha256(owner.encode()).hexdigest()
        try:
            with self._engine().connect() as connection, connection.begin():
                head, lines = load_tables(connection)
                record, details = dao.invoice_detail(connection, head, lines, tenant, invoice_id)
                if record is None:
                    raise ApiError(404, "发票不存在或当前身份无权查看")
                return invoice_detail_view(record, details)
        except SQLAlchemyError:
            raise ApiError(503, "发票详情读取失败，请检查业务数据库连接") from None

    def invoice_details(self, invoice_ids, owner):
        """供匹配模块批量读取当前页，沿用单票详情的身份与有效性边界。"""
        tenant = hashlib.sha256(owner.encode()).hexdigest()
        try:
            with self._engine().connect() as connection, connection.begin():
                head, lines = load_tables(connection)
                records, details = dao.invoice_details(connection, head, lines, tenant, invoice_ids)
                if {row["id"] for row in records} != set(invoice_ids):
                    raise ApiError(404, "发票不存在或当前身份无权查看")
                grouped = {row["id"]: [] for row in records}
                for row in details:
                    grouped[row["invoice_id"]].append(row)
                return [invoice_detail_view(row, grouped[row["id"]]) for row in records]
        except SQLAlchemyError:
            raise ApiError(503, "发票详情读取失败，请检查业务数据库连接") from None

    def signature(self, owner, filename, file_hash, deadline):
        return hmac.new(
            self.secret, f"{owner}\0{filename}\0{file_hash}\0{deadline}".encode(), hashlib.sha256
        ).hexdigest()

    def process(self, body, owner, commit=False):
        engine = self._engine()
        documents, file_hash = parse_file(body.filename, body.content)
        source_count = len(documents)
        documents = [doc for doc in documents if doc["head"]["business_type_name"] == "采购固定资产"]
        if commit:
            token = body.previewToken or ""
            deadline, _, signature = token.partition(".")
            if (
                not deadline.isdigit()
                or int(deadline) < time.time()
                or not hmac.compare_digest(
                    signature, self.signature(owner, body.filename, file_hash, deadline)
                )
            ):
                raise ApiError(409, "预览已失效或文件发生变化，请重新预览")
            if not documents:
                raise ApiError(422, "文件中没有业务类型为“采购固定资产”的发票，未写入数据")
        tenant = hashlib.sha256(owner.encode()).hexdigest()
        lock_name = hashlib.sha256(f"invoice-import:{engine.url.database}:{tenant}".encode()).hexdigest()
        try:
            with engine.connect() as connection:
                with connection.begin():
                    acquired = dao.lock(connection, lock_name)
                if not acquired:
                    raise ApiError(409, "当前用户已有发票导入操作，请稍后重新预览")
                try:
                    with connection.begin():
                        head_table, line_table = load_tables(connection)
                        self.validate_lengths(documents, head_table, line_table)
                        old = dao.existing(
                            connection, head_table, tenant, [doc["head"]["invoice_no"] for doc in documents]
                        )
                        actions = self.classify(documents, old)
                        view = result(documents, actions)
                        if commit and "conflict" in actions:
                            raise ApiError(409, "发现同票内容或来源冲突，整批未写入，请重新预览并核实")
                        if commit:
                            now = datetime.now(timezone.utc).replace(tzinfo=None)
                            for doc, action in zip(documents, actions, strict=True):
                                if action == "new":
                                    head, lines = storage_values(
                                        doc, tenant, owner, body.filename, file_hash, now
                                    )
                                    dao.insert(connection, head_table, line_table, head, lines)
                    # 提交成功后才返回成功结果，释放锁失败不掩盖业务提交。
                finally:
                    try:
                        dao.unlock(connection, lock_name)
                        connection.commit()
                    except SQLAlchemyError:
                        connection.invalidate()
        except SQLAlchemyError:
            raise ApiError(
                503, "发票数据库操作失败或提交结果不明。请重新预览核实，系统不会覆盖已存发票"
            ) from None
        deadline = str(int(time.time()) + 1800)
        return {
            **view,
            "sourceInvoiceCount": source_count,
            "excludedCount": source_count - len(documents),
            "businessType": "采购固定资产",
            "saved": commit,
            "filename": body.filename,
            "allowed": bool(documents) and "conflict" not in actions,
            "reason": "没有采购固定资产发票，无需导入"
            if not documents
            else "存在冲突，整批不能导入"
            if "conflict" in actions
            else "校验通过，可确认导入",
            "previewToken": None
            if commit
            else f"{deadline}.{self.signature(owner, body.filename, file_hash, deadline)}",
            "message": "导入完成，新增发票已提交数据库，重复记录已跳过"
            if commit
            else "预览完成，尚未写入数据库",
        }

    def import_image_snapshot(self, raw, owner, source_name, source_hash):
        """保存用户提供并已人工核对的票面摘录；不推断业务分类或发票状态。"""
        if (
            not source_name
            or any(char in source_name for char in ("/", "\\", "\x00"))
            or not re.fullmatch(r"[0-9a-f]{64}", source_hash)
        ):
            raise ApiError(422, "发票图片来源信息无效")
        no = raw.get("invoice_no", "")
        if not isinstance(no, str) or not re.fullmatch(r"[0-9]{20}", no):
            raise ApiError(422, "数电发票号码须为20位文本")
        try:
            invoice_date = date.fromisoformat(raw["invoice_date"])
        except (KeyError, TypeError, ValueError):
            raise ApiError(422, "开票日期须为YYYY-MM-DD") from None
        for field in ("invoice_type_name", "seller_name", "seller_tax_no", "buyer_name", "buyer_tax_no"):
            if not isinstance(raw.get(field), str) or not raw[field].strip():
                raise ApiError(422, f"票面缺少{field}")
        rate_raw = raw.get("tax_rate_raw", "")
        if not isinstance(rate_raw, str) or not re.fullmatch(r"\d+(?:\.\d+)?%", rate_raw):
            raise ApiError(422, "票面税率格式不正确")
        tax_rate = number(rate_raw[:-1], 6, "票面税率") / 100
        if not 0 <= tax_rate <= 1:
            raise ApiError(422, "票面税率超出范围")
        amounts = {
            field: number(raw.get(field), 6, field)
            for field in ("amount_excluding_tax", "tax_amount", "amount_including_tax")
        }
        if amounts["amount_excluding_tax"] + amounts["tax_amount"] != amounts["amount_including_tax"]:
            raise ApiError(422, "票面价税合计不等于金额加税额")
        raw_lines = raw.get("lines")
        if not isinstance(raw_lines, list) or not 1 <= len(raw_lines) <= 100:
            raise ApiError(422, "票面商品明细须为1至100行")
        lines = []
        line_occurrences = Counter()
        price_overflow = False
        for index, item in enumerate(raw_lines, 1):
            if not isinstance(item, dict) or not all(
                isinstance(item.get(field), str) and item[field].strip()
                for field in ("item_name", "unit_name", "unit_price_raw")
            ):
                raise ApiError(422, f"第{index}行商品名称、单位或票面单价缺失")
            quantity = number(item.get("quantity"), 8, f"第{index}行数量")
            net = number(item.get("amount_excluding_tax"), 6, f"第{index}行金额")
            tax = number(item.get("tax_amount"), 6, f"第{index}行税额")
            try:
                price = Decimal(item["unit_price_raw"])
            except InvalidOperation:
                raise ApiError(422, f"第{index}行票面单价无效") from None
            if not price.is_finite() or abs(price) >= Decimal(10) ** 18 or min(quantity, net, tax, price) < 0:
                raise ApiError(422, f"第{index}行存在无效负值")
            if price != price.quantize(Decimal("0.00000001")):
                price_overflow = True
                stored_price = None
            else:
                stored_price = price
            line = {
                "item_name": item["item_name"].strip(),
                "unit_name": item["unit_name"].strip(),
                "quantity": quantity,
                "unit_price": stored_price,
                "unit_price_raw": item["unit_price_raw"],
                "amount_excluding_tax": net,
                "tax_amount": tax,
                "amount_including_tax": net + tax,
            }
            line_hash = digest(line)
            line_occurrences[line_hash] += 1
            line["source_line_key"] = f"{line_hash}:{line_occurrences[line_hash]}"
            lines.append(line)
        if any(
            sum(line[field] for line in lines) != amounts[field]
            for field in ("amount_excluding_tax", "tax_amount", "amount_including_tax")
        ):
            raise ApiError(422, "票面明细汇总与票头金额不一致")
        issues = [
            {"code": "BUSINESS_TYPE_UNVERIFIED", "message": "票面没有业务类型，须核实分类"},
            {"code": "INVOICE_STATUS_UNVERIFIED", "message": "图片未提供可核实的发票状态"},
        ]
        if price_overflow:
            issues.append(
                {
                    "code": "UNIT_PRICE_PRECISION",
                    "message": "票面单价超过数据库八位小数精度，原文保留在来源快照，标准单价字段为空",
                }
            )
        snapshot = {
            **amounts,
            "invoice_no": no,
            "invoice_date": invoice_date,
            "invoice_type_name": raw["invoice_type_name"].strip(),
            "seller_name": raw["seller_name"].strip(),
            "seller_tax_no": raw["seller_tax_no"].strip(),
            "seller_bank_account": raw.get("seller_bank_account"),
            "buyer_name": raw["buyer_name"].strip(),
            "buyer_tax_no": raw["buyer_tax_no"].strip(),
            "tax_rate_raw": rate_raw,
            "tax_rate": tax_rate,
            "remark": raw.get("remark"),
            "lines": lines,
            "raw_header": {key: value for key, value in raw.items() if key != "lines"},
            "raw_lines": raw_lines,
            "source_name": source_name,
            "source_hash": source_hash,
            "validation_errors": issues,
            "import_key": digest({"version": 1, "type": "digital", "no": no}),
        }
        snapshot["content_hash"] = digest(
            {"header": snapshot["raw_header"], "lines": sorted(digest(line) for line in lines)}
        )
        engine = self._engine()
        tenant = hashlib.sha256(owner.encode()).hexdigest()
        lock_name = hashlib.sha256(f"invoice-import:{engine.url.database}:{tenant}".encode()).hexdigest()
        try:
            with engine.connect() as connection:
                with connection.begin():
                    acquired = dao.lock(connection, lock_name)
                if not acquired:
                    raise ApiError(409, "当前用户已有发票导入操作，请稍后重试")
                try:
                    with connection.begin():
                        head_table, line_table = load_tables(connection)
                        now = datetime.now(timezone.utc).replace(tzinfo=None)
                        head, detail = image_storage_values(snapshot, tenant, owner, now)
                        self.validate_lengths([{"head": head, "lines": detail}], head_table, line_table)
                        existing = dao.existing(connection, head_table, tenant, [no])
                        if existing:
                            if len(existing) != 1 or any(
                                existing[0][key] != value
                                for key, value in {
                                    "content_hash": snapshot["content_hash"],
                                    "external_system": "manual",
                                    "external_account": "user-image",
                                    "import_key": snapshot["import_key"],
                                }.items()
                            ):
                                raise ApiError(409, "同号发票已存在且内容或来源不同，未覆盖")
                            invoice_id = existing[0]["id"]
                            state = "unchanged"
                        else:
                            invoice_id = dao.insert(connection, head_table, line_table, head, detail)
                            state = "created"
                finally:
                    try:
                        dao.unlock(connection, lock_name)
                        connection.commit()
                    except SQLAlchemyError:
                        connection.invalidate()
        except SQLAlchemyError:
            raise ApiError(503, "发票入库失败或提交结果不明，请先按票号核实") from None
        return {"id": str(invoice_id), "state": state, "number": no, "lineCount": len(lines)}

    @staticmethod
    def classify(documents, existing):
        grouped = {}
        for row in existing:
            grouped.setdefault(row["invoice_no"], []).append(row)
        actions = []
        for doc in documents:
            matches = grouped.get(doc["head"]["invoice_no"], [])
            if not matches:
                actions.append("new")
            elif len(matches) == 1 and all(
                matches[0][key] == value
                for key, value in {
                    "content_hash": doc["head"]["content_hash"],
                    "import_key": doc["head"]["import_key"],
                    "external_system": "excel",
                    "external_account": "lemon-excel",
                }.items()
            ):
                actions.append("unchanged")
            else:
                actions.append("conflict")
        return actions

    @staticmethod
    def validate_lengths(documents, head_table, line_table):
        for doc in documents:
            for values, table in [(doc["head"], head_table), *[(line, line_table) for line in doc["lines"]]]:
                for key, value in values.items():
                    length = getattr(table.c[key].type, "length", None)
                    if isinstance(value, str) and length and len(value) > length:
                        raise ApiError(422, f"发票{doc['head']['invoice_no']}字段{key}超过数据库长度{length}")
