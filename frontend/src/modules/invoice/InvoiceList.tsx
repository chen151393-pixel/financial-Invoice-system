import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { matchingInvoicePath } from "../../app/paths";
import { Button } from "../../shared/components/Button";
import { Pagination } from "../../shared/components/Pagination";
import { openLocalSession } from "../identity/api";
import { getMatchingSummaries, type MatchingSummary } from "../matching/api";
import { getInvoice, listInvoices, type InvoiceDetail, type InvoiceListResult } from "./api";
import "./invoice-list.css";

const emptyFilters = { q: "", status: "", date_from: "", date_to: "" };
// 仅调整十进制字符串的展示，不转换浮点或计算金额。
const money = (value: string | null) => {
  if (value === null) return "—";
  const [integer, fraction = ""] = value.split(".");
  return `${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${fraction.replace(/0+$/, "").padEnd(2, "0")}`;
};
const shown = (value: string | null) => value || "—";

export function InvoiceList() {
  const navigate = useNavigate();
  const [expandedFilters, setExpandedFilters] = useState(false);
  const [checked, setChecked] = useState<string[]>([]);
  const [draft, setDraft] = useState(emptyFilters);
  const [query, setQuery] = useState({ ...emptyFilters, page: 1, pageSize: 20, version: 0 });
  const [data, setData] = useState<InvoiceListResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [matching, setMatching] = useState<Record<string, MatchingSummary>>({});
  const [matchingError, setMatchingError] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<InvoiceDetail | null>(null);
  const [detailError, setDetailError] = useState("");
  const detailHeading = useRef<HTMLHeadingElement>(null);

  const detailDialog = useRef<HTMLDialogElement>(null);
  function updateQuery(next: typeof query) {
    setChecked([]);
    setLoading(true);
    setError("");
    setSelected(null);
    setData(null);
    setMatching({});
    setMatchingError("");
    setQuery(next);
  }
  function openDetail(id: string) {
    if (selected === id) {
      detailHeading.current?.focus();
      return;
    }
    setDetail(null);
    setDetailError("");
    setSelected(id);
  }

  useEffect(() => {
    function restore(event: PageTransitionEvent) {
      if (!event.persisted) return;
      setMatching({});
      setMatchingError("");
      setData(null);
      setLoading(true);
      setQuery((current) => ({ ...current, version: current.version + 1 }));
    }
    window.addEventListener("pageshow", restore);
    return () => window.removeEventListener("pageshow", restore);
  }, []);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        await openLocalSession();
        const params = new URLSearchParams({ page: String(query.page), page_size: String(query.pageSize) });
        for (const key of ["q", "status", "date_from", "date_to"] as const)
          if (query[key]) params.set(key, query[key]);
        const response = await listInvoices(params);
        if (!active) return;
        setData(response);
        setLoading(false);
        if (response.rows.length) {
          try {
            const summaries = await getMatchingSummaries(response.rows.map((row) => row.id));
            if (active) setMatching(Object.fromEntries(summaries.rows.map((row) => [row.invoiceId, row])));
          } catch (error) {
            if (active) setMatchingError(error instanceof Error ? error.message : "匹配状态读取失败");
          }
        }
      } catch (error) {
        if (active) setError(error instanceof Error ? error.message : "读取发票失败");
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
      void getInvoice(selected)
        .then((value) => {
          if (active) setDetail(value);
        })
        .catch((error) => {
          if (active) setDetailError(error instanceof Error ? error.message : "读取明细失败");
        });
    }
    return () => {
      active = false;
    };
  }, [selected]);

  useEffect(() => {
    if (!selected) return;
    const dialog = detailDialog.current;
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    dialog?.showModal();
    detailHeading.current?.focus();
    document.body.style.overflow = "hidden";
    return () => {
      dialog?.close();
      document.body.style.overflow = previousOverflow;
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, [selected]);

  const pageCount = data ? Math.max(1, Math.ceil(data.total / data.pageSize)) : 1;

  return (
    <div className="invoice-list">
      <section className="invoice-list__summary" aria-label="当前筛选汇总">
        <div className="invoice-list__metric">
          <span>价税合计</span>
          {data ? (
            data.amounts.length ? (
              data.amounts.map((amount) => (
                <div key={amount.currency ?? "unknown"}>
                  <strong>
                    {amount.currency === "CNY" ? "¥ " : amount.currency ? `${amount.currency} ` : ""}
                    {money(amount.gross)}
                  </strong>
                  <small>
                    {amount.currency || "币种待核实"} · {amount.count} 张发票
                  </small>
                </div>
              ))
            ) : (
              <>
                <strong>—</strong>
                <small>当前筛选无发票</small>
              </>
            )
          ) : (
            <>
              <strong>—</strong>
              <small>{loading ? "正在读取" : "读取失败"}</small>
            </>
          )}
        </div>
        {["可抵扣税额", "待匹配金额", "异常金额"].map((label) => (
          <div className="invoice-list__metric" key={label}>
            <span>{label}</span>
            <strong>—</strong>
            <small>对应业务数据尚未接入</small>
          </div>
        ))}
      </section>
      <section className="invoice-list__panel" aria-label="进项发票查询">
        <div className="invoice-list__tabs" aria-label="匹配状态">
          <span className="invoice-list__active-tab">全部 {data?.total ?? "—"}</span>
          {["已匹配", "待确认", "待匹配", "异常", "待回写", "已回写"].map((label) => (
            <button key={label} disabled title="全量匹配统计与回写状态尚未接入">
              {label} —
            </button>
          ))}
          <small>匹配统计与回写尚未接入</small>
        </div>
        <form
          className="invoice-list__filters"
          onSubmit={(event) => {
            event.preventDefault();
            updateQuery({ ...draft, page: 1, pageSize: query.pageSize, version: query.version + 1 });
          }}
        >
          <div className="invoice-list__toolbar">
            <input
              aria-label="搜索发票号码、供应商或税号"
              value={draft.q}
              maxLength={100}
              placeholder="搜索发票 / 供应商 / 税号"
              onChange={(event) => setDraft({ ...draft, q: event.target.value })}
            />
            <Button type="submit" disabled={loading}>
              查询
            </Button>
            <div className="invoice-list__tools">
              {["主体", "会计期间", "币种", "匹配关系"].map((label) => (
                <Button key={label} disabled title="该筛选尚未接入">
                  {label}⌄
                </Button>
              ))}
              <Button
                aria-expanded={expandedFilters}
                aria-controls="invoice-more-filters"
                onClick={() => setExpandedFilters(!expandedFilters)}
              >
                更多筛选
              </Button>
              <Button
                disabled={loading}
                onClick={() => updateQuery({ ...query, version: query.version + 1 })}
              >
                刷新数据
              </Button>
            </div>
          </div>
          {expandedFilters && (
            <div className="invoice-list__more-filters" id="invoice-more-filters">
              <label>
                票面状态
                <select
                  value={draft.status}
                  onChange={(event) => setDraft({ ...draft, status: event.target.value })}
                >
                  <option value="">全部状态</option>
                  <option value="normal">正常</option>
                  <option value="red_offset">已红冲</option>
                  <option value="void">作废</option>
                  <option value="unknown">未知</option>
                </select>
              </label>
              <label>
                开票日期从
                <input
                  type="date"
                  value={draft.date_from}
                  onChange={(event) => setDraft({ ...draft, date_from: event.target.value })}
                />
              </label>
              <label>
                至
                <input
                  type="date"
                  value={draft.date_to}
                  onChange={(event) => setDraft({ ...draft, date_to: event.target.value })}
                />
              </label>
              <Button type="submit" disabled={loading}>
                应用筛选
              </Button>
              <Button
                disabled={loading}
                onClick={() => {
                  setDraft(emptyFilters);
                  updateQuery({
                    ...emptyFilters,
                    page: 1,
                    pageSize: query.pageSize,
                    version: query.version + 1,
                  });
                }}
              >
                重置
              </Button>
            </div>
          )}
        </form>
        <div className="invoice-list__context">
          <span>数据范围：当前身份的数据库进项发票</span>
          <span>金额按币种分别汇总，包含红字金额</span>
          <span>票面税额不代表可抵扣税额</span>
          {checked.length > 0 && <span>已选 {checked.length} 张</span>}
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
        {data && (
          <>
            {data.rows.length === 0 ? (
              <p className="invoice-list__message" role="status">
                当前条件下没有发票。可调整筛选，或前往“导入发票”。
              </p>
            ) : (
              <div
                className="invoice-list__table invoice-list__main-table"
                role="region"
                aria-label="真实进项发票列表，可横向滚动"
              >
                <table>
                  <thead>
                    <tr>
                      <th scope="col">
                        <input
                          type="checkbox"
                          aria-label="选择本页全部发票"
                          checked={checked.length === data.rows.length}
                          onChange={(event) =>
                            setChecked(event.target.checked ? data.rows.map((row) => row.id) : [])
                          }
                        />
                      </th>
                      {[
                        "发票号码 / 来源",
                        "供应商 / 税号",
                        "开票日期",
                        "价税合计",
                        "关联方式",
                        "置信度",
                        "入库时间（UTC）",
                        "票面状态 / 匹配校验",
                        "操作",
                      ].map((text) => (
                        <th scope="col" key={text}>
                          {text}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((row) => (
                      <tr key={row.id}>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`选择发票${row.number}`}
                            checked={checked.includes(row.id)}
                            onChange={(event) =>
                              setChecked(
                                event.target.checked
                                  ? [...checked, row.id]
                                  : checked.filter((id) => id !== row.id),
                              )
                            }
                          />
                        </td>
                        <td>
                          <b>{shown(row.number)}</b>
                          <small>
                            {row.source} · {shown(row.type)}
                          </small>
                        </td>
                        <td>
                          <b>{shown(row.seller)}</b>
                          <small>{shown(row.sellerTaxNo)}</small>
                        </td>
                        <td>{shown(row.date)}</td>
                        <td className="invoice-list__amount">
                          {row.currency === "CNY" ? "¥ " : ""}
                          {money(row.gross)}
                          <small>税额 {money(row.tax)}</small>
                          <small>{row.currency || "币种待核实"}</small>
                        </td>
                        <td>
                          <span className="invoice-list__badge">
                            {matching[row.id]?.method || (matchingError ? "读取失败" : "读取中…")}
                          </span>
                        </td>
                        <td>
                          <span
                            className={`invoice-list__match-state invoice-list__match-state--${matching[row.id]?.tone || "neutral"}`}
                          >
                            {matching[row.id]?.confidence || "—"}
                          </span>
                        </td>
                        <td>
                          {row.importedAt?.slice(0, 10) || "—"}
                          <small>{row.importedAt?.slice(11, 19) || ""}</small>
                        </td>
                        <td>
                          <span className="invoice-list__badge">{row.status}</span>
                          <small
                            className={`invoice-list__match-state invoice-list__match-state--${matching[row.id]?.tone || "neutral"}`}
                          >
                            {matching[row.id]?.validation || (matchingError ? "校验读取失败" : "校验读取中…")}
                          </small>
                        </td>
                        <td>
                          <Button
                            className="invoice-list__view"
                            onClick={() => navigate(matchingInvoicePath(row.id))}
                            aria-label={`查看发票${row.number}自动匹配`}
                          >
                            查看
                          </Button>
                          <Button className="invoice-list__view" onClick={() => openDetail(row.id)}>
                            票面详情
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <Pagination
              label="发票分页"
              total={data.total}
              page={data.page}
              pageCount={pageCount}
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
        <dialog
          ref={detailDialog}
          className="invoice-list__detail"
          aria-labelledby="invoice-detail-title"
          onCancel={(event) => {
            event.preventDefault();
            setSelected(null);
          }}
        >
          <div className="invoice-list__detail-header">
            <h2 id="invoice-detail-title" ref={detailHeading} tabIndex={-1}>
              发票详情
            </h2>
            <Button
              className="invoice-list__close"
              aria-label="关闭票面详情"
              onClick={() => setSelected(null)}
            >
              ×
            </Button>
          </div>
          <div className="invoice-list__detail-body">
            {!detail && !detailError && <p role="status">正在读取发票及商品明细…</p>}
            {detailError && (
              <p role="alert" className="invoice-list__error">
                {detailError}，请关闭后重新查看。
              </p>
            )}
            {detail && (
              <>
                <dl className="invoice-list__metadata">
                  {[
                    ["发票号码", detail.number],
                    ["发票类型", detail.type],
                    ["供应商", detail.seller],
                    ["供应商税号", detail.sellerTaxNo],
                    ["开票日期", detail.date],
                    ["价税合计", money(detail.gross)],
                    ["不含税金额", money(detail.net)],
                    ["税额", money(detail.tax)],
                    ["币种", detail.currency || "待核实"],
                    ["发票代码", detail.invoiceCode],
                    ["票面状态", detail.status],
                    ["数据校验", detail.validation],
                    ["购买方", detail.buyer],
                    ["购买方税号", detail.buyerTaxNo],
                    ["项目", detail.project],
                    ["部门", detail.department],
                    ["职员", detail.employee],
                    ["关联凭证", detail.voucher],
                    ["备注", detail.remark],
                    ["入库同步时间（UTC）", detail.importedAt],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <dt>{label}</dt>
                      <dd>{shown(value)}</dd>
                    </div>
                  ))}
                </dl>
                {detail.validationMessages.length > 0 && (
                  <ul>
                    {detail.validationMessages.map((message, index) => (
                      <li key={index}>{message}</li>
                    ))}
                  </ul>
                )}
                <h3 className="invoice-list__section-title">商品明细</h3>
                <div className="invoice-list__table" role="region" aria-label="发票商品明细，可横向滚动">
                  <table>
                    <caption>票面商品明细 · {detail.lineCount} 行</caption>
                    <thead>
                      <tr>
                        {[
                          "行号",
                          "商品名称",
                          "规格型号",
                          "数量",
                          "单位",
                          "原始单价",
                          "金额",
                          "税率",
                          "税额",
                          "价税合计",
                        ].map((text) => (
                          <th key={text} scope="col">
                            {text}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {detail.lines.length === 0 && (
                        <tr>
                          <td colSpan={10}>暂无商品明细</td>
                        </tr>
                      )}
                      {detail.lines.map((line) => (
                        <tr key={line.id}>
                          {[
                            line.number,
                            line.item,
                            line.specification,
                            line.quantity,
                            line.unit,
                            line.unitPrice,
                            line.net,
                            line.taxRate,
                            line.tax,
                            line.gross,
                          ].map((value, index) => (
                            <td key={index}>{shown(value)}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            {detail && (
              <>
                <h3 className="invoice-list__section-title">关联采购订单</h3>
                <p className="invoice-list__detail-empty">
                  {matching[detail.id]
                    ? `${matching[detail.id].method} · ${matching[detail.id].validation}`
                    : matchingError
                      ? "匹配状态读取失败"
                      : "正在读取匹配状态…"}
                  <Button
                    className="invoice-list__view"
                    onClick={() => navigate(matchingInvoicePath(detail.id))}
                  >
                    查看匹配详情
                  </Button>
                </p>
                <h3 className="invoice-list__section-title">关联付款记录</h3>
                <p className="invoice-list__detail-empty">付款记录尚未接入。</p>
              </>
            )}
          </div>
        </dialog>
      )}
    </div>
  );
}
