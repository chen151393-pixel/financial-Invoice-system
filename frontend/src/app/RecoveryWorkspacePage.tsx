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
      description="按通知月份统计开票任务的发票回收；本页只读，处理任务请到开票跟进"
      meta={[
        { label: "回收期限", value: "通知后次月底前" },
        { label: "已收回", value: "发票全部收齐" },
        { label: "采购员", value: "供应商当前负责人" },
      ]}
    >
      <RecoveryBoardPage />
    </AppFrame>
  );
}
