import { useEffect } from "react";
import { FinanceReconciliationPage } from "../modules/reconciliation/pages/FinanceReconciliationPage";
import { AppFrame } from "../shared/components/AppFrame";
import { navigation } from "./navigation";
import { viewPath } from "./views";

export default function FinanceWorkspacePage() {
  useEffect(() => {
    if (location.pathname !== "/finance-reconciliation")
      history.replaceState(null, "", "/finance-reconciliation");
  }, []);
  return (
    <AppFrame
      groups={navigation}
      activeId="finance"
      onNavigate={(target) => location.assign(viewPath(target))}
      title="财务核对"
      subtitle="自动列出已入库报关单与关联采购，逐层核对明细后整单审核。"
      mode="live"
      dataLabel="已入库 NS 单据"
      actions={
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <a className="ui-button ui-button--secondary" href="/finance-reconciliation/example">
            查看闭环示例
          </a>
          <a className="ui-button ui-button--secondary" href="/invoice-followup">
            开票跟进
          </a>
        </div>
      }
      notice="按 NS 报关单引用自动显示关联子采购明细，由财务核对后点击「审核通过」，保存整单审核记录。"
    >
      <FinanceReconciliationPage />
    </AppFrame>
  );
}
