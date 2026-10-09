# 财务核对

职责：展示已入库的报关单、报关行和关联子采购明细，已有NS明确行引用时逐行展开，由财务核对后在应用库保存整单审核。保留兼容的NS实时查询入口，不写入NS，也不通知供应商。

## 自动列表（已实现）

打开财务核对页面时调用 `POST /api/reconciliation/declarations`，请求 `{keyword, account, status, page, pageSize}`，默认空关键字、全部账套、全部状态、第1页、每页20张（最多50张）。通过 business 公开的 `CustomsReconciliationSource` 按登录身份读取已同步的报关单、报关汇总行及同租户同账套的直接外键关联子采购单。关键字支持 CD、真实报关号、PL、子采购/母采购单号、供应商和商品名；匹配任意明细后仍返回完整单据，分页与计数在后端完成。

响应 `source=database`，含 `accounts/page/pageSize/total/pages` 和每单 `account`。财务人工审核流程为 **待审核 → 审核通过**，不再设置“关联核实”前置状态。优先采用已验证的 NS v3 行引用；没有 v3 时，business 模块使用已存子采购来源引用、Packing 和原报关品名等依据定位唯一报关行，`local_mapper.py` 返回各行独立的 `purchaseLines/purchaseCount`。未唯一定位的行留在 `unlinkedLines`，在整单审核窗口保留，不混入任意报关行的展开区域；不是按普通商品名强配。

打开页面不查询NS，按当前身份读取已保存单据。所有未审核单据计入待审核；缺少报关或关联采购明细时，按钮显示具体数据缺失原因。机器依据的 `partial/collected/matched` 和 `review_ready` 仍保存在business结果表中供同步追溯，不决定财务人工审核状态。

具备权限且有报关、采购明细时生成15分钟有效的本地审核快照。确认时在business账户同步锁内重新读取本地内容，内容一致才保存审核和审计；不要求当前NS连接账套与所审本地单据相同。数据归属、账套和报关身份仍由后端读取的快照确定，客户端不能提交或改写金额、账户或权限。

来源更新后重新比较内容摘要；变化的单据恢复待审核，历史记录保留。相同内容重复拉取的同步时间不影响审核结果。搜索、状态计数与分页在后端完成；`blocked`请求值保留兼容，本地列表该状态计数为0，前端不显示其筛选入口。

采购数量、金额保留来源口径。没有逐行分摊的采购行仍标为 `scope=order`，财务审核不自动将整单原值作为可开票额度；后续开票只能采用明确属于本次已报关范围的数据。申报数量/单位使用 `declared_quantity/declared_unit`，申报公司来自明细公司字段。

NS逐行自动匹配的缺失数据仍由同步模块补充，不因人工审核将技术依据标记为完整；正式接口状态见[来源说明](../../../docs/finance-source-reader.md)。

## 文件及接口

- `controller.py`：自动列表与`POST /api/reconciliation/query` 与 `POST /api/reconciliation/approve`。
- `dto.py`、`vo.py`：请求及展示契约。查询请求为 `{criteria: PlScriptQuery, status: all|pending|approved|blocked}`；确认请求仅接收 `{snapshotId, note}`，备注最多300字。
- `service.py`：身份、查询、不可变预览、本地来源复核和审核事务；兼容旧NS实时查询审核。调用business公开只读服务与audit公开写入接口。
- `dao.py`、`entity.py`：应用数据库SQL和表定义，共用Service事务。
- `mapper.py`：只按NS显式父行引用建立展示树，金额、数量保持十进制字符串。
- `policy.py`：本地人工审核权限和明细存在性检查；旧NS实时接口保留原完整性校验。

响应含每张报关单的`review.status/label/allowed/reason`、审核人、时间、备注、后端统计与树形明细。前端只使用`allowed`显示按钮；确认时服务端再次验证。

## 审核规则

