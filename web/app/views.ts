export type View =
  | "dashboard"
  | "invoices"
  | "match"
  | "exceptions"
  | "sync"
  | "pl"
  | "finance"
  | "invoice-followup"
  | "reconcile"
  | "writeback";

// 正式页面在同一主应用中运行；其余视图继续使用现有演示入口。
export const workspaceRoutes: Partial<Record<View, string>> = {
  invoices: "/invoices",
  match: "/matching",
  sync: "/sync",
  pl: "/pl-reconciliation",
  finance: "/finance-reconciliation",
  "invoice-followup": "/invoice-followup",
};

export function viewPath(view: View): string {
  return workspaceRoutes[view] ?? `/demo?view=${view}`;
}
