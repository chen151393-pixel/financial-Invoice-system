import { Button } from "../../../shared/components/Button";
import { Panel } from "../../../shared/components/Panel";
import { JsonView } from "../../../shared/components/JsonView";

export function RecordQuery({
  recordTypes,
  type,
  id,
  record,
  busy,
  onType,
  onId,
  onQuery,
}: {
  recordTypes: string[];
  type: string;
  id: string;
  record: unknown;
  busy: boolean;
  onType: (value: string) => void;
  onId: (value: string) => void;
  onQuery: (mode: "list" | "detail") => void;
}) {
  return (
    <Panel title="1. 拉取 NS 数据">
      <div className="live-fields">
        <label>
          记录类型
          <select value={type} disabled={busy} onChange={(event) => onType(event.target.value)}>
            <option value="">选择允许访问的记录类型</option>
            {recordTypes.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </label>
        <label>
          NS Internal ID
          <input
            value={id}
            disabled={busy}
            placeholder="输入需要校对的记录 ID"
            onChange={(event) => onId(event.target.value)}
          />
        </label>
      </div>
      <div className="live-actions">
        <Button disabled={busy} onClick={() => onQuery("list")}>
          查询前 50 条记录
        </Button>
        <Button variant="primary" disabled={busy} onClick={() => onQuery("detail")}>
          拉取指定记录
        </Button>
      </div>
      {record !== null && <JsonView value={record} />}
    </Panel>
  );
}
