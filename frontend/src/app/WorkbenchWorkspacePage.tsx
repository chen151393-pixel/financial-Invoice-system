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
      title="总体工作台"
      description="报关审核、开票任务、收票与发票比对一屏总览"
    >
      <WorkbenchPage state={state} />
    </AppFrame>
  );
}
