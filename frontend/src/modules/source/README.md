# 采购报关联查

`/pl-reconciliation`：按 PL、CD 或真实报关单号实时调用 NS 共用脚本，只读查询，不入库、不创建审核记录。

| 文件                                | 说明                                                                                      |
| ----------------------------------- | ----------------------------------------------------------------------------------------- |
| `pages/PlReconciliationPage.tsx`    | 页面：查询条件、加载、空结果、失败与结果                                                  |
| `components/PlSearchForm.tsx`       | 查询表单：默认按 CD；PL / CD / 真实报关单号同一行，申报月份与创建日期范围在“更多查询条件” |
| `components/PlSourceComparison.tsx` | 结果：保留 NS 原值与来源行序，金额为后端十进制字符串                                      |
| `api.ts`                            | `POST /api/source/pl-comparison`                                                          |
| `types.ts`、`source-types.ts`       | 查询条件与后端返回结构                                                                    |

架构 v2 第 4 步中，原本放在本目录的页面已移到对应模块：

- 财务核对 → [review 模块](../review/README.md)（第 4b 步，`/review`）。
- 开票跟进、开票任务详情、供应商群配置 → [task 模块](../task/README.md)（第 4c 步，`/tasks`、`/tasks/:id`、`/tasks/supplier-groups`）。

验证：`npm.cmd run build`、`npm.cmd run lint`、`npm.cmd run typecheck`、`npm.cmd run test:web`（含联查结果渲染测试）。
