"""资料归集与任务完结（2026-10-23）：报关资料 NS 下载与单项重试、回签合同批量上传、资料齐全才完结。

SQLite 隔离库；source 与 review 真实保存，NS 下载用假实现，共享盘为临时目录。
"""

import base64
import json
from pathlib import Path

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.modules.matching.dto.matching_dto import ConfirmBody
from backend.modules.source.public import SourceDirectory
from backend.modules.task.dto.signed_contract_dto import SignedContractUpload
from backend.modules.task.service.contract_worker import ContractWorker
from backend.modules.task.service.declaration_document_service import DeclarationDocumentService
from backend.modules.task.service.progress_service import refresh_tasks
from backend.modules.task.service.signed_contract_service import SignedContractService
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import FLUID, INK, import_invoices, invoice_id, proposals
from backend.tests.test_matching import world as world  # 共用夹具
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_source_storage import engine as engine  # 共用夹具
from backend.tests.test_source_storage import ns as ns  # 共用夹具
from backend.tests.test_task import USER, approve, task_rows
from backend.tests.test_task import app_services as app_services  # 共用夹具
from fastapi.testclient import TestClient

PDF = b"%PDF-1.4\nsigned\n%%EOF"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


@pytest.fixture
def services(engine, app_services):
    directory = SourceDirectory(engine)
    tasks = app_services["tasks"]
    declarations = DeclarationDocumentService(engine, directory, tasks.contracts, tasks.archive, tasks)
    return {
        **app_services,
        "declarations": declarations,
        "signed": SignedContractService(engine, directory, tasks.archive),
        "worker": ContractWorker(engine, app_services["documents"], declarations),
    }


@pytest.fixture
def approved(ns, engine, services):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    approve(services, "CD870")
    return task_rows(engine)[0]


def declaration_rows(engine):
    # 原生 SQL 读取时 SQLite 把 JSON 列返回为字符串
    return {
        row["doc_type"]: {
            **row,
            "files": json.loads(row["files"]) if isinstance(row["files"], str) else row["files"],
        }
        for row in rows(engine, "SELECT * FROM task_declaration_documents ORDER BY doc_type")
    }


def upload(services, files, actor=USER):
    body = SignedContractUpload(
        files=[
            {"filename": name, "content": base64.b64encode(content).decode(), "orderNo": order}
            for name, content, order in files
        ]
    )
    return services["signed"].upload(body, actor).items


def status(engine):
    return task_rows(engine)[-1]["status"]


def test_approval_registers_declaration_documents_and_worker_archives_them(engine, services, approved):
    assert {key: row["status"] for key, row in declaration_rows(engine).items()} == {
        "customs_declaration": "pending",
        "invoice": "pending",
        "sales_contract": "pending",
    }
    services["worker"].run_once()
    found = declaration_rows(engine)
    assert all(row["status"] == "archived" and row["attempts"] == 1 for row in found.values())
    contracts = services["contracts"]
    assert sorted(call[2] for call in contracts.declaration_calls) == [
        "customs_declaration",
        "invoice",
        "sales_contract",
    ]
    assert all(call[:2] == ("CD870", "REAL870") for call in contracts.declaration_calls)
    path = Path(found["customs_declaration"]["files"][0]["path"])
    assert path.name == "报关单_CD870.pdf"
    assert path.parent.name == "CD870_REAL870" and path.parent.parent.name == "2026年09月"
    assert path.read_bytes() == contracts.content
    # 子采购合同也在同一报关单文件夹
    sub = rows(engine, "SELECT archive_path FROM task_documents")[0]["archive_path"]
    assert Path(sub).parent == path.parent


