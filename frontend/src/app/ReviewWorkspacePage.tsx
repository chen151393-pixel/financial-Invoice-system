import { ReviewPage } from "../modules/review/pages/ReviewPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { useViewNavigate } from "./useViewNavigate";

export default function ReviewWorkspacePage() {
  const navigateView = useViewNavigate();
  return (
    <AppFrame
      groups={navigation}
      activeId="finance"
      onNavigate={navigateView}
      title="财务核对"
      description="核对 NS 报关单与子采购开票口径，整单审核通过后按供应商自动生成开票任务"
      meta={[{ label: "数据来源", value: "NS 正式环境" }]}
    >
      <ReviewPage />
    </AppFrame>
  );
}
