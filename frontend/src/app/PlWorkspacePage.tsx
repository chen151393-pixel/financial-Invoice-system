import { PlReconciliationPage } from "../modules/source/pages/PlReconciliationPage";
import { AppFrame } from "./WorkspaceFrame";
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
      description="按 PL 单号联查 NS 报关明细与对应的子采购来源"
      meta={[{ label: "数据来源", value: "NS 正式环境" }]}
    >
      <PlReconciliationPage />
    </AppFrame>
  );
}