1. 只有当前 `user:<ADMIN_USERNAME>` 可以确认，服务身份只读。按身份、账套、报关内部ID隔离；尚未实现多财务角色共享审批。
2. 财务页审核已入库的报关单及所有直接关联采购明细，包括尚无报关行归属的采购行。审核窗口完整展示本次数量/金额或子单原值标签，确认后留存同一份内容。
3. 预览不可变且15分钟有效。确认时重新读取业务库；来源字段、数量、金额、币种、关联或有效状态变化均拒绝旧预览，不从前端接收金额或审核状态。
4. 复用同步账户锁直到审核提交，阻止同期同步替换来源；审核头行锁、revision条件更新和审计唯一键防止重复确认。同内容已审核请求幂等返回，备注不覆盖；审计失败整笔回滚。当前MySQL业务库与应用库之间不执行NS网络请求。
5. “通知供应商（预留）”仅禁用占位，不发送通知、不写回NS、不自动生成可开票额度。
6. 兼容接口 `POST /api/reconciliation/query` 仍实时读取NS并生成旧版审核快照；该路径继续要求v3明确行引用和完整来源，确认时实时重读NS。它不作为财务自动列表的前置步骤，不删除其历史审核记录或保护规则。

## 数据库存储

使用`DATABASE_URL`应用库（当前本机是SQLite；生产可配置MySQL），不修改`BUSINESS_MYSQL_*`的八张来源表。迁移为`0002_finance_review`，运行`npm.cmd run db:upgrade`。

| 表                       | 作用及关联                                   | 字段                                                                                                           |
| ------------------------ | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| finance_review_snapshots | 不可变审核范围；每次查询一份；本地content及display或兼容NS v3快照 | id UUID主键，owner，account，declaration_id，digest SHA256，revision，payload JSON文本，created_at，expires_at |
| finance_reviews          | 每个身份/账户/报关单的当前审核头             | owner+account+declaration_id联合主键，revision，snapshot_id外键→快照，digest，reviewed_at，reviewed_by，note   |
| finance_review_audit     | 追加式审核操作历史，跟审核事务一起保存       | id自增主键，at，actor，snapshot_id唯一外键→快照，note                                                          |

时间戳字段均为UTC秒，接口审核时间为ISO字符串。未审核头的审核字段为空；每次审核revision递增。来源金额保存在快照中，不向来源采购表写“整单已开票”等状态。当前不自动清理快照或审核历史。

## 审核后开票任务（已实现）

从应用迁移 `0003_invoice_tasks` 起，新审核在**同一应用库事务**内保存审核头、审计与开票任务。任一保存失败全部回滚；重试同一审核或同来源的另一预览复用已保存任务。已有审核不会在浏览、刷新或迁移时补建任务。

- 归属仍为 `reconciliation`，`task_service.py` 负责任务生成与查询，`task_policy.py` 拆分来源范围，`task_dao.py` 负责SQL，`task_mapper.py` / `task_vo.py` 负责展示契约。`task_entity.py` 注册应用库表 `finance_invoice_tasks`。
- 每张报关单按供应商身份、采购公司身份、币种拆分，账套与操作者隔离；同一审核快照与分组键有唯一约束。身份缺失时隔离至子采购单，不能仅凭同名供应商合并，也不能拿申报主体替代采购购方。
- 保存审核快照外键、审核版本、来源子单及行标识、原始数量金额。新任务为 `documents_pending`（待保存子采购合同），财务审核通过即具备准备开票资料的依据，无二次范围确认。`expectedAmount=null` 仅表示不在任务中推算应开票金额，不是流程阻塞。不汇总整张采购单原值为应开票额度；金额原样以字符串返回。
- 来源变化后重新审核，新建新版本任务，原任务改为 `superseded`（已被新版本替代），原快照、原明细和旧任务标识保留。当前流程不允许对旧任务继续操作；后续接入发送/收票时需增加执行状态保护，不能直接复用目前的替代规则。
- 默认按供应商，支持按报关单查看同一批任务，搜索、账套过滤、当前/历史版本过滤、完整分组分页及统计由后端完成。同名但身份不同、身份缺失或不同账套的分组可能具有相同展示名称，不合并身份。
- 一次任务查询使用一致的数据库读快照：MySQL仅此连接使用REPEATABLE READ，SQLite显式开启读事务，避免同时重新审核时分组键与任务行跨版本；不修改全局事务设置。
- 待开票＝待保存合同、待通知和等待供应商开票的任务数；待处理＝同一批需准备资料或通知的任务数，两者重叠。收票关联尚未接入，`receivedInvoices=null`，页面显示“未接入”。不以0或模拟收票冒充真实统计。
- 详情通过业务模块公开读取接口核验本地来源摘要，返回 `current/changed/unavailable/superseded`。列表仅为审核时的快照；获取原件时仍复核当前来源及审核版本。

