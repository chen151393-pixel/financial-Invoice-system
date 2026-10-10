import { Link } from "react-router";
import { MatchingPage } from "../modules/matching/MatchingPage";
import { AppFrame } from "../shared/components/AppFrame";
import { navigation } from "./navigation";
import { paths } from "./paths";
import { useViewNavigate } from "./useViewNavigate";
export default function MatchingWorkspacePage() {
  const navigateView = useViewNavigate();
  return (
    <AppFrame
      groups={navigation}
      activeId="match"
      onNavigate={navigateView}
      title="自动匹配"
      subtitle="发票与子采购单逐项对照及整票关联"
      mode="live"
      dataLabel="真实数据库 · 本地匹配"
      notice="系统按备注订单和商品信息展示候选；人工核对并确认后才保存本地关联，不回写 NS。"
      actions={
        <Link className="ui-button" to={paths.invoices}>
          返回进项发票
        </Link>
      }
    >
      <MatchingPage />
    </AppFrame>
  );
}
