import { Link } from "react-router";
import { WorkflowDemoPage } from "../modules/task/demo/WorkflowDemoPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { paths } from "./paths";
import { useViewNavigate } from "./useViewNavigate";

export default function TaskWorkflowDemoWorkspacePage() {
  const navigate = useViewNavigate();
  return (
    <AppFrame
      groups={navigation}
      activeId="invoice-followup"
      onNavigate={navigate}
      title="开票跟进 · 优化示例"
      breadcrumb={<Link to={paths.tasks}>开票跟进</Link>}
    >
      <WorkflowDemoPage />
    </AppFrame>
  );
}