新增接口（均使用认证身份，不能提交owner、状态、金额或合计）：

| 接口 | 请求 / 响应 |
| --- | --- |
| `POST /api/reconciliation/invoice-tasks/query` | `keyword`最长120字、`account`、`groupBy=supplier/declaration`、`status=current/superseded/all`、`page`、`pageSize`最大50；返回groups、counts、accounts、total分组数、pages |
| `GET /api/reconciliation/invoice-tasks/{UUID}` | 返回任务、原始采购行、待补齐原因、六节点流程、来源核验结果、prepare/notify/compare的allowed与reason；无权访问返回404 |
| `POST /api/reconciliation/approve` | 保持原请求，响应新增 `invoiceTaskCount`，表示该审核版本已关联的任务数，重试不表示再次创建 |

启用前运行 `npm.cmd run db:upgrade` 并重启后端；应用库增量迁移不修改业务八表，不触发NS写入。采购原件获取已接入，通知草稿和人工发送登记已接入；企微自动发送、收票与比对关联尚未接入，不会模拟渠道发送成功。正式前端见 [前端模块说明](../../../web/modules/reconciliation/README.md)。

## 验证

`backend/tests/test_invoice_tasks.py` 验证审核自动生成、重复提交、任务失败回滚审核及审计、来源变化与新旧任务版本、精确金额字符串、身份隔离、分组完整分页及视图任务集合一致。两项现有MySQL并发测试已增加任务数量断言，未配置专用建库连接时仍跳过。手动界面验收可运行 `node scripts/python.mjs -m backend.tests.preview_invoice_tasks`，打开 `http://localhost:5181/invoice-followup`；使用临时SQLite和带“隔离数据”标记的合成单据，退出自动清理，不连接正式业务库或NS。

`backend/tests/test_finance_list.py`覆盖分页、搜索、身份/账套隔离、停用行排除及未分摊金额语义；`test_finance_manual_review.py`覆盖人工审核、过期、来源变化、幂等与审计回滚；`test_finance_manual_mysql.py`用独立MySQL业务库及应用库验证审核期间同步互斥和并发确认；`backend/tests/test_reconciliation.py`覆盖显式关联、来源变化、过期、权限/账户隔离、幂等与审计回滚；`test_reconciliation_mysql.py`用随机新建独立MySQL库验证真实并发，需`FINANCE_TEST_SERVER_URL`建库连接，结束仅删除该随机测试库。未配置时跳过，不声称SQLite证明MySQL并发。NS部署步骤见[接口说明](../../../docs/pl-script-integration.md)。

## 子采购订单原件（已实现）

应用迁移 `0004_task_documents` 将既有 `scope_pending` 转为 `documents_pending`，不修改历史审核快照。`finance_task_documents` 按任务和子采购单唯一保存 PDF、正式来源环境、NS 内部 ID、SHA-256 和获取时间。全部合同成功保存到共享盘后任务变为 `notify_pending`。失败不保存截断文件、不推进节点；已有原件的请求幂等返回，历史版本保留已归档文件供追溯。

- `POST /api/reconciliation/invoice-tasks/{UUID}/documents/{orderId}/prepare`：只允许任务中存在的子采购单；服务端按审核快照核验身份、当前来源及版本。调用 business 公开 `SubpoContractSource`，外部 HTTP 在数据库事务与来源锁之外；下载成功后重新加锁核验来源及审核版本再保存。返回最新任务详情。
- 页面不提供 PDF 原件下载，原 `/documents/{orderId}/file` 路由已移除，统一通过共享盘取用合同。
- 设置 `NETSUITE_SUBPO_CONTRACT_SCRIPT`、`NETSUITE_SUBPO_CONTRACT_DEPLOY`。可选 `NETSUITE_SUBPO_CONNECTION_FILE` 指向服务端独立认证环境文件，适用于审核来源为沙箱、原件在正式环境的情况；只读取 NS 认证参数，不继承外部项目数据库或写入开关，不向浏览器返回凭据。
- 专用连接需要 `restlets` 与 `rest_webservices` 读取权限。通过子采购单编号精确查询目标环境，唯一命中后核对单号、供应商和报关单编号；不沿用沙箱内部 ID，不默认用普通采购单 PDF 代替合同。RESTlet GET 返回 `{zid, filename, contentBase64}`，允许外层 JSON 字符串；核验 zid、base64、PDF 头尾及大小，使用服务端固定文件名。
- `backend/tests/test_task_documents.py` 覆盖状态推进、幂等、身份隔离、下载途中来源变化、网络失败、跨环境编号校验和错误 PDF。MySQL 并发仍需专用环境验证，SQLite 测试不代表该项通过。

