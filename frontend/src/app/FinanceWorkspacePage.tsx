import { Link } from "react-router";
import { FinanceReconciliationPage } from "../modules/reconciliation/pages/FinanceReconciliationPage";
import { AppFrame } from "../shared/components/AppFrame";
import { navigation } from "./navigation";
import { paths } from "./paths";
import { useViewNavigate } from "./useViewNavigate";

export default function FinanceWorkspacePage() {
  const navigateView = useViewNavigate();
  return (
    <AppFrame
      groups={navigation}
      activeId="finance"
      onNavigate={navigateView}
      title="财务核对"
      subtitle="自动列出已入库报关单与关联采购，逐层核对明细后整单审核。"
      mode="live"
      dataLabel="已入库 NS 单据"
      actions={
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Link className="ui-button ui-button--secondary" to={paths.invoiceFollowup}>
            开票跟进
          </Link>
        </div>
      }
      notice="按 NS 报关单引用自动显示关联子采购明细，由财务核对后点击「审核通过」，保存整单审核记录。"
    >
      <FinanceReconciliationPage />
    </AppFrame>
  );
}
