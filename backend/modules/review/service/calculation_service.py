"""后台计算财务读模型：事务外读取计算，短事务按请求代次原子发布。"""

from datetime import UTC, datetime, timedelta

from backend.core.write_lock import transaction

from ..dao import calculation_job_dao as jobs
from ..dao import declaration_snapshot_dao as snapshots
from ..mapper.snapshot_mapper import snapshot_rows
from ..policy.calculation_policy import calculation_key


def now_utc():
    return datetime.now(UTC).replace(tzinfo=None)


def request_calculation(connection, event):
    """由 app.py 登记来源同步和审核通过订阅；与发布方同一事务，仅写队列。"""
    jobs.request(connection, event.ns_account, now_utc())


class CalculationService:
    def __init__(self, review):
        self.review, self.engine = review, review.engine
        self.key = calculation_key(review.tolerance)

    def initialize(self, *, force=False):
        """初次部署、规则/容差变化自动补算；force 用于运维全量重建。"""
        accounts = set(self.review.declarations.accounts())
        with transaction(self.engine) as connection:
            accounts.update(jobs.accounts(connection))
            for account in sorted(accounts):
                previous = jobs.get(connection, account, lock=True)
                if force or previous is None or previous["calculation_key"] != self.key:
                    jobs.request(connection, account, now_utc())
                    jobs.set_key(connection, account, self.key, now_utc())
        return len(accounts)

    def pending(self):
        with self.engine.connect() as connection:
            return jobs.pending(connection, now_utc())

    def calculate(self, requested):
        account = requested["ns_account"]
        with transaction(self.engine) as connection:
            job = jobs.get(connection, account, lock=True)
            if job["requested_revision"] == job["completed_revision"]:
                return False
            # 新账套首次同步创建的作业尚无算法版本，由当前消费者认领版本。
            if not job["calculation_key"]:
                jobs.set_key(connection, account, self.key, now_utc())
                job["calculation_key"] = self.key
            if job["calculation_key"] != self.key:
                return False  # 其他版本进程不得覆盖当前版本的结果。
        rows, suppliers = self.build(account)
        with transaction(self.engine) as connection:
            current = jobs.get(connection, account, lock=True)
            if (
                current["requested_revision"] != job["requested_revision"]
                or current["calculation_key"] != job["calculation_key"]
                or current["completed_revision"] >= job["requested_revision"]
            ):
                return False  # 计算期间同步或审核已提交，保留新队列，丢弃旧结果。
            snapshots.replace_account(connection, account, rows, suppliers)
            jobs.complete(connection, job, now_utc())
        return True

    def build(self, account):
        index = self.review.declarations.index(account, "")
        actives = self.review._actives([row["id"] for row in index])
        states = {
            row["id"]: self.review._state(
                row["content_sha256"], row["declaration_no"], row["order_count"], actives.get(row["id"])
            )
            for row in index
        }
        ids = [row["id"] for row in index if states[row["id"]][0] != "unshipped"]
        now, rows, suppliers = now_utc(), [], []
        for offset in range(0, len(ids), 50):
            contents = [
                content for content in self.review.declarations.details(ids[offset : offset + 50]) if content
            ]
            built = self.review.build_declarations(contents, states, actives)
            for content in contents:
                identity = content["declaration"]["id"]
                row, options = snapshot_rows(
                    content, built[identity], states[identity][1], actives.get(identity), now
                )
                rows.append(row)
                suppliers.extend(options)
        return rows, suppliers

    def fail(self, job):
        now = now_utc()
        delay = min(300, 2 ** min(job["attempts"] + 1, 8))
        with transaction(self.engine) as connection:
            # 刚发现的新账套可能在 calculate 中设置了版本，失败状态也须使用该版本。
            job = {**job, "calculation_key": job["calculation_key"] or self.key}
            jobs.fail(
                connection, job, "财务后台计算失败，请检查服务日志", now + timedelta(seconds=delay), now
            )

    def rebuild(self):
        """管理命令同步消费一次完整补算；错误向上抛出，不能把失败报成完成。"""
        self.initialize(force=True)
        completed = 0
        while pending := self.pending():
            progressed = False
            for job in pending:
                if job["calculation_key"] not in ("", self.key):
                    raise RuntimeError("财务计算版本已变化，请使用当前后端配置重试")
                try:
                    published = self.calculate(job)
                except Exception:
                    # CLI 与线程共用失败记录；继续抛出，命令不能把失败报告为完成。
                    self.fail(job)
                    raise
                if published:
                    completed += 1
                    progressed = True
            if not progressed and self.pending():
                raise RuntimeError("补算期间来源持续变化或其他进程已完成，请稍后核对计算队列")
        with self.engine.connect() as connection:
            if jobs.unfinished(connection):
                raise RuntimeError("仍有财务计算作业等待重试，补算尚未全部完成，请检查服务日志")
        return completed
