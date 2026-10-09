# 供应商发票平台：保存对象与角色权限

核对日期：2026-09-13。来源为用户提供的 `供应商发票平台.zip`，SHA-256：`e08beb35db78446796a99e0b7ba62ad2f5a03f67f54c895c7da10df3d8a581f4`。以下行号对应压缩包原文件。此次仅做源码核对与语法检查，未运行 NS 脚本、发送通知或修改 NS 数据、角色、部署。

## 已确认的保存链路

页面保存会创建自定义供应商发票主记录及明细，并回写已有供应商账单。仅配置 Bills 的编辑权限不足以覆盖整个用例。

| 文件与位置 | 行为 |
| --- | --- |
| `SWC_CS_VendorInvoice.js:51` | 浏览器检查选中行及金额，设置保存标记，提交页面 |
| `SWC_Sl_VendorInvoice.js:163` | 按发票号码、开票日期、供应商分组，传递账单、母采购单、子采购单及金额 |
| `SWC_Sl_VendorInvoice.js:179` | 提交计划脚本 `customscript_swc_ss_vendorinvoice`，参数为 `custscript_swc_json`、`custscript_swc_userid` |
| `SWC_SS_VendorInvoice.js:22` | 创建 `customrecord_swc_vendor_invoice`，通过子列表创建关联明细 |
| `SWC_MR_Update.js:23` | 确认明细类型为 `customrecord_swc_vendor_invoice_detail`；此文件是另一个汇总修复入口，是否部署或定时执行未知 |
| `SWC_SS_VendorInvoice.js:47` | 加载已有 `vendorbill`，更新累计收票金额和关联发票记录后保存 |
| `SWC_UE_Hide.js:46` | 若已部署且触发 edit 事件，修改发票明细金额会调整对应账单累计金额 |
| `SWC_UE_DeleteRec.js:19` | 若已部署，删除发票时会扣减账单金额并删除关联明细；不属于当前自动录入范围 |

包内没有 RESTlet 入口。Python 后端当前提供 SuiteTalk REST 通用读写能力，尚未实现此平台的完整业务适配。M2M 认证成功不代表已经完成上述多记录写入。

## 业务权限

在“设置 → 用户/角色 → 管理角色 → 编辑 → 权限”配置。以下是源码涉及操作对应的权限基线；自定义记录的中文名称需在本账号按脚本 ID 对照，不把推测名称当作实际菜单名称。

| 页签 | 权限或记录类型 | 首次录入 | 录入后修正 |
| --- | --- | --- | --- |
| 自定义记录 | `customrecord_swc_vendor_invoice`：供应商发票主记录 | 创建 | 编辑 |
| 自定义记录 | `customrecord_swc_vendor_invoice_detail`：供应商发票明细 | 创建 | 编辑 |
| 交易 | Bills／供应商账单，`vendorbill` | 编辑 | 编辑 |
| 交易 | Purchase Order／母采购订单，`purchaseorder` | 查看 | 查看 |
| 自定义记录 | 子采购订单，`customrecord_swc_subpo` | 查看 | 查看 |
| 列表 | Vendors／供应商、Subsidiaries／子公司 | 查看 | 查看 |

当前保存链路没有修改母采购订单、子采购订单、供应商，也没有审批或支付账单。付款记录的读取仅用于 `VendorInvoice.js:121` 的付款单入口；使用该入口时另核对供应商付款记录的查看权限。

自定义记录入口：“自定义 → 列表、记录和字段 → 记录类型”。找到上述两个发票记录类型，在权限页签为业务角色添加权限。`Use Permission List` 模式下，记录类型的权限列表才按此方式生效；不要为方便接入直接改变共享记录的现有访问模式。创建包含查看，编辑包含查看、创建、修改，完全还包含删除。依据：[Oracle 自定义记录权限](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N2879931.html)。

角色的子公司、部门及自定义记录访问限制应覆盖实际处理的单据；字段访问权限、必填项、工作流及其他已部署脚本还需在 NS 中验证，压缩包没有这些配置。

## M2M 与现有任务流程的附加权限

M2M 角色需要 `Log in using OAuth 2.0 Access Tokens`；通过 SuiteTalk REST 访问时，保留 `REST Web Services`（完全）和 `SuiteAnalytics Workbook`（报告页签，编辑）。集成应用及令牌 scope 应与实际接口匹配。依据：[OAuth 角色](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_157771510070.html)、[REST 前置配置](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/article_5085602973.html)。

沿用现有计划任务提交方式时，执行提交操作的角色另需：

| 页签 | 权限 | 级别 |
| --- | --- | --- |
| 设置 | SuiteScript Scheduling／SuiteScript 计划 | 完全 |
| 设置 | SuiteScript | 查看 |
| 列表 | Documents and Files／文档和文件 | 查看，并能访问相关脚本文件夹 |

依据：[SuiteCloud Processors 权限](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1506357231.html)。通过其他脚本提交计划任务时，官方说明执行权限继承调用脚本的用户和角色；需要检查页面部署实际使用的执行角色，不能只看操作人的登录角色。依据：[按需提交计划任务](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1508948669.html)。

