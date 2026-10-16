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
      subtitle="自动列出已入库报关单与关联采购，逐层核对明细后整单审核。"
      mode="live"
      dataLabel="已入库 NS 单据"
      actions={
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Link className="ui-button ui-button--secondary" to={paths.tasks}>
            开票跟进
          </Link>
        </div>
      }
      notice="按 NS 报关单引用自动显示关联子采购明细，财务核对后点击「审核通过」：保存审核记录，冻结子采购的开票数量、单位和含税金额，并按供应商、采购公司和币种自动生成开票任务。"
    >
      <ReviewPage />
    </AppFrame>
  );
}
