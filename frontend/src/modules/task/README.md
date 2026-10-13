# 开票跟进页面

架构 v2 第 4c 步由 `reconciliation` 移出，改用 task 模块新接口。后端规则见[后端 task 模块](../../../../backend/modules/task/README.md)。

| 路径                     | 页面                                                                    |
| ------------------------ | ----------------------------------------------------------------------- |
| `/tasks`                 | `pages/TaskListPage.tsx`：按供应商 / 按报关单分组、搜索、版本筛选、分页 |
| `/tasks/:id`             | `pages/TaskDetailPage.tsx`：六节点流程、合同、通知、流转记录            |
| `/tasks/supplier-groups` | `pages/SupplierGroupsPage.tsx`：供应商默认企微群                        |

旧地址 `/invoice-followup`、`/invoice-followup/supplier-groups` 跳转到新地址；旧任务详情地址跳转到任务列表（旧任务不迁移）。外壳在 `app/TaskWorkspacePage.tsx`。

## 文件

| 目录          | 内容                                                                                                                                                                                                                                    |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `api/`        | `task.ts`（列表、详情、保存合同、通知草稿、登记发送）、`supplier-group.ts`                                                                                                                                                              |
| `types/`      | 与后端 VO 一致的类型；金额、数量为字符串                                                                                                                                                                                                |
| `components/` | `TaskGroupTable`、`TaskOverview`、`TaskDocuments`、`TaskLines`、`TaskHistory`、`TaskNotification`（含 `NotificationDialog`、`NotificationRecordForm`、`NotificationHistory`）、`SupplierGroupEditor`、`WecomGroupPicker`、`GroupLookup` |

组件不直接调用接口：请求函数由页面传入（通知保存与登记、供应商与企微群查询、群配置保存）。时间统一按北京时间显示（`components/format.ts`）。

## 规则

- 按钮可用与原因只来自后端 `allowed/reason`；状态文案、应开金额合计由后端返回。
- 收票统计与比对在发票比对接入（第 4d 步）前显示“未接入”，不显示 0。
- 合同保存、通知登记失败时显示后端真实错误，不自动重试。

## 验证

`npm.cmd run build`、`npm.cmd run lint`、`npm.cmd run typecheck`、`npm.cmd run check:architecture`。2026-10-13 在本地隔离 SQLite（合成数据，假企微）上做浏览器检查：财务核对审核通过后任务出现在列表、旧地址跳转、详情六节点与合同不可保存原因、供应商群新增并带入通知、保存通知版本、流转记录、375px 窄屏无页面横向滚动。合同实际下载与共享盘写入只由后端测试覆盖，未连接真实 NS、企微与共享盘。
