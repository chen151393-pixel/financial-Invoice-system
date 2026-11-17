# settlement 模块：结汇对账

## 职责

报关之后的结汇：客户货款必须与报关金额一致。按报关单“贸易国”分两条回款路径：

| 路径                  | 判定                 | 资金流                       | 对账                                                                                 |
| --------------------- | -------------------- | ---------------------------- | ------------------------------------------------------------------------------------ |
| `hk_transit` 香港中转 | 贸易国为中国香港     | 客户 → 香港账户 → 汇回境内   | 两段：香港到账对报关合计；汇回境内对报关合计。批次与汇回一一对应（按资料一单一单做） |
| `direct` 直接收汇     | 贸易国为真实客户国家 | 客户 → 境内账户（NS 已核销） | 一段：到账对报关合计                                                                 |

**差额只认手续费**：到账金额 + 手续费 = 报关合计，严格相等才通过；手续费超过 `SETTLEMENT_FEE_ALERT` 时提示复核，防止把少收款当作手续费。

> 海关回执导入文件目前不含“贸易国”。未取得贸易国时，按境外收货人是否为集团香港公司判定（`SETTLEMENT_HK_CONSIGNEES`，分号分隔；为空时使用 `policy/route_policy.py` 内置名单）。NS 报关记录字段 `custrecord_swc_country_body`（值 95 为中国香港）同步进 source 后，可直接传入 `route_of()` 的 `trade_country`。

## 拥有的表

- `settlement_batches`：结汇批次（一笔回款），含到账、手续费、汇回、状态与经办人。
- `settlement_batch_items`：批次包含的报关单，建批次时冻结海关回执成交总价；`active_declaration_no` 唯一约束保证同一报关单只在一个有效批次中，作废后释放。

- `settlement_bills`：批次的提单文件及提单号、装运口岸、目的口岸、装船日期、对应的报关单；移除为软删除。
- `settlement_contracts`：按模板生成的销售合同 PDF（批次内每个出口合同号一份）及生成依据摘要。
- `settlement_parties`：销售合同买卖双方抬头（中英文名称、地址、电话）与印章图片。

文件本体（提单、合同 PDF、印章图片）保存在 `SETTLEMENT_DOCUMENT_ROOT`，只用服务端 UUID 命名，数据库记录标识与校验值；部署时该目录须为持久卷。

迁移：`0045_settlement_batches.py`、`0046_settlement_documents.py`。

## 读取依赖

- `review.public.settlement_declarations`：海关回执当前版本（境外收货人、出口日期、出口合同号、成交总价）；只取已匹配到 NS 报关单的回执。
- `review.public.settlement_declaration_lines`：海关回执当前版本明细（品名、规格、数量、单位、成交总价、出口合同号），供生成销售合同。
- `source.public.declaration_refs_by_number`：真实报关单号 → NS CD 编号（展示）。

不发布、不订阅事件；`public.py` 暂无对外函数。

## 状态

```text
香港中转：collected 香港已收 → documents_ready 资料已出 → settled 已结汇（汇回对平）
直接收汇：collected 已收款   → settled 已结汇（到账对平）
未结汇前均可 cancelled 作废，作废释放报关单。
```

状态转换集中在 `policy/batch_state_policy.py`；可操作判断（`allowed/reason`）由后端返回，执行时再次校验。

## 结汇资料（香港中转）

香港中转批次在“香港已收”阶段准备资料，**提单与销售合同齐全后才能确认资料已出**；确认后资料只读，仍可下载。

- **提单**：上传 PDF（单个不超过 8 MB），`policy/bill_parse_policy.py` 从文字中识别提单号、装运口岸、目的口岸、装船日期；识别不到的留空由人工填写，不猜测港口。扫描件没有文字层，需全部人工填写。每张提单标明对应的报关单（默认批次内全部）。
- **销售合同**：按 `templates/sales_contract.json`（由原人工模板整理的版式与条款）生成 PDF，批次内每个出口合同号一份。明细与金额取海关回执成交总价，单价 = 成交总价 ÷ 成交数量（仅展示）；签订日期 = 最早出口日期往前推 `SETTLEMENT_CONTRACT_LEAD_DAYS` 天（默认 28）；装运口岸、目的口岸取对应提单；买方按境外收货人匹配合同抬头，卖方、成交方式、付款条件由经办人确认。双方印章取合同抬头的印章图片，缺印章时照常生成并提示。
- **需重新生成**：提单口岸、海关回执明细、合同抬头或印章变化后，已生成合同的依据摘要不再一致，须重新生成才算齐全。海关回执换版导致合计与建批次时不一致时，须作废批次重建。
- **资料包**：齐全后可下载 zip，结构为“批次 / 出口合同号 / 销售合同与提单 PDF”，附文件清单。
- 中文字体：默认使用 PDF 内置 STSong-Light（不嵌入，英文数字用 Helvetica）；配置 `SETTLEMENT_PDF_FONT`（TTF 路径）后改为嵌入该字体。

