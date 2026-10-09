# 原始报关行只读导出接口（待部署）

财务页面现采用人工整单审核：待审核 → 审核通过，不以本文件所述的机器逐行匹配完整性作为前置步骤。以下 `partial/matched` 均为来源技术状态；缺少明确行归属的子采购仍在单头下供财务核对，审核不自动生成开票额度。详见[审核规则](../backend/modules/reconciliation/README.md)。

财务列表已经读取本地业务库，但当前正式 M2M 身份无法通过 REST 或 SuiteQL 读取脚本使用的 `customrecord_swc_declare_line`；REST 元数据目录也没有这个类型。Packing 与销售—采购交易行关联可读取。`customrecord_swc_delare_detail_comm` 在 CD000839 样本中没有记录，不能冒充原始行。

正式创建脚本 `SWC_SL_DeclareBackend.js`、子采购创建脚本实际从报关头的 `recmachcustrecord_swc_sl_relate` 子列表写入或读取原始来源。本接口直接只读加载报关头与该子列表，避免猜测其子记录类型名称。

## 已准备内容

- 文件：[`finance_source_restlet.js`](../scripts/netsuite/finance_source_restlet.js)。独立 RESTlet，不替换已有创建或审批脚本。
- 输入：`POST {"declarationIds":["839"]}`，只接受最多20个不同的内部ID。
- 输出：`contractVersion=1`、`complete`、规范化账套及每张单的原始行。每行保留唯一ID、报关头、PL、Packing、公司、货品、履行及行号、母采购、开票品名与原始装箱数量。
- 缺失子列表、来源字段、唯一ID、超限或权限失败时，返回明确失败且不返回部分成功数据。最多2000行。
- 不提供任意记录类型、任意查询、保存、创建、删除、发送通知或审核功能；仅使用 `N/record.load` 和读取方法。

## 部署边界

用户已授权新增正式环境只读接口部署，**尚未上传、创建或修改任何正式 NS 脚本部署**。已检查 SuiteCloud 本地认证，仅存在沙箱 `5939865-sb1`；正式 `5939865` 的部署登录正在等待用户完成。业务 M2M 读取凭证不等同于 SuiteCloud 部署凭证，不将沙箱登录用于正式部署。使用现有 M2M 身份和读取权限，不选择无需登录访问，不提升为管理员执行。

建议新增脚本 ID `customscript_finance_source_read`，部署 ID `customdeploy_finance_source_read`；实际ID以 NS 创建结果为准。上线前先读单张839，确认行身份及字段完整、返回账套5939865，再接入逐行匹配。若记录加载后仍不可见，应由 NS 管理员核实原始子行的实际记录类型及该角色权限。

匹配必须继续经过原始报关行 → Packing → 销售/母采购行 → 子采购行；原始行还需唯一归属报关汇总行。重复候选、跨账套、数量上限冲突和分摊依据缺失不得强配。此文件本身不意味着精确匹配或审核已经完成。

验证：`node --test tests/ns-finance-source.test.mjs` 使用隔离模拟 API，覆盖输入边界、只读方法、唯一来源身份、额度与失败响应；不代表真实 NS 部署验收。

## 同步时保存的对应关系

已接入 `StorageService.sync/sync_page`，在拉取并保存报关/子采购时一并读取关系，复用原有账户锁、明细更新和原子事务。现使用独立表 `customs_reconciliation_results`，一张报关单一条当前结果；状态、数量、摘要、时间为独立列，原始依据与v3结果分别存入 `evidence_data`、`comparison_payload`。字段、外键与迁移见[关联结果表说明](mysql/customs-reconciliation-results.md)。下表是读取器内部契约，存储转换由 `relation_storage_mapper.py` 完成，不再写入报关主表JSON：

