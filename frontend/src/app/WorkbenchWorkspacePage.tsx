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
      actions={<WorkbenchToolbar state={state} />}
    >
      <WorkbenchPage state={state} />
    </AppFrame>
  );
}
