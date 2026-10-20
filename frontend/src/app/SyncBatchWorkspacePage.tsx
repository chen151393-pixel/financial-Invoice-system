import { Link } from "react-router";
import { SyncBatchDetailPage } from "../modules/sync/pages/SyncBatchDetailPage";
import { paths } from "./paths";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { useViewNavigate } from "./useViewNavigate";

export default function SyncBatchWorkspacePage() {
  const navigate = useViewNavigate();
  return (
    <AppFrame
      groups={navigation}
      activeId="sync"
      onNavigate={navigate}
      title="同步批次详情"
      breadcrumb={
        <>
          <Link to={paths.sync}>数据同步</Link> / <Link to={paths.sync}>执行记录</Link>
        </>
      }
    >
      <SyncBatchDetailPage />
    </AppFrame>
  );
}
