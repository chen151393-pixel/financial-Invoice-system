"""按报关关联单元逐个提交，已确认成功的单元不受后续业务失败影响。

默认整页只读取一次 NS（单头、明细、反查子采购、关联依据、母单），再按关联组分别校验和提交，
避免每组重复同一串 NS 请求。整页读取遇到业务错误时，改为逐组读取，保持“失败只影响本组”的原规则。
"""

import logging

from sqlalchemy.exc import SQLAlchemyError

from backend.core import write_lock
from backend.core.errors import ApiError
from backend.integrations.netsuite.read_batch import quiet_progress

from ..mapper.group_bundle import split_groups
from ..mapper.ns_fields import reference
from ..mapper.storage_mapper import validate_storage_config
from ..policy.ns_config import parse_config
from ..vo.partial_sync_result import PartialResult
from .declaration_service import sync_lock_name
from .ns_reader import PlReader

logger = logging.getLogger("ns_api.source")


class PartialSyncService:
    def __init__(self, storage):
        self.storage = storage

    def run(self, kind, read_page, progress=None):
        if kind not in ("sub-purchase-orders", "customs-declarations"):
            raise ApiError(422, "当前仅支持子采购订单和报关单入库")
        storage = self.storage
        if storage.engine is None:
            raise ApiError(503, "独立MySQL业务库尚未配置")
        config = parse_config(storage.ns.settings)
        validate_storage_config(config)
        account = storage.account()
        lock = sync_lock_name(storage.engine, account)
        report = progress or quiet_progress
        report("等待当前账户保存锁")
        # 整页读取期间只持账户锁，保持同一账户互斥；每组提交时由 commit() 短暂取得账本锁。
        try:
            with write_lock.locked(storage.engine, lock, ledger=False) as connection:
                page = read_page()
                result = PartialResult(page)
                context = (connection, kind, config, account, lock, report, result)
                groups = self._read_whole_page(kind, page["rows"], config, report, result)
                if groups is None:
                    self._save_each_group(context, page["rows"])
                else:
                    self._commit_groups(context, groups)
                return result.response()
        except SQLAlchemyError:
            raise ApiError(503, "数据库连接中断，请先核实已保存单据，不要自动重试") from None

    def _read_whole_page(self, kind, rows, config, report, result):
        """整页一次读取；返回按组拆分的数据包，业务读取失败时返回 None 交由逐组读取定位。"""
        if not rows:
            return []

        def phase(message, completed=None, count=None):
            report("整页读取：" + message, completed, count)

        try:
            bundle = self.storage.read_bundle(
                lambda: PlReader(self.storage.ns, phase).collect_records(kind, rows), config, True, phase
            )
        except ApiError as error:
            # 不记录单据内容；逐组读取会把具体失败原因写入对应单据结果。
            logger.info("ns_sync_whole_page_fallback kind=%s status=%s", kind, error.status)
            report("整页读取未通过，改为逐组读取以定位失败单据")
            return None
        result.mark_skipped(bundle.get("skipped", []))
        return split_groups(bundle, kind, rows, config)

    def _commit_groups(self, context, groups):
        connection, _, config, account, lock, _, _ = context
        for index, (rows, bundle) in enumerate(groups, 1):

            def save(phase, bundle=bundle):
                saved = self.storage.commit(connection, bundle, config, account, lock, phase)
                return saved, bundle

            if not self._save_group(context, rows, index, len(groups), save):
                break

    def _save_each_group(self, context, rows):
        connection, kind, config, account, lock, _, _ = context
        groups = self._groups(kind, rows, config)
        pl_cache = {}
        for index, group in enumerate(groups, 1):

            def save(phase, group=group):
                collected = None

                def collect():
                    nonlocal collected
                    reader = PlReader(self.storage.ns, phase, pl_cache=pl_cache)
                    collected = reader.collect_records(kind, group)
                    return collected

                saved = self.storage._save_locked(connection, collect, config, account, lock, True, phase)
                return saved, collected

            if not self._save_group(context, group, index, len(groups), save):
                break

    def _groups(self, kind, rows, config):
        groups = {}
        for row in rows:
            if kind == "customs-declarations":
                key = ("customs", row["id"])
            else:
                customs_id = reference(row["record"].get(config.purchase.customs))
                key = ("customs", customs_id) if customs_id else ("purchase", row["id"])
            groups.setdefault(key, []).append(row)
        return list(groups.values())

    def _save_group(self, context, group, index, total, save):
        _, kind, _, _, _, report, result = context
        label = f"第 {index}/{total} 组（已保存 {result.saved_groups} 组）："

        def phase(message, completed=None, count=None):
            report(label + message, completed, count)

        try:
            saved, collected = save(phase)
        except SQLAlchemyError:
            # 连接/提交异常无法确认该组结果；保留此前确认成功的计数，停止后续组及翻页。
            result.mark(group, "unknown", "数据库保存结果待核实，请核对本地记录后处理，勿直接重试")
            result.interrupted = True
            return False
        except ApiError as error:
            result.mark(group, "failed", f"本关联组未保存；{error.message}")
            if error.status not in (404, 422, 502):
                result.interrupted = True
                return False
        else:
            result.add(saved)
            result.mark_skipped(collected.get("skipped", []))
            section = "customs" if kind == "customs-declarations" else "purchases"
            saved_ids = {identity for identity, _, _ in collected[section]}
            # 初次单头读取失败的入口，若作为完整关联单据成功读回并提交，按实际结果更新状态。
            included = [{"id": identity} for identity in saved_ids if identity in result.items]
            result.mark(included, "saved", "本单及完整关联数据已提交保存")
        return True
