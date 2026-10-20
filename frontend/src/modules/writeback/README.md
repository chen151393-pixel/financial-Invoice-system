# NS 回写（前端）

## 职责

把已确认分配的进项发票登记到 NS“供应商发票勾选平台”对应的记录：选择发票 → 生成不可变预览 → 勾选核对后确认写入 → 查看结果或核实。页面只展示后端结果与 `allowed/reason`，不计算金额、不判断能否写入。

**当前状态：仅前端已实现，后端 `/api/writeback/*` 与 NS 端写入脚本尚未实现。** 接口返回 404“接口不存在”或 405 时，页面显示“NS 回写尚未接入”及限制说明，不显示示例数据，也不提供任何写入入口。

## 页面与路由

| 路径                    | 页面                             | 内容                                                                             |
| ----------------------- | -------------------------------- | -------------------------------------------------------------------------------- |
| `/writeback`            | `pages/WritebackListPage.tsx`    | 写入开关、查询条件、按状态筛选、发票列表与行操作、分页                           |
| `/writeback/:requestId` | `pages/WritebackRequestPage.tsx` | 状态头与操作；待确认时显示校验与明细，执行后显示 NS 记录、账单回读核实；执行记录 |

确认弹窗 `components/ConfirmDialog.tsx` 使用原生 `<dialog>`，打开聚焦、关闭返回触发按钮；勾选“我已核对”前不能提交。

## 主要文件

- `types.ts`：接口契约类型、状态筛选项、北京时间格式化。
- `api.ts`：经 `shared/api/http.ts` 调用；`isNotConnected` 区分“接口未登记”和“记录不存在”。
- `hooks/useWritebackList.ts`：按提交的条件读取列表，忽略过期响应。
- `hooks/useCreatePreview.ts`：生成预览；同一发票重试沿用同一请求编号。
- `hooks/useWritebackRequest.ts`：读取记录，执行中按后端 `poll` 轮询；执行、核实各提交一次，失败不自动重发。
- `components/`：状态标签、列表、查询条件、写入开关、状态头、概况、校验、明细、结果、执行记录、未接入说明。
- 样式：`writeback.css`（公共）、`writeback-list.css`、`writeback-request.css`、`writeback-dialog.css`，均限定 `wb-` 前缀。

## 计划中的接口契约（后端待实现）

| 方法与路径                                         | 请求                                                                     | 响应                                                                                    |
| -------------------------------------------------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------- |
| GET `/api/writeback/invoices`                      | `page`、`pageSize`、`phase`、`vendor`、`invoiceNo`、`dateFrom`、`dateTo` | `WritebackList`：`items`、分页、`counts`（各状态数量）、`write`（写入开关、账套、说明） |
| POST `/api/writeback/previews`                     | `{invoiceId, requestId}`                                                 | `WritebackRequest`；同一 `requestId` 重复提交返回原预览                                 |
| GET `/api/writeback/requests/{requestId}`          | —                                                                        | `WritebackRequest`                                                                      |
| POST `/api/writeback/requests/{requestId}/execute` | `{confirm: true}`                                                        | `WritebackRequest`；后端重新校验开关、有效期与账单锁                                    |
| POST `/api/writeback/requests/{requestId}/verify`  | `{}`                                                                     | `WritebackRequest`；按请求编号查询 NS，不重新提交                                       |

状态 `phase`：`ready` 可回写、`blocked` 不可回写、`pending` 待确认、`executing` 执行中、`unknown` 结果待核实、`failed` 失败（NS 未写入）、`succeeded` 已回写。字段定义见 `types.ts`；金额均为后端十进制字符串。

## 关键规则

- 能否生成预览、执行、核实、重新预览，全部以后端 `preview/execute/verify/refresh` 的 `allowed/reason` 为准，禁用时就近显示原因。
- 结果待核实时只提供“核实 NS 结果”，不提供重试；执行请求失败或响应丢失时提示刷新查看，不自动重发。
- “写入后已收”缺失显示“未回读”，不显示为 0；时间缺失显示“—”。

## 验证

在 `frontend/` 下运行 `npm.cmd run build`、`npm.cmd run lint`、`npm.cmd run typecheck`、`npm.cmd test`（含 `tests/writeback.test.mjs`）。接入后端前，只能验证“未接入”状态及组件在给定数据下的渲染。