def test_failed_declaration_document_does_not_block_notification_and_can_be_retried(
    engine, services, approved
):
    contracts = services["contracts"]
    contracts.declaration_files["invoice"] = ApiError(404, "NS 中暂无该报关单的发票文件，请在 NS 补齐后重试")
    services["worker"].run_once()
    found = declaration_rows(engine)
    assert found["invoice"]["status"] == "failed" and "暂无" in found["invoice"]["error_message"]
    assert found["customs_declaration"]["status"] == "archived"
    assert status(engine) == "notify_pending"  # 报关资料失败不影响通知供应商
    detail = services["tasks"].detail(approved["id"])
    invoice_doc = next(doc for doc in detail.declarationDocuments if doc.type == "invoice")
    assert invoice_doc.status == "failed" and invoice_doc.retry.allowed and "暂无" in invoice_doc.error
    assert "发票" in detail.completion.missing and not detail.completion.ready
    # 失败后不会被后台自动重复下载；人工单项重试，可重复多次
    services["worker"].run_once()
    assert declaration_rows(engine)["invoice"]["attempts"] == 1
    with pytest.raises(ApiError):
        services["declarations"].retry(approved["id"], "invoice", USER)
    contracts.declaration_files["invoice"] = [PDF, PDF + b" "]
    detail = services["declarations"].retry(approved["id"], "invoice", USER)
    invoice_doc = next(doc for doc in detail.declarationDocuments if doc.type == "invoice")
    assert invoice_doc.status == "archived" and [f.filename for f in invoice_doc.files] == [
        "发票_CD870_1.pdf",
        "发票_CD870_2.pdf",
    ]
    assert declaration_rows(engine)["invoice"]["attempts"] == 3


def test_redownload_of_archived_document_never_overwrites_changed_file(engine, services, approved):
    services["worker"].run_once()
    services["declarations"].retry(approved["id"], "sales_contract", USER)  # 内容相同：重复下载无变化
    services["contracts"].declaration_files["sales_contract"] = [PDF]
    with pytest.raises(ApiError, match="同名但内容不同") as error:
        services["declarations"].retry(approved["id"], "sales_contract", USER)
    assert error.value.status == 409
    assert declaration_rows(engine)["sales_contract"]["status"] == "archived"
    with pytest.raises(ApiError) as error:
        services["declarations"].retry(approved["id"], "sales_contract", "service:feishu")
    assert error.value.status == 403


def test_unconfigured_interface_is_recorded_and_shown(engine, services, approved):
    services["contracts"].declaration_reason = "报关资料下载接口尚未配置"
    services["worker"].run_once()
    assert {row["error_message"] for row in declaration_rows(engine).values()} == {"报关资料下载接口尚未配置"}
    detail = services["tasks"].detail(approved["id"])
    assert all(
        not doc.retry.allowed and doc.retry.reason == "报关资料下载接口尚未配置"
        for doc in detail.declarationDocuments
    )


def test_signed_contract_upload_matches_filename_and_refuses_guessing(ns, engine, services, approved):
    items = upload(
        services,
        [
            ("SUB-200 回签.pdf", PDF, ""),
            ("扫描件.pdf", PDF, ""),
            ("手工指定.png", PNG, "SUB-999"),
            ("SUB-200.txt", b"plain text", ""),
        ],
    )
    assert [(item.status, item.orderNumber) for item in items] == [
        ("saved", "SUB-200"),
        ("unmatched", ""),
        ("unmatched", "SUB-999"),
        ("failed", ""),
    ]
    path = Path(items[0].archivePath)
    assert path.name == "回签合同_SUB-200.pdf" and path.parent.name == "CD870_REAL870"
    assert "未能从文件名识别" in items[1].reason and "仅支持" in items[3].reason
    again = upload(services, [("任意名称.pdf", PDF, "SUB-200"), ("SUB-200-新版.pdf", PDF + b" ", "")])
    assert again[0].status == "saved" and "相同文件" in again[0].reason
    assert again[1].status == "conflict" and path.read_bytes() == PDF
    with pytest.raises(ApiError) as error:
        upload(services, [("SUB-200.pdf", PDF, "")], actor="service:feishu")
    assert error.value.status == 403


