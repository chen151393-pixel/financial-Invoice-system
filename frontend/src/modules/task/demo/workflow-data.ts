import type { Tone } from "../../../shared/components/ui";

// 全部为隔离样例，金额、差异与操作资格预先给定，不承载生产业务规则。
export type DemoCategory = "review" | "followup" | "documents";
export interface DemoTask {
  id: string;
  supplier: string;
  declaration: string;
  order: string;
  category: DemoCategory;
  stage: string;
  tone: Tone;
  outstanding: string;
  expected: string;
  received: string;
  blocker: string;
  next: string;
  promise: string;
  timing: string;
  contact: string;
  invoices: string[];
}
export interface DemoCheck {
  field: string;
  basis: string;
  invoice: string;
  result: string;
  different: boolean;
}
export interface DemoInvoice {
  id: string;
  taskId: string;
  number: string;
  amount: string;
  product: string;
  allowed: boolean;
  reason: string;
  checks: DemoCheck[];
}

export const demoTasks: DemoTask[] = [
  {
    id: "sample-01",
    supplier: "示例 · 澄川包装",
    declaration: "DEMO-CD-1021",
    order: "DEMO-PO-0861",
    category: "review",
    stage: "待核票",
    tone: "info",
    outstanding: "18,600.00",
    expected: "18,600.00",
    received: "0.00",
    blocker: "两张发票已到，等待人工确认",
    next: "核对关联发票",
    promise: "2026-10-26",
    timing: "发票已到 · 待核验",
    contact: "10-24 14:20 · 已登记通知",
    invoices: ["sample-invoice-01", "sample-invoice-02"],
  },
  {
    id: "sample-02",
    supplier: "示例 · 远禾纸品",
    declaration: "DEMO-CD-1018",
    order: "DEMO-PO-0855",
    category: "review",
    stage: "需核实单位",
    tone: "warning",
    outstanding: "9,600.00",
    expected: "9,600.00",
    received: "0.00",
    blocker: "发票为“箱”，采购为“个”，缺换算依据",
    next: "查看单位差异",
    promise: "2026-10-25",
    timing: "等待补充换算依据",
    contact: "10-25 09:10 · 已登记通知",
    invoices: ["sample-invoice-03"],
  },
  {
    id: "sample-03",
    supplier: "示例 · 青屿日用品",
    declaration: "DEMO-CD-1016",
    order: "DEMO-PO-0842",
    category: "followup",
    stage: "待催票",
    tone: "warning",
    outstanding: "12,400.00",
    expected: "24,800.00",
    received: "12,400.00",
    blocker: "尚有一批货物未收票，已超承诺日期",
    next: "预览催票草稿",
    promise: "2026-10-23",
    timing: "超承诺 3 天（样例口径）",
    contact: "10-22 16:40 · 已登记通知",
    invoices: [],
  },
  {
    id: "sample-04",
    supplier: "示例 · 沐森贸易",
    declaration: "DEMO-CD-1023",
    order: "DEMO-PO-0873",
    category: "followup",
    stage: "等待开票",
    tone: "info",
    outstanding: "8,640.00",
    expected: "8,640.00",
    received: "0.00",
    blocker: "供应商承诺 10 月 28 日开票",
    next: "查看跟进计划",
    promise: "2026-10-28",
    timing: "承诺日期未到（样例口径）",
    contact: "10-25 11:30 · 已登记通知",
    invoices: [],
  },
  {
    id: "sample-05",
    supplier: "示例 · 星桥工贸",
    declaration: "DEMO-CD-1012",
    order: "DEMO-PO-0826",
    category: "documents",
    stage: "待补回签",
    tone: "progress",
    outstanding: "0.00",
    expected: "32,000.00",
    received: "32,000.00",
    blocker: "票已收齐，仍缺子采购回签合同",
    next: "查看缺失资料",
    promise: "2026-10-22",
    timing: "等待回签合同",
    contact: "10-24 10:15 · 已登记通知",
    invoices: [],
  },
];

const normalChecks: DemoCheck[] = [
  { field: "主体", basis: "示例 · 澄川包装", invoice: "示例 · 澄川包装", result: "一致", different: false },
  {
    field: "规格",
    basis: "纸箱 · 40 × 30 × 25 cm",
    invoice: "纸箱 · 40 × 30 × 25 cm",
    result: "一致",
    different: false,
  },
  { field: "单位", basis: "个", invoice: "个", result: "一致", different: false },
  { field: "币种", basis: "CNY", invoice: "CNY", result: "一致", different: false },
  {
    field: "本次分配数量",
    basis: "500 个（本次候选）",
    invoice: "500 个",
    result: "可分配",
    different: false,
  },
  {
    field: "本次含税金额",
    basis: "9,300.00（本次候选）",
    invoice: "9,300.00",
    result: "一致",
    different: false,
  },
];
export const demoInvoices: DemoInvoice[] = [
  {
    id: "sample-invoice-01",
    taskId: "sample-01",
    number: "DEMO-FP-001",
    amount: "9,300.00",
    product: "纸箱 · 第一批",
    allowed: true,
    reason: "样例校验均通过，可演练人工确认。",
    checks: normalChecks,
  },
  {
    id: "sample-invoice-02",
    taskId: "sample-01",
    number: "DEMO-FP-002",
    amount: "9,300.00",
    product: "纸箱 · 第二批",
    allowed: true,
    reason: "样例校验均通过，可演练人工确认。",
    checks: normalChecks,
  },
  {
    id: "sample-invoice-03",
    taskId: "sample-02",
    number: "DEMO-FP-003",
    amount: "9,600.00",
    product: "纸杯 · 250 ml",
    allowed: false,
    reason: "缺少该商品与规格的单位换算依据；填写说明不能替代换算证据。",
    checks: [
      {
        field: "主体",
        basis: "示例 · 远禾纸品",
        invoice: "示例 · 远禾纸品",
        result: "一致",
        different: false,
      },
      { field: "规格", basis: "纸杯 · 250 ml", invoice: "纸杯 · 250 ml", result: "一致", different: false },
      { field: "单位", basis: "个", invoice: "箱", result: "缺换算依据", different: true },
      { field: "数量", basis: "12,000 个", invoice: "60 箱", result: "暂不能核实", different: true },
      { field: "含税金额", basis: "9,600.00", invoice: "9,600.00", result: "一致", different: false },
    ],
  },
];
