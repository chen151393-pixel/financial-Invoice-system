// 仅用于独立演示页，数量、金额和状态均为固定示例，不作为业务判断依据。
export type FollowupTask = {
  id: string;
  supplier: string;
  declaration: string;
  purchase: string;
  stage: number;
  status: string;
  tone: "normal" | "attention" | "done";
  category: "supplier" | "mine" | "done";
  description: string;
  next: string;
  owner: string;
  elapsed: string;
  due: string;
  total: string;
  received: string;
  confirmed: string;
  invoiceCount: string;
  tracking: { awaitingInvoice: boolean; receivedInvoices: number; needsAttention: boolean };
  comparisonProgress?: string;
  documentsReady: boolean;
  notification: string;
  action: string;
  history: { time: string; title: string; detail: string }[];
};

export const stages = ["财务审核", "资料准备", "通知供应商", "等待收票", "发票比对", "完成"];

export const followupTasks: FollowupTask[] = [
  {
    id: "KP-202609-001",
    tracking: { awaitingInvoice: true, receivedInvoices: 0, needsAttention: false },
    supplier: "宁波海川五金有限公司",
    declaration: "CD-2609018",
    purchase: "PO-2608126",
    stage: 3,
    status: "等待供应商开票",
    tone: "normal",
    category: "supplier",
    description: "开票资料已送出，等待供应商提交本次采购发票。",
    next: "可预览催票通知，或查看已发送的开票资料。",
    owner: "供应商 · 陈女士",
    elapsed: "已等待 2 天",
    due: "2026-09-26",
    total: "¥128,600.00",
    received: "¥0.00",
    confirmed: "¥0.00",
    invoiceCount: "尚未收票",
    documentsReady: true,
    notification: "已发送 · 09-22 10:05",
    action: "预览催票通知",
    history: [
      {
        time: "09-22 10:05",
        title: "开票通知已发送",
        detail: "发送至供应商联系人；附本次开票清单与子采购单。示例不代表已读。",
      },
      { time: "09-22 10:03", title: "开票资料已准备", detail: "采购单与本次开票范围已保存为版本 V1。" },
      { time: "09-22 10:00", title: "财务审核通过", detail: "林晓 · 已保存本次报关及关联采购的审核快照。" },
    ],
  },
  {
    id: "KP-202609-002",
    tracking: { awaitingInvoice: true, receivedInvoices: 2, needsAttention: false },
    supplier: "苏州恒远精密制造有限公司",
    declaration: "CD-2609018",
    purchase: "PO-2608132",
    stage: 3,
    status: "部分收票",
    tone: "normal",
    category: "supplier",
    description: "已收到首批发票，尚有部分开票范围等待供应商补齐。",
    next: "已收发票可先行比对，剩余部分继续跟进。",
    owner: "供应商 · 周先生",
    elapsed: "已等待 1 天",
    due: "2026-09-27",
    total: "¥96,000.00",
    received: "¥60,000.00",
    confirmed: "¥40,000.00",
    invoiceCount: "已收 2 张 · 1 张已确认",
    comparisonProgress: "部分已确认",
    documentsReady: true,
    notification: "已发送 · 09-23 09:10",
    action: "查看已收发票",
    history: [
      {
        time: "09-24 09:30",
        title: "首批发票部分确认",
        detail: "已收票 ¥60,000.00，其中 ¥40,000.00 已确认匹配。",
      },
      { time: "09-23 09:10", title: "开票通知已发送", detail: "供应商按本次开票范围分批提交发票。" },
      { time: "09-23 09:00", title: "审核与资料准备完成", detail: "本次开票范围已确认，采购文件版本 V1。" },
    ],
  },
  {
    id: "KP-202609-003",
    tracking: { awaitingInvoice: false, receivedInvoices: 1, needsAttention: true },
    supplier: "宁波海川五金有限公司",
    declaration: "CD-2609021",
    purchase: "PO-2608140",
    stage: 4,
    status: "比对存在差异",
    tone: "attention",
    category: "mine",
    description: "发票含税金额与本次采购依据相差 ¥200.00，需要财务核实。",
    next: "核对差异明细后联系供应商更正，原始发票与记录保留。",
    owner: "财务 · 林晓",
    elapsed: "待处理 3 小时",
    due: "2026-09-24",
    total: "¥42,800.00",
    received: "¥43,000.00",
    confirmed: "¥0.00",
    invoiceCount: "已收 1 张 · 待核实",
    documentsReady: true,
    notification: "已发送 · 09-22 14:00",
    action: "查看比对差异",
    history: [
      { time: "09-24 09:00", title: "比对发现金额差异", detail: "含税金额差额 +¥200.00，尚未确认分配。" },
      { time: "09-24 08:55", title: "收到供应商发票", detail: "示例发票 INV-DEMO-003，共 1 项商品。" },
      { time: "09-22 14:00", title: "开票通知已发送", detail: "通知关联采购单 PO-2608140 与开票清单 V1。" },
      { time: "09-22 13:50", title: "财务审核通过", detail: "林晓 · 本次审核范围已留存。" },
    ],
  },
  {
    id: "KP-202609-004",
    tracking: { awaitingInvoice: true, receivedInvoices: 0, needsAttention: true },
    supplier: "嘉兴嘉禾包装有限公司",
    declaration: "CD-2609024",
    purchase: "PO-2608156",
    stage: 1,
    status: "采购单获取失败",
    tone: "attention",
    category: "mine",
    description: "子采购单附件暂时无法获取，开票资料尚未齐备。",
    next: "核实采购单文件来源后重新准备资料；供应商通知尚未发送。",
    owner: "采购 · 赵明",
    elapsed: "停留 20 分钟",
    due: "2026-09-28",
    total: "¥18,500.00",
    received: "¥0.00",
    confirmed: "¥0.00",
    invoiceCount: "尚未收票",
    documentsReady: false,
    notification: "未发送 · 等待资料",
    action: "查看失败原因",
    history: [
      {
        time: "09-24 11:40",
        title: "采购单文件获取失败",
        detail: "文件服务暂不可用。下一节点已暂停，不影响已保存的审核记录。",
      },
      { time: "09-24 11:38", title: "财务审核通过", detail: "林晓 · 审核快照已保存。" },
    ],
  },
  {
    id: "KP-202609-005",
    tracking: { awaitingInvoice: true, receivedInvoices: 0, needsAttention: true },
    supplier: "苏州恒远精密制造有限公司",
    declaration: "CD-2609026",
    purchase: "PO-2608161",
    stage: 2,
    status: "通知结果待核实",
    tone: "attention",
    category: "mine",
    description: "通知请求已提交，但尚未取得发送结果。",
    next: "先核实原通知的发送记录，避免供应商重复收到开票通知。",
    owner: "采购 · 赵明",
    elapsed: "待核实 10 分钟",
    due: "2026-09-28",
    total: "¥75,200.00",
    received: "¥0.00",
    confirmed: "¥0.00",
    invoiceCount: "尚未收票",
    documentsReady: true,
    notification: "结果未知 · 请核实",
    action: "查看通知记录",
    history: [
      { time: "09-24 11:50", title: "通知发送结果待核实", detail: "已保留原请求标识，暂停再次发送。" },
      { time: "09-24 11:48", title: "开票资料已准备", detail: "资料版本 V1 已保存。" },
      { time: "09-24 11:45", title: "财务审核通过", detail: "林晓 · 本次审核范围已留存。" },
    ],
  },
  {
    id: "KP-202609-006",
    tracking: { awaitingInvoice: false, receivedInvoices: 1, needsAttention: false },
    supplier: "宁波海川五金有限公司",
    declaration: "CD-2609012",
    purchase: "PO-2608095",
    stage: 5,
    status: "已完成",
    tone: "done",
    category: "done",
    description: "本次开票范围已全部收票，且已确认匹配。",
    next: "可查看关联资料及完整操作记录；本流程完成不代表已付款或已回写 NS。",
    owner: "财务 · 林晓",
    elapsed: "09-24 已完成",
    due: "2026-09-24",
    total: "¥64,800.00",
    received: "¥64,800.00",
    confirmed: "¥64,800.00",
    invoiceCount: "已收 1 张 · 已确认",
    documentsReady: true,
    notification: "已发送 · 09-20 10:00",
    action: "查看比对结果",
    history: [
      {
        time: "09-24 10:20",
        title: "本次开票任务完成",
        detail: "全部收票且确认匹配，未执行 NS 回写或付款。",
      },
      { time: "09-24 10:18", title: "财务确认比对结果", detail: "林晓 · 本次确认 ¥64,800.00。" },
      { time: "09-23 16:30", title: "发票已接收", detail: "示例发票 INV-DEMO-006，已进入比对。" },
      { time: "09-20 10:00", title: "开票通知已发送", detail: "采购依据及开票清单 V1 随通知发送。" },
      { time: "09-20 09:50", title: "审核与资料准备完成", detail: "财务审核快照及开票范围已保存。" },
    ],
  },
];

export type FollowupGroupBy = "supplier" | "declaration";
export type FollowupGroup = {
  key: string;
  tasks: FollowupTask[];
  relatedCount: number;
  awaitingCount: number;
  receivedCount: number;
  attentionCount: number;
};

// 仅聚合原型的固定数量标记，不计算金额、不推断业务状态；正式版由后端提供分组响应。
export function groupFollowupTasks(tasks: FollowupTask[], groupBy: FollowupGroupBy): FollowupGroup[] {
  const groups = new Map<string, FollowupTask[]>();
  for (const task of tasks) {
    const key = task[groupBy];
    const current = groups.get(key) ?? [];
    current.push(task);
    groups.set(key, current);
  }
  return Array.from(groups, ([key, members]) => ({
    key,
    tasks: members,
    relatedCount: new Set(members.map((task) => task[groupBy === "supplier" ? "declaration" : "supplier"]))
      .size,
    awaitingCount: members.filter((task) => task.tracking.awaitingInvoice).length,
    receivedCount: members.reduce((total, task) => total + task.tracking.receivedInvoices, 0),
    attentionCount: members.filter((task) => task.tracking.needsAttention).length,
  }));
}