| 字段 | 含义 |
| --- | --- |
| version/account/declarationId/readAt | 证据版本、来源账套、NS 报关内部ID、本次读取时间 |
| status/issues | matched：来源与逐行关联完整；collected：仅来源已读取；partial：缺失或冲突。不是审核通过 |
| rawLines | 报关原始子行，保留原始行ID、PL、Packing、货品、公司、履行行、母采购引用，以及原装箱数量、申报数量、申报单位ID和型号 |
| packingLines | `customrecord_swc_packinglist` 原始装箱明细（非名称相近的 packinglist1），保留销售行、母单、PL、货品及来源数量 |
| rawPackingLinks | 原始报关行ID→明确引用的Packing行ID，不按品名生成 |
| purchaseLinks | NextTransactionLineLink 的销售单/行→母采购单/行原生关系 |
| parentLines | 母采购 transactionline 的原生行ID、uniquekey、商品及数量等依据 |
| childOrders | 对应子采购ID、母采购引用、子行ID、原始母行引用及商品身份 |
| comparison.payload | `version=3/group`，NS共用脚本返回的整单展示结果，包含 `sourceKey/customsRowId` 及本次分摊数量金额 |
| comparison.digest/ready/reason | 展示内容SHA-256、是否满足业务完整性、未满足原因。身份权限与审批仍由财务模块校验 |
| comparison.requestId/readCompletedAt | 本次NS关联查询编号和完成时间 |

子采购→报关单仍落在 `purchase_orders.customs_declaration_id` 外键。报关汇总行来源保留在原来的 `source_data.lines`；逐行归属与分摊直接复用NS v3查询结果，不把汇总行上的母单字段当作全部来源，不在Python维护第二套分摊算法。财务页只读数据库中的明确关联，不在打开页面时重新抓取NS。

部署后在服务器配置中填写实际创建的脚本和部署ID（两项必须同时填写），并保持已有 `restlets` 授权：

```dotenv
NETSUITE_FINANCE_SOURCE_SCRIPT=customscript_finance_source_read
NETSUITE_FINANCE_SOURCE_DEPLOY=customdeploy_finance_source_read
NETSUITE_PL_RESTLET_SCRIPT=customscript_pl_web_query
NETSUITE_PL_RESTLET_DEPLOY=customdeploy_pl_web_query
```

2026-09-24完整同步流程调整：必须配置同账套的原始行与v3查询接口，缺少配置会在读取保存前报错；旧版关联接口、失败、跨账套、漏单、重复行或范围不一致时整页不保存。查询v3接口的部署要求见[接入说明](pl-script-integration.md)。来源存在真实歧义时保留已明确的关系和具体原因，不能整单审核。重新拉取替换证据及关联，不沿用旧结果；数据库提交结果不明时先核实本地记录。仅补拉历史依据的 `RelationBackfillService` 仍可以记录partial，不等同于完整同步。

子采购改挂或独立更新时，本次未重新完整读取的原报关单会在同一事务中清除结果表的旧 `comparison_payload/comparison_digest`，保留来源证据并标记 `dependency_changed/partial`；不会继续套用旧审核摘要。隔离测试覆盖初次匹配、重复拉取、失败不覆盖旧快照、关联范围变化、状态分页、审核重新核对及改挂失效。此次后端测试378项通过；MySQL专用关系测试28项通过（含4项实际数据库测试）。这些结果不代表正式NS接口已经部署。

2026-09-24早先：新读取器对正式 `CD000839` 只读验收，得到2张子采购、5条Packing、5条销售采购行关系、12条母采购来源行；原始行接口未部署，`rawLines=0/status=partial`。这次真实验收没有写入业务库。之后已实现同步v3关联结果、数据库自动展示和待审核状态，但正式部署与真实逐行验收仍未完成。

## 正式来源依据补拉结果（2026-09-24）

上述单张只读验收之后，按用户要求已对当前身份本地存储的120张正式报关单执行依据补拉并入库。去重后取得1062条Packing、995条销售采购行关系、1586条母采购来源行；原始报关子行为0条，120张均为partial。正式接口试读返回404；查询正式script及scriptdeployment均无对应记录；SuiteCloud当前仍仅有沙箱登录，尚未部署正式原始行接口。

最初补拉用 `RelationBackfillService` 仅更新报关主表的关系JSON（后由 `0005_customs_relations` 迁移到独立表），并记录 `mode=evidence_backfill/baseSyncedAt`。子采购行沿用原同步快照，未宣称已重新核实其NS最新版本。补拉前后对原主单、明细、采购数据及沙箱记录计算摘要，除本次关系JSON外一致。未修改NS业务记录或执行审核。

财务列表已改为先对主键排序分页、再读取该页的关联结果；原始证据大JSON无需进入财务列表，避免大JSON参与MySQL排序。真实业务库公开读取接口已核实120张正式单据、首20张均含关系状态；隔离MySQL测试覆盖大JSON分页、原内容保留、失败回滚、并发快照变化拒绝及身份隔离。原始接口待部署文件另补齐申报数量、申报单位ID和型号；这些字段尚未完成正式读取验收。
