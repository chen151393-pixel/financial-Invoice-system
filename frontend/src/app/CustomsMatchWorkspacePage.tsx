import { useLocation } from "react-router";
import { CustomsMatchPage } from "../modules/review/pages/CustomsMatchPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { useViewNavigate } from "./useViewNavigate";
import { useReviewLinks } from "./useReviewLinks";

export default function CustomsMatchWorkspacePage() {
  const navigateView = useViewNavigate();
  const links = useReviewLinks();
  const { search } = useLocation();
  return (
    <AppFrame
      groups={navigation}
      activeId="customs-match"
      onNavigate={navigateView}
      title="报关单比对"
      description="导入海关回执，核对 NS 报关单的品名、单位和数量。海关与财务审核均通过后，系统处理开票任务。"
      meta={[{ label: "数据来源", value: "NS 正式环境 · 海关回执导入" }]}
    >
      <CustomsMatchPage key={search} links={links} />
    </AppFrame>
  );
}
