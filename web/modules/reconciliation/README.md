# PL 采购报关核对

正式入口：`/pl-reconciliation`，首页 `/` 也进入本页。旧记录工作台及 PL 单联查页面已移除。旧 `/demo?view=pl` 自动转到该页面。已接入真实 NS REST 记录查询，复用后端 M2M 和现有身份校验，无额外角色白名单。

- `pages/PlReconciliationPage.tsx`：协调只读查询、加载、失败重试、重置及过期响应忽略。
- `api.ts`：通过 shared HTTP 调用 `POST /api/ns/pl-comparison`。
- `components/PlSearchForm.tsx`：收集完整 PL 单号及可选申报公司名称关键词或内部 ID。
- `components/PlComparison.tsx`：展示后端分组；报关在上、采购在下；导出当前响应中的 Excel。
- `types.ts`：固定 15 列和查询结果契约；局部 CSS 复用设计变量与公共按钮。
- `web/app/PlWorkspacePage.tsx`：装配全站 AppFrame、统一导航与本业务页面。

公司筛选、归组及 Excel 均由后端 business 模块负责。本页不计算金额、不做商品自动匹配，不直接访问 NS，也不保存数据库或回写 NS。金额保留来源币种；缺失币种显示“未返回币种”；含税单价统一“待确认”。Excel 包含合并核对和来源明细，范围与页面本次查询一致。

当前数据来自自定义记录 REST 接口；尚未接入保存搜索 839/954，不能将源明细称为搜索 GROUP/MAX/SUM 汇总。读取过程中 NS 数据可能变化；本次响应及导出一致，但不是 NS 跨记录事务快照。配置和接口见 [PL 查询说明](../../../docs/pl-lookup.md)。

验证：前端构建、类型、lint、架构检查，后端 `test_pl_comparison.py`；浏览器检查真实查询、加载、无结果、错误、重置、导出及窄屏布局。
