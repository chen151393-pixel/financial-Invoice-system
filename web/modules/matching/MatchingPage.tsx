import { useEffect, useState } from "react";
import { Button } from "../../shared/components/Button";
import { HttpError } from "../../shared/api/http";
import { openLocalSession } from "../identity/api";
import { AllocationForm } from "./AllocationForm";
import { ManualPurchaseSearch } from "./ManualPurchaseSearch";
import {
  linkMatching,
  previewMatching,
  reviewMatchingLinks,
  type LinkMatching,
  type LinkReview,
  type MatchingCandidate,
  type MatchingPreview,
} from "./api";
import "./matching.css";

const candidateKey = (invoiceLineId: string, purchaseLineId: string) => `${invoiceLineId}:${purchaseLineId}`;

function amount(value: string | null, currency: string | null) {
  if (!value) return "—";
  const label = ["CNY", "RMB", "人民币"].includes(currency || "") ? "¥" : currency || "";
  const [integer, fraction = ""] = value.split(".");
  return `${label} ${integer}.${fraction.replace(/0+$/, "").padEnd(2, "0")}`.trim();
}

const decimalText = (value: string | null) => value?.replace(/(\.\d*?[1-9])0+$|\.0+$/, "$1") || "—";

export function MatchingPage() {
  const id = new URLSearchParams(location.search).get("invoiceId");
  const [data, setData] = useState<MatchingPreview | null>(null);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [manualCandidates, setManualCandidates] = useState<MatchingCandidate[]>([]);
  const [selected, setSelected] = useState<MatchingCandidate[]>([]);
  const [pending, setPending] = useState<LinkMatching | null>(null);
  const [linkError, setLinkError] = useState("");
  const [review, setReview] = useState<LinkReview | null>(null);
  const [reviewError, setReviewError] = useState("");
  const [reviewVersion, setReviewVersion] = useState(0);
  const [acknowledged, setAcknowledged] = useState(false);
  const [manualReason, setManualReason] = useState("");

  useEffect(() => {
    if (!id || !data || selected.length === 0) return;
    let active = true;
    void reviewMatchingLinks(id, {
      snapshot: data.snapshot,
      pairs: selected.map(({ invoiceLineId, purchaseLineId }) => ({ invoiceLineId, purchaseLineId })),
    })
      .then((value) => {
        if (active) setReview(value);
      })
      .catch((reason: unknown) => {
        if (active) setReviewError(reason instanceof Error ? reason.message : "关联复核失败");
      });
    return () => {
      active = false;
    };
  }, [id, data, selected, reviewVersion]);

  useEffect(() => {
    let active = true;
    if (!id) return;
    void openLocalSession()
      .then(() => previewMatching(id))
      .then((value) => {
        if (active) {
          setData(value);
          setError("");
        }
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "读取匹配结果失败");
      });
    return () => {
      active = false;
    };
  }, [id, version]);

  const refresh = () => {
    setError("");
    setData(null);
    setSelected([]);
    setManualCandidates([]);
    setPending(null);
    setLinkError("");
    setReview(null);
    setReviewError("");
    setAcknowledged(false);
    setManualReason("");
    setVersion((value) => value + 1);
  };

  const selectCandidate = (candidate: MatchingCandidate, remove = false) => {
    setReview(null);
    setReviewError("");
    setAcknowledged(false);
    setLinkError("");
    setSelected((current) => {
      const remaining = current.filter((row) => row.purchaseLineId !== candidate.purchaseLineId);
      return remove ? remaining : [...remaining, candidate];
    });
  };

  const addManualCandidates = (candidates: MatchingCandidate[]) => {
    setManualCandidates((current) => [
      ...new Map(
        [...current, ...candidates].map((row) => [candidateKey(row.invoiceLineId, row.purchaseLineId), row]),
      ).values(),
    ]);
    setSelected((current) => [
      ...new Map([...current, ...candidates].map((row) => [row.purchaseLineId, row])).values(),
    ]);
    setReview(null);
    setReviewError("");
    setAcknowledged(false);
    setLinkError("");
  };

  if (!id) {
    return (
      <p className="matching-workspace__state">
        请从<a href="/invoices">进项发票列表</a>选择一张发票开始匹配。
      </p>
    );
  }
  if (error) {
    return (
      <div className="matching-workspace__state" role="alert">
        {error} <Button onClick={refresh}>重试</Button>
      </div>
    );
  }
  if (!data) {
    return (
      <p className="matching-workspace__state" role="status">
        正在读取发票与本地子采购单…
      </p>
    );
  }

  const invoice = data.invoice;
  const candidates = [
    ...new Map(
      [...data.candidates, ...manualCandidates].map((row) => [
        candidateKey(row.invoiceLineId, row.purchaseLineId),
        row,
      ]),
    ).values(),
  ];
  const submitLinks = () => {
    if (
      busy ||
      !review?.allowed ||
      selected.length === 0 ||
      (review.requiresManualConfirmation && !acknowledged)
    )
      return;
    const body = pending ?? {
      requestId: crypto.randomUUID(),
      snapshot: data.snapshot,
      pairs: selected.map((candidate) => ({
        invoiceLineId: candidate.invoiceLineId,
        purchaseLineId: candidate.purchaseLineId,
      })),
      manualConfirmation: review.requiresManualConfirmation && acknowledged,
      manualReason: review.requiresManualConfirmation ? manualReason : "",
    };
    setPending(body);
    setBusy(true);
    setLinkError("");
    void linkMatching(id, body)
      .then((result) => {
        setMessage(`${result.message}，关联 ${result.linkedLines} 条子采购明细`);
        refresh();
      })
      .catch((reason: unknown) => {
        if (reason instanceof HttpError && [400, 422].includes(reason.status)) setPending(null);
        setLinkError(reason instanceof Error ? reason.message : "保存失败，请刷新记录核实");
      })
      .finally(() => setBusy(false));
  };

  return (
    <div className="matching-workspace">
      {message && (
        <p className="matching-workspace__notice" role="status">
          {message}
        </p>
      )}
      <div className="matching-workspace__columns">
        <section className="matching-workspace__panel matching-workspace__invoice-panel">
          <div className="matching-workspace__panel-head">
            <div>
              <h2>柠檬云发票信息</h2>
              <p>
                {invoice.source} · {invoice.status} · {invoice.date || "日期待核实"}
              </p>
            </div>
            <Button disabled={busy} onClick={refresh}>
              刷新数据
            </Button>
          </div>
          <div className="matching-workspace__invoice">
            <div className="matching-workspace__paper-title">
              <strong>{invoice.type || "进项发票"}</strong>
              <span>{invoice.validation}</span>
            </div>
            <div className="matching-workspace__paper-meta">
              <span>发票号码 {invoice.number || "待核实"}</span>
              <span>开票日期 {invoice.date || "待核实"}</span>
            </div>
            <dl className="matching-workspace__parties">
              <div>
                <dt>购买方</dt>
                <dd>{invoice.buyer || "待核实"}</dd>
                <small>{invoice.buyerTaxNo || "税号未提供"}</small>
              </div>
              <div>
                <dt>销售方</dt>
                <dd>{invoice.seller || "待核实"}</dd>
                <small>{invoice.sellerTaxNo || "税号未提供"}</small>
              </div>
            </dl>
            <div className="matching-workspace__table">
              <table>
                <thead>
                  <tr>
                    <th>项目名称</th>
                    <th>规格型号</th>
                    <th className="matching-workspace__numeric">数量</th>
                    <th>单位</th>
                    <th className="matching-workspace__numeric">未税金额</th>
                    <th className="matching-workspace__numeric">税额</th>
                    <th className="matching-workspace__numeric">价税合计</th>
                  </tr>
                </thead>
                <tbody>
                  {invoice.lines.map((line) => (
                    <tr key={line.id}>
                      <td>{line.item || "—"}</td>
                      <td>{line.specification || "—"}</td>
                      <td className="matching-workspace__numeric">{decimalText(line.quantity)}</td>
                      <td>{line.unit || "—"}</td>
                      <td className="matching-workspace__numeric">{decimalText(line.net)}</td>
                      <td className="matching-workspace__numeric">{decimalText(line.tax)}</td>
                      <td className="matching-workspace__numeric">{decimalText(line.gross)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="matching-workspace__paper-total">
              <span>价税合计（小写）</span>
              <strong>{amount(invoice.gross, invoice.currency)}</strong>
            </div>
          </div>
          <section className="matching-workspace__rules" aria-labelledby="matching-rules-title">
            <h3 id="matching-rules-title">自动匹配依据</h3>
            <div className="matching-workspace__rule-grid">
              <span>备注采购单定位 · 命中 {data.remarkOrderCount} 张</span>
              <span>销售方与子采购供应商主体复核</span>
              <span>报关品名、数量与子采购报关单位核对</span>
              <span>采购人民币含税金额按发票行汇总核对</span>
            </div>
            <details>
              <summary>查看备注与金额核对口径</summary>
              <p>发票备注：{invoice.remark || "无"}</p>
              <p>{data.priceReason}</p>
              <p>名称仅统一全半角、空白及发票税收分类前缀；简称、别名与单位换算需人工核实。</p>
            </details>
          </section>
          {invoice.validationMessages.length > 0 && (
            <div className="matching-workspace__validation" role="note">
              <strong>发票来源待核实</strong>
              <ul>
                {invoice.validationMessages.map((text, index) => (
                  <li key={index}>{text}</li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <section className="matching-workspace__panel matching-workspace__candidate-panel">
          <div className="matching-workspace__panel-head">
            <div>
              <h2>NetSuite 候选业务单据</h2>
              <p>
                本地已同步 {data.purchaseCount} 张子采购单、{data.purchaseLineCount} 条明细 · 当前候选{" "}
                {data.candidateCount} 条
              </p>
            </div>
            <span className="matching-workspace__source-tag">本地规则候选</span>
          </div>
          <div className="matching-workspace__relationship" aria-label="关联关系：发票明细对应子采购报关明细">
            <span>发票明细</span>
            <span aria-hidden="true">→</span>
            <span>子采购报关明细</span>
          </div>
          {(data.links?.length ?? 0) > 0 && (
            <div className="matching-workspace__saved">
              <h3>已确认整票关联</h3>
              {data.links?.map((link) => (
                <div key={candidateKey(link.invoiceLineId, link.purchaseLineId)}>
                  <p>
                    发票行 {link.invoiceLineId} → {link.orderNo || "子采购单"} / 明细 {link.purchaseLineId}
                    <span>
                      {link.needsReview
                        ? "来源已变化，待复核"
                        : link.manualConfirmation
                          ? "存在差异，已人工确认"
                          : "已保存"}
                    </span>
                  </p>
                  {link.manualConfirmation && (
                    <div className="matching-workspace__warning-text">
                      <p>确认说明：{link.manualReason}</p>
                      <ul>
                        {link.warnings.map((warning) => (
                          <li key={warning}>{warning}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          {data.allocations.length > 0 && (
            <div className="matching-workspace__saved">
              <h3>已确认数量分配</h3>
              {data.allocations.map((row, index) => (
                <p key={`${row.invoiceLineId}:${row.purchaseLineId}:${index}`}>
                  发票行 {row.invoiceLineId} → {row.orderNo || "子采购单"} / 明细 {row.purchaseLineId}
                  <span>
                    数量 {row.quantity} · 含税金额 {row.gross} · {row.needsReview ? "待复核" : "已保存"}
                  </span>
                </p>
              ))}
            </div>
          )}
          {candidates.length === 0 && (
            <div className="matching-workspace__empty" role="status">
              <h3>未找到可匹配的采购明细</h3>
              <p>
                {data.sameSupplierCount === 0
                  ? `当前本地采购数据中没有供应商“${invoice.seller}”的同名子采购单。`
                  : "同名供应商的子采购单暂无有效明细。"}
              </p>

              <a href="/sync/ns">前往数据同步</a>
            </div>
          )}
          <div className="matching-workspace__candidate-list">
            {candidates.map((candidate) => {
              const key = candidateKey(candidate.invoiceLineId, candidate.purchaseLineId);
              const checked = selected.some(
                (row) => candidateKey(row.invoiceLineId, row.purchaseLineId) === key,
              );
              return (
                <article
                  className={`matching-workspace__candidate${checked ? " is-selected" : ""}`}
                  key={key}
                >
                  <label className="matching-workspace__candidate-main">
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={busy || pending !== null || !data.manualLinkAllowed}
                      onChange={() => selectCandidate(candidate, checked)}
                      aria-label={`选择子采购单 ${candidate.orderNo} 的明细 ${candidate.purchaseLineId} 对应发票行 ${candidate.invoiceLineId}`}
                    />
                    <span className="matching-workspace__candidate-body">
                      <span className="matching-workspace__candidate-kicker">
                        子采购单 {candidate.orderNo}
                      </span>
                      <strong>{candidate.declarationName || candidate.item || "品名待核实"}</strong>
                      <span>
                        发票：{candidate.invoiceItem || "品名待核实"} → 报关：
                        {candidate.declarationName || "品名待核实"}
                      </span>
                      <span>
                        {decimalText(candidate.quantity)} {candidate.unit || "单位待核实"} · 含税单价{" "}
                        {decimalText(candidate.price)} · {candidate.currency || "币种待核实"}
                      </span>
                      <span>子单供应商：{candidate.supplier || "待核实"}</span>
                    </span>
                    <span className="matching-workspace__candidate-side">
                      <span className="matching-workspace__status">
                        {candidate.warnings.length > 0 ? "有差异" : candidate.matchStatus}
                      </span>
                      <strong>{amount(candidate.gross, candidate.currency)}</strong>
                    </span>
                  </label>
                  <details className="matching-workspace__candidate-details">
                    <summary
                      className={candidate.warnings.length > 0 ? "matching-workspace__warning-text" : ""}
                    >
                      {candidate.warnings.length > 0
                        ? [...new Set(candidate.warnings.map((warning) => warning.split("：")[0]))].join(
                            "、",
                          ) + " · 查看差异"
                        : "核对明细"}
                    </summary>
                    <p className="matching-workspace__hint">
                      {candidate.basis} · 母采购单 {candidate.parentOrderNo || "未关联"} · 报关单{" "}
                      {candidate.customsNo || "未关联"}
                    </p>
                    <div className="matching-workspace__checks">
                      {candidate.checks.map((check) => (
                        <div key={check.label} className={check.matched ? "is-matched" : ""}>
                          <strong>
                            {check.matched ? "一致" : "不一致或缺失"} · {check.label}
                          </strong>
                          <span>
                            发票 {check.invoiceValue ?? "缺失"} / 子采购 {check.purchaseValue ?? "缺失"}
                          </span>
                          {check.difference !== null && <span>差额 {check.difference}</span>}
                        </div>
                      ))}
                    </div>
                    <AllocationForm
                      key={data.snapshot}
                      invoiceId={id}
                      snapshot={data.snapshot}
                      candidate={candidate}
                      busy={busy}
                      onBusy={setBusy}
                      onSaved={(text) => {
                        setMessage(text);
                        refresh();
                      }}
                    />
                  </details>
                </article>
              );
            })}
          </div>
          {data.truncated && (
            <p className="matching-workspace__hint">候选较多，仅展示前 100 条；未展示的候选不代表已匹配。</p>
          )}
          <ManualPurchaseSearch
            key={data.snapshot}
            invoiceId={id}
            disabled={busy || pending !== null || !data.manualLinkAllowed}
            onSelect={addManualCandidates}
          />
          <div className="matching-workspace__balance">
            <div>
              <span>发票价税合计</span>
              <strong>{amount(invoice.gross, invoice.currency)}</strong>
            </div>
            <div>
              <span>本次选择</span>
              <strong>{selected.length} 条子采购明细</strong>
            </div>
            <div
              role="status"
              className={`matching-workspace__balance-note${review?.allowed && !review.requiresManualConfirmation ? " is-ready" : ""}`}
            >
              <span>整票关联核对</span>
              <strong>
                {(review?.allowed
                  ? review.requiresManualConfirmation
                    ? "有差异，待人工确认"
                    : "核对一致"
                  : review?.reason) ||
                  (reviewError
                    ? "复核失败，请重试"
                    : selected.length > 0
                      ? "正在复核所选关联…"
                      : data.manualLinkAllowed
                        ? "请选择关联明细"
                        : data.manualLinkReason)}
              </strong>
            </div>
          </div>
          {reviewError && (
            <p className="matching-workspace__error" role="alert">
              {reviewError}
              <Button
                disabled={busy || pending !== null}
                onClick={() => {
                  setReviewError("");
                  setReview(null);
                  setReviewVersion((value) => value + 1);
                }}
              >
                重新复核
              </Button>
            </p>
          )}
          {review && review.warnings.length > 0 && (
            <details className="matching-workspace__review-differences">
              <summary>{review.warnings.length} 项待核实 · 查看详情</summary>
              <ul>
                {review.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </details>
          )}
          {review?.allowed && review.requiresManualConfirmation && (
            <div className="matching-workspace__manual-confirm">
              <label className="matching-workspace__acknowledgement">
                <input
                  type="checkbox"
                  checked={acknowledged}
                  disabled={busy || pending !== null}
                  onChange={(event) => setAcknowledged(event.target.checked)}
                />
                已核实差异，确认关联
              </label>
              <label>
                人工确认说明（必填）
                <textarea
                  value={manualReason}
                  disabled={busy || pending !== null}
                  onChange={(event) => {
                    setManualReason(event.target.value);
                    setLinkError("");
                  }}
                />
              </label>
            </div>
          )}
          {linkError && (
            <p className="matching-workspace__error" role="alert">
              {linkError}。
              {pending ? "请先刷新核实已保存记录；重试本次提交会沿用原请求标识。" : "请修改后重新提交。"}
            </p>
          )}
          <div className="matching-workspace__actions">
            <Button disabled={busy} onClick={refresh}>
              刷新候选
            </Button>
            <Button
              variant="primary"
              disabled={
                busy ||
                !review?.allowed ||
                selected.length === 0 ||
                (review.requiresManualConfirmation && !acknowledged)
              }
              onClick={submitLinks}
            >
              {busy
                ? "正在保存…"
                : pending
                  ? "重试本次关联"
                  : review?.requiresManualConfirmation
                    ? "确认关联"
                    : "确认关联"}
            </Button>
          </div>
        </section>
      </div>
    </div>
  );
}
