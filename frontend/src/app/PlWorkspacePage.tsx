import { PlReconciliationPage } from "../modules/reconciliation/pages/PlReconciliationPage";
import { AppFrame } from "../shared/components/AppFrame";
import { navigation } from "./navigation";
import { useViewNavigate } from "./useViewNavigate";

export default function PlWorkspacePage() {
  const navigateView = useViewNavigate();
  return (
    <AppFrame
      groups={navigation}
      activeId="pl"
      onNavigate={navigateView}
      title="采购报关联查"
      subtitle="按 CD、PL 或真实报关单号查询，查看 NS 采购与报关来源对照。"
      mode="live"
      dataLabel="NS真实数据 · 只读查询"
      notice="按 NS 返回顺序展示来源明细；整单审核请进入独立的“财务核对”页面。"
    >
      <PlReconciliationPage />
    </AppFrame>
  );
}
