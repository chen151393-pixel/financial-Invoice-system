import { useEffect, useRef, useState } from "react";
import { Button } from "../../shared/components/Button";
import { previewMatching, type MatchingCandidate, type MatchingPreview } from "./api";

export function ManualPurchaseSearch({
  invoiceId,
  disabled,
  onSelect,
}: {
  invoiceId: string;
  disabled: boolean;
  onSelect: (candidates: MatchingCandidate[]) => void;
}) {
  const disclosure = useRef<HTMLDetailsElement>(null);
  const [query, setQuery] = useState("");
  const [request, setRequest] = useState<{ query: string; page: number } | null>(null);
  const [result, setResult] = useState<MatchingPreview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<MatchingCandidate[]>([]);

  useEffect(() => {
    if (!request) return;
    let active = true;
    void previewMatching(
      invoiceId,
      new URLSearchParams({
        purchaseQuery: request.query,
        page: String(request.page),
      }),
    )
      .then((value) => {
        if (active) setResult(value);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "搜索失败，请重试");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [invoiceId, request]);

  const search = (next: NonNullable<typeof request>, reset = false) => {
    setResult(null);
    setError("");
    setLoading(true);
    if (reset) {
      setChoices({});
      setSelected([]);
    }
    setRequest(next);
  };
  const groups = new Map<string, MatchingCandidate[]>();
  for (const candidate of result?.candidates ?? []) {
    const group = groups.get(candidate.purchaseLineId) ?? [];
    group.push(candidate);
    groups.set(candidate.purchaseLineId, group);
  }

  return (
    <details ref={disclosure} className="matching-workspace__manual-search">
      <summary>＋ 手动关联子采购单</summary>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          search({ query, page: 1 }, true);
        }}
      >
        <label>
          子采购单号、供应商或品名
          <input value={query} disabled={disabled} onChange={(event) => setQuery(event.target.value)} />
        </label>
        <Button type="submit" disabled={disabled || loading}>
          {loading ? "搜索中…" : "搜索"}
        </Button>
      </form>
      {loading && <p role="status">正在搜索…</p>}
      {error && (
        <p className="matching-workspace__error" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div>
          <p className="matching-workspace__hint" role="status">
            搜索：{request?.query} · 第 {result.page} 页
          </p>
          {result.candidateCount === 0 && <p role="status">未找到子采购明细</p>}
          <div className="matching-workspace__search-results">
            {[...groups].map(([purchaseLineId, candidates]) => {
              const candidate =
                candidates.find((row) => row.invoiceLineId === choices[purchaseLineId]) ?? candidates[0];
              const checked = selected.some((row) => row.purchaseLineId === purchaseLineId);
              return (
                <div className="matching-workspace__search-row" key={purchaseLineId}>
                  <label
                    className="matching-workspace__search-choice"
                    htmlFor={`manual-purchase-${purchaseLineId}`}
                    aria-label={`选择 ${candidate.orderNo} 的 ${candidate.declarationName || candidate.item || "采购明细"}`}
                  >
                    <input
                      id={`manual-purchase-${purchaseLineId}`}
                      type="checkbox"
                      disabled={disabled}
                      checked={checked}
                      onChange={() =>
                        setSelected((current) =>
                          checked
                            ? current.filter((row) => row.purchaseLineId !== purchaseLineId)
                            : [...current, candidate],
                        )
                      }
                    />
                    <span>
                      <strong>
                        {candidate.orderNo} · {candidate.declarationName || candidate.item || "品名待核实"}
                      </strong>
                      <small>
                        {candidate.supplier || "供应商待核实"} · {candidate.quantity || "—"}{" "}
                        {candidate.unit || ""} · {candidate.gross || "—"} {candidate.currency || ""}
                      </small>
                    </span>
                  </label>
                  <label className="matching-workspace__search-mapping">
                    对应发票明细
                    <select
                      value={candidate.invoiceLineId}
                      disabled={disabled}
                      onChange={(event) => {
                        const next = candidates.find((row) => row.invoiceLineId === event.target.value);
                        if (!next) return;
                        setChoices((current) => ({ ...current, [purchaseLineId]: next.invoiceLineId }));
                        if (checked)
                          setSelected((current) =>
                            current.map((row) => (row.purchaseLineId === purchaseLineId ? next : row)),
                          );
                      }}
                    >
                      {candidates.map((row) => (
                        <option key={row.invoiceLineId} value={row.invoiceLineId}>
                          第 {result.invoice.lines.findIndex((line) => line.id === row.invoiceLineId) + 1} 行
                          · {row.invoiceItem || "品名待核实"}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              );
            })}
          </div>
          {(result.page > 1 || result.hasNext) && (
            <div className="matching-workspace__actions">
              <Button
                disabled={disabled || result.page <= 1}
                onClick={() => request && search({ ...request, page: result.page - 1 })}
              >
                上一页
              </Button>
              <Button
                disabled={disabled || !result.hasNext}
                onClick={() => request && search({ ...request, page: result.page + 1 })}
              >
                下一页
              </Button>
            </div>
          )}
          {selected.length > 0 && (
            <Button
              disabled={disabled || loading}
              onClick={() => {
                onSelect(selected);
                setSelected([]);
                if (disclosure.current) disclosure.current.open = false;
              }}
            >
              加入 {selected.length} 条明细
            </Button>
          )}
        </div>
      )}
    </details>
  );
}
