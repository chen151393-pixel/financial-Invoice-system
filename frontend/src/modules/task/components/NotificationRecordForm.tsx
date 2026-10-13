import { useState } from "react";
import { Button } from "../../../shared/components/Button";

export interface RecordInput {
  sentAt: string;
  note: string;
  confirmed: boolean;
}

export function NotificationRecordForm({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (value: RecordInput) => void;
}) {
  const [sentAt, setSentAt] = useState("");
  const [note, setNote] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        // datetime-local 为本地时间，转成带时区的 ISO 字符串；时间范围由后端校验。
        onSubmit({ sentAt: sentAt ? new Date(sentAt).toISOString() : "", note, confirmed });
      }}
    >
      <p className="it-help">
        请在企微外部群实际发送正文及合同后登记。登记后保存内容快照，任务进入等待收票。
      </p>
      <label className="itn-field">
        实际发送时间
        <input
          type="datetime-local"
          value={sentAt}
          disabled={busy}
          onChange={(e) => setSentAt(e.target.value)}
        />
      </label>
      <label className="itn-field">
        登记说明
        <textarea
          rows={3}
          maxLength={500}
          value={note}
          disabled={busy}
          placeholder="例如：已核对外部群并发送正文及合同"
          onChange={(e) => setNote(e.target.value)}
        />
      </label>
      <label className="itn-check">
        <input
          type="checkbox"
          checked={confirmed}
          disabled={busy}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        我确认已在上述外部群发送本次通知及合同
      </label>
      <Button type="submit" variant="primary" disabled={busy}>
        {busy ? "登记中…" : "保存发送登记"}
      </Button>
    </form>
  );
}
