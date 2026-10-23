# 财务核对页面

`/review`（旧地址 `/finance-reconciliation` 自动跳转）。架构 v2 第 4b 步由 `reconciliation` 移出，改用 review 模块新接口。后端规则见[后端 review 模块](../../../../backend/modules/review/README.md)。

## 文件

| 文件                                                                  | 说明                                                                                                    |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `pages/ReviewPage.tsx`                                                | 打开即读取已入库报关单；搜索、账套、供应商、状态筛选、分页、刷新；单张与批量审核；忽略过期响应          |
| `components/FinanceSearchForm.tsx`                                    | 关键字、账套与供应商查询（供应商选项由后端返回）                                                        |
| `components/FinanceComparison.tsx`                                    | 报关单列表：状态筛选、全部展开/收起、当前页勾选与批量审核入口                                           |
| `components/DeclarationRow.tsx`                                       | 第一层报关单行：勾选（仅后端允许审核的）、状态、单张审核入口                                            |
| `components/CustomsRows.tsx`、`PurchaseRows.tsx`、`review-levels.css` | 第二层报关行、第三层子采购行：逐级缩进并以竖线标示从属，列宽只在同一层内对齐                            |
| `components/BatchApproveDialog.tsx`                                   | 批量审核确认（范围为当前页已选）与逐张结果                                                              |
| `components/ReviewDialog.tsx`                                         | 整单审核确认、审核备注、审核记录与子采购只读详情                                                        |
| `api.ts`                                                              | `POST /api/review/declarations/query`；`/{id}/approve`（提交 `contentSha256` 与备注）；`/approve-batch` |
| `types.ts`                                                            | 后端 VO；数量与金额为十进制字符串，前端不重算                                                           |

外壳复用 AppFrame、Button、Pagination；路由在 `app/router.tsx`，路径在 `app/paths.ts`。

## 规则

- 子采购行显示开票口径：采购数量、采购单位、含税金额；报关数量在说明中显示。
- 能否审核、状态、计数、筛选和分页均由后端返回；按钮使用后端 `allowed/reason`，点击后后端重新校验。
- 来源在页面打开后变化时，后端拒绝审核并提示刷新；页面显示真实错误，不自动重发。
- 未出库（缺真实报关单号或无子采购单）的报关单自 2026-10-23 起拉取时即跳过，页面不再提供"未出库"筛选。
- 批量审核只提交当前页已勾选的报关单，窗口写明范围；结果按后端返回逐张展示，跳过的显示原因，完成后重新读取列表。
- 第 4c 步接入开票任务前，审核通过只保存审核记录与冻结行，不生成任务；页面说明已标明。

## 验证

`npm.cmd run build`、`npm.cmd run lint`、`npm.cmd run typecheck`、`npm.cmd run test:web`。2026-10-12 在本地隔离 SQLite（合成数据）上做浏览器检查：列表、逐级展开、开票口径显示、金额缺失行、整单审核与记录查看、状态计数、待审核筛选、375px 窄屏无页面横向滚动。未连接真实 NS 与 MySQL。

2026-10-22 在本地隔离 SQLite（合成数据）上复查：供应商筛选、未出库筛选及说明、三级缩进展开、当前页勾选与批量审核（结果窗口、列表自动刷新）、工作台未出库提示、375px 窄屏无页面横向滚动。未连接真实 NS 与 MySQL。

## 申报幅度（2026-10-23）

报关行最后一列“申报幅度”显示后端计算值及“申报 / 采购”人民币金额；负数标注“采购价高于申报价”，无法计算时显示“—”及原因，不显示 0。
