import { SettlementPage } from "../modules/settlement/pages/SettlementPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { useViewNavigate } from "./useViewNavigate";

export default function SettlementWorkspacePage() {
  const navigateView = useViewNavigate();
  return (
    <AppFrame
      groups={navigation}
      activeId="settlement"
      onNavigate={navigateView}
      title="结汇对账"
      description="回款与报关金额核对：贸易国为香港走香港中转（香港收款 → 资料包 → 汇回境内），贸易国为客户国家走直接收汇。差额只认手续费。"
      meta={[{ label: "数据来源", value: "海关回执成交总价 · 银行水单登记" }]}
    >
      <SettlementPage />
    </AppFrame>
  );
}
