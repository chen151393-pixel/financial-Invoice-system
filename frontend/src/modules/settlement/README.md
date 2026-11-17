# 结汇对账页面（settlement）

侧栏“财务”分组的“结汇对账”下有三个子页面，共用页面权限代码 `settlement`，路径在 `app/paths.ts`：

| 子页面       | 路由                     | 内容                                               |
| ------------ | ------------------------ | -------------------------------------------------- |
| 待结汇报关单 | `/settlement`            | 查询、勾选报关单，登记回款建批次                   |
| 香港中转批次 | `/settlement/hk-transit` | 贸易国为香港的批次：香港已收 → 资料已出 → 汇回结汇 |
| 直接收汇批次 | `/settlement/direct`     | 贸易国为客户国家的批次：到账对平后结汇             |

后端规则见[后端 settlement 模块](../../../../backend/modules/settlement/README.md)。

| 文件                                   | 作用                                                              |
| -------------------------------------- | ----------------------------------------------------------------- |
| `pages/SettlementDeclarationsPage.tsx` | 待结汇报关单页；建好批次后立即打开批次详情                        |
| `pages/SettlementBatchesPage.tsx`      | 某一回款路径的批次列表（状态筛选按路径给出）                      |
| `components/CandidatePanel.tsx`        | 可结汇报关单查询、勾选、按收款金额推荐组合                        |
| `components/CreateBatchDialog.tsx`     | 登记回款建批次（到账、手续费、付款方、账户、流水号）              |
| `components/BatchDetailDialog.tsx`     | 批次详情：到账 / 汇回核对、确认资料已出、登记汇回、确认结汇、作废 |
| `api.ts`、`types.ts`                   | 接口与类型，金额为十进制字符串                                    |

前端不计算金额与差额，不判断能否操作：核对结果、状态文案和 `allowed/reason` 全部来自后端。
