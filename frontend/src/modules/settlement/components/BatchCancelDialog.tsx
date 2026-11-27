import { Alert, Button, Dialog, Field } from "../../../shared/components/ui";

export function BatchCancelDialog({
  busy,
  onClose,
  onSubmit,
  error,
}: {
  busy: boolean;
  onClose: () => void;
  onSubmit: (reason: string) => void;
  error: string;
}) {
  return (
    <Dialog title="作废批次" busy={busy} onClose={onClose}>
      {error && (
        <Alert tone="danger" title="作废未完成">
          {error}
        </Alert>
      )}
      <form
        className="settlement-form"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit(String(new FormData(event.currentTarget).get("reason") || "").trim());
        }}
      >
        <div className="settlement-form__wide">
          <Field label="作废原因（作废后报关单可重新建批次）">
            <input name="reason" maxLength={300} disabled={busy} />
          </Field>
        </div>
        <div className="settlement-form__actions">
          <Button onClick={onClose} disabled={busy}>
            返回
          </Button>
          <Button type="submit" disabled={busy}>
            {busy ? "正在作废…" : "确认作废"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
