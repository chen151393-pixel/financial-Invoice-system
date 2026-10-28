import { useSearchParams } from "react-router";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardHeader,
  ErrorState,
  Skeleton,
  Dialog,
} from "../../../shared/components/ui";
import { DirectoryConfirmation } from "../components/DirectoryConfirmation";
import { DirectoryPicker } from "../components/DirectoryPicker";
import { ImportedDirectory } from "../components/ImportedDirectory";
import { useAccess } from "../hooks/useAccess";
import { useDirectorySelection } from "../hooks/useDirectorySelection";
import { formatTime } from "../format";
import "./access.css";

export function AccessPage() {
  const [params, setParams] = useSearchParams();
  const { data, error, loading, reload } = useAccess();
  const flow = useDirectorySelection(reload);
  function chooseImportedDepartment(id: string) {
    const next = new URLSearchParams(params);
    for (const key of ["member", "page", "department"]) next.delete(key);
    setParams(next, { replace: true });
    flow.chooseDepartment(id);
  }
  if (!data)
    return loading ? (
      <Skeleton rows={6} label="正在读取人员与权限" />
    ) : (
      <ErrorState
        title="人员与权限读取失败"
        message={error}
        action={<Button onClick={() => void reload()}>重新读取</Button>}
      />
    );
  return (
    <div className="identity-access-page">
      <Card>
        <CardHeader
          title="飞书组织同步"
          description="默认展示已导入员工。点击同步飞书读取最新组织，选择部门或人员后确认导入。"
          actions={
            <Button
              variant="primary"
              disabled={(flow.busy && data.feishuConfigured) || !data.feishuConfigured}
              onClick={() => void flow.start()}
            >
              {flow.busy ? "正在处理…" : "同步飞书"}
            </Button>
          }
        />
        <CardContent>
          {!data.feishuConfigured ? (
            <Alert tone="warning">请先配置飞书应用 App ID 与 App Secret。</Alert>
          ) : (
            <p className="identity-access-muted">
              {data.lastSync
                ? `最近同步：${formatTime(data.lastSync.startedAt)} · ${data.lastSync.status === "succeeded" ? "成功" : data.lastSync.status === "failed" ? "失败" : "进行中"} · 新增 ${data.lastSync.usersAdded} 人，更新 ${data.lastSync.usersUpdated} 人，移出 ${data.lastSync.usersDeactivated} 人`
                : "尚未导入成员。选择部门或人员后，确认同步范围。"}{" "}
              保存范围后每日自动同步，新增人员默认待授权。
            </p>
          )}
          {data.lastSync?.error && <Alert tone="danger">{data.lastSync.error}</Alert>}
        </CardContent>
      </Card>
      {error && (
        <ErrorState
          title="页面刷新失败"
          message={error}
          action={<Button onClick={() => void reload()}>重新读取</Button>}
        />
      )}
      {flow.error && (
        <Alert tone="danger" title="操作未完成">
          {flow.error}
        </Alert>
      )}
      {flow.busy && !flow.preview && <Alert>正在读取飞书组织，已导入员工仍可查看。</Alert>}
      {flow.preview && <DirectoryPicker flow={flow} />}
      {flow.plan && (
        <Dialog title="确认同步范围" onClose={flow.back} busy={flow.busy}>
          {flow.error && <Alert tone="danger">{flow.error}</Alert>}
          <DirectoryConfirmation
            plan={flow.plan}
            busy={flow.busy}
            onBack={flow.back}
            onConfirm={() => void flow.confirm()}
          />
        </Dialog>
      )}
      {flow.result && (
        <Alert tone="success" title="飞书同步已完成">
          新增 {flow.result.usersAdded} 人，更新 {flow.result.usersUpdated} 人，移出范围{" "}
          {flow.result.usersDeactivated} 人。请在下方设置成员角色与启用状态。
        </Alert>
      )}
      {!flow.preview && (
        <ImportedDirectory
          key={flow.result?.id ?? "local"}
          data={data}
          department={flow.department}
          onSelect={chooseImportedDepartment}
          onSaved={reload}
        />
      )}
    </div>
  );
}
