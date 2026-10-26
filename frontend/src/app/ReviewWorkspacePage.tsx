import { ReviewPage } from "../modules/review/pages/ReviewPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { useViewNavigate } from "./useViewNavigate";

export default function ReviewWorkspacePage() {
  const navigateView = useViewNavigate();
  return (
    <AppFrame groups={navigation} activeId="finance" onNavigate={navigateView} title="财务核对">
      <ReviewPage />
    </AppFrame>
  );
}
