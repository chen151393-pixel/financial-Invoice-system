"""供应商合并通知并发与整批回滚：仅在随机新建的专用 MySQL 库执行。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from backend.core.config import Settings
from backend.core.errors import ApiError
from backend.modules.task.dto.delivery_dto import DeliveryPreviewRequest, DeliverySubmitRequest
from backend.modules.task.service.delivery_submit_service import DeliverySubmitService
from backend.tests.delivery_fixtures import Channel
from backend.tests.test_matching_mysql import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_supplier_tasks import archive, body
from backend.tests.test_supplier_tasks import grouped as grouped
from backend.tests.test_supplier_tasks import (
    test_manual_record_rolls_back_all_members_on_database_failure as test_manual_record_rolls_back_all_members_on_database_failure,
)
from backend.tests.test_supplier_tasks import (
    test_non_root_basis_change_during_upload_prevents_channel_create as test_non_root_basis_change_during_upload_prevents_channel_create,
)
from backend.tests.test_task import USER, draft
from backend.tests.test_task import app_services as app_services


def test_upload_holds_every_member_against_concurrent_edits(grouped, engine, app_services):
    tasks, groups, notifications = grouped
    archive(app_services, tasks)
    settings = Settings(wecom_send_enabled=True, subpo_archive_root=app_services["tasks"].archive.root)
    app_services["tasks"].settings = settings
    notifications.save_draft(tasks[0]["id"], body(groups, tasks[0]["id"]), USER)
    channel = Channel()
    submit = DeliverySubmitService(engine, settings, channel, app_services["tasks"])
    preview = submit.preview(tasks[0]["id"], DeliveryPreviewRequest(revision=1, groupRevision=1), USER)
    request = DeliverySubmitRequest(
        revision=1, groupRevision=1, snapshotSha256=preview.snapshotSha256, requestId=uuid4().hex
    )
    entered, release = Event(), Event()

    def pause():
        entered.set()
        assert release.wait(20)

    channel.after_upload = pause
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(submit.submit, tasks[0]["id"], request, USER)
        try:
            assert entered.wait(20)
            with pytest.raises(ApiError, match="未决"):
                app_services["notifications"].save_draft(tasks[1]["id"], draft(revision=1), USER)
            with pytest.raises(ApiError, match="未决"):
                notifications.save_draft(tasks[0]["id"], body(groups, tasks[0]["id"]), USER)
            assert submit.submit(tasks[0]["id"], request, USER).status == "preparing"
        finally:
            release.set()
        assert future.result(timeout=30).status == "pending_confirmation"
    assert len(channel.creates) == 1 and len(channel.uploads) == 2
