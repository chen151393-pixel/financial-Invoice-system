import { MatchingPage } from "../modules/matching/MatchingPage";
import { AppFrame } from "../shared/components/AppFrame";
import { navigation } from "./navigation";
import { viewPath } from "./views";
export default function MatchingWorkspacePage() {
  return (
    <AppFrame
      groups={navigation}
      activeId="match"
      onNavigate={(target) => location.assign(viewPath(target))}
      title="自动匹配"
      subtitle="发票与子采购单逐项对照及整票关联"
      mode="live"
      dataLabel="真实数据库 · 本地匹配"
      notice="系统按备注订单和商品信息展示候选；人工核对并确认后才保存本地关联，不回写 NS。"
      actions={
        <a className="ui-button" href="/invoices">
          返回进项发票
        </a>
      }
    >
      <MatchingPage />
    </AppFrame>
  );
}
