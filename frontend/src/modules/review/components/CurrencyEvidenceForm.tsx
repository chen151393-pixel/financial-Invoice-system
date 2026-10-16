import type { ComparisonGroup, CurrencyEvidence } from "../types";

export function CurrencyEvidenceForm({
  checks,
  value,
  onChange,
  busy,
}: {
  checks: ComparisonGroup["currencyChecks"];
  value: CurrencyEvidence[];
  onChange: (value: CurrencyEvidence[]) => void;
  busy: boolean;
}) {
  return (
    <div className="fr-currency-evidence">
      {checks.map((check) => {
        const row = value.find((v) => v.purchaseOrderId === check.purchaseOrderId);
        const update = (key: "currency" | "reference" | "note", text: string) =>
          onChange(
            value.map((v) => (v.purchaseOrderId === check.purchaseOrderId ? { ...v, [key]: text } : v)),
          );
        return (
          <fieldset key={check.purchaseOrderId} disabled={busy || !check.allowed}>
            <legend>{check.orderNumber} · 结算币种核实</legend>
            <p>{check.reason}</p>
            {check.allowed && (
              <label>
                <input
                  type="checkbox"
                  checked={!!row}
                  onChange={(e) =>
                    onChange(
                      e.target.checked
                        ? [
                            ...value,
                            { purchaseOrderId: check.purchaseOrderId, currency: "", reference: "", note: "" },
                          ]
                        : value.filter((v) => v.purchaseOrderId !== check.purchaseOrderId),
                    )
                  }
                />
                本次提交结算币种证据
              </label>
            )}
            {row && (
              <div className="fr-currency-fields">
                <label>
                  币种代码
                  <input
                    value={row.currency}
                    onChange={(e) => update("currency", e.target.value)}
                    placeholder="例如 CNY"
                  />
                </label>
                <label>
                  合同或证据引用
                  <input value={row.reference} onChange={(e) => update("reference", e.target.value)} />
                </label>
                <label>
                  核实说明
                  <textarea rows={2} value={row.note} onChange={(e) => update("note", e.target.value)} />
                </label>
              </div>
            )}
          </fieldset>
        );
      })}
    </div>
  );
}
