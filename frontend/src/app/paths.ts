// 全部页面路径集中在此；页面和模块之间跳转只用这里的常量。
export const paths = {
  login: "/login",
  workbench: "/workbench",
  pl: "/pl-reconciliation",
  review: "/review",
  tasks: "/tasks",
  taskWorkflowDemo: "/tasks/workflow-demo",
  supplierGroups: "/suppliers",
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

// 带筛选条件的列表地址（工作台业务状态分区跳转用）；空值不写入地址
function withQuery(path: string, filters: Record<string, string>) {
  const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
  return query.size ? `${path}?${query}` : path;
}
export const reviewListPath = (filters: { status?: string }) => withQuery(paths.review, filters);
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
export const syncNsBatchPath = (id: string) => `${paths.syncNsBatches}/${encodeURIComponent(id)}`;
export const writebackRequestPath = (id: string) => `${paths.writeback}/${encodeURIComponent(id)}`;
export const matchingInvoicePath = (invoiceId: string) =>
  `${paths.matching}/${encodeURIComponent(invoiceId)}`;

// 侧栏菜单项与页面路径的对应。
export type View =
  | "workbench"
  | "invoices"
  | "match"
  | "sync"
  | "pl"
  | "finance"
  | "invoice-followup"
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
  "invoice-followup": paths.tasks,
  writeback: paths.writeback,
  "supplier-profiles": paths.supplierGroups,
  access: paths.access,
};

export function viewPath(view: View): string {
  return viewPaths[view];
}
