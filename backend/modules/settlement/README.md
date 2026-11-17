# settlement 模块：结汇对账

## 职责

报关之后的结汇：客户货款必须与报关金额一致。按报关单“贸易国”分两条回款路径：

| 路径 | 判定 | 资金流 | 对账 |
| --- | --- | --- | --- |
| `hk_transit` 香港中转 | 贸易国为中国香港 | 客户 → 香港账户 → 汇回境内 | 两段：香港到账对报关合计；汇回境内对报关合计。批次与汇回一一对应（按资料一单一单做） |
| `direct` 直接收汇 | 贸易国为真实客户国家 | 客户 → 境内账户（NS 已核销） | 一段：到账对报关合计 |

**差额只认手续费**：到账金额 + 手续费 = 报关合计，严格相等才通过；手续费超过 `SETTLEMENT_FEE_ALERT` 时提示复核，防止把少收款当作手续费。

> 海关回执导入文件目前不含“贸易国”。未取得贸易国时，按境外收货人是否为集团香港公司判定（`SETTLEMENT_HK_CONSIGNEES`，分号分隔；为空时使用 `policy/route_policy.py` 内置名单）。NS 报关记录字段 `custrecord_swc_country_body`（值 95 为中国香港）同步进 source 后，可直接传入 `route_of()` 的 `trade_country`。

## 拥有的表

- `settlement_batches`：结汇批次（一笔回款），含到账、手续费、汇回、状态与经办人。
- `settlement_batch_items`：批次包含的报关单，建批次时冻结海关回执成交总价；`active_declaration_no` 唯一约束保证同一报关单只在一个有效批次中，作废后释放。

迁移：`backend/migrations/versions/0045_settlement_batches.py`。

## 读取依赖

- `review.public.settlement_declarations`：海关回执当前版本（境外收货人、出口日期、出口合同号、成交总价）；只取已匹配到 NS 报关单的回执。
- `source.public.declaration_refs_by_number`：真实报关单号 → NS CD 编号（展示）。

不发布、不订阅事件；`public.py` 暂无对外函数。

## 状态

```text
香港中转：collected 香港已收 → documents_ready 资料已出 → settled 已结汇（汇回对平）
直接收汇：collected 已收款   → settled 已结汇（到账对平）
未结汇前均可 cancelled 作废，作废释放报关单。
```

状态转换集中在 `policy/batch_state_policy.py`；可操作判断（`allowed/reason`）由后端返回，执行时再次校验。

## HTTP 接口（页面权限代码 `settlement`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/settlement/candidates/query` | 可结汇报关单、路径判定、已报关未结汇汇总；带 `targetAmount` 时推荐金额恰好吻合的组合 |
| POST | `/api/settlement/batches/query` | 批次列表（路径、状态、收货人、批次号、报关单号筛选） |
| POST | `/api/settlement/batches` | 登记回款建批次（`requestId` 幂等） |
| GET | `/api/settlement/batches/{id}` | 批次详情与金额核对 |
| POST | `/api/settlement/batches/{id}/documents-ready` | 香港中转：确认资料已出（须香港到账对平） |
| POST | `/api/settlement/batches/{id}/remittance` | 香港中转：登记汇回并确认结汇（须汇回对平） |
| POST | `/api/settlement/batches/{id}/settle` | 直接收汇：确认结汇（须到账对平） |
| POST | `/api/settlement/batches/{id}/cancel` | 作废（填写原因） |

## 尚未实现（计划）

- NS 客户收款与核销记录同步：目前直接收汇的到账需人工登记，计划由 sync 模块同步 NS 收款后自动建批次。
- 贸易国字段同步（见上方说明）。
- 资料包：提单上传与解析、销售合同生成（NS 报关资料接口尚未提供销售合同）、xls 转 PDF、盖章与按批次打包。

## 验证

```bash
python -m pytest backend/tests/settlement
```
