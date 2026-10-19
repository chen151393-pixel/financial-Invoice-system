import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { matchingInvoicePath } from "../../../app/paths";
import { Pagination } from "../../../shared/components/Pagination";
import { openLocalSession } from "../../identity/api";
import {
  getInvoiceTotals,
  getMatchingSummaries,
  type InvoiceTotals,
  type MatchingSummary,
} from "../../matching/api";
import { getInvoice, listInvoices } from "../api/invoice";
import { emptyFilters, InvoiceFilters } from "../components/InvoiceFilters";
import { InvoiceDetailDrawer } from "../components/InvoiceDetailDrawer";
import { InvoiceSummary } from "../components/InvoiceSummary";
import { InvoiceTable } from "../components/InvoiceTable";
import type { InvoiceDetail, InvoiceListResult } from "../types/invoice";
import "./invoice-list.css";

type Query = typeof emptyFilters & { page: number; pageSize: number; version: number };

export function InvoiceListPage() {
  const navigate = useNavigate();
  const [draft, setDraft] = useState(emptyFilters);
  const [query, setQuery] = useState<Query>({ ...emptyFilters, page: 1, pageSize: 20, version: 0 });
  const [data, setData] = useState<InvoiceListResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [matching, setMatching] = useState<Record<string, MatchingSummary>>({});
  const [matchingError, setMatchingError] = useState("");
  const [totals, setTotals] = useState<InvoiceTotals | null>(null);
  const [totalsLoading, setTotalsLoading] = useState(true);
  const [totalsError, setTotalsError] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<InvoiceDetail | null>(null);
  const [detailError, setDetailError] = useState("");

  function updateQuery(next: Query) {
    setLoading(true);
    setError("");
    setSelected(null);
    setData(null);
    setMatching({});
    setMatchingError("");
    setTotals(null);
    setTotalsLoading(true);
    setTotalsError("");
    setQuery(next);
  }
  const refresh = () => updateQuery({ ...query, version: query.version + 1 });

  useEffect(() => {
    // 浏览器返回缓存页时重新查询，避免显示过期的比对状态。
    function restore(event: PageTransitionEvent) {
      if (!event.persisted) return;
      setMatching({});
      setData(null);
      setLoading(true);
      setTotals(null);
      setTotalsLoading(true);
      setTotalsError("");
      setQuery((current) => ({ ...current, version: current.version + 1 }));
    }
    window.addEventListener("pageshow", restore);
    return () => window.removeEventListener("pageshow", restore);
  }, []);

  useEffect(() => {
    let active = true;
    async function loadTotals() {
      try {
        const response = await getInvoiceTotals(query);
        if (active) setTotals(response);
      } catch (reason) {
        if (active) setTotalsError(reason instanceof Error ? reason.message : "金额统计读取失败");
      } finally {
        if (active) setTotalsLoading(false);
      }
    }
    async function load() {
      let totalsStarted = false;
      try {
        await openLocalSession();
        if (!active) return;
        totalsStarted = true;
        void loadTotals();
        const params = new URLSearchParams({ page: String(query.page), page_size: String(query.pageSize) });
        for (const key of ["q", "status", "date_from", "date_to"] as const)
          if (query[key]) params.set(key, query[key]);
        const response = await listInvoices(params);
        if (!active) return;
        setData(response);
        setLoading(false);
        if (!response.rows.length) return;
        try {
          const summaries = await getMatchingSummaries(response.rows.map((row) => row.id));
          if (active) setMatching(Object.fromEntries(summaries.rows.map((row) => [row.invoiceId, row])));
        } catch (reason) {
          if (active) setMatchingError(reason instanceof Error ? reason.message : "比对状态读取失败");
        }
      } catch (reason) {
        if (active) {
          const message = reason instanceof Error ? reason.message : "读取发票失败";
          setError(message);
          if (!totalsStarted) {
            setTotalsError(message);
            setTotalsLoading(false);
          }
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [query]);

  useEffect(() => {
    let active = true;
    if (selected) {
      getInvoice(selected).then(
        (value) => active && setDetail(value),
        (reason: unknown) =>
          active && setDetailError(reason instanceof Error ? reason.message : "读取明细失败"),
      );
    }
    return () => {
      active = false;
    };
  }, [selected]);

  const openMatching = (id: string) => navigate(matchingInvoicePath(id));
  return (
    <div className="invoice-list">
      <InvoiceSummary data={totals} loading={totalsLoading} error={totalsError} />
      <section className="invoice-list__panel" aria-label="进项发票查询">
        <InvoiceFilters
          draft={draft}
          loading={loading}
          onChange={setDraft}
          onSubmit={() =>
            updateQuery({ ...draft, page: 1, pageSize: query.pageSize, version: query.version + 1 })
          }
          onReset={() => {
            setDraft(emptyFilters);
            updateQuery({ ...emptyFilters, page: 1, pageSize: query.pageSize, version: query.version + 1 });
          }}
          onRefresh={refresh}
        />
        <div className="invoice-list__context">
          <span>数据范围：已导入的进项发票，统计覆盖当前筛选的全部页</span>
          <span>金额按币种分别汇总，包含红字金额</span>
          <span>票面税额不代表可抵扣税额</span>
          <span>待复核金额与待匹配金额可能重叠，不应相加</span>
        </div>
        {loading && (
          <p className="invoice-list__message" role="status">
            正在读取数据库发票…
          </p>
        )}
        {error && (
          <p role="alert" className="invoice-list__message invoice-list__error">
            {error}，可点击“刷新数据”重试。
          </p>
        )}
        {matchingError && (
          <p role="alert" className="invoice-list__message invoice-list__error">
            {matchingError}，请点击“刷新数据”重试。
          </p>
        )}
        {totalsError && totalsError !== error && (
          <p role="alert" className="invoice-list__message invoice-list__error">
            {totalsError}，请点击“刷新数据”重试。
          </p>
        )}
        {data && (
          <>
            {data.rows.length === 0 ? (
              <p className="invoice-list__message" role="status">
                当前条件下没有发票。可调整筛选，或在“数据同步 → 柠檬云”导入发票。
              </p>
            ) : (
              <InvoiceTable
                rows={data.rows}
                matching={matching}
                matchingError={matchingError}
                onMatch={openMatching}
                onDetail={(id) => {
                  setDetail(null);
                  setDetailError("");
                  setSelected(id);
                }}
              />
            )}
            <Pagination
              label="发票分页"
              total={data.total}
              page={data.page}
              pageCount={Math.max(1, Math.ceil(data.total / data.pageSize))}
              pageSize={data.pageSize}
              pageSizes={[10, 20, 50, 100]}
              disabled={loading}
              onPageChange={(page) => updateQuery({ ...query, page })}
              onPageSizeChange={(pageSize) => updateQuery({ ...query, page: 1, pageSize })}
            />
          </>
        )}
      </section>
      {selected && (
        <InvoiceDetailDrawer
          detail={detail}
          error={detailError}
          summary={matching[selected]}
          onClose={() => setSelected(null)}
          onMatch={openMatching}
        />
      )}
    </div>
  );
}
