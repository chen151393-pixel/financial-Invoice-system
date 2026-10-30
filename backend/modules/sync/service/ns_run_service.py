"""NS 来源按批后台保存：持久请求编号，后台线程执行，按编号查询实际结果。

解决“代理先超时、后端仍在保存”导致页面结果与数据库不一致：提交接口立即返回，
结果写入 sync_ns_runs 后由页面按请求编号查询。同编号重复提交只返回原记录，不重新执行；
结果未知的批次不自动重试。执行状态只在当前进程内跟踪，适用于当前单进程部署。
"""

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import ns_run_dao as runs
from ..vo.ns_run_vo import run_view

logger = logging.getLogger("ns_api.sync")


class NsRunService:
    def __init__(self, engine, pulls, executor=None):
        self.engine, self.pulls = engine, pulls
        self.lock = Lock()
        self.active = {}
        self.stopping = Event()
        # 同一账户的保存本就由账户锁串行；单线程排队，避免多批同时争锁失败。
        self.executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="ns-sync")

    def scope(self, owner):
        account = self.pulls.settings.account or ""
        return hashlib.sha256(f"ns-sync\n{account}\n{owner}".encode()).hexdigest()

    def start(self, owner, body):
        if self.engine is None:
            raise ApiError(503, "独立MySQL业务库尚未配置")
        if self.stopping.is_set():
            raise ApiError(503, "服务正在停止，请稍后重新发起本批")
        # 配置类问题同步返回，不创建记录，避免后台失败被误判为结果未知。
        self.pulls.ensure_storage(body.kind)
        scope = self.scope(owner)
        ticket = self.pulls.progress.create(owner)["progressId"]
        previous = self._create(scope, body)
        if previous is not None:
            if previous["kind"] != body.kind or previous["request"] != body.snapshot():
                raise ApiError(409, "同一请求编号不能用于不同单据类型或分页条件，请查询原结果")
            return self.read(owner, body.requestId)
        with self.lock:
            self.active[scope, body.requestId] = ticket
        try:
            self.executor.submit(self._execute, owner, scope, body, ticket)
        except RuntimeError:
            # 执行器已关闭（服务停止中），本批确定未开始。
            self._finish(scope, body.requestId, "failed", None, "服务正在停止，本批未开始执行，请重新发起")
        return self.read(owner, body.requestId)

    def execute_now(self, owner, scope, body, run_id):
        """定时计划在后台线程内同步执行一页：建 running 记录并直接执行，结果写回同一记录。

        复用手动按批保存的执行与结果映射；执行标记先于记录登记，避免查询把刚建的记录显示为待核实。
        """
        ticket = self.pulls.progress.create(owner)["progressId"]
        with self.lock:
            self.active[scope, body.requestId] = ticket
        try:
            previous = self._create(scope, body, run_id=run_id)
        except BaseException:
            with self.lock:
                self.active.pop((scope, body.requestId), None)
            raise
        if previous is not None:
            with self.lock:
                self.active.pop((scope, body.requestId), None)
            raise ApiError(409, "分页请求编号已存在，未重复执行")
        self._execute(owner, scope, body, ticket)

    def executing(self, scope):
        """本进程正在执行的请求编号；不在其中的 running 记录按结果待核实展示。"""
        with self.lock:
            return frozenset(request for key, request in self.active if key == scope)

    def progress(self, scope, request_id, owner):
        with self.lock:
            ticket = self.active.get((scope, request_id))
        if ticket is None:
            return None
        try:
            return self.pulls.progress.get(ticket, owner)
        except ApiError:
            return None

    def _create(self, scope, body, *, run_id=None):
        """新建 running 记录并返回 None；同编号已存在时返回原记录。"""
        values = {
            "scope_key": scope,
            "request_id": body.requestId,
            "kind": body.kind,
            "request": body.snapshot(),
            "status": "running",
            **({"run_id": run_id} if run_id is not None else {}),
        }
        try:
            with self.engine.begin() as connection:
                previous = runs.get(connection, scope, body.requestId)
                if previous is None:
                    runs.create(connection, values)
                return previous
        except IntegrityError:
            # 并发提交同一编号时以先写入的记录为准。
            with self.engine.connect() as connection:
                previous = runs.get(connection, scope, body.requestId)
            if previous is None:
                raise ApiError(503, "同步记录未能确认创建，请按原请求编号查询") from None
            return previous
        except SQLAlchemyError:
            raise ApiError(503, "同步记录未能确认创建，请按原请求编号查询，不要换编号重新提交") from None

    def read(self, owner, request_id):
        scope = self.scope(owner)
        # 先取执行标记再读记录，避免刚结束的批次被短暂显示为待核实。
        with self.lock:
            ticket = self.active.get((scope, request_id))
        try:
            with self.engine.connect() as connection:
                row = runs.get(connection, scope, request_id)
        except SQLAlchemyError:
            raise ApiError(503, "同步记录暂时无法查询，请稍后按原请求编号重试查询") from None
        if row is None:
            raise ApiError(404, "未找到该同步批次，请确认请求编号或重新发起本批")
        progress = None
        if ticket is not None:
            try:
                progress = self.pulls.progress.get(ticket, owner)
            except ApiError:
                progress = None
        return run_view(row, active=ticket is not None, progress=progress)

    def _execute(self, owner, scope, body, ticket):
        status, result = "unknown", None
        error = "后台执行异常，结果待核实，请核对本地记录后再处理"
        try:
            if self.stopping.is_set():
                status, error = "failed", "服务正在停止，本批未开始执行，请重新发起"
            else:
                result = self.pulls.pull_and_save(body.kind, body.pull_request(ticket), owner)
                status, error = result["batch"]["status"], None
        except ApiError as exc:
            # 部分保存把各组失败写入逐单结果；逃逸的错误发生在组提交之前，
            # 只有数据库中断（503）可能发生在提交之后，保守标为待核实。
            status = "unknown" if exc.status == 503 else "failed"
            error = exc.message[:500]
        except Exception:
            logger.exception("NS 后台同步批次异常，记录标为待核实")
        finally:
            self._finish(scope, body.requestId, status, result, error)

    def _finish(self, scope, request_id, status, result, error):
        try:
            with self.engine.begin() as connection:
                runs.finish(connection, scope, request_id, status, result=result, error=error)
        except SQLAlchemyError:
            # 记录保持 running，进程内执行标记移除后查询显示为待核实。
            logger.exception("NS 后台同步结果未能写入，记录保持待核实")
        finally:
            with self.lock:
                self.active.pop((scope, request_id), None)

    def stop(self):
        """停止接收新批次；排队未开始的批次记为未执行，正在执行的批次等待结束。"""
        self.stopping.set()
        self.executor.shutdown(wait=True)
