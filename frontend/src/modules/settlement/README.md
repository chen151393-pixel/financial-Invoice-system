# 结汇对账页面（settlement）

侧栏“财务”分组的“结汇对账”下有五个子页面，共用页面权限代码 `settlement`，路径在 `app/paths.ts`：

| 子页面       | 路由                        | 内容                                                                       |
| ------------ | --------------------------- | -------------------------------------------------------------------------- |
| 报关应收汇   | `/settlement`               | 按境外收货人汇总应收汇、显示回款路径；香港中转的报关单勾选后登记回款建批次 |
| 银行收汇明细 | `/settlement/bank-receipts` | 导入银行 .xlsx、查询收汇记录、实际客户与三方代付标记 |
| 香港中转批次 | `/settlement/hk-transit`    | 贸易国为香港的批次：香港已收 → 资料已出 → 汇回结汇                         |
| 直接收汇明细 | `/settlement/direct`        | 非香港中转的总账：按境外收货人、收款人和币种汇总差额，可展开查看出口与收汇流水             |
| 合同抬头     | `/settlement/parties`       | 销售合同买卖双方的名称、地址、电话与印章                                   |

直接收汇不再建批次，原“直接收汇批次”列表已由“直接收汇明细”取代（2026-11-18）。

后端规则见[后端 settlement 模块](../../../../backend/modules/settlement/README.md)。

| 文件                                                                | 作用                                                                                                     |
| ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `pages/SettlementDeclarationsPage.tsx`                              | 报关应收汇页；建好批次后立即打开批次详情                                                                 |
| `pages/SettlementBatchesPage.tsx`                                   | 批次列表（目前只挂载香港中转；状态筛选按路径给出）                                                       |
| `pages/SettlementBankReceiptsPage.tsx`、`components/BankReceiptImportDialog.tsx` | 银行流水导入、导入结果、收汇抬头汇总、列表与筛选 |
| `pages/SettlementLedgerPage.tsx`、`components/LedgerGroupTable.tsx` | 直接收汇明细：按境外收货人、收款人和币种汇总，可展开查看流水、单据编号及每笔后的累计余额 |
| `components/CandidatePanel.tsx`                                     | 报关应收汇：查询、按境外收货人汇总、报关单明细勾选、按香港到账金额推荐组合                               |
| `components/ReceivableStats.tsx`、`ConsigneeSummary.tsx`            | 按回款路径的应收汇概况卡；按境外收货人汇总表（路径、出口抬头、张数、金额、处理方式）                     |
| `components/CreateBatchDialog.tsx`                                  | 登记回款建批次（到账、手续费、付款方、账户、流水号）                                                     |
| `components/BatchDetailDialog.tsx`                                  | 批次详情：到账 / 汇回核对、确认资料已出、登记汇回、确认结汇、作废                                        |
| `components/BatchDocuments.tsx`                                     | 香港中转批次详情中的资料区：提单上传 / 修改 / 移除、销售合同（形式发票）生成、报关单归档状态、资料包下载 |
| `components/BillEditForm.tsx`、`ContractGenerateForm.tsx`           | 提单字段人工确认表单；生成销售合同前确认卖方与条款的表单                                                 |
| `pages/SettlementPartiesPage.tsx`、`components/PartyDialog.tsx`     | 合同抬头列表、新增 / 修改、印章上传                                                                      |
| `api.ts`、`types.ts`                                                | 接口与类型，金额为十进制字符串                                                                           |

文件只读取字节后以 base64 提交，格式校验、提单解析、资料齐全度都在后端。前端不计算金额与差额，不判断能否操作：核对结果、状态文案和 `allowed/reason` 全部来自后端。报关单能否选入批次按后端返回的 `handling`（`batch` 建批次 / `ledger` 进总账）与 `blockedReason` 展示；直接收汇明细的总账差额、状态与合计也全部来自后端。
