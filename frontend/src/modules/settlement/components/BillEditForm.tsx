import { Button } from "../../../shared/components/ui";
import type { Bill, BillFields } from "../types";

/** 人工确认或修正提单字段；字段是否齐全由后端判断。 */
export function BillEditForm({
  bill,
  declarationNos,
  busy,
  onCancel,
  onSubmit,
}: {
  bill: Bill;
  declarationNos: string[];
  busy: boolean;
  onCancel: () => void;
  onSubmit: (fields: BillFields) => void;
}) {
  return (
    <form
      className="settlement-form"
      aria-label={`修改提单 ${bill.blNo || bill.fileName}`}
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const value = (name: string) => String(data.get(name) || "").trim();
        onSubmit({
          blNo: value("blNo"),
          portOfLoading: value("portOfLoading"),
          portOfDischarge: value("portOfDischarge"),
          onBoardDate: value("onBoardDate") || null,
          declarationNos: data.getAll("declarationNos").map(String),
        });
      }}
    >
      <label>
        提单号
        <input name="blNo" defaultValue={bill.blNo} maxLength={100} />
      </label>
      <label>
        装船日期
        <input name="onBoardDate" type="date" defaultValue={bill.onBoardDate} />
      </label>
      <label>
        装运口岸（英文，按提单填写）
        <input name="portOfLoading" defaultValue={bill.portOfLoading} maxLength={200} />
      </label>
      <label>
        目的口岸（英文，按提单填写）
        <input name="portOfDischarge" defaultValue={bill.portOfDischarge} maxLength={200} />
      </label>
      <fieldset className="settlement-form__wide settlement-checks">
        <legend>该提单对应的报关单</legend>
        {declarationNos.map((number) => (
          <label key={number}>
            <input
              type="checkbox"
              name="declarationNos"
              value={number}
              defaultChecked={bill.declarationNos.includes(number)}
            />
            {number}
          </label>
        ))}
      </fieldset>
      <div className="settlement-form__actions">
        <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
          取消
        </Button>
        <Button type="submit" variant="primary" disabled={busy}>
          保存提单信息
        </Button>
      </div>
    </form>
  );
}
