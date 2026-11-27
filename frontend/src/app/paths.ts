// 全部页面路径集中在此；页面和模块之间跳转只用这里的常量。
export const paths = {
  login: "/login",
  workbench: "/workbench",
  pl: "/pl-reconciliation",
  review: "/review",
  // 海关报关单比对（财务核对下的独立页面）
  reviewCustoms: "/review/customs",
  // 结汇对账：收汇总览、报关应收汇、银行收汇明细、香港中转批次、直接收汇明细
  settlement: "/settlement",
  settlementOverview: "/settlement/overview",
  settlementBank: "/settlement/bank-receipts",
  settlementHk: "/settlement/hk-transit",
  settlementHkRegister: "/settlement/hk-transit/register",
  // 非香港中转的总账（2026-11-18 起取代“直接收汇批次”列表）
  settlementDirect: "/settlement/direct",
  settlementDocumentGroups: "/settlement/direct/document-groups",
  settlementDocumentMerge: "/settlement/direct/document-groups/merge",
  // 销售合同买卖双方抬头与印章
  settlementParties: "/settlement/parties",
  tasks: "/tasks",
  supplierTasks: "/tasks/supplier",
  taskWorkflowDemo: "/tasks/workflow-demo",
  // 应收看板：按通知月份审计发票回收，只读
  invoiceRecovery: "/invoice-recovery",
  supplierGroups: "/suppliers",
  supplierOwners: "/suppliers/owners",
  externalGroups: "/suppliers/external-groups",
  invoices: "/invoices",
  matching: "/matching",
  sync: "/sync",
  syncNs: "/sync/ns",
  syncLemon: "/sync/lemon",
  syncBatches: "/sync/batches",
  syncNsBatches: "/sync/ns/batches",
  writeback: "/writeback",
  access: "/settings/access",
  rolePages: "/settings/access/roles",
  forbidden: "/access-denied",
} as const;

// 旧地址，路由中重定向到新地址；保留一个版本后删除。
export const legacyPaths = {
  taskBoard: "/tasks/board",
  finance: "/finance-reconciliation",
  invoiceFollowup: "/invoice-followup",
  supplierGroups: "/invoice-followup/supplier-groups",
  taskSupplierGroups: "/tasks/supplier-groups",
} as const;

export const taskPath = (id: string) => `${paths.tasks}/${encodeURIComponent(id)}`;
export const supplierTaskPath = (id: string, completed = false) =>
  `${paths.supplierTasks}/${encodeURIComponent(id)}${completed ? "?completed=1" : ""}`;

// 带筛选条件的列表地址（工作台业务状态分区跳转用）；空值不写入地址
function withQuery(path: string, filters: Record<string, string>) {
  const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
  return query.size ? `${path}?${query}` : path;
}
export const reviewListPath = (filters: { status?: string }) => withQuery(paths.review, filters);
export const settlementReceiptPath = (consignee = "") =>
  withQuery(paths.settlementHk, { tab: "receipts", consignee });
export const settlementBatchListPath = (consignee: string, batchNo = "") =>
  withQuery(paths.settlementHk, { consignee, batchNo });
export const settlementDirectDocumentsPath = (consignee = "", declarationNo = "") =>
  withQuery(paths.settlementDirect, { tab: "documents", consignee, declarationNo });
export const settlementLedgerPath = (consignee: string) => withQuery(paths.settlementDirect, { consignee });
export const financeDeclarationPath = (exactDeclarationNo: string) =>
  withQuery(paths.review, { exactDeclarationNo });
export const customsDeclarationPath = (exactDeclarationNo: string, importing = false) =>
  withQuery(paths.reviewCustoms, { exactDeclarationNo, importReceipt: importing ? "1" : "" });
export const taskListPath = (filters: {
  stage?: string;
  // 开票跟进节点（documents / notification / invoices / comparison / completion / done）
  node?: string;
  supplierId?: string;
  createdFrom?: string;
  createdTo?: string;
}) => withQuery(paths.tasks, filters);
// 比对审核队列：tier 为置信度分档（high / medium / low），空为全部
export const matchingQueuePath = (filters: { tier?: string }) => withQuery(paths.matching, filters);
export const syncBatchPath = (id: string) => `${paths.syncBatches}/${encodeURIComponent(id)}`;
export const syncNsBatchPath = (id: string, recordType: "plan" | "manual" = "plan") =>
  `${paths.syncNsBatches}/${encodeURIComponent(id)}${recordType === "manual" ? "?recordType=manual" : ""}`;
