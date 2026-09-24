"""两个独立MySQL测试库验证人工审核期间同步互斥与重复确认。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from backend.core.errors import ApiError
from backend.modules.audit.entity import finance_audit
from backend.modules.business.public import CustomsReconciliationSource
from backend.modules.business.storage_service import StorageService
from backend.modules.reconciliation import service as review_module
from backend.modules.reconciliation.dto import ApproveRequest, DeclarationListQuery
from backend.modules.reconciliation.entity import reviews
from backend.modules.reconciliation.service import ReconciliationService
from backend.modules.reconciliation.task_entity import tasks
from backend.tests.test_business_migrations import migrated_engine as migrated_engine
from backend.tests.test_reconciliation_mysql import mysql_finance_context as mysql_finance_context
from backend.tests.test_related_purchase_storage import sample as sample
from sqlalchemy import func, select


def test_manual_approval_excludes_sync_and_concurrent_confirm(
    mysql_finance_context, migrated_engine, sample, monkeypatch
):
    context = mysql_finance_context
    ns, bundle = sample
    owner = f"user:{context.settings.admin_user}"
    storage = StorageService(ns, migrated_engine)
    storage.save_related_snapshot(bundle, owner)
    local = CustomsReconciliationSource(migrated_engine)
    service = ReconciliationService(context.settings, None, context.engine, local)
    query = DeclarationListQuery(keyword="CD70", account=ns.settings.account)
    first = service.browse(query, owner).groups[0]
    second = service.browse(query, owner).groups[0]
    assert first.review.allowed and first.unlinkedLines
    holding, release = Event(), Event()
    audit = review_module.record_finance_review

    def pause_audit(*args, **kwargs):
        holding.set()
        assert release.wait(timeout=10), "测试未释放审核屏障"
        return audit(*args, **kwargs)

    monkeypatch.setattr(review_module, "record_finance_review", pause_audit)
    with ThreadPoolExecutor(max_workers=1) as pool:
        job = pool.submit(
            service.approve, ApproveRequest(snapshotId=first.snapshotId, note="首次审核"), owner
        )
        try:
            assert holding.wait(timeout=10)
            with pytest.raises(ApiError) as busy:
                storage.save_related_snapshot(bundle, owner)
            assert busy.value.status == 409
            with pytest.raises(ApiError) as conflict:
                service.approve(ApproveRequest(snapshotId=second.snapshotId), owner)
            assert conflict.value.status == 409
        finally:
            release.set()
        assert job.result(timeout=10).review.status == "approved"
    retry = service.approve(ApproveRequest(snapshotId=second.snapshotId, note="不覆盖"), owner)
    assert retry.review.status == "approved" and retry.review.note == "首次审核"
    with context.engine.connect() as connection:
        assert connection.scalar(select(reviews.c.revision)) == 1
        assert connection.scalar(select(func.count()).select_from(finance_audit)) == 1
        assert connection.scalar(select(func.count()).select_from(tasks)) == retry.invoiceTaskCount
        assert retry.invoiceTaskCount > 0
    storage.save_related_snapshot(bundle, owner)
    # 相同来源重复拉取不改变业务内容，不会清掉财务结论。
    assert service.browse(query, owner).groups[0].review.status == "approved"
