import { SyncBatchDetailPage } from "../modules/sync/pages/SyncBatchDetailPage";
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
      title="同步任务详情"
      subtitle="查看每个账套的日期范围、保存统计和失败原因"
      mode="live"
      dataLabel="柠檬云 · 持久任务记录"
      notice="本页展示柠檬云后台拉取的实际提交结果。明细完整后生成待审核建议，不自动通过比对，不写回 NS。"
    >
      <SyncBatchDetailPage />
    </AppFrame>
  );
}