页面或后续 RESTlet 的部署受众应覆盖接口角色；计划任务部署应已启用，按需提交的状态为 `Not Scheduled`。不要为了接口访问把业务脚本设为免登录公开。依据：[脚本受众](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/chapter_N2999041.html)、[任务提交要求](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_460871520995.html)。

计划脚本第 64 行还会以固定员工身份发通知邮件。沿用此行为时，应核对固定发件人的有效性、收件人和代发邮件权限；通知失败发生在记录写入之后，不能把通知失败当成整批未写入而重新提交。Oracle 的邮件权限说明见：[代发邮件权限](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_4358552361.html)。本次没有执行通知。

## 字段映射

以下是源码使用的 SuiteScript 字段 ID。页面 `custpage_*` 字段只是输入控件；若使用 SuiteTalk REST，应再核对账户元数据及父子记录接口能力。

| 业务含义 | 保存记录 | 字段 ID |
| --- | --- | --- |
| 发票号码 | 发票主记录 | `name` |
| 开票日期 | 发票主记录 | `custrecord_swc_vi_billdate` |
| 供应商 | 发票主记录 | `custrecord_swc_vi_vendor` |
| 本次实收发票金额 | 发票明细 | `custrecord_swc_cid_current_amount` |
| 主记录关联 | 发票明细 | `custrecord_swc_vid_main` |
| 对应供应商账单 | 发票明细 | `custrecord_swc_vid_bill` |
| 对应母采购订单 | 发票明细 | `custrecord_swc_vid_po` |
| 对应子采购订单 | 发票明细 | `custrecord_swc_vid_subpo` |
| 应收、此前已收金额快照 | 发票明细 | `custrecord_swc_vid_billamount`、`custrecord_swc_vid_billpaied` |
| 账单累计已收发票金额 | 已有供应商账单 | `custbody_swc_vendor_amount` |
| 关联的发票主记录 ID 列表 | 已有供应商账单 | `custbody_swc_bill_vendor_num` |

主记录上的明细子列表为 `recmachcustrecord_swc_vid_main`。金额字段中实际前缀是 `cid`，应按源码保留。账单的 `custbody_swc_bill_vendor_num` 保存关联记录 ID，不能直接写发票号码文本。证据：`SWC_SS_VendorInvoice.js:22`、`:28`、`:47`。

## 自动接入前需要处理的问题

1. 压缩包中的 `SWC_SS_VendorInvoice.js:55` 为 `originalArr.split('\x')`，`node --check` 报 `Invalid hexadecimal escape sequence`。必须对照 NS 现网脚本确认是否为导出损坏或版本差异，不能据此断言现网已经故障，也不能把这份文件直接作为验证通过的部署文件。
2. `SWC_SS_VendorInvoice.js:22` 每次直接创建发票，所给代码中没有查询重复发票或幂等请求。重试可能产生重复记录；账户其他工作流或唯一性设置未提供。
3. 计划脚本先创建所有发票，再逐一回写账单，没有跨记录回滚。中途失败可能留下主明细已创建、账单未更新的部分结果。页面 `SWC_Sl_VendorInvoice.js:190` 还会吞掉任务提交异常，任务 ID 只进入日志。
4. `SWC_SS_VendorInvoice.js:36` 使用页面提交的此前已收金额加本次金额，再于第 48 行覆盖账单。若同一账单原已收 100，在不同发票组中分别登记 20、30，可能先写 120 再写 130，而业务期望是 150；并发提交同一账单也有覆盖风险。相同分组内重复账单行只计算第一次。自动化需要按真实账单聚合、重新校验余额并控制并发。
5. 超额校验主要位于客户端 `SWC_CS_VendorInvoice.js:51`。页面和后台任务没有完整复核提交金额、账单与供应商/订单的归属、重复行及最新可收余额。外部接口需要补齐服务端业务校验。
6. 修改明细后的累计金额联动在 `SWC_UE_Hide.js:48` 只处理 `edit`，按行下标对比新旧金额。采用外部接口更新时，需要验证实际事件类型、部署上下文和明细对应关系，避免遗漏联动或重复累计。

建议由 M2M 调用受认证的 RESTlet，复用经修正的业务保存逻辑，并提供任务及逐条业务结果查询。只有主记录、明细、账单金额和关联均核实成功后，飞书才回写“是否录入系统＝是”；部分成功或结果未知应先核实已有记录，再决定补偿或重试。本次没有实施这一适配。

## 本次验证范围

已检查压缩包内 9 个业务脚本的调用和记录操作；另一个文件是 `decimal.js`。10 个 JavaScript 文件进行了仅解析、不执行的 `node --check`：9 个通过，计划脚本 1 个失败，原因见上文。未进行 NS 运行测试，未修改原压缩包或生产脚本。

压缩包的 `VendorInvoice.js:181` 已使用 `subsidiary` 筛选，和先前下载目录中的 `class` 版本不同；本说明以压缩包为准。上线前仍需核实部署所引用的脚本版本、两个自定义记录的访问模式、字段限制和关联事件脚本。
