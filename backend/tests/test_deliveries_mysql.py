"""多实例并发只能在专用 MySQL 测试库验收；没有配置时明确跳过。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from backend.core.errors import ApiError
from backend.modules.task.service.delivery_submit_service import DeliverySubmitService
from backend.tests.delivery_fixtures import delivery as delivery
from backend.tests.delivery_fixtures import request
from backend.tests.test_delivery_boundaries import second_task
from backend.tests.test_matching_mysql import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_task import USER
from backend.tests.test_task import app_services as app_services
from backend.tests.test_task import approved as approved


@pytest.mark.parametrize("same_task", [True, False])
def test_two_instances_cannot_duplicate_create(delivery, ns, engine, same_task):
    body = request(delivery)
    other = delivery if same_task else second_task(delivery, ns, engine)
    other_body = body if same_task else request(other)
    entered, finish = Event(), Event()
    original = delivery.channel.upload

    def upload(*args):
        entered.set()
        assert finish.wait(30)
        return original(*args)

    delivery.channel.upload = upload
    second = DeliverySubmitService(
        delivery.submit.engine, delivery.settings, delivery.channel, delivery.services["tasks"]
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(delivery.submit.submit, delivery.task_id, body, USER)
        try:
            assert entered.wait(20)
            if same_task:
                replay = second.submit(delivery.task_id, body, USER)
                assert replay.status == "preparing"
                with pytest.raises(ApiError, match="未决"):
                    second.submit(
                        delivery.task_id, body.model_copy(update={"requestId": "different-request"}), USER
                    )
            else:
                with pytest.raises(ApiError, match="客户群有未决"):
                    second.submit(other.task_id, other_body, USER)
        finally:
            finish.set()
        result = first.result(timeout=30)
    assert result.status == "pending_confirmation" and len(delivery.channel.creates) == 1
