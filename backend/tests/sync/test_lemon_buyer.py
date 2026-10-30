"""柠檬云进项票购买方取账套名称：新票填写，已入库且未变化的票不换版。"""

from backend.modules.invoice.entity import headers, versions
from backend.modules.matching.policy.comparison_policy import buyer_note
from backend.tests.sync.test_lemon_invoices import BASE, body, count, invoice
from backend.tests.sync.test_lemon_invoices import setup as setup
from sqlalchemy import select, update


def buyer(engine):
    with engine.connect() as connection:
        return connection.execute(select(headers.c.buyer_name, headers.c.buyer_name_normalized)).one()


def pull(setup):
    response = setup.client.post(BASE + "/invoices/pull-save", json=body())
    assert response.status_code == 200
    return response.json()["result"]


def test_new_invoice_buyer_is_account_name(setup):
    assert pull(setup)["created"] == 1
    # 假上游账套 7 的名称为“测试账套”
    assert buyer(setup.engine) == ("测试账套", "测试账套")
    assert pull(setup)["unchanged"] == 1
    assert count(setup.engine, versions) == 1


def test_saved_invoice_without_buyer_is_not_reversioned(setup):
    assert pull(setup)["created"] == 1
    # 模拟购买方规则上线前入库的票
    with setup.engine.begin() as connection:
        connection.execute(update(headers).values(buyer_name=None, buyer_name_normalized=None))
    assert pull(setup)["unchanged"] == 1
    assert count(setup.engine, versions) == 1
    assert buyer(setup.engine) == (None, None)
    # 票据内容本身变化时换版，同时补上购买方
    setup.upstream.rows = [invoice(Note="改了备注")]
    assert pull(setup)["updated"] == 1
    assert count(setup.engine, versions) == 2
    assert buyer(setup.engine)[0] == "测试账套"


def test_buyer_note_names_its_source():
    assert buyer_note({"buyer_name": None, "lemon_account": "open2:x"}) == "发票未提供购买方"
    assert buyer_note({"buyer_name": "公司", "lemon_account": "open2:x"}) == "购买方取自柠檬云账套名称"
    assert buyer_note({"buyer_name": "公司", "lemon_account": "professional:x"}) == "购买方取自柠檬云账套名称"
    assert buyer_note({"buyer_name": "公司", "lemon_account": "lemon"}) == ""
