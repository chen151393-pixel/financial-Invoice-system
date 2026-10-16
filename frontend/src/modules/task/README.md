# 开票跟进页面

架构 v2 第 4c 步由 `reconciliation` 移出，改用 task 模块新接口。后端规则见[后端 task 模块](../../../../backend/modules/task/README.md)。

| 路径         | 页面                                                                    |
| ------------ | ----------------------------------------------------------------------- |
| `/tasks`     | `pages/TaskListPage.tsx`：按供应商 / 按报关单分组、搜索、版本筛选、分页 |
| `/tasks/:id` | `pages/TaskDetailPage.tsx`：六节点流程、合同、通知、流转记录            |
| `/suppliers` | `pages/SupplierGroupsPage.tsx`：供应商档案：已同步供应商及默认企微群    |

旧地址 `/invoice-followup`、`/invoice-followup/supplier-groups` 跳转到新地址；旧任务详情地址跳转到任务列表（旧任务不迁移）。外壳在 `app/TaskWorkspacePage.tsx`。

## 文件

| 目录          | 内容                                                                                                                                                                                                                     |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `api/`        | `task.ts`（列表、详情、保存合同、通知草稿、登记发送）、`supplier-group.ts`                                                                                                                                               |
| `types/`      | 与后端 VO 一致的类型；金额、数量为字符串                                                                                                                                                                                 |
| `components/` | `TaskGroupTable`、`TaskOverview`、`TaskDocuments`、`TaskLines`、`TaskHistory`、`TaskNotification`（含 `NotificationDialog`、`NotificationRecordForm`、`NotificationHistory`）、`SupplierGroupEditor`、`WecomGroupPicker` |

组件不直接调用接口：请求函数由页面传入（通知保存与登记、供应商与企微群查询、群配置保存）。时间统一按北京时间显示（`components/format.ts`）。

## 规则

- 按钮可用与原因只来自后端 `allowed/reason`；状态文案、应开金额合计由后端返回。
- 列表统计显示待开票、已完成、待处理任务数；收票进度（应开明细中的已收数量与金额）由发票比对通过的分配汇总，详情页“等待收票”展示、“比对结果”链接到比对审核队列。
- 合同保存、通知登记失败时显示后端真实错误，不自动重试。

## 验证

`npm.cmd run build`、`npm.cmd run lint`、`npm.cmd run typecheck`、`npm.cmd run check:architecture`。2026-10-13 在本地隔离 SQLite（合成数据，假企微）上做浏览器检查：财务核对审核通过后任务出现在列表、旧地址跳转、详情六节点与合同不可保存原因、供应商群新增并带入通知、保存通知版本、流转记录、375px 窄屏无页面横向滚动。合同实际下载与共享盘写入只由后端测试覆盖，未连接真实 NS、企微与共享盘。

## 供应商档案维护

侧栏“基础资料 → 供应商档案”进入 `/suppliers`；旧 `/tasks/supplier-groups` 和 `/invoice-followup/supplier-groups` 重定向到此页，兼容一版本后清理。此页继续归属 task，开票跟进引用同一份绑定。

`SupplierGroupsPage` 使用 `useSupplierProfiles` 查询真实供应商（包括未绑定），`SupplierProfilesTable` 展示群、群主、NS 身份和绑定状态；筛选/分页保存在 URL。每行“维护档案”打开现有编辑区，自动请求名称候选，手动选择群后保存。没有虚构联系人或采购负责人。

匹配依据与排序来自后端，前端只展示；改变关键词可查简称、群主和群 ID。已保存的绑定不会因推荐变化自动覆盖。保存失败保留选择，旧响应不覆盖新查询；取消返回触发按钮。原 GroupLookup 供应商二次选择组件退出，此页直接从档案行进入维护，不再重复查询选择供应商。

验证入口增加 `frontend/tests/supplier-profiles.test.mjs`，覆盖独立导航、未绑定供应商、群主身份展示及失败不自动重放。真实企微权限与目录完整性需部署环境联调。
