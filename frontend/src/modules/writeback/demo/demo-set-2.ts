// 演示数据二：多账单、外币发票、校验未通过与红冲发票；确认后演示“超时待核实”，核实后转为已回写。
import type { WritebackItem } from "../types";
import { line, type DemoDataset } from "./demo-builders";

const ok = { allowed: true, reason: "" };
const item = (
  value: Omit<WritebackItem, "currency" | "preview"> & Partial<WritebackItem>,
): WritebackItem => ({
  currency: "CNY",
  preview: ok,
  ...value,
});

const threeBills = [
  line("VB-20260512-0201", "YE-HH20260510-X1102", "YE-HH20260510-X1102-01", {
    due: "25,000.00",
    received: "5,000.00",
    remaining: "20,000.00",
    amount: "20,000.00",
    after: "25,000.00",
  }),
  line("VB-20260512-0202", "YE-HH20260510-X1102", "YE-HH20260510-X1102-02", {
    due: "18,320.00",
    received: "0.00",
    remaining: "18,320.00",
    amount: "18,320.00",
    after: "18,320.00",
  }),
  line("VB-20260513-0215", "YE-HH20260511-X1108", "YE-HH20260511-X1108-01", {
    due: "30,000.00",
    received: "10,000.00",
    remaining: "20,000.00",
    amount: "20,000.00",
    after: "30,000.00",
  }),
];

export const dataset: DemoDataset = {
  write: { enabled: true, account: "正式账套 5939865", reason: "可生成预览并执行写入" },
  outcome: "unknown",
  items: [
    item({
      invoiceId: "d2-1",
      invoiceNo: "25322000000187340012",
      invoiceDate: "2026-10-18",
      vendorName: "苏州宏达精密机械有限公司",
      amount: "58,320.00",
      purchaseOrders: "YE-HH20260510-X1102 等 3 张",
      allocation: "3 / 3 已确认",
      phase: "ready",
      label: "可回写",
      requestId: null,
      note: null,
    }),
    item({
      invoiceId: "d2-2",
      invoiceNo: "INV-DGLC-2026-0931",
      invoiceDate: "2026-10-17",
      vendorName: "东莞联创电子有限公司",
      amount: "12,450.00",
      currency: "USD",
      purchaseOrders: "YE-HH20260509-X1097",
      allocation: "1 / 1 已确认",
      phase: "ready",
      label: "可回写",
      requestId: null,
      note: null,
    }),
    item({
      invoiceId: "d2-3",
      invoiceNo: "25322000000187340057",
      invoiceDate: "2026-10-18",
      vendorName: "苏州宏达精密机械有限公司",
      amount: "9,000.00",
      purchaseOrders: "YE-HH20260511-X1110",
      allocation: "1 / 1 已确认",
      phase: "pending",
      label: "待确认",
      requestId: "WB-D2-BLOCKED",
      note: "有校验未通过，不能执行",
    }),
    item({
      invoiceId: "d2-4",
      invoiceNo: "25322000000187339980",
      invoiceDate: "2026-10-15",
      vendorName: "苏州宏达精密机械有限公司",
      amount: "-3,600.00",
      purchaseOrders: "YE-HH20260503-X1071",
      allocation: "—",
      phase: "blocked",
      label: "不可回写",
      requestId: null,
      note: null,
      preview: { allowed: false, reason: "红字发票，按冲回流程在 NS 人工处理" },
    }),
    item({
      invoiceId: "d2-5",
      invoiceNo: "INV-DGLC-2026-0918",
      invoiceDate: "2026-10-14",
      vendorName: "东莞联创电子有限公司",
      amount: "7,800.00",
      currency: "USD",
      purchaseOrders: "YE-HH20260505-X1083 等 2 张",
      allocation: "2 / 2 已确认",
      phase: "failed",
      label: "失败",
      requestId: "WB-D2-FAILED",
      note: "账单已收金额已变化，未写入",
    }),
    item({
      invoiceId: "d2-6",
      invoiceNo: "25322000000187339611",
      invoiceDate: "2026-10-11",
      vendorName: "苏州宏达精密机械有限公司",
      amount: "41,200.00",
      purchaseOrders: "YE-HH20260426-X1040 等 2 张",
      allocation: "2 / 2 已确认",
      phase: "succeeded",
      label: "已回写",
      requestId: "WB-D2-DONE",
      note: "NS 发票记录 #48197",
    }),
  ],
  specs: {
    "d2-1": { lines: threeBills, total: "58,320.00" },
    "d2-2": {
      lines: [
        line("VB-20260510-0188", "YE-HH20260509-X1097", "YE-HH20260509-X1097-01", {
          due: "12,450.00",
          received: "0.00",
          remaining: "12,450.00",
          amount: "12,450.00",
          after: "12,450.00",
        }),
      ],
      total: "12,450.00",
    },
    "d2-3": {
      lines: [
        line(
          "VB-20260512-0209",
          "YE-HH20260511-X1110",
          "YE-HH20260511-X1110-01",
          {
            due: "15,000.00",
            received: "8,500.00",
            remaining: "6,500.00",
            amount: "9,000.00",
            after: "17,500.00",
          },
          { passed: false, label: "超出未收 2,500.00" },
        ),
      ],
      total: "9,000.00",
      blockedBy: "账单 VB-20260512-0209 本次实收 9,000.00 超过 NS 未收 6,500.00",
    },
    "d2-5": {
      lines: [
        line("VB-20260506-0160", "YE-HH20260505-X1083", "YE-HH20260505-X1083-01", {
          due: "5,000.00",
          received: "0.00",
          remaining: "5,000.00",
          amount: "5,000.00",
          after: "5,000.00",
        }),
        line("VB-20260506-0161", "YE-HH20260505-X1083", "YE-HH20260505-X1083-02", {
          due: "2,800.00",
          received: "0.00",
          remaining: "2,800.00",
          amount: "2,800.00",
          after: "2,800.00",
        }),
      ],
      total: "7,800.00",
      changedReceived: "1,200.00",
    },
    "d2-6": {
      lines: [
        line("VB-20260428-0122", "YE-HH20260426-X1040", "YE-HH20260426-X1040-01", {
          due: "26,000.00",
          received: "0.00",
          remaining: "26,000.00",
          amount: "26,000.00",
          after: "26,000.00",
        }),
        line("VB-20260428-0123", "YE-HH20260426-X1040", "YE-HH20260426-X1040-02", {
          due: "15,200.00",
          received: "0.00",
          remaining: "15,200.00",
          amount: "15,200.00",
          after: "15,200.00",
        }),
      ],
      total: "41,200.00",
    },
  },
  records: [
    { invoiceId: "d2-3", requestId: "WB-D2-BLOCKED", state: "pending" },
    { invoiceId: "d2-5", requestId: "WB-D2-FAILED", state: "failed" },
    { invoiceId: "d2-6", requestId: "WB-D2-DONE", state: "succeeded" },
  ],
};
