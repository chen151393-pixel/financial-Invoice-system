import { Button } from "../../../shared/components/Button";
import { Panel } from "../../../shared/components/Panel";
import type { Operation } from "../api";

export function PreviewEditor({
  operation,
  payload,
  fields,
  busy,
  onOperation,
  onPayload,
  onPreview,
}: {
  operation: Operation;
  payload: string;
  fields: string[];
  busy: boolean;
  onOperation: (value: Operation) => void;
  onPayload: (value: string) => void;
  onPreview: () => void;
}) {
  return (
    <Panel title="2. 校对并生成预览">
      <p>当前提供字段级人工校对。自动发票匹配和业务字段映射尚未接入。</p>
      <label>
        操作
        <select
          value={operation}
          disabled={busy}
          onChange={(event) => onOperation(event.target.value as Operation)}
        >
          <option value="update">更新现有记录</option>
          <option value="create">创建新记录</option>
        </select>
      </label>
      <p>允许写入的字段：{fields.join("、") || "尚未配置"}</p>
      <p>创建新记录时需填写稳定且唯一的 externalId；字段与内容由后端校验。</p>
      <label>
        拟写入的字段（JSON）
        <textarea
          rows={10}
          spellCheck={false}
          value={payload}
          disabled={busy}
          onChange={(event) => onPayload(event.target.value)}
        />
      </label>
      <Button variant="primary" disabled={busy} onClick={onPreview}>
        生成预览，不写入 NS
      </Button>
    </Panel>
  );
}
