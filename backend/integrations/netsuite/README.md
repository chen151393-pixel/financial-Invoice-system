# NetSuite 适配器

`auth.py`生成M2M签名；`client.py`维护Token缓存、HTTP请求、目标类型许可、超时与响应解析。保留现有SuiteTalk协议，不修改业务字段映射。

通过构造函数注入HTTPX客户端；测试使用MockTransport/FakeNS。此目录不判断用户审批或匹配金额，不自行重试写入。身份、字段许可和执行状态由业务模块再次校验。

验证：`npm.cmd run test:api` 中的签名、缓存、重定向与超时用例。
