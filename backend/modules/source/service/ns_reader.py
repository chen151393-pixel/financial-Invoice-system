"""实时联查与落库共用完整读取链路；报关单保存时保留其他PL的明细。"""

from backend.core.errors import ApiError
from backend.integrations.netsuite.read_batch import RecordReader

from ..mapper.ns_fields import reference, text
from ..policy.line_read_policy import line_projection
from ..policy.ns_config import parse_config


class PlReader:
    def __init__(self, ns, progress=None, *, pl_cache=None):
        self.ns = ns
        self.config = parse_config(ns.settings)
        self.reader = RecordReader(ns, progress)
        self.cache = self.reader.cache
        self.progress = self.reader.progress
        self.pl_cache = pl_cache if pl_cache is not None else {}

    def read(self, spec, record_id):
        return self.reader.read(spec.type, record_id)

    def grouped(self, spec, field, parent_ids, label, *, batch_size=20):
        """合并同类父记录筛选，但逐条核实返回记录的所属身份。"""
        parents = list(dict.fromkeys(parent_ids))
        result = {identity: [] for identity in parents}
        seen = set()
        for offset in range(0, len(parents), batch_size):
            batch = parents[offset : offset + batch_size]
            self.progress(label)
            ids = self.ns.filtered_ids(
                spec.type, field, batch[0] if len(batch) == 1 else batch, reference=True
            )
            if len(set(ids)) != len(ids) or seen.intersection(ids):
                raise ApiError(502, "NS明细身份重复，未保存")
            seen.update(ids)
            self.prefetch(spec, ids, label)
            for identity in ids:
                record = self.read(spec, identity)
                parent = reference(record.get(field))
                if parent not in batch:
                    raise ApiError(502, "NS明细所属报关单不一致或采购订单不一致")
                result[parent].append((identity, record))
        return result

    def prefetch(self, spec, ids, label):
        projection = line_projection(spec)
        if projection is None:
            self.reader.prefetch(spec.type, ids, label)
            return
        pending = [identity for identity in ids if (spec.type, identity) not in self.cache]
        completed = len(ids) - len(pending)
        self.progress(label, completed, len(ids))
        for start in range(0, len(pending), 300):
            batch = pending[start : start + 300]
            records = self.ns.projected_records(spec.type, batch, projection)
            if set(records) != set(batch) or any(
                str(record.get("id")) != key for key, record in records.items()
            ):
                raise ApiError(502, "NS 批量明细身份或范围不一致，未保存")
            self.cache.update({(spec.type, key): record for key, record in records.items()})
            completed += len(batch)
            self.progress(label, completed, len(ids))

    def lines(self, spec, parent_id):
        return self.grouped(spec, spec.parent, [parent_id], "读取单据明细")[parent_id]

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
            self.cache[spec.type, record_id] = head
        purchase_lines = self.grouped(
            config.purchase_line,
            config.purchase_line.parent,
            [row["id"] for row in rows] if kind == "sub-purchase-orders" else [],
            "读取子采购明细",
        )
        for row in rows:
            record_id, head = row["id"], row["record"]
            if kind == "sub-purchase-orders":
                bundle["purchases"].append((record_id, head, purchase_lines[record_id]))
                linked = reference(head.get(config.purchase.customs))
                if linked:
                    customs_ids.add(linked)
            else:
                customs_ids.add(record_id)
        self.reader.prefetch(config.customs.type, sorted(customs_ids), "读取关联报关单")
        customs_lines = self.grouped(
            config.customs_line, config.customs_line.parent, sorted(customs_ids), "读取报关明细"
        )
        for record_id in sorted(customs_ids):
            bundle["customs"].append(
                (record_id, self.read(config.customs, record_id), customs_lines[record_id])
            )
        self.complete_customs_purchases(bundle)
        self.resolve_pl_names(bundle)
        return bundle

    def complete_customs_purchases(self, bundle):
        """按 NS 显式报关引用反查全量子单，避免只同步报关头或漏掉同单的其他子采购。"""
        config = self.config
        purchases = {identity: (identity, head, lines) for identity, head, lines in bundle["purchases"]}
        membership = {}
        grouped = self.grouped(
            config.purchase,
            config.purchase.customs,
            [identity for identity, _, _ in bundle["customs"]],
            "查找完整关联子采购",
            # 子采购入口已有单头缓存，逐报关核实其查询归属，避免漏检批内改挂。
            batch_size=1 if purchases else 20,
        )
        new_ids = [key for records in grouped.values() for key, _ in records if key not in purchases]
        lines = self.grouped(config.purchase_line, config.purchase_line.parent, new_ids, "读取关联子采购明细")
        for identity, records in grouped.items():
            ids = [key for key, _ in records]
            previous = {
                key
                for key, (_, head, _) in purchases.items()
                if reference(head.get(config.purchase.customs)) == identity
            }
            if not previous.issubset(ids):
                raise ApiError(502, "读取期间子采购报关引用发生变化，未保存本页")
            for purchase_id, head in records:
                if purchase_id not in purchases:
                    purchases[purchase_id] = (purchase_id, head, lines[purchase_id])
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
        for pl_id in pl_ids - {""}:
            if pl_id in self.pl_cache:
                self.cache[config.pl.type, pl_id] = self.pl_cache[pl_id]
        self.reader.prefetch(config.pl.type, sorted(pl_ids - {""}), "核对 PL 单号")
        for pl_id in sorted(pl_ids - {""}):
            record = self.read(config.pl, pl_id)
            number = text(record.get(config.pl.number))
            if not number:
                raise ApiError(502, "关联PL单号未能完整解析，未保存")
            self.pl_cache[pl_id] = record
            bundle["pl_names"][pl_id] = number
