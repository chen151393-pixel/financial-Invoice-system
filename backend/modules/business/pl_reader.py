"""实时联查与落库共用完整读取链路；报关单保存时保留其他PL的明细。"""

from backend.core.errors import ApiError

from .pl_config import parse_config
from .pl_mapper import reference, text


class PlReader:
    def __init__(self, ns):
        self.ns = ns
        self.config = parse_config(ns.settings)
        self.cache = {}

    def read(self, spec, record_id):
        key = (spec.type, record_id)
        if key not in self.cache:
            if len(self.cache) >= 300:
                raise ApiError(422, "本次联查超过 300 条详情读取上限，未保存不完整结果")
            self.ns.validate(spec.type, record_id)
            record = self.ns.request("GET", spec.type, record_id, exact_numbers=True)["data"]
            if not isinstance(record, dict) or ("id" in record and str(record["id"]) != record_id):
                raise ApiError(502, "NS详情响应不完整或记录身份不一致")
            self.cache[key] = record
        return self.cache[key]

    def lines(self, spec, parent_id):
        ids = self.ns.filtered_ids(spec.type, spec.parent, parent_id, reference=True)
        if len(set(ids)) != len(ids):
            raise ApiError(502, "NS明细身份重复，未保存")
        records = []
        for record_id in ids:
            record = self.read(spec, record_id)
            if reference(record.get(spec.parent)) != parent_id:
                raise ApiError(502, "NS明细所属报关单不一致或采购订单不一致")
            records.append((record_id, record))
        return records

    def collect(self, pl_number, *, resolve_all_pl=False, discover_customs=False):
        config = self.config
        pl_ids = self.ns.filtered_ids(config.pl.type, config.pl.number, pl_number)
        if len(pl_ids) > 1:
            raise ApiError(409, "该PL单号对应多个内部记录，需先核实唯一性")
        bundle = {"purchases": [], "customs": [], "warnings": [], "pl_id": None, "pl_names": {}}
        if not pl_ids:
            bundle["warnings"].append("未找到该PL单号，未修改已有本地数据")
            return bundle
        pl_id = bundle["pl_id"] = pl_ids[0]
        bundle["pl_names"][pl_id] = pl_number
        ids = self.ns.filtered_ids(config.purchase.type, config.purchase.pl, pl_id, reference=True)
        if len(set(ids)) != len(ids):
            raise ApiError(502, "NS采购订单身份重复")
        customs_ids = set()
        direct_ids = []
        if discover_customs:
            # 只读核对独立查找报关来源，不能依赖采购单是否填写报关关联。
            direct_ids = self.ns.filtered_ids(
                config.customs_line.type, config.customs_line.pl, pl_id, reference=True
            )
            if len(set(direct_ids)) != len(direct_ids):
                raise ApiError(502, "NS报关明细身份重复")
            for line_id in direct_ids:
                line = self.read(config.customs_line, line_id)
                if reference(line.get(config.customs_line.pl)) != pl_id:
                    raise ApiError(502, "报关明细PL关联与筛选结果不一致")
                parent_id = reference(line.get(config.customs_line.parent))
                if not parent_id:
                    raise ApiError(502, "报关明细缺少所属报关单，无法返回完整结果")
                customs_ids.add(parent_id)
        for record_id in ids:
            head = self.read(config.purchase, record_id)
            if reference(head.get(config.purchase.pl)) != pl_id:
                raise ApiError(502, "采购单PL关联与筛选结果不一致")
            customs_id = reference(head.get(config.purchase.customs))
            if customs_id:
                customs_ids.add(customs_id)
            else:
                bundle["warnings"].append(f"子采购订单 {text(head.get('name')) or record_id} 未关联报关单")
            lines = self.lines(config.purchase_line, record_id)
            if not lines:
                bundle["warnings"].append(f"子采购订单 {record_id} 未查询到货品行")
            bundle["purchases"].append((record_id, head, lines))
        for record_id in sorted(customs_ids):
            head = self.read(config.customs, record_id)
            lines = self.lines(config.customs_line, record_id)
            bundle["customs"].append((record_id, head, lines))
            if not any(reference(line.get(config.customs_line.pl)) == pl_id for _, line in lines):
                bundle["warnings"].append(f"报关单 {record_id} 未找到该PL的报关明细")
            if resolve_all_pl:
                for _, line in lines:
                    other = reference(line.get(config.customs_line.pl))
                    if other and other not in bundle["pl_names"]:
                        pl = self.read(config.pl, other)
                        number = text(pl.get(config.pl.number))
                        if not number:
                            raise ApiError(502, "关联报关明细的PL单号未能完整解析")
                        bundle["pl_names"][other] = number
        returned_lines = {line_id for _, _, lines in bundle["customs"] for line_id, _ in lines}
        if not set(direct_ids).issubset(returned_lines):
            raise ApiError(502, "报关明细在读取期间发生变化，请重新查询完整结果")
        if not ids and not discover_customs:
            bundle["warnings"].append("该PL未找到子采购订单；本功能沿采购单引用联查，未独立扫描其他报关单")
        return bundle

    def collect_records(self, kind, rows):
        """按同步页的服务器读取结果补齐明细；不从浏览器接收待保存正文。"""
        config = self.config
        spec = config.purchase if kind == "sub-purchase-orders" else config.customs
        bundle = {"purchases": [], "customs": [], "warnings": [], "pl_names": {}}
        customs_ids = set()
        for row in rows:
            record_id, head = row["id"], row["record"]
            self.ns.validate(spec.type, record_id)
            if str(head.get("id")) != record_id:
                raise ApiError(502, "同步单据身份不一致，未保存")
            if (spec.type, record_id) not in self.cache and len(self.cache) >= 300:
                raise ApiError(422, "本次同步超过 300 条详情读取上限，未保存不完整结果")
            self.cache[spec.type, record_id] = head
            if kind == "sub-purchase-orders":
                lines = self.lines(config.purchase_line, record_id)
                bundle["purchases"].append((record_id, head, lines))
                linked = reference(head.get(config.purchase.customs))
                if linked:
                    customs_ids.add(linked)
            else:
                customs_ids.add(record_id)
        for record_id in sorted(customs_ids):
            bundle["customs"].append(
                (record_id, self.read(config.customs, record_id), self.lines(config.customs_line, record_id))
            )
        self.complete_customs_purchases(bundle)
        self.resolve_pl_names(bundle)
        return bundle

    def complete_customs_purchases(self, bundle):
        """按 NS 显式报关引用反查全量子单，避免只同步报关头或漏掉同单的其他子采购。"""
        config = self.config
        purchases = {identity: (identity, head, lines) for identity, head, lines in bundle["purchases"]}
        membership = {}
        for identity, _, _ in bundle["customs"]:
            ids = self.ns.filtered_ids(
                config.purchase.type, config.purchase.customs, identity, reference=True
            )
            if len(set(ids)) != len(ids):
                raise ApiError(502, "关联子采购单身份重复，未保存")
            previous = {
                key
                for key, (_, head, _) in purchases.items()
                if reference(head.get(config.purchase.customs)) == identity
            }
            if not previous.issubset(ids):
                raise ApiError(502, "读取期间子采购报关引用发生变化，未保存本页")
            for purchase_id in ids:
                head = self.read(config.purchase, purchase_id)
                if reference(head.get(config.purchase.customs)) != identity:
                    raise ApiError(502, "关联子采购单的报关引用与查询范围不一致")
                if purchase_id not in purchases:
                    purchases[purchase_id] = (
                        purchase_id,
                        head,
                        self.lines(config.purchase_line, purchase_id),
                    )
            membership[identity] = ids
        bundle["purchases"] = list(purchases.values())
        bundle["customs_purchase_membership"] = membership

    def resolve_pl_names(self, bundle):
        config = self.config
        pl_ids = {reference(head.get(config.purchase.pl)) for _, head, _ in bundle["purchases"]}
        pl_ids.update(
            reference(line.get(config.customs_line.pl))
            for _, _, lines in bundle["customs"]
            for _, line in lines
        )
        for pl_id in sorted(pl_ids - {""}):
            record = self.read(config.pl, pl_id)
            number = text(record.get(config.pl.number))
            if not number:
                raise ApiError(502, "关联PL单号未能完整解析，未保存")
            bundle["pl_names"][pl_id] = number
