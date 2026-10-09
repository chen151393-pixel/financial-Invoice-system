# 报关关联依据与当前结果表

所属模块：`business`。表名：`customs_reconciliation_results`。增量版本：`0005_customs_relations`，前置版本 `0004_invoice_allocations`。

一张报关单保存一条当前核对记录，重复拉取更新同一条记录。原始报关子行、Packing、母子采购来源关系及NS脚本计算的逐行结果集中保存在此表。多行数组仍使用JSON，当前不另建逐行分配表；数量、金额保持来源十进制字符串，不能转浮点。

## 关联与职责

- 组合外键 `(tenant_id, ns_account, customs_declaration_id)` 对应 `customs_declarations(tenant_id, ns_account, id)`，同时设唯一约束，阻止跨身份、跨账套及重复关联结果。
- NS报关内部ID、CD编号、真实报关号通过报关主表查询，不重复复制。子采购单头仍通过原有 `purchase_orders.customs_declaration_id` 关联报关单。
- `comparison_payload.group.rows` 中的 `sourceKey/customsRowId` 保存明确来源与报关行归属，不按PL、品名或相邻行推断。`evidence_data` 保留追溯依据。
- `review_ready` 仅表示机器来源是否完整，不是财务人工审核的前置门槛，也不表示审核通过或操作者有权限。整单审核、不可变快照和审核历史继续由财务模块保存在应用数据库。

## 字段

| 字段 | MySQL类型 | 作用 |
| --- | --- | --- |
| id | BIGINT UNSIGNED | 自增主键 |
| tenant_id | VARCHAR(100) | 后端身份派生的数据归属 |
| ns_account | VARCHAR(100) | NS账套 |
| customs_declaration_id | BIGINT UNSIGNED | 本地报关单外键 |
| evidence_version | INT | 依据契约版本，当前为1 |
| status | VARCHAR(16) | `partial`缺失/冲突；`collected`仅取得依据；`matched`关联完整 |
| mode | VARCHAR(32) | `full_sync`完整同步；`evidence_backfill`仅补依据；`dependency_changed`依赖更新使旧结果失效 |
| review_ready | BOOLEAN | 机器关联来源是否完整；不决定财务人工审核是否允许 |
| reason | TEXT | 不能确认完整性的原因 |
| issues | JSON | 具体来源问题列表 |
| raw_line_count | INT | 原始报关子行数 |
| packing_line_count | INT | Packing明细数 |
| purchase_link_count | INT | 销售行到母采购行关系数 |
| parent_line_count | INT | 母采购来源行数 |
| evidence_data | JSON | `rawLines/packingLines/rawPackingLinks/purchaseLinks/parentLines/childOrders` 等原始依据；补拉时含 `baseSyncedAt` |
| evidence_read_at | DATETIME(6)，可空 | 本次依据读取时间，UTC |
| comparison_payload | JSON，可空 | NS v3 `version/group` 展示契约，含逐行关联及本次数量、金额、币种 |
| comparison_digest | VARCHAR(64)，可空 | NS逐行展示内容SHA-256；本地人工审核另对实际来源快照计算摘要 |
| query_request_id | VARCHAR(100)，可空 | NS关联查询编号 |
| query_completed_at | DATETIME(6)，可空 | 关联查询完成时间，UTC |
| created_at | DATETIME(6) | 本地首次保存时间，UTC；更新时保留 |
| updated_at | DATETIME(6) | 最近保存时间，UTC |

索引 `ix_customs_reconciliation_status(tenant_id, ns_account, status, review_ready)` 支持按身份、账套、技术状态查询。财务列表根据当前有效审核快照统计并分页；先分页轻量主键，再加载当前页来源与依据（以及校验已有审核需要的单据），避免大JSON参与排序。缺少v3时按已存来源引用、Packing和原报关品名定位唯一报关汇总行，详见[business模块](../../backend/modules/business/README.md)。原始JSON不返回前端；此展示关系不回填v3契约或修改 `status/review_ready`，不生成开票分摊金额。

## 保存、更新和迁移

完整同步复用现有账户锁：先读完NS来源，再将报关单、子采购、外键和关联结果在同一个数据库事务中保存。失败一起回滚。子采购改挂或独立更新时，旧报关结果清除展示契约和摘要，并改为 `dependency_changed/partial`。

仅补依据调用同一个结果保存入口；原单据、采购行和完整同步时间不变。没有本次完整依据的内部快照导入会保存 `partial`，覆盖旧关联，防止继续展示已失效的逐行结果。财务人工审核独立校验本地来源快照。

部署前停止本项目API及同步任务，运行：

```powershell
npm.cmd run db:business:upgrade
```

迁移先检查旧依据的账套、报关身份和版本，再复制 `customs_declarations.source_data.relationEvidence` 到新表。复制成功后仅删除旧JSON中的这个键；原单据字段、金额、外键和同步时间保留。没有历史依据的报关单保持无结果，后续完整同步时生成。历史 `partial` 不会因换表变为已匹配。

如需手动执行，使用 [0005增量SQL](customs-reconciliation-results.sql)，仅适用于已经处于 `0004_invoice_allocations` 的业务库。命令迁移和手动SQL二选一，不重复执行；命令还提供旧依据身份预检与迁移互斥锁。不会重建业务库，也不会写入NS。

## 查看数据

```sql
SELECT c.record_no, c.declaration_no, r.ns_account,
       r.status, r.review_ready, r.reason,
       r.raw_line_count, r.packing_line_count,
       r.purchase_link_count, r.parent_line_count,
       r.evidence_read_at, r.updated_at
FROM customs_reconciliation_results r
JOIN customs_declarations c
  ON c.id = r.customs_declaration_id
 AND c.tenant_id = r.tenant_id AND c.ns_account = r.ns_account
WHERE c.tenant_id = :tenant_id AND c.ns_account = :ns_account
ORDER BY c.id DESC;
```

参数由后端身份及服务器账套配置提供。要查看逐行结果，读取对应行的 `comparison_payload`；要追溯来源，读取 `evidence_data`。

## 本地落库验证（2026-09-24）

已对本项目配置的业务库执行 `0004 → 0005` 迁移，新增1张表，迁入120条正式报关依据。迁移前后八张来源业务表摘要一致，依据往返内容一致，旧JSON关联键剩余0个。没有新增NS业务记录或执行财务审核。

服务重启后经5173页面代理验证：正式账套共120张，前两页各20张；CD000839查询返回1张；待审核筛选返回0张。所有历史依据仍为 `partial`，正式原始行及v3接口部署仍未完成。

验证结果：后端回归378项通过、74项因未配置对应独立数据库而跳过；另行使用随机隔离MySQL库运行迁移、关系存储及同步测试57项全部通过，包含跨身份/账套外键、幂等更新、原始精度、事务回滚和大JSON分页。优化列表读取后重跑相关33项通过。后端lint、架构检查与本次Python文件格式检查通过。未修改页面布局，未重复进行视觉验收。
