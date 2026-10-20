import { useEffect, useState } from "react";
import { Button } from "../../../shared/components/Button";
import { Pagination } from "../../../shared/components/Pagination";
import { openLocalSession } from "../../identity/api";
import { confirmBatch, getMatchingQueue } from "../api";
import { batchable, QueueTable } from "../components/QueueTable";
import type { Queue, QueueQuery } from "../types/matching";
import "./matching.css";
import "./matching-parts.css";

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
      <section className="matching-panel matching-panel--flush" aria-label="待审核比对建议">
        <div className="matching-tabs" role="group" aria-label="按置信度筛选">
          {TABS.map(([tier, label]) => (
            <button
              type="button"
              key={tier}
              className="matching-tab"
              aria-pressed={query.tier === tier}
              onClick={() => change({ tier })}
            >
              {label}
              {data && <span className="matching-count">{data.counts[tier]}</span>}
            </button>
          ))}
          <Button
            className="matching-tabs__refresh"
            disabled={busy}
            onClick={() => setRefresh((value) => value + 1)}
          >
            刷新
          </Button>
        </div>
        <div className="matching-body">
          {feedback && (
            <p className="matching-feedback" role={feedback.error ? "alert" : "status"}>
              {feedback.text}
            </p>
          )}
          {selected.length > 0 && (
            <div className="matching-selection" role="status">
              <span>
                <strong>已选 {selected.length} 条</strong> · 仅高置信度且比对项全部一致的建议可勾选
              </span>
              <span className="matching-row">
                <Button disabled={busy} onClick={() => setSelected([])}>
                  取消选择
                </Button>
                <Button variant="primary" disabled={busy} onClick={() => void confirmSelected()}>
                  {busy ? "处理中…" : `批量通过（${selected.length}）`}
                </Button>
              </span>
            </div>
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
            <QueueTable
              rows={data.rows}
              selected={selected}
              onToggle={(id, checked) =>
                setSelected((current) =>
                  checked ? [...current, id] : current.filter((value) => value !== id),
                )
              }
              onToggleAll={(checked) =>
                setSelected(checked ? data.rows.filter(batchable).map((row) => row.allocation.id) : [])
              }
            />
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
        </div>
      </section>
    </div>
  );
}
