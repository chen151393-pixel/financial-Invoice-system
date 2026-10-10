import { Link } from "react-router";
import { paths } from "../../app/paths";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { openLocalSession } from "../identity/api";
import { Button } from "../../shared/components/Button";
import {
  getSources,
  pullRecords,
  type Sources,
  type Source,
  type SourceKind,
  type PullResult,
  type DateRange,
} from "./api";
import "./sync.css";
import { SyncOverview } from "./SyncOverview";

function PullPanel({ source }: { source: Source }) {
  const [result, setResult] = useState<PullResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [range, setRange] = useState<DateRange>({ startDate: "", endDate: "" });
  const changed =
    result !== null &&
    (range.startDate !== result.dateRange.startDate || range.endDate !== result.dateRange.endDate);
  const current = useRef(0);
  useEffect(
    () => () => {
      current.current += 1;
    },
    [],
  );
  async function pull(offset: number, submittedRange: DateRange = range, save = false) {
    const id = ++current.current;
    setBusy(true);
    setError("");
    try {
      const data = await pullRecords(source.kind, offset, submittedRange, save);
      if (id === current.current) setResult(data);
    } catch (error) {
      if (id === current.current) setError(error instanceof Error ? error.message : "拉取失败");
    } finally {
      if (id === current.current) setBusy(false);
    }
  }
  return (
    <section
      className="sync-page__panel sync-page__results"
      aria-busy={busy}
      aria-label={`${source.label}拉取结果`}
    >
      <div className="sync-page__heading">
        <div>
          <div className="sync-page__result-title">
            <h2>{source.label}</h2>
            <span className="sync-page__tag">不修改 NS</span>
          </div>
          <p>{source.reason}</p>
        </div>
      </div>
      <form
        className="sync-page__filters"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          void pull(0);
        }}
      >
        <fieldset disabled={busy}>
          <legend>按创建日期拉取</legend>
          <div className="sync-page__date-fields">
            <label htmlFor={`${source.kind}-start`}>
              开始日期
              <input
                id={`${source.kind}-start`}
                type="date"
                value={range.startDate}
                aria-describedby={`${source.kind}-date-help`}
                onChange={(event) => setRange((value) => ({ ...value, startDate: event.target.value }))}
              />
            </label>
            <label htmlFor={`${source.kind}-end`}>
              结束日期
              <input
                id={`${source.kind}-end`}
                type="date"
                value={range.endDate}
                aria-describedby={`${source.kind}-date-help`}
                onChange={(event) => setRange((value) => ({ ...value, endDate: event.target.value }))}
              />
            </label>
            <Button type="submit" disabled={!source.allowed || busy}>
              仅拉取首页
            </Button>
            <Button
              variant="primary"
              disabled={!source.storageAllowed || busy}
              onClick={() => void pull(0, range, true)}
            >
              拉取首页并保存
            </Button>
            <Button
              disabled={busy || (!range.startDate && !range.endDate)}
              onClick={() => setRange({ startDate: "", endDate: "" })}
            >
              清空日期
            </Button>
          </div>
          <p id={`${source.kind}-date-help`}>
            按 NS 查询时区，包含起止当天；留空则不限制日期，每页最多 20 张。
          </p>
          <p>
            {source.storageReason}
            。拉取并保存会补齐报关单与对应子采购单、明细及可读取的关联依据；重复拉取更新原记录。
          </p>
        </fieldset>
      </form>
      {changed && (
        <p className="sync-page__scope-change" role="status">
          日期条件已修改，请重新拉取首页。下方仍为上次结果。
        </p>
      )}
      {busy && (
        <div className="sync-page__feedback" role="status">
          <span className="sync-page__loader" aria-hidden="true" />
          正在处理本页单据，请稍候；保存操作需要补齐明细并提交数据库…
        </div>
      )}
      {error && (
        <p role="alert" className="sync-page__error">
          {error}。若保存时连接中断，请先核实本地记录；上次展示结果不代表本次保存状态。
        </p>
      )}
      {!result && !busy && !error && (
        <div className="sync-page__empty">
          <span className="sync-page__empty-symbol" aria-hidden="true">
            NS
          </span>
          <strong>{source.allowed ? `准备读取${source.label}` : "当前单据暂不可拉取"}</strong>
          <p>{source.allowed ? "可选择日期，仅拉取查看，或拉取并保存到 MySQL。" : source.reason}</p>
          <span className="sync-page__empty-note">每页最多 20 张 · 手动分页 · 不修改源单据</span>
        </div>
      )}
      {result && (
        <>
          <p className="sync-page__applied-range">
            本次结果 · {result.dateRange.label}：
            {result.dateRange.startDate
              ? `${result.dateRange.startDate} 至 ${result.dateRange.endDate}（含起止当天）`
              : "不限日期"}
          </p>
          <p role="status" className="sync-page__result-summary">
            {result.message} · 本页 {result.count} 张 ·{" "}
            {new Date(result.pulledAt).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}（北京时间）
          </p>
          {result.storage && (
            <div role="status" className="sync-page__result-summary">
              <p>
                保存时间：
                {new Date(result.storage.savedAt).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}
                （北京时间）
              </p>
              <p>
                采购单：新增 {result.storage.purchase.created} 张，更新 {result.storage.purchase.updated}{" "}
                张；明细新增 {result.storage.purchase.linesCreated} 行，更新{" "}
                {result.storage.purchase.linesUpdated} 行。
              </p>
              <p>
                报关单（含关联单据）：新增 {result.storage.customs.created} 张，更新{" "}
                {result.storage.customs.updated} 张；明细新增 {result.storage.customs.linesCreated} 行，更新{" "}
                {result.storage.customs.linesUpdated} 行。
              </p>
              {result.storage.relations && (
                <p>
                  关联依据：{result.storage.relations.collected} 张已读取，{result.storage.relations.partial}{" "}
                  张待补齐； 原始报关行 {result.storage.relations.rawLines} 条，装箱明细{" "}
                  {result.storage.relations.packingLines} 条， 销售与采购行关系{" "}
                  {result.storage.relations.purchaseLinks} 条。读取依据不代表审核通过。
                </p>
              )}
              {result.storage.warnings?.map((warning) => (
                <p key={warning}>{warning}</p>
              ))}
            </div>
          )}
          {result.count === 0 ? (
            <div className="sync-page__empty">
              <strong>当前页没有单据</strong>
              <p>可重新拉取首页，查看最新数据。</p>
            </div>
          ) : (
            <div className="sync-page__table">
              <table>
                <thead>
                  <tr>
                    <th>内部编号</th>
                    <th>单据编号</th>
                    <th>单据详情</th>
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row) => (
                    <tr key={row.id}>
                      <td>{row.id}</td>
                      <td>{row.number}</td>
                      <td>
                        <details>
                          <summary>查看原始字段</summary>
                          <pre>{JSON.stringify(row.record, null, 2)}</pre>
                        </details>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="sync-page__pagination">
            <span>
              起始位置 {result.offset} · {result.hasMore ? "还有后续数据" : "已到最后一页"}
            </span>
            <Button
              disabled={!source.allowed || busy || changed || result.nextOffset === null}
              onClick={() => {
                if (result.nextOffset !== null)
                  void pull(
                    result.nextOffset,
                    {
                      startDate: result.dateRange.startDate,
                      endDate: result.dateRange.endDate,
                    },
                    Boolean(result.storage),
                  );
              }}
            >
              {result.storage ? "拉取下一页并保存" : "仅拉取下一页"}
            </Button>
          </div>
        </>
      )}
    </section>
  );
}

