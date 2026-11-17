# 结汇对账页面（settlement）

路由 `/settlement`（`app/paths.ts` 的 `settlement`），侧栏“财务”分组，页面权限代码 `settlement`。后端规则见[后端 settlement 模块](../../../../backend/modules/settlement/README.md)。

| 文件 | 作用 |
| --- | --- |
| `pages/SettlementPage.tsx` | 页面：上方待结汇报关单，下方结汇批次列表（路径、状态筛选） |
| `components/CandidatePanel.tsx` | 可结汇报关单查询、勾选、按收款金额推荐组合 |
| `components/CreateBatchDialog.tsx` | 登记回款建批次（到账、手续费、付款方、账户、流水号） |
| `components/BatchDetailDialog.tsx` | 批次详情：到账 / 汇回核对、确认资料已出、登记汇回、确认结汇、作废 |
| `api.ts`、`types.ts` | 接口与类型，金额为十进制字符串 |

前端不计算金额与差额，不判断能否操作：核对结果、状态文案和 `allowed/reason` 全部来自后端。
