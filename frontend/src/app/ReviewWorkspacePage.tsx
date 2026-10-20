import { Link } from "react-router";
import { ReviewPage } from "../modules/review/pages/ReviewPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { paths } from "./paths";
import { useViewNavigate } from "./useViewNavigate";

export default function ReviewWorkspacePage() {
  const navigateView = useViewNavigate();
  return (
    <AppFrame
      groups={navigation}
      activeId="finance"
      onNavigate={navigateView}
      title="财务核对"
      actions={
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Link className="ui-button ui-button--secondary" to={paths.tasks}>
            开票跟进
          </Link>
        </div>
      }
    >
      <ReviewPage />
    </AppFrame>
  );
}