export default function SyncPage({
  source,
  children,
}: {
  source: "ns" | "lemon" | "overview";
  children?: ReactNode;
}) {
  const [sources, setSources] = useState<Sources | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [selectedKind, setSelectedKind] = useState<SourceKind>("customs-declarations");
  useEffect(() => {
    if (source !== "ns") return;
    let active = true;
    async function load() {
      try {
        await openLocalSession();
        const data = await getSources();
        if (active) {
          setSources(data);
          setError("");
        }
      } catch (error) {
        if (active) setError(error instanceof Error ? error.message : "读取配置失败");
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [attempt, source]);
  return (
    <div className={`sync-page${source === "ns" ? " sync-page--ns" : ""}`}>
      {source !== "overview" && (
        <nav className="sync-page__nav" aria-label="返回上级">
          <Link to={paths.sync}>← 返回数据同步中心</Link>
          {source === "ns" && <span>NetSuite / 单据拉取</span>}
        </nav>
      )}
      {source === "overview" && <SyncOverview />}
      {error && (
        <div role="alert" className="sync-page__panel">
          <p>{error}</p>
          <Button
            onClick={() => {
              setError("");
              setAttempt((value) => value + 1);
            }}
          >
            重新加载配置
          </Button>
        </div>
      )}
      {source === "ns" && !sources && !error && <p role="status">正在读取连接配置…</p>}
      {source === "ns" && sources && (
        <div className="sync-page__workspace">
          <fieldset className="sync-page__selector">
            <legend>选择单据类型</legend>
            <p>切换类型后，已拉取的结果仍保留在当前页面。</p>
            <div className="sync-page__choices">
              {sources.sources.map((item) => (
                <label
                  key={item.kind}
                  className="sync-page__choice"
                  htmlFor={`sync-kind-${item.kind}`}
                  aria-label={item.label}
                >
                  <input
                    id={`sync-kind-${item.kind}`}
                    type="radio"
                    name="ns-document-kind"
                    value={item.kind}
                    checked={selectedKind === item.kind}
                    onChange={() => setSelectedKind(item.kind)}
                  />
                  <span>
                    <strong>{item.label}</strong>
                    <small>{item.allowed ? "按需读取单据详情" : "暂不可拉取，查看原因"}</small>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          {sources.sources.length === 0 && <p role="status">尚未配置可展示的 NS 单据类型。</p>}
          {sources.sources.map((item) => (
            <div key={item.kind} className="sync-page__result-slot" hidden={selectedKind !== item.kind}>
              <PullPanel source={item} />
            </div>
          ))}
          <div className="sync-page__footnote">
            <strong>结果保留范围</strong>
            <span>
              仅拉取的结果刷新后清除；“拉取并保存”成功后主单及明细保留在 MySQL，页面展示仍只包含当前页。
            </span>
          </div>
        </div>
      )}
      {source === "lemon" && children}
    </div>
  );
}
