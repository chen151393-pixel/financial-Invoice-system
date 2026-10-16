"""手动界面验收入口：仅使用临时SQLite与合成来源，退出时自动清理。"""

from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from backend.app import create_app
from backend.core.config import load_settings
from backend.database import make_engine
from backend.integrations.contract_archive import ContractArchive
from backend.manage import upgrade
from backend.modules.reconciliation.dto import ApproveRequest, DeclarationListQuery, TaskListQuery
from backend.modules.reconciliation.group_entity import bindings
from backend.modules.reconciliation.service import ReconciliationService
from backend.modules.reconciliation.task_service import InvoiceTaskService
from backend.tests.conftest import FakeNS
from backend.tests.test_finance_list import OWNER, local_source
from backend.tests.test_invoice_tasks import seed_grouped_sources
from backend.tests.test_supplier_groups import FakeWecom
from backend.tests.test_task_documents import ContractSource


def main():
    with TemporaryDirectory(prefix="invoice-task-preview-") as temporary:
        root = Path(temporary)
        settings = load_settings(
            {
                "DATABASE_URL": f"sqlite:///{root / 'app.sqlite'}",
                "NETSUITE_ACCOUNT_ID": "test-preview",
                "LOCAL_BROWSER_ACCESS": "true",
                "APP_ORIGIN": "http://localhost:5181",
            }
        )
        upgrade(settings.database_url)
        engine = make_engine(settings.database_url)
        source_fixture = local_source.__wrapped__(root)
        source = next(source_fixture)
        try:
            seed_grouped_sources(source)
            bindings.create(source.engine)
            service = ReconciliationService(settings, None, engine, source)
            for keyword in ("CD001", "CD006-TEST"):
                group = service.browse(DeclarationListQuery(keyword=keyword), OWNER).groups[0]
                service.approve(ApproveRequest(snapshotId=group.snapshotId), OWNER)
            followup = InvoiceTaskService(engine, source, ContractSource(), ContractArchive(root))
            task = followup.browse(TaskListQuery(), OWNER).groups[0].tasks[0]
            for document in followup.detail(task.id, OWNER).documents:
                followup.prepare_document(task.id, document.orderId, OWNER)
            print(f"隔离任务：http://localhost:5181/invoice-followup/{task.id}#task-notification", flush=True)
            app = create_app(settings, FakeNS(settings), engine, source.engine, wecom=FakeWecom())
            uvicorn.run(app, host="127.0.0.1", port=5181, access_log=False)
        finally:
            source_fixture.close()
            source.engine.dispose()
            engine.dispose()


if __name__ == "__main__":
    main()
