import { RecoveryBoardPage } from "../modules/task/pages/RecoveryBoardPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { useViewNavigate } from "./useViewNavigate";

export default function RecoveryWorkspacePage() {
  const navigateView = useViewNavigate();
  return (
    <AppFrame
      groups={navigation}
      activeId="invoice-recovery"
      onNavigate={navigateView}
      title="应收看板"
      description="按财务审核通过日期（北京时间）归入开票月份，生成任务后即纳入；本页只读"
      meta={[
        { label: "回收期限", value: "开票月份的次月底前" },
        { label: "已收回", value: "发票全部收齐" },
        { label: "采购员", value: "供应商当前负责人" },
      ]}
    >
      <RecoveryBoardPage />
    </AppFrame>
  );
}
