import { useLocation } from "react-router";
import { ReviewPage } from "../modules/review/pages/ReviewPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { useViewNavigate } from "./useViewNavigate";
import { useReviewLinks } from "./useReviewLinks";

export default function ReviewWorkspacePage() {
  const navigateView = useViewNavigate();
  const links = useReviewLinks();
  const { search } = useLocation();
  return (
    <AppFrame
      groups={navigation}
      activeId="finance"
      onNavigate={navigateView}
      title="财务核对"
      description="核对 NS 报关单与子采购开票口径。财务与海关审核均通过后，系统处理开票任务。"
      meta={[{ label: "数据来源", value: "NS 正式环境" }]}
    >
      <ReviewPage key={search} links={links} />
    </AppFrame>
  );
}
