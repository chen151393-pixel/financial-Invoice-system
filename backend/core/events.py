"""进程内同步事件总线（后端规则第 5.2 节）。

- 事件契约（不可变数据类）定义在发布方模块的 public.py 中；订阅关系只在 app.py 中登记。
- publish 在发布方的数据库事务中同步执行全部订阅方，订阅方使用同一个 connection；
  任一订阅方抛出异常，异常原样向上传递，由发布方的事务整体回滚。
- 订阅方不能调用外部系统、不能开启新事务。
"""

from collections import defaultdict


class EventBus:
    def __init__(self):
        self._handlers = defaultdict(list)

    def subscribe(self, event_type, handler):
        """登记订阅；同一处理函数对同一事件只能登记一次，避免重复执行。"""
        if handler in self._handlers[event_type]:
            raise ValueError(f"{event_type.__name__} 已登记该订阅方")
        self._handlers[event_type].append(handler)

    def publish(self, connection, event):
        """按登记顺序执行订阅方；必须在发布方已开启的事务中调用。"""
        if not connection.in_transaction():
            raise RuntimeError("事件必须在发布方的数据库事务中发布")
        for handler in self._handlers[type(event)]:
            handler(connection, event)
