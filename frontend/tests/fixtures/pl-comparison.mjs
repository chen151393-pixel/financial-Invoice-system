// 合成样本只用于组件验证，不连接真实NS或业务数据库。
export function createPlComparisonState() {
  const purchase = {
    id: "p1",
    child: "SUB-TEST",
    parent: "PO-TEST",
    name: "合成相纸",
    model: "A4",
    supplier: "合成供应商",
    quantity: "12.5000",
    unit: "千克",
    price: "2.00",
    amount: "9007199254740993.01",
    currency: "CNY",
    note: "合成来源备注",
  };
  const group = {
    id: "101",
    snapshotId: "00000000-0000-4000-8000-000000000001",
    recordNumber: "CDTEST001",
    declaration: "合成真实报关号",
    pl: "PL-TEST",
    company: "合成申报公司",
    customsCount: 1,
    purchaseCount: 1,
    warnings: [],
    unlinkedLines: [],
    review: {
      status: "pending",
      label: "待审核",
      allowed: true,
      reason: "",
      reviewedAt: null,
      reviewedBy: null,
      note: "",
    },
    customsLines: [
      {
        id: "customs:0",
        lineNo: 1,
        name: "合成相纸",
        model: "A4",
        quantity: "12.5000",
        unit: "千克",
        price: "1.30",
        amount: "16.2500",
        currency: "USD",
        purchaseCount: 1,
        purchaseLines: [purchase],
      },
    ],
  };
  return {
    kind: "ready",
    result: {
      source: "netsuite",
      requestId: "synthetic-1",
      readCompletedAt: "2026-09-23T01:00:00Z",
      groups: [group],
      counts: { all: 1, pending: 1, approved: 0, blocked: 0, shown: 1, customs: 1, purchase: 1 },
      notices: [],
    },
  };
}
