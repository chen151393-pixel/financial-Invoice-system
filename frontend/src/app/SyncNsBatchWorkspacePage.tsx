import { Link } from "react-router";
import { NsPlanBatchPage } from "../modules/sync/pages/NsPlanBatchPage";
import { paths } from "./paths";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { useViewNavigate } from "./useViewNavigate";

export default function SyncNsBatchWorkspacePage() {
  const navigate = useViewNavigate();
  return (
    <AppFrame
      groups={navigation}
      activeId="sync"
      onNavigate={navigate}
      title="NS 计划批次详情"
      description="单次定时同步批次的日期范围、各分页执行结果与失败原因"
      breadcrumb={<Link to={paths.syncNs}>NS 数据同步</Link>}
    >
      <NsPlanBatchPage />
    </AppFrame>
  );
}
