import { useState } from "react";
import { Alert, Badge, Button, Card, CardContent, CardHeader } from "../../../shared/components/ui";
import { syncDirectory } from "../api";
import { formatTime } from "../format";
import type { SyncRun } from "../types";

const STATUS = {
  running: { label: "同步中", tone: "info" },
  succeeded: { label: "同步成功", tone: "success" },
  failed: { label: "同步失败", tone: "danger" },
} as const;

/** 飞书部门与成员同步：手动立即同步，另有每日定时同步；结果以后端同步记录为准。 */
export function SyncCard({
  configured,
  lastSync,
  onDone,
}: {
  configured: boolean;
  lastSync: SyncRun | null;
  onDone: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    setBusy(true);
    setError("");
    try {
      await syncDirectory();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "飞书同步失败");
    } finally {
      await onDone();
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title="飞书同步"
        description="从飞书读取部门，并同步“同步范围”内部门的成员；每天另自动同步一次"
        actions={
          <Button variant="primary" disabled={!configured || busy} onClick={() => void run()}>
            {busy ? "同步中…" : "立即同步飞书"}
          </Button>
        }
      />
      <CardContent>
        {!configured ? (
          <Alert tone="warning" title="飞书应用尚未配置">
            请在服务器配置 FEISHU_APP_ID 与 FEISHU_APP_SECRET 后重启服务，再同步部门。
          </Alert>
        ) : lastSync ? (
          <div className="identity-access-sync" role="status">
            <Badge tone={STATUS[lastSync.status].tone}>{STATUS[lastSync.status].label}</Badge>
            <span>
              {lastSync.trigger === "schedule" ? "定时同步" : "手动同步"}，开始于{" "}
              {formatTime(lastSync.startedAt)}
            </span>
            {lastSync.status === "succeeded" && (
              <span>
                部门 {lastSync.departments} 个；新增 {lastSync.usersAdded} 人，变更 {lastSync.usersUpdated}{" "}
                人，停用 {lastSync.usersDeactivated} 人
              </span>
            )}
          </div>
        ) : (
          <p className="identity-access-muted">尚未同步。先同步飞书部门，再选择同步范围并设置部门角色。</p>
        )}
        {(error || lastSync?.error) && (
          <Alert tone="danger" title="同步未完成">
            {error || lastSync?.error}（同步失败时不会停用任何人员）
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}
