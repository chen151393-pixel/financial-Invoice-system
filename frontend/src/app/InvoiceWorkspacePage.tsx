import { InvoiceListPage } from "../modules/invoice/pages/InvoiceListPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { useViewNavigate } from "./useViewNavigate";

export default function InvoiceWorkspacePage() {
  const navigateView = useViewNavigate();
  return (
    <AppFrame
      groups={navigation}
      activeId="invoices"
      onNavigate={navigateView}
      title="进项发票"
      description="柠檬云拉取与 Excel 导入的发票，按票面状态与匹配进度管理"
      meta={[{ label: "数据来源", value: "柠檬云账套 · Excel 导入" }]}
    >
      <InvoiceListPage />
    </AppFrame>
  );
}