### 共享盘保存规则

应用库迁移 `0005_contract_archive` 增加 `archive_path/archived_at`，将原仅暂存系统、尚未写入共享盘的任务恢复为资料待准备。后端 `NETSUITE_SUBPO_ARCHIVE_ROOT` 配置共享盘根目录，运行账号须能访问并写入。共享盘不存在时不会自动创建根目录或降级写到本机。

在项目根目录 `.env` 中手动设置 `NETSUITE_SUBPO_ARCHIVE_ROOT`，值填写绝对路径或 UNC 共享路径，不加引号、不追加日期目录。后端启动时加载该值，代码没有固定共享盘路径或默认回退目录。修改后重启后端生效；已经保存的合同保留原路径，新保存的合同使用新配置。配置优先级为进程环境变量 > `.env.local` > `.env`，请避免同名配置覆盖。配置格式和注释见根目录 `.env.example`。

文件路径为 `根目录/2026年8月17日/子采购订单号供应商.pdf`，日期采用首次获取原件时的北京时间，同一天共用同一目录，重试仍使用原下载日期。非法 Windows 文件名字符替换为下划线，空名称和超长名称拒绝保存。先写完整临时文件再无覆盖发布，校验内容；同名同内容直接复用，同名异内容报冲突。不会覆盖既有合同。

原件暂存在系统数据库用于断网重试及历史追溯，不再暴露文件下载接口。`documents.status=archive_pending` 表示原件已取得但共享盘尚未保存；此时任务仍为 `documents_pending`。共享盘 I/O 在事务锁外，成功后记录路径、文件名、实际保存时间，重新核对来源和审核版本，全部保存成功才推进状态。共享盘成功但数据库提交失败时可重试，同内容文件不会覆盖或重复生成。原件日期和共享盘保存时间分别记录。

`test_contract_archive.py` 使用临时目录覆盖北京时间跨日、同日目录、命名、重复保存、冲突不覆盖、共享盘不可达和缓存重试；不会在测试中写真实共享盘。


### 企微外部群通知（本地登记已实现）

应用库迁移 `0006_task_notifications` 新增不可变通知版本表。通知信息按本任务保存，不作为已验证的企微群绑定，也不自动跨任务复用。后端按真实审核任务生成默认正文，可手动修改；不向通知正文填入内部共享盘路径。所有操作沿用任务身份与环境隔离，提交时再次锁定来源、审核头、任务行并校验快照，版本冲突返回409。

- `POST /api/reconciliation/invoice-tasks/{id}/notification/draft`：`revision`（首次0）、`groupName`（200字以内）、`employee`（100字以内）、`message`（非空且4000字以内）。允许先保存正文、稍后补齐接收信息；每次保存新增版本，记录认证操作者和时间。
- `POST /api/reconciliation/invoice-tasks/{id}/notification/record`：`revision`、`sentAt`（带时区，任务生成至当前时间之间）、`note`（1–500字）、`confirmed=true`。仅当前来源、合同全部归档、接收信息已保存时允许。原子写入人工发送快照并将任务推进为 `awaiting_invoice`；发送快照包含正文、群名、发送员工和合同文件名。相同登记请求重试返回原记录，不重复推进；其他重复或旧版本请求拒绝。
- 两接口返回完整任务详情；新增 `notification` 含默认正文、保存正文、当前版本、操作 `allowed/reason` 及历史版本。登记后通知只读，重新审核保留旧任务历史。

页面明确显示“人工登记已发送”，不是企微回执，不代表供应商已读或已开票。企微官方接口、群身份核验、自动附送合同和收票比对仍未接入；系统不会向外部群发送消息。合同仍从共享盘使用，无网页PDF下载入口。

`backend/tests/test_task_notifications.py` 覆盖真实迁移、持久化、身份隔离、旧版本冲突、重复登记、日期校验、来源变化、历史只读以及事务回滚。SQLite验证不代表MySQL并发验收通过。
