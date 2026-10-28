# NS 回写准备页面

`/writeback` 为真实任务列表，`/writeback/:requestId` 显示准备任务详情。沿用既有路由参数名，值为后端任务 ID。

- 列表由后端搜索、筛选和分页；状态、原因和允许动作由后端返回。
- 详情展示审核分配、候选账单、目标方案和审计记录。金额保持十进制字符串。
- 人工确认支持多账单拆分、归属依据和实际 NS 子公司核实。请求携带当前 revision 与稳定 requestId；失败不伪装成功、不自动重试确认。
- 匹配发票详情通过公开 API 显示整票就绪原因和当前任务链接；可重新检查历史发票。
- 已删除原手工预览/执行演示 API、demo1/demo2 数据与不再引用的旧组件和样式。历史演示 URL 不再有模拟成功行为。
- NS 写入尚未实现，方案确认不代表回写成功。页面无 execute/apply 按钮或调用。

接口与部署见 [后端模块](../../../../backend/modules/writeback/README.md)、[部署说明](../../../../docs/ns-writeback-prepare.md)。验证：前端 lint、typecheck、build，`tests/writeback.test.mjs` 覆盖实际接口参数、错误与关键状态展示。
