# 采购报关联查与开票跟进

## 开票跟进正式页

`/invoice-followup` 从导航“开票跟进”或财务核对右上角进入（旧链路任务），读取真实的审核后任务。`pages/InvoiceTaskPage.tsx` 复用 AppFrame、Button、Pagination，默认按供应商、可切换按报关单，后端完成分组、搜索、统计和分页。供应商展开后列出各报关单任务；“查看节点”跳转独立详情页，显示六节点流程、原件获取与只读审核明细。所有金额使用后端字符串，未确认额度不显示采购单合计。

页面包含加载、错误重试、空结果及历史版本查看；查询切换忽略过期响应。审核完成提示关联任务数，不把重复审核当作重复生成。历史已审核数据不会自动补建。收票统计为未接入，共享盘保存使用真实接口；通知及比对操作按后端能力禁用，不能冒充执行成功。后端规则和新增应用库迁移见 [审核模块](../../../../backend/modules/reconciliation/README.md#审核后开票任务已实现)。

采购报关联查 `/pl-reconciliation`：`pages/PlReconciliationPage.tsx`、`components/PlSourceComparison.tsx`、`components/PlSearchForm.tsx`，调用 POST `/api/source/pl-comparison` 实时读取 NS，只读不入库，保留原值与来源行序。

财务核对已于架构 v2 第 4b 步移到 [review 模块](../review/README.md)（`/review`，旧地址自动跳转），改用 `/api/review/*` 新接口。第 4c 步接入新开票任务前，开票跟进页仍读取旧链路生成的任务。

验证：`npm.cmd run build`、`npm.cmd run lint`、`npm.cmd run typecheck`、`npm.cmd run test:web`。

## 开票任务独立详情

`/invoice-followup/{taskId}` 使用 `InvoiceTaskDetailPage.tsx`，列表“查看节点”导航到此页，支持直接链接、刷新和返回全部任务。展示六节点流程、当前动作、审核来源环境与原件下载环境，以及可点击的六个流程节点和流转记录分区。“保存到共享盘”按钮调用后端 prepare 接口，成功才显示共享盘保存路径和时间；失败显示实际错误且允许重试。币种缺失是来源提示，不构成二次审核门槛。前端不推算金额，不伪造通知、收票或比对结果。

页面不再提供 PDF 原件下载按钮；合同通过共享盘使用。保存失败时展示真实错误，可重试，资料节点不会提前完成。

正式详情的“通知供应商”复用现有视觉，业务组件为 `components/TaskNotification.tsx`，调用真实草稿保存与人工登记接口。默认正文由后端生成，可编辑、恢复默认、居中预览、复制；接收信息按当前任务保存。未保存修改切换节点仍保留，登记必须使用已保存版本，刷新后读取数据库。人工记录与企微回执明确区分，自动发送按钮展示未接入原因。

节点和分区通过 `#task-review/documents/notification/invoices/comparison/completion/history` 切换，支持直接链接和浏览器前进后退，只切换查看内容、不修改业务状态。选中节点只用文字下划线，不显示大框或“查看详情／正在查看”提示。旧 `#task-documents` 链接继续可用。

## 供应商群配置

`/invoice-followup/supplier-groups` 从开票跟进右上角进入，复用 AppFrame、Button 和 Pagination。支持新增供应商默认群、查询、修改、停用及重新启用。供应商从已同步采购来源选择，通过 `WecomGroupPicker` 输入群名查询并选择，自动获取群 ID 与群主信息，保存到 MySQL 业务库的映射表；查询、分页、字段校验、版本冲突和维护权限均由后端处理。

页面支持加载、失败重试、空结果与保存的真实反馈。已移除 Excel 群清单导入及群目录选择入口，仅维护当前映射。详情通知区展示当前有效默认群，新通知自动带出群名和群主，已保存内容不被配置变化覆盖。保存前由后端重新核验群身份与群主，群发接口仍未接入。群 ID 和群主 ID 仅只读展示；重名群通过群主、人数、创建时间及群标识区分，查询失败或权限不完整时显示实际原因。
