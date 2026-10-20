import { PlReconciliationPage } from "../modules/source/pages/PlReconciliationPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { useViewNavigate } from "./useViewNavigate";

export default function PlWorkspacePage() {
  const navigateView = useViewNavigate();
  return (
    <AppFrame groups={navigation} activeId="pl" onNavigate={navigateView} title="采购报关联查">
      <PlReconciliationPage />
    </AppFrame>
  );
}
