import { CustomsMatchPage } from "../modules/review/pages/CustomsMatchPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { useViewNavigate } from "./useViewNavigate";

export default function CustomsMatchWorkspacePage() {
  const navigateView = useViewNavigate();
  return (
    <AppFrame
      groups={navigation}
      activeId="customs-match"
      onNavigate={navigateView}
      title="海关报关单比对"
      description="按真实报关单号匹配 NS 报关单与海关回执，比对明细行的品名、单位和数量，并保存回执中的境外收货人"
      meta={[{ label: "数据来源", value: "NS 正式环境 · 海关回执导入" }]}
    >
      <CustomsMatchPage />
    </AppFrame>
  );
}
