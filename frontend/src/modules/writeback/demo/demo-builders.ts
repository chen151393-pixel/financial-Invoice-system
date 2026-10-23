// 演示数据的记录构造：金额等文本在数据集里写好，这里只组装后端契约形状，不做金额计算。
import type { PreviewLine, WriteSwitch, WritebackItem, WritebackRequest } from "../types";

export type Outcome = "succeeded" | "unknown" | "failed";

/** 一套演示数据：列表、各发票的预览内容、初始记录及“确认回写”后的演示结果。 */
export interface DemoDataset {
  write: WriteSwitch;
  outcome: Outcome;
  items: WritebackItem[];
  specs: Record<string, PreviewSpec>;
  records: { invoiceId: string; requestId: string; state: "pending" | "executing" | Outcome }[];
}

export interface PreviewSpec {
  lines: PreviewLine[];
  total: string;
  /** 后端校验未通过时的原因；有值即不允许执行。 */
  blockedBy?: string;
  /** NS 拒绝写入时演示用的“提交时已收”。 */
  changedReceived?: string;
}

const ok = { allowed: true, reason: "" };
const ago = (minutes: number) => new Date(Date.now() - minutes * 60000).toISOString();
const later = (minutes: number) => new Date(Date.now() + minutes * 60000).toISOString();

export function line(
  billNo: string,
  poNo: string,
  subPoNo: string,
  money: { due: string; received: string; remaining: string; amount: string; after: string },
  check = { passed: true, label: "未超未收" },
): PreviewLine {
  return {
    billNo,
    poNo,
    subPoNo,
    due: money.due,
    received: money.received,
    remaining: money.remaining,
    amount: money.amount,
    receivedAfter: money.after,
    check,
  };
}

export function preview(item: WritebackItem, requestId: string, spec: PreviewSpec): WritebackRequest {
  const checks = [
    { label: "NS 中没有同号、同供应商的发票记录", passed: true, detail: null },
    { label: "发票的全部分配均已确认，无待复核问题", passed: true, detail: null },
    { label: "账单、母采购订单与子采购订单属于同一供应商", passed: true, detail: null },
    {
      label: "每张账单的本次实收不超过 NS 当前未收金额",
      passed: !spec.blockedBy,
      detail: spec.blockedBy ?? null,
    },
  ];
  return {
    requestId,
    invoiceId: item.invoiceId,
    invoiceNo: item.invoiceNo,
    invoiceDate: item.invoiceDate,
    vendorName: item.vendorName,
    vendorRef: "NS 供应商 #1203",
    invoiceAmount: item.amount,
    totalAmount: spec.total,
    currency: item.currency,
    account: "正式账套 5939865",
    phase: "pending",
    label: "待确认",
    message: spec.blockedBy ? "预览已生成，但有校验未通过" : "预览已生成，等待确认",
    createdAt: ago(3),
    createdBy: "管理员",
    expiresAt: later(12),
    readAt: ago(3),
    checks,
    lines: spec.lines,
    totalLabel: "合计",
    operations: [
      "新建 1 条供应商发票主记录：发票编码、开票日期、供应商",
      `新建 ${spec.lines.length} 条发票明细：每张账单的本次实收，关联母采购订单与子采购订单`,
      `更新 ${spec.lines.length} 张供应商账单的累计已收发票金额（合计 +${spec.total}），并关联本发票记录`,
    ],
    execute: spec.blockedBy ? { allowed: false, reason: `校验未通过：${spec.blockedBy}` } : ok,
    refresh: ok,
    verify: { allowed: false, reason: "当前状态无需核实" },
    records: [],
    bills: [],
    poll: false,
    events: [{ at: ago(3), action: "生成预览", actor: "管理员", detail: "" }],
  };
}

/** 由待确认预览推出执行后的记录，演示成功、超时待核实、NS 拒绝三种结果。 */
export function executed(
  pending: WritebackRequest,
  outcome: Outcome,
  changed = "5,000.00",
): WritebackRequest {
  const now = new Date().toISOString();
  const lines = pending.lines;
  const confirm = { at: now, action: "确认回写", actor: "管理员", detail: "" };
  const submit = { at: now, action: "提交 NS", actor: "系统", detail: `已锁定 ${lines.length} 张账单` };
  const base = { ...pending, expiresAt: null, poll: false, execute: { allowed: false, reason: "已执行" } };
  const bills = (
    after: (index: number) => string | null,
    status: (index: number) => string,
    passed: boolean,
  ) =>
    lines.map((l, index) => ({
      billNo: l.billNo,
      subPoNo: l.subPoNo,
      before: l.received,
      amount: l.amount,
      after: after(index),
      status: status(index),
      passed,
    }));
  if (outcome === "succeeded")
    return {
      ...base,
      phase: "succeeded",
      label: "已回写",
      message: "已写入 NetSuite，回读核实一致",
      verify: { allowed: false, reason: "已回写" },
      refresh: { allowed: false, reason: "已回写" },
      records: [
        { label: "供应商发票主记录 #48213", url: null },
        { label: `发票明细 ${lines.map((_, i) => `#9012${i + 1}`).join("、")}`, url: null },
      ],
      bills: bills(
        (i) => lines[i].receivedAfter,
        () => "一致",
        true,
      ),
      events: [
        ...pending.events,
        confirm,
        submit,
        { at: now, action: "NS 返回成功", actor: "系统", detail: "主记录 #48213" },
        { at: now, action: "回读核实一致", actor: "系统", detail: "已释放账单锁" },
      ],
    };
  if (outcome === "unknown")
    return {
      ...base,
      phase: "unknown",
      label: "结果待核实",
      message: "NS 响应超时，无法确认是否已写入；相关账单已锁定，不提供重新提交",
      verify: ok,
      refresh: { allowed: false, reason: "结果待核实时不能重新生成预览" },
      bills: bills(
        () => null,
        () => "待核实",
        false,
      ),
      events: [
        ...pending.events,
        confirm,
        submit,
        { at: now, action: "等待 60 秒无响应", actor: "系统", detail: "标为待核实，未自动重试" },
      ],
    };
  return {
    ...base,
    phase: "failed",
    label: "失败",
    message: `回写失败，NS 未写入任何记录：账单 ${lines[0].billNo} 的已收金额已变化（预览时 ${lines[0].received}，提交时 ${changed}）`,
    verify: { allowed: false, reason: "NS 未写入，无需核实" },
    refresh: ok,
    bills: bills(
      (i) => (i === 0 ? changed : null),
      (i) => (i === 0 ? "已收金额已变化" : "未写入"),
      false,
    ),
    events: [
      ...pending.events,
      confirm,
      submit,
      { at: now, action: "NS 拒绝写入", actor: "系统", detail: "账单已收金额已变化；已释放账单锁" },
    ],
  };
}
