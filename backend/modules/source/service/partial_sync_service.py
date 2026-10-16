"""按报关关联单元逐个提交，已确认成功的单元不受后续业务失败影响。"""

from sqlalchemy.exc import SQLAlchemyError

from backend.core import write_lock
from backend.core.errors import ApiError
from backend.integrations.netsuite.read_batch import quiet_progress

from ..mapper.ns_fields import reference
from ..mapper.storage_mapper import validate_storage_config
from ..policy.ns_config import parse_config
from ..vo.partial_sync_result import PartialResult
from .declaration_service import sync_lock_name
from .ns_reader import PlReader


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
        # 保留同一账户整个读取期间的互斥，组间只结束数据库事务，不释放账本锁。
        try:
            with write_lock.locked(storage.engine, lock) as connection:
                page = read_page()
                result = PartialResult(page)
                groups = self._groups(kind, page["rows"], config)
                for index, group in enumerate(groups, 1):
                    if not self._save_group(
                        connection, kind, group, config, account, lock, report, result, index, len(groups)
                    ):
                        break
                return result.response()
        except SQLAlchemyError:
            raise ApiError(503, "数据库连接中断，请先核实已保存单据，不要自动重试") from None

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

    def _save_group(self, connection, kind, group, config, account, lock, report, result, index, total):
        label = f"第 {index}/{total} 组（已保存 {result.saved_groups} 组）："

        def phase(message, completed=None, count=None):
            report(label + message, completed, count)

        collected = None

        def collect():
            nonlocal collected
            collected = PlReader(self.storage.ns, phase).collect_records(kind, group)
            return collected

        try:
            saved = self.storage._save_locked(connection, collect, config, account, lock, True, phase)
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
            section = "customs" if kind == "customs-declarations" else "purchases"
            saved_ids = {identity for identity, _, _ in collected[section]}
            # 初次单头读取失败的入口，若作为完整关联单据成功读回并提交，按实际结果更新状态。
            included = [{"id": identity} for identity in saved_ids if identity in result.items]
            result.mark(included, "saved", "本单及完整关联数据已提交保存")
        return True
