// 全部页面路径集中在此；页面和模块之间跳转只用这里的常量。
export const paths = {
  pl: "/pl-reconciliation",
  finance: "/finance-reconciliation",
  invoiceFollowup: "/invoice-followup",
  supplierGroups: "/invoice-followup/supplier-groups",
  invoices: "/invoices",
  matching: "/matching",
  sync: "/sync",
  syncNs: "/sync/ns",
  syncLemon: "/sync/lemon",
} as const;

export const invoiceTaskPath = (id: string) => `${paths.invoiceFollowup}/${encodeURIComponent(id)}`;
export const matchingInvoicePath = (invoiceId: string) =>
  `${paths.matching}?invoiceId=${encodeURIComponent(invoiceId)}`;

// 侧栏菜单项与页面路径的对应。
export type View = "invoices" | "match" | "sync" | "pl" | "finance" | "invoice-followup";

const viewPaths: Record<View, string> = {
  invoices: paths.invoices,
  match: paths.matching,
  sync: paths.sync,
  pl: paths.pl,
  finance: paths.finance,
  "invoice-followup": paths.invoiceFollowup,
};

export function viewPath(view: View): string {
  return viewPaths[view];
}
