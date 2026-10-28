"""采购开票任务台接口：按当前节点汇总任务并逐个展示六个节点，只读。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.task_dto import TaskBoardQuery
from ..vo.task_vo import TaskBoard


def create_router(board):
    router = APIRouter(tags=["采购开票任务台"])

    # 旧客户端保留一版兼容；升级到 /api/task/board/query 后删除旧入口。
    @router.post("/api/tasks/board/query", response_model=TaskBoard, include_in_schema=False)
    @router.post("/api/task/board/query", response_model=TaskBoard)
    def query(body: TaskBoardQuery, owner: Owner):
        return board.browse(body)

    return router
