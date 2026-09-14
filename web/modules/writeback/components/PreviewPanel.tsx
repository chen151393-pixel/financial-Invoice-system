import { Button } from "../../../shared/components/Button";
import { Panel } from "../../../shared/components/Panel";
import { JsonView } from "../../../shared/components/JsonView";
import type { Preview } from "../api";

export function PreviewPanel({
  preview,
  confirmed,
  busy,
  onConfirm,
  onExecute,
  onRefresh,
}: {
  preview: Preview;
  confirmed: boolean;
  busy: boolean;
  onConfirm: (value: boolean) => void;
  onExecute: () => void;
  onRefresh: () => void;
}) {
  const action = preview.actions.execute;
  return (
    <Panel title="3. 确认写入">
      <p>
        目标：{preview.target} · 状态：{preview.stateLabel}
      </p>
      <p>预览有效至：{new Date(preview.expires).toLocaleString()}。执行前会再次检查 NS 数据是否变化。</p>
      <div className="live-diff">
        <div>
          <h3>NS 当前记录</h3>
          <JsonView value={preview.before} />
        </div>
        <div>
          <h3>本次拟写入字段</h3>
          <JsonView value={preview.payload} />
        </div>
      </div>
      {action.allowed && (
        <label className="live-confirm">
          <input
            type="checkbox"
            checked={confirmed}
            disabled={busy}
            onChange={(event) => onConfirm(event.target.checked)}
          />
          我已核对目标及字段，确认执行上述 NS 写入
        </label>
      )}
      <div className="live-actions">
        <Button variant="primary" disabled={busy || !confirmed || !action.allowed} onClick={onExecute}>
          确认写入 NS
        </Button>
        <Button disabled={busy} onClick={onRefresh}>
          刷新任务状态
        </Button>
      </div>
      {action.reason && <p>{action.reason}</p>}
      {preview.result !== null && <JsonView value={preview.result} />}
    </Panel>
  );
}
