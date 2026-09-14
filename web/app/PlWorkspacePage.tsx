import { useEffect } from "react";
import { PlReconciliationPage } from "../modules/reconciliation/pages/PlReconciliationPage";
import { AppFrame } from "../shared/components/AppFrame";
import { navigation } from "./navigation";

export default function PlWorkspacePage() {
  useEffect(() => {
    if (location.pathname !== "/pl-reconciliation") history.replaceState(null, "", "/pl-reconciliation");
  }, []);
  return (
    <AppFrame
      groups={navigation}
      activeId="pl"
      onNavigate={(target) =>
        location.assign(target === "pl" ? "/pl-reconciliation" : `/demo?view=${target}`)
      }
      title="PL 采购报关核对"
      subtitle="根据 PL 和申报公司，拉取对应的子采购订单与报关明细。"
      mode="live"
    >
      <PlReconciliationPage />
    </AppFrame>
  );
}