def test_ambiguous_filename_needs_order_number(ns, engine, services):
    save(ns, engine, bundle([purchase("200", "870"), purchase("201", "870")], [customs("870")]))
    items = upload(services, [("SUB-200与SUB-201合并.pdf", PDF, "")])
    assert items[0].status == "ambiguous" and "SUB-200、SUB-201" in items[0].reason


def test_completion_requires_invoices_and_all_documents(engine, services, world, approved):
    import_invoices(world, [invoice("26000000000000006601", [INK, FLUID], remark="SUB-200")])
    for proposal in proposals(world, invoice_id(engine, "26000000000000006601")):
        world["allocations"].confirm(int(proposal.id), ConfirmBody(), USER)
    assert status(engine) == "documents_incomplete"
    services["worker"].run_once()  # 子采购合同与报关资料归档
    assert status(engine) == "documents_incomplete"
    detail = services["tasks"].detail(approved["id"])
    assert detail.completion.missing == ["回签合同"]
    assert [contract.uploaded for contract in detail.signedContracts] == [False]
    upload(services, [("SUB-200.pdf", PDF, "")])  # 最后一份资料到齐：自动完结
    done = task_rows(engine)[-1]
    assert done["status"] == "completed" and done["completed_at"] is not None
    events = [row["to_status"] for row in rows(engine, "SELECT to_status FROM task_events ORDER BY id")]
    assert events[-2:] == ["documents_incomplete", "completed"]


def test_tasks_completed_before_the_rule_are_not_reverted(engine, services, world, approved):
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE task_lines SET status = 'received'")
        connection.exec_driver_sql("UPDATE task_tasks SET status = 'completed'")
    with engine.begin() as connection:
        refresh_tasks(connection, [approved["id"]], USER, "测试", None)
    assert status(engine) == "completed"


def test_http_upload_and_retry_routes(context, ns, engine, tmp_path):
    from dataclasses import replace

    save(ns, engine, bundle([purchase()], [customs("870")]))
    settings = replace(context.settings, subpo_archive_root=tmp_path)
    app = create_app(settings, context.ns, engine)
    with TestClient(app) as client:
        path = "/api/tasks/signed-contracts/upload"
        assert client.post(path, json={"files": []}).status_code == 401
        headers = {"Origin": settings.origin}
        login = client.post(
            "/api/session", headers=headers, json={"username": "admin", "password": settings.admin_password}
        )
        assert login.status_code == 200
        assert client.post(path, json={"files": []}, headers=headers).status_code == 400
        item = client.post("/api/review/declarations/query", json={}, headers=headers).json()["groups"][0]
        client.post(
            f"/api/review/declarations/{item['id']}/approve",
            json={"contentSha256": item["contentSha256"]},
            headers=headers,
        )
        body = {"files": [{"filename": "SUB-200.pdf", "content": base64.b64encode(PDF).decode()}]}
        result = client.post(path, json=body, headers=headers)
        assert result.status_code == 200 and result.json()["items"][0]["status"] == "saved"
        task_id = client.post("/api/tasks/query", json={}, headers=headers).json()["groups"][0]["tasks"][0][
            "id"
        ]
        bad = client.post(
            f"/api/tasks/{task_id}/declaration-documents/unknown/prepare", json={}, headers=headers
        )
        assert bad.status_code in (400, 404, 422)
        retry = client.post(
            f"/api/tasks/{task_id}/declaration-documents/invoice/prepare", json={}, headers=headers
        )
        assert retry.status_code == 503  # 测试环境未配置报关资料接口，返回真实原因
        detail = client.get(f"/api/tasks/{task_id}", headers=headers).json()
        assert [doc["type"] for doc in detail["declarationDocuments"]] == [
            "customs_declaration",
            "sales_contract",
            "invoice",
        ]
        assert detail["signedContracts"][0]["uploaded"] is True
