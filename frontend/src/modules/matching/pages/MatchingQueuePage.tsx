import { useEffect, useState } from "react";
import { Button } from "../../../shared/components/Button";
import { Pagination } from "../../../shared/components/Pagination";
import { openLocalSession } from "../../identity/api";
import { confirmBatch, getMatchingQueue } from "../api";
import { batchable, QueueTable } from "../components/QueueTable";
import type { Queue, QueueQuery } from "../types/matching";
import "./matching.css";

type Remote = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: Queue };
const TABS: [QueueQuery["tier"], string][] = [
  ["all", "全部建议"],
  ["high", "高置信度"],
  ["medium", "中置信度"],
  ["low", "低置信度"],
];

export function MatchingQueuePage() {
  const [query, setQuery] = useState<QueueQuery>({ tier: "all", page: 1, pageSize: 20 });
  const [refresh, setRefresh] = useState(0);
  const [state, setState] = useState<Remote>({ kind: "loading" });
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ error: boolean; text: string } | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        await openLocalSession();
        const data = await getMatchingQueue(query);
        if (active) setState({ kind: "ready", data });
      } catch (error) {
        if (active)
          setState({ kind: "error", message: error instanceof Error ? error.message : "审核队列读取失败" });
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [query, refresh]);

  function change(patch: Partial<QueueQuery>) {
    setSelected([]);
    setState({ kind: "loading" });
    setQuery((current) => ({ ...current, page: 1, ...patch }));
  }
  async function confirmSelected() {
    setBusy(true);
    setFeedback(null);
    try {
      const result = await confirmBatch(selected);
      const skipped = result.skipped.map((item) => item.reason).join("；");
      setFeedback({
        error: result.skipped.length > 0,
        text: `已通过 ${result.confirmed} 条${result.skipped.length ? `，跳过 ${result.skipped.length} 条：${skipped}` : "。"}`,
      });
      setSelected([]);
      setRefresh((value) => value + 1);
    } catch (error) {
      setFeedback({
        error: true,
        text: error instanceof Error ? error.message : "批量通过失败，请刷新后核对",
      });
    } finally {
      setBusy(false);
    }
  }

  const data = state.kind === "ready" ? state.data : null;
  return (
    <div className="matching-page">
      <section className="matching-panel" aria-label="待审核比对建议">
        <div className="matching-heading">
          <div className="matching-tabs" role="group" aria-label="按置信度筛选">
            {TABS.map(([tier, label]) => (
              <Button key={tier} aria-pressed={query.tier === tier} onClick={() => change({ tier })}>
                {label} {data ? data.counts[tier] : ""}
              </Button>
            ))}
          </div>
          <div className="matching-row">
            <Button
              variant="primary"
              disabled={busy || selected.length === 0}
              onClick={() => void confirmSelected()}
            >
              {busy ? "处理中…" : `批量通过（${selected.length}）`}
            </Button>
            <Button disabled={busy} onClick={() => setRefresh((value) => value + 1)}>
              刷新
            </Button>
          </div>
        </div>
        <p className="matching-help">
          发票导入后系统按已审核的子采购行生成建议，全部需要人工审核。高置信度且比对项全部一致的建议可勾选批量通过，仍记录操作人；
          其他建议请点击“审核”逐条处理。置信度：80 分以上为高，50–79 为中，50 以下为低。
        </p>
        {feedback && (
          <p className="matching-feedback" role={feedback.error ? "alert" : "status"}>
            {feedback.text}
          </p>
        )}
        {state.kind === "loading" && <p role="status">正在读取待审核建议…</p>}
        {state.kind === "error" && (
          <p role="alert" className="matching-feedback">
            {state.message}
          </p>
        )}
        {data && data.rows.length === 0 && (
          <p className="matching-empty">
            没有待审核的比对建议。导入发票后，系统会为已审核的子采购行自动生成建议。
          </p>
        )}
        {data && data.rows.length > 0 && (
          <>
            {data.rows.some(batchable) && (
              <label className="matching-row">
                <input
                  type="checkbox"
                  checked={data.rows.filter(batchable).every((row) => selected.includes(row.allocation.id))}
                  onChange={(event) =>
                    setSelected(
                      event.target.checked ? data.rows.filter(batchable).map((row) => row.allocation.id) : [],
                    )
                  }
                />
                选择本页全部可批量通过的建议
              </label>
            )}
            <QueueTable
              rows={data.rows}
              selected={selected}
              onToggle={(id, checked) =>
                setSelected((current) =>
                  checked ? [...current, id] : current.filter((value) => value !== id),
                )
              }
            />
          </>
        )}
        {data && (
          <Pagination
            label="审核队列分页"
            total={data.total}
            page={data.page}
            pageCount={data.pages}
            pageSize={data.pageSize}
            pageSizes={[10, 20, 50]}
            disabled={busy}
            onPageChange={(page) => {
              setSelected([]);
              setQuery((current) => ({ ...current, page }));
            }}
            onPageSizeChange={(pageSize) => change({ pageSize })}
          />
        )}
      </section>
    </div>
  );
}
