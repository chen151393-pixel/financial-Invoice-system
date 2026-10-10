export type View = "invoices" | "match" | "sync" | "pl" | "finance" | "invoice-followup";

// 菜单只列正式页面；演示页面已删除。
export const workspaceRoutes: Record<View, string> = {
  invoices: "/invoices",
  match: "/matching",
  sync: "/sync",
  pl: "/pl-reconciliation",
  finance: "/finance-reconciliation",
  "invoice-followup": "/invoice-followup",
};

export function viewPath(view: View): string {
  return workspaceRoutes[view];
}
