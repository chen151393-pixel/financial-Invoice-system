// 应收看板：开票月份按财务审核通过日期归属，回收期限和金额由后端计算，前端只展示。
export type RecoveryView = "due" | "collected" | "outstanding" | "overdue";

export interface RecoveryQuery {
  // 空为默认月份（本月到期的上月通知）；all 为全部月份；否则为 YYYY-MM
  month: string;
  view: RecoveryView;
  // 空为全部采购员；none 为未指定负责人
  memberId: string;
  companyId: string;
  supplierName: string;
  orderNo: string;
  page: number;
  pageSize: number;
}

export interface RecoverySummary {
  tasks: number;
  suppliers: number;
  amount: string;
  // 应开金额缺失、未计入金额合计的任务数
  unknown: number;
}

export interface RecoveryCards {
  due: RecoverySummary;
  collected: RecoverySummary & { rate: number | null };
  outstanding: RecoverySummary & { daysLeft: number | null };
  overdue: RecoverySummary & { longOverdue: number; months: string[] };
}

export interface RecoveryMonth {
  month: string;
  label: string;
  dueDate: string;
  // closed 已过期限；due 本月到期；open 本月通知、尚在回收期
  state: "closed" | "due" | "open";
  tasks: number;
  collected: number;
  rate: number | null;
  expected: string;
  collectedAmount: string;
  outstandingAmount: string;
  unknown: number;
}

export interface RecoveryBuyer {
  memberId: string;
  name: string;
  tasks: number;
  outstanding: number;
  rate: number | null;
}

export interface RecoveryShare {
  supplierId: number | null;
  name: string;
  amount: string;
  share: number | null;
}

export interface RecoveryConcentration {
  amount: string;
  suppliers: number;
  top: RecoveryShare[];
  topAmount: string;
  topShare: number | null;
  restSuppliers: number;
  restAmount: string;
  restShare: number | null;
}

export interface RecoveryTask {
  taskId: string;
  recordNo: string;
  orders: string[];
  expected: string | null;
  received: string | null;
  outstanding: string | null;
  approvedOn: string;
  dueDate: string;
  collected: boolean;
  node: string;
  nodeLabel: string;
}

export interface RecoveryGroup {
  key: string;
  supplierId: number | null;
  supplierName: string;
  companyId: number | null;
  companyName: string;
  memberId: string;
  memberName: string;
  tasks: number;
  amount: string;
  unknown: number;
  approvedOn: string;
  dueDate: string;
  // 未收回才有剩余天数；负数为已逾期天数
  daysLeft: number | null;
  items: RecoveryTask[];
}

export interface RecoveryOption {
  id: string;
  name: string;
}

export interface RecoveryBoard {
  today: string;
  month: string;
  monthLabel: string;
  dueDate: string | null;
  defaultMonth: string;
  cards: RecoveryCards;
  months: RecoveryMonth[];
  recentRate: number | null;
  buyers: RecoveryBuyer[];
  concentration: RecoveryConcentration;
  list: {
    view: RecoveryView;
    summary: RecoverySummary;
    items: RecoveryGroup[];
    total: number;
    page: number;
    pageSize: number;
    pages: number;
  };
  options: { buyers: RecoveryOption[]; companies: RecoveryOption[]; months: RecoveryOption[] };
}

export interface RecoveryExport {
  filename: string;
  content: string;
  count: number;
}
