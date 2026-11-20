"""香港中转工作区：阶段、冻结金额、筛选分页与只读隔离。"""

import csv
import io
from datetime import date, datetime
from decimal import Decimal

import pytest
from backend.core.dependencies import current_owner
from backend.core.errors import ApiError
from backend.modules.settlement.controller.hk_workbench_controller import create_router
from backend.modules.settlement.dao import batch_dao
from backend.modules.settlement.dto.hk_workbench_dto import HkReceiptPreview, HkWorkbenchQuery
from backend.modules.settlement.entity.batch import settlement_batches
from backend.modules.settlement.service.document_reader import DocumentReader
from backend.modules.settlement.service.hk_workbench_service import HkWorkbenchService
from backend.tests.settlement.test_settlement_batches import create, legacy_direct_batch, services
from backend.tests.settlement.test_settlement_batches import seeded as seeded
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import ns as ns
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select

TODAY = date(2026, 12, 20)


def workbench(engine):
    candidates, _ = services(engine)
    return HkWorkbenchService(
        engine, candidates, DocumentReader(), fee_alert=Decimal("50"), today=lambda: TODAY
    )


def test_workbench_combines_pending_and_batch_without_double_counting(seeded):
    _, batches = services(seeded)
    batch = create(batches, ["REAL870"], "590", fee="10", receivedReference="HSBC-LOOKUP")
    legacy_direct_batch(seeded)
    service = workbench(seeded)
    with seeded.connect() as c:
        before = c.scalar(select(func.count()).select_from(settlement_batches))
    result = service.query(HkWorkbenchQuery())
    assert result.pendingTotal == 1 and result.pending[0].declarationNo == "REAL871"
    assert result.pending[0].amount == "400.50" and result.pending[0].select.allowed
    assert result.batchTotal == 1 and result.batches[0].batch.id == batch.id
    assert result.batches[0].batch.declaredTotal == "600.00"
    assert result.batches[0].primaryAction == "documents"
    assert result.batches[0].issue and not result.batches[0].package.allowed
    assert not result.batches[0].batch.actions.documentsReady.allowed
    assert {stage.key: stage.value for stage in result.stages}["open"] == "1 票 · 1 批"
    assert result.asOf == "2026-12-20"
    found = service.query(HkWorkbenchQuery(keyword="hsbc-lookup"))
    assert found.batchTotal == 1 and found.pendingTotal == 0
    assert service.query(HkWorkbenchQuery(keyword="REAL871")).pendingTotal == 1
    assert service.query(HkWorkbenchQuery(keyword="REAL870")).batchTotal == 1
    assert service.query(HkWorkbenchQuery(consignee="ACME")).batchTotal == 0
    assert service.query(HkWorkbenchQuery(stage="register")).batchTotal == 0
    assert service.query(HkWorkbenchQuery(stage="settled")).batchTotal == 0
    assert service.query(HkWorkbenchQuery(page=999, pendingPage=999)).page == 1
    with seeded.connect() as c:
        assert c.scalar(select(func.count()).select_from(settlement_batches)) == before


def test_ready_overdue_settled_and_cancelled_filters(seeded):
    _, batches = services(seeded)
    first = create(batches, ["REAL870"], "600")
    second = create(batches, ["REAL871"], "400.5")
    with seeded.begin() as c:
        batch_dao.update_batch(
            c,
            first.id,
            {
                "status": "documents_ready",
                "received_on": date(2026, 11, 1),
                "documents_ready_at": datetime(2026, 11, 3),
            },
            datetime(2026, 11, 3),
        )
        batch_dao.update_batch(
            c,
            second.id,
            {
                "status": "settled",
                "remitted_on": date(2026, 11, 12),
                "remitted_amount": Decimal("400.5"),
                "remitted_fee": Decimal("0"),
            },
            datetime(2026, 11, 12),
        )
    service = workbench(seeded)
    ready = service.query(HkWorkbenchQuery(stage="documents_ready"))
    assert ready.batchTotal == 1 and ready.batches[0].overdue
    assert ready.batches[0].waitingLabel == "滞留香港 49 天"
    assert ready.batches[0].steps[-1].state == "current"
    settled = service.query(HkWorkbenchQuery(stage="settled"))
    assert settled.batches[0].waitingLabel == "2026-11-12 结汇"
    assert not settled.batches[0].overdue
    assert all(step.state == "done" for step in settled.batches[0].steps)
    assert service.query(HkWorkbenchQuery()).batchTotal == 1
    assert service.query(HkWorkbenchQuery(stage="all", pageSize=1, page=2)).pageCount == 2


def test_workbench_http_is_read_only_and_serves_real_counts(seeded):
    app = FastAPI()
    app.include_router(create_router(workbench(seeded)))
    app.dependency_overrides[current_owner] = lambda: "service:validation"
    client = TestClient(app)
    result = client.post("/api/settlement/hk-workbench/query", json={})
    assert result.status_code == 200
    assert result.json()["pendingTotal"] == 2 and result.json()["batchTotal"] == 0
    assert client.post("/api/settlement/hk-workbench/query", json={"stage": "made-up"}).status_code == 422


def test_receipt_preview_uses_server_totals_and_does_not_write(seeded):
    service = workbench(seeded)
    checked = service.preview(
        HkReceiptPreview(declarationNos=["REAL870", "REAL871"], receivedAmount="1,000.50")
    )
    assert checked.declaredTotal == "1000.50" and checked.arrivedTotal == "1000.50"
    assert checked.balanced and checked.submit.allowed and checked.difference == "0.00"
    partial = service.preview(
        HkReceiptPreview(declarationNos=["REAL870"], receivedAmount="500", receivedFee="1")
    )
    assert not partial.balanced and partial.submit.allowed  # 沿用既有允许登记实际到账的规则。
    blank = service.preview(HkReceiptPreview(declarationNos=["REAL870"]))
    assert not blank.submit.allowed
    with pytest.raises(ApiError, match="直接收汇"):
        service.preview(HkReceiptPreview(declarationNos=["REAL870", "REAL872"], receivedAmount="1600"))
    with pytest.raises(ValidationError):
        HkReceiptPreview(declarationNos=["REAL870", "REAL870"], receivedAmount="1200")
    with seeded.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(settlement_batches)) == 0


def test_export_is_not_limited_to_the_displayed_page_and_escapes_formulas(seeded):
    _, batches = services(seeded)
    create(batches, ["REAL870"], "600", receivedReference="=HYPERLINK(test)")
    create(batches, ["REAL871"], "400.50")
    service = workbench(seeded)
    report = service.export(HkWorkbenchQuery(stage="all", pageSize=1, page=2))
    assert report.content.startswith("\ufeff")
    rows = list(csv.reader(io.StringIO(report.content.lstrip("\ufeff"))))
    assert len(rows) == 3
    assert any(row[-1] == "'=HYPERLINK(test)" for row in rows[1:])
    assert (
        len(list(csv.reader(io.StringIO(service.export(HkWorkbenchQuery(keyword="REAL870")).content)))) == 2
    )
