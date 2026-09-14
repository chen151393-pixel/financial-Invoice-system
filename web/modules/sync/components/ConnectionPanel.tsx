import { Button } from "../../../shared/components/Button";
import { Panel } from "../../../shared/components/Panel";
import type { ConnectionStatus } from "../api";

export function ConnectionPanel({
  status,
  busy,
  onConnect,
  onLogout,
}: {
  status: ConnectionStatus;
  busy: boolean;
  onConnect: () => void;
  onLogout: () => void;
}) {
  return (
    <Panel
      title="连接与写入状态"
      actions={
        <Button disabled={busy} onClick={onLogout}>
          退出登录
        </Button>
      }
    >
      <p>
        账户：{status.account || "未配置"} · 配置：{status.configured ? "已填写，连接需验证" : "不完整"}·
        实际写入：{status.writeEnabled ? "已启用" : "关闭"}
      </p>
      <p>
        最近认证成功：
        {status.lastConnection ? new Date(status.lastConnection.at).toLocaleString() : "尚未验证"}
      </p>
      {status.missing.length > 0 && <p>缺少配置：{status.missing.join("、")}</p>}
      <Button variant="primary" disabled={busy} onClick={onConnect}>
        验证 M2M 连接
      </Button>
    </Panel>
  );
}