export const writebackRequestPath = (id: string) => `${paths.writeback}/${encodeURIComponent(id)}`;
export const matchingInvoicePath = (invoiceId: string) =>
  `${paths.matching}/${encodeURIComponent(invoiceId)}`;

export const directDocumentGroupPath = (id: number) => `${paths.settlementDocumentGroups}/${id}`;
export const directDocumentMergePath = (declarationNo: string) =>
  withQuery(paths.settlementDocumentMerge, { declarationNo });

// 侧栏菜单项与页面路径的对应。
export type View =
  | "workbench"
  | "invoices"
  | "match"
  | "sync"
  | "pl"
  | "finance"
  | "customs-match"
  | "settlement"
  | "invoice-followup"
  | "invoice-recovery"
  | "writeback"
  | "supplier-profiles"
  | "access";

const viewPaths: Record<View, string> = {
  workbench: paths.workbench,
  invoices: paths.invoices,
  match: paths.matching,
  sync: paths.sync,
  pl: paths.pl,
  finance: paths.review,
  "customs-match": paths.reviewCustoms,
  settlement: paths.settlementOverview,
  "invoice-followup": paths.tasks,
  "invoice-recovery": paths.invoiceRecovery,
  writeback: paths.writeback,
  "supplier-profiles": paths.supplierGroups,
  access: paths.access,
};

export function viewPath(view: View): string {
  return viewPaths[view];
}

// 侧栏子页面与路径的对应；子页面沿用所属菜单项的页面权限。
export type SubView =
  | "settlement-overview"
  | "settlement-declarations"
  | "settlement-bank"
  | "settlement-hk"
  | "settlement-direct"
  | "settlement-parties";

const subViewPaths: Record<SubView, string> = {
  "settlement-overview": paths.settlementOverview,
  "settlement-declarations": paths.settlement,
  "settlement-bank": paths.settlementBank,
  "settlement-hk": paths.settlementHk,
  "settlement-direct": paths.settlementDirect,
  "settlement-parties": paths.settlementParties,
};

export function subViewPath(id: string): string | undefined {
  return Object.hasOwn(subViewPaths, id) ? subViewPaths[id as SubView] : undefined;
}

export function homePath(pages: readonly string[] = []): string {
  if (pages.includes("workbench")) return paths.workbench;
  const first = pages.find((code): code is View => Object.hasOwn(viewPaths, code));
  return first ? viewPaths[first] : paths.forbidden;
}

// 侧栏详情保持当前结汇子页面与筛选，直接访问时默认落在报关单明细。
export function settlementDeclarationDetailPath(
  number: string,
  pathname: string = paths.settlement,
  search = "",
) {
  const query = new URLSearchParams(search);
  query.set("detail", number);
  return `${pathname}?${query}`;
}

// 总览阶段金额图跳转报关单明细；筛选条件保留在 URL。
export const settlementStagePath = (filters: {
  route: string;
  stage: string;
  currency: string;
  consignee: string;
}) => withQuery(paths.settlement, { view: "declarations", ...filters });

export function settlementHkRegistrationPath(numbers: readonly string[], draftId: string) {
  const params = new URLSearchParams({ draft: draftId });
  numbers.forEach((number) => params.append("declarationNo", number));
  return `${paths.settlementHkRegister}?${params}`;
}

// 总览待办入口：只携带展示范围，不在前端推断业务是否可办理。
export function settlementOverviewActionPath(
  action: {
    target: "declarations" | "hk" | "receipts" | "ledger";
    consignee: string;
    route: string;
    stage: string;
    batchNo: string;
  },
  currency: string,
) {
  const common = { consignee: action.consignee, currency };
  if (action.target === "hk") return withQuery(paths.settlementHk, { ...common, batchNo: action.batchNo });
  if (action.target === "receipts") return withQuery(paths.settlementHk, { ...common, tab: "receipts" });
  if (action.target === "ledger") return withQuery(paths.settlementDirect, common);
  return settlementStagePath({ ...common, route: action.route, stage: action.stage });
}
