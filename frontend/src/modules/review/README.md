# 财务核对页面

`/review`（旧地址 `/finance-reconciliation` 自动跳转）。架构 v2 第 4b 步由 `reconciliation` 移出，改用 review 模块新接口。后端规则见[后端 review 模块](../../../../backend/modules/review/README.md)。

## 文件

| 文件                                                                  | 说明                                                                                                               |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `pages/ReviewPage.tsx`                                                | 打开即读取已入库报关单；搜索、账套、状态筛选、分页、刷新；忽略过期响应                                             |
| `components/FinanceSearchForm.tsx`                                    | 关键字与账套查询                                                                                                   |
| `components/FinanceComparison.tsx`                                    | 报关单列表：主单 → 报关行 → 子采购行逐级展开，全部展开/收起                                                        |
| `components/CustomsRows.tsx`、`PurchaseRows.tsx`、`DetailColumns.tsx` | 报关明细与子采购明细，共用列宽                                                                                     |
| `components/ReviewDialog.tsx`                                         | 整单审核确认、审核备注、审核记录与子采购只读详情                                                                   |
| `api.ts`                                                              | `POST /api/review/declarations/query`；`POST /api/review/declarations/{id}/approve`（提交 `contentSha256` 与备注） |
| `types.ts`                                                            | 后端 VO；数量与金额为十进制字符串，前端不重算                                                                      |

外壳复用 AppFrame、Button、Pagination；路由在 `app/router.tsx`，路径在 `app/paths.ts`。

## 规则

- 子采购行显示开票口径：采购数量、采购单位、含税金额；报关数量在说明中显示。
- 能否审核、状态、计数、筛选和分页均由后端返回；按钮使用后端 `allowed/reason`，点击后后端重新校验。
- 来源在页面打开后变化时，后端拒绝审核并提示刷新；页面显示真实错误，不自动重发。
- 第 4c 步接入开票任务前，审核通过只保存审核记录与冻结行，不生成任务；页面说明已标明。

## 验证

`npm.cmd run build`、`npm.cmd run lint`、`npm.cmd run typecheck`、`npm.cmd run test:web`。2026-10-12 在本地隔离 SQLite（合成数据）上做浏览器检查：列表、逐级展开、开票口径显示、金额缺失行、整单审核与记录查看、状态计数、待审核筛选、375px 窄屏无页面横向滚动。未连接真实 NS 与 MySQL。
