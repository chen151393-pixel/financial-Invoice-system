"""通知隔离夹具：真实业务数据库及合同归档，企微使用可控假适配器。"""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from backend.core.config import Settings
from backend.core.errors import ApiError
from backend.modules.task.dto.delivery_dto import DeliveryPreviewRequest, DeliverySubmitRequest
from backend.modules.task.dto.supplier_group_dto import GroupSave
from backend.modules.task.service.delivery_receipt_service import DeliveryReceiptService
from backend.modules.task.service.delivery_reconcile_service import DeliveryReconcileService
from backend.modules.task.service.delivery_submit_service import DeliverySubmitService
from backend.tests.test_task import USER, draft, prepare_all


class Channel:
    def __init__(self):
        self.corp = "test-corp"
        self.owner = "zhangsan"
        self.uploads, self.creates = [], []
        self.create_error = self.upload_error = self.query_error = None
        self.after_upload = self.after_create = None
        self.receipts, self.record_list = [], []

    def corp_id(self):
        return self.corp

    def _identity(self, corp):
        if corp != self.corp:
            raise ApiError(409, "企业凭证已变化")

    def group(self, corp, chat):
        self._identity(corp)
        return {"groupName": "上海供应商开票群", "chatId": chat, "employee": "张三", "userid": self.owner}

    def upload(self, corp, name, content):
        self._identity(corp)
        if self.upload_error:
            raise self.upload_error
        self.uploads.append((name, content))
        if self.after_upload:
            self.after_upload()
        return "media-" + str(len(self.uploads))

    def create(self, corp, chat, sender, message, media):
        self._identity(corp)
        self.creates.append((corp, chat, sender, message, media))
        if self.after_create:
            self.after_create()
        if self.create_error:
            raise self.create_error
        return "msg-" + str(len(self.creates))

    def results(self, corp, msgid, sender):
        self._identity(corp)
        if self.query_error:
            raise self.query_error
        return self.receipts

    def records(self, corp, start, end):
        self._identity(corp)
        return self.record_list

    def members(self, corp, msgid):
        self._identity(corp)
        return [{"userid": self.owner}]

    def success(self, chat="wr001"):
        self.receipts = [
            {
                "chat_id": chat,
                "userid": self.owner,
                "status": 1,
                "send_time": int(datetime.now(UTC).timestamp()),
            }
        ]


@pytest.fixture
def delivery(engine, app_services, approved):
    task_id = approved["id"]
    prepare_all(app_services, task_id)
    app_services["groups"].save(
        GroupSave(supplierId=str(approved["supplier_id"]), chatId="wr001", revision=0, enabled=True), USER
    )
    app_services["notifications"].save_draft(task_id, draft(), USER)
    channel = Channel()
    settings = Settings(
        wecom_send_enabled=True,
        subpo_archive_root=app_services["tasks"].archive.root,
    )
    app_services["tasks"].settings = settings
    submissions = DeliverySubmitService(engine, settings, channel, app_services["tasks"])
    receipts = DeliveryReceiptService(engine, channel)
    return SimpleNamespace(
        task_id=task_id,
        channel=channel,
        settings=settings,
        submit=submissions,
        receipts=receipts,
        reconcile=DeliveryReconcileService(engine, channel, receipts),
        services=app_services,
    )


def request(delivery):
    preview = delivery.submit.preview(
        delivery.task_id, DeliveryPreviewRequest(revision=1, groupRevision=1), USER
    )
    return DeliverySubmitRequest(
        revision=preview.revision,
        groupRevision=preview.groupRevision,
        snapshotSha256=preview.snapshotSha256,
        requestId=uuid4().hex,
    )
