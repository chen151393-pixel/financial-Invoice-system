import { Link, useParams } from "react-router";
import { WritebackListPage } from "../modules/writeback/pages/WritebackListPage";
import { WritebackRequestPage } from "../modules/writeback/pages/WritebackRequestPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { paths } from "./paths";
import { useViewNavigate } from "./useViewNavigate";

export default function WritebackWorkspacePage() {
  const navigateView = useViewNavigate();
  const { requestId } = useParams();
  return (
    <AppFrame
      groups={navigation}
      activeId="writeback"
      onNavigate={navigateView}
      title={requestId ? "回写详情" : "NS 回写"}
      description="整票审核后生成任务，查询候选账单并确认分配方案；当前尚不执行 NS 写入"
      breadcrumb={requestId ? <Link to={paths.writeback}>NS 回写</Link> : undefined}
    >
      {requestId ? <WritebackRequestPage key={requestId} requestId={requestId} /> : <WritebackListPage />}
    </AppFrame>
  );
}
