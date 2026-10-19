import { WorkbenchToolbar } from "../modules/matching/components/WorkbenchToolbar";
import { useWorkbench } from "../modules/matching/hooks/useWorkbench";
import { WorkbenchPage } from "../modules/matching/pages/WorkbenchPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { useViewNavigate } from "./useViewNavigate";

export default function WorkbenchWorkspacePage() {
  const navigate = useViewNavigate();
  const state = useWorkbench();
  return (
    <AppFrame
      groups={navigation}
      activeId="workbench"
      onNavigate={navigate}
      title="发票工作台"
      subtitle="先处理待复核事项，再推进核对与开票，让每一笔业务及时闭环。"
      mode="live"
      dataLabel="已入库业务数据"
      notice={null}
      actions={<WorkbenchToolbar state={state} />}
    >
      <WorkbenchPage state={state} />
    </AppFrame>
  );
}