## HTTP 接口（页面权限代码 `settlement`）

| 方法 | 路径                                                       | 说明                                                                                 |
| ---- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| POST | `/api/settlement/candidates/query`                         | 可结汇报关单、路径判定、已报关未结汇汇总；带 `targetAmount` 时推荐金额恰好吻合的组合 |
| POST | `/api/settlement/batches/query`                            | 批次列表（路径、状态、收货人、批次号、报关单号筛选）                                 |
| POST | `/api/settlement/batches`                                  | 登记回款建批次（`requestId` 幂等）                                                   |
| GET  | `/api/settlement/batches/{id}`                             | 批次详情与金额核对                                                                   |
| POST | `/api/settlement/batches/{id}/documents-ready`             | 香港中转：确认资料已出（须香港到账对平，且提单与销售合同齐全）                       |
| POST | `/api/settlement/batches/{id}/remittance`                  | 香港中转：登记汇回并确认结汇（须汇回对平）                                           |
| POST | `/api/settlement/batches/{id}/settle`                      | 直接收汇：确认结汇（须到账对平）                                                     |
| POST | `/api/settlement/batches/{id}/cancel`                      | 作废（填写原因）                                                                     |
| GET  | `/api/settlement/batches/{id}/documents`                   | 批次资料：提单、销售合同、齐全度、缺项与可操作判断                                   |
| POST | `/api/settlement/batches/{id}/bills`                       | 上传提单（`fileName`、base64 `content`、可选 `declarationNos`）                      |
| POST | `/api/settlement/batches/{id}/bills/{billId}`              | 人工修改提单字段与对应报关单                                                         |
| POST | `/api/settlement/batches/{id}/bills/{billId}/remove`       | 移除提单                                                                             |
| GET  | `/api/settlement/batches/{id}/bills/{billId}/file`         | 查看提单 PDF                                                                         |
| POST | `/api/settlement/batches/{id}/contracts/generate`          | 按模板生成 / 重新生成销售合同（卖方、成交方式、付款条件）                            |
| GET  | `/api/settlement/batches/{id}/contracts/{contractId}/file` | 查看销售合同 PDF                                                                     |
| GET  | `/api/settlement/batches/{id}/package`                     | 下载资料包 zip（资料未齐时拒绝）                                                     |
| POST | `/api/settlement/parties/query`                            | 合同抬头列表                                                                         |
| POST | `/api/settlement/parties`                                  | 新增 / 修改合同抬头                                                                  |
| POST | `/api/settlement/parties/{id}/stamp`                       | 上传印章图片（PNG / JPG，不超过 2 MB）                                               |
| GET  | `/api/settlement/parties/{id}/stamp`                       | 查看印章图片                                                                         |

## 尚未实现（计划）

- NS 客户收款与核销记录同步：目前直接收汇的到账需人工登记，计划由 sync 模块同步 NS 收款后自动建批次。
- 贸易国字段同步（见上方说明）。
- 报关单与形式发票并入资料包：两者由 NS 报关资料下载提供且为 xls，需先在服务端转 PDF（如 LibreOffice），目前资料包只含销售合同与提单，文件清单中注明需另行准备。
- 提单与报关单的交叉核对（提运单号、件数、毛重、柜号）：本地尚未同步报关单的这些字段。
- 提单扫描件 OCR、按船公司的专用解析模板、从共享盘批量导入。
- 成交方式、付款条件取自 NS 销售订单（目前由经办人确认，默认值来自模板）；商品英文名（目前使用海关回执中文品名）。
- 合同抬头与印章的维护目前只受 `settlement` 页面权限控制，未单独限制为管理员；资料包下载未留下载记录。

## 验证

```bash
python -m pytest backend/tests/settlement
```
