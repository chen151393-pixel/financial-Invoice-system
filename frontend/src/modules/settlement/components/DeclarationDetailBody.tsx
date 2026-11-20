import { Link } from "react-router";
import {
  directDocumentGroupPath,
  settlementBatchListPath,
  settlementDirectDocumentsPath,
  settlementLedgerPath,
  settlementReceiptPath,
} from "../../../app/paths";
import { Alert, Badge, Progress, SectionTitle } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { DeclarationDetail } from "../types/declaration-detail";
import { DeclarationAllocationTable } from "./DeclarationAllocationTable";
import { DeclarationReadOnlyDocuments } from "./DeclarationReadOnlyDocuments";
import { stageTone } from "./receivable-tones";

const formatTime = (value: string) =>
  new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));

/** 报关单只读工作区；办理操作统一跳回所属批次或资料页。 */
export function DeclarationDetailBody({ detail }: { detail: DeclarationDetail }) {
  const { item, batch } = detail;
  const target =
    item.route === "hk_transit"
      ? batch
        ? settlementBatchListPath("", batch.batchNo)
        : settlementReceiptPath(item.consignee)
      : detail.documents.groupId
        ? directDocumentGroupPath(detail.documents.groupId)
        : settlementDirectDocumentsPath(item.consignee, item.declarationNo);
  return (
    <div className="settlement-declaration">
      <div className="settlement-declaration__identity">
        <p>
          出口 {item.exportDate || "日期待补"} ·{" "}
          {item.agingDays === null ? "已结汇或账龄不可用" : `账龄 ${item.agingDays} 天`}
        </p>
        <h2>{item.declarationNo}</h2>
        <p>
          {item.consignee || "境外收货人待补"} · {item.exportCompany || "出口抬头待补"}
        </p>
        <div className="settlement-badges">
          <Badge tone={item.route === "hk_transit" ? "info" : "neutral"}>{item.routeLabel}</Badge>
          <Badge tone={stageTone(item.stage)}>{item.stageLabel}</Badge>
          {item.alert && <Badge tone="danger">{item.alert}</Badge>}
        </div>
      </div>
      {item.issue && (
        <Alert tone="warning" title="报关依据待处理">
          {item.issue}
        </Alert>
      )}
      <ol className="settlement-declaration__steps" aria-label="报关单结汇进度">
        {detail.steps.map((step) => (
          <li key={step.key} data-state={step.state}>
            <Progress
              width={step.percent}
              label={step.label}
              tone={step.state === "done" ? "success" : "progress"}
            />
            <strong>{step.label}</strong>
            <span>
              {step.description}
              {step.key === "export" && item.amount && ` · ${item.currency} ${money(item.amount)}`}
            </span>
          </li>
        ))}
      </ol>
      {batch ? (
        <section className="settlement-declaration__section" aria-label="香港批次核对">
          <SectionTitle title="所在批次" count={batch.batchNo} actions={<Link to={target}>查看批次</Link>} />
          <p className="settlement-declaration__note">
            {batch.declarationCount} 张报关单 · 金额在建批次时冻结
            {batch.receivedReference && ` · 流水 ${batch.receivedReference}`}
          </p>
          <dl className="settlement-declaration__balances">
            <div>
              <dt>批次报关合计</dt>
              <dd>
                {batch.currency} {money(batch.declaredTotal)}
              </dd>
            </div>
            {batch.balances.map((balance) => (
              <div key={balance.stage}>
                <dt>{balance.label} + 手续费</dt>
                <dd>
                  {money(balance.arrived)} + {money(balance.fee)}{" "}
                  <Badge tone={balance.balanced ? "success" : "warning"}>
                    {balance.balanced ? "对平" : `差额 ${money(balance.difference)}`}
                  </Badge>
                </dd>
              </div>
            ))}
            {!batch.remittedOn && (
              <div>
                <dt>汇回境内</dt>
                <dd>资料已出后登记</dd>
              </div>
            )}
          </dl>
        </section>
      ) : item.route === "direct" ? (
        <section className="settlement-declaration__section" aria-label="收款推算">
          <SectionTitle title="收款推算" count={item.currency} />
          <p className="settlement-declaration__note">
            {item.exportCompany || "收款抬头待补"} · 先出口先冲抵
          </p>
          <DeclarationAllocationTable rows={detail.allocations} />
          <p className="settlement-declaration__note">
            {detail.ledgerNote}
            {detail.ledgerBalance && (
              <>
                当前客户该抬头余额 {item.currency} {money(detail.ledgerBalance)}。{" "}
              </>
            )}
            <Link to={settlementLedgerPath(item.consignee)}>查看客户总账</Link>
          </p>
        </section>
      ) : (
        <Alert tone="info">当前报关单尚未登记香港回款，登记后按批次办理资料。</Alert>
      )}
      <DeclarationReadOnlyDocuments documents={detail.documents} />
      {detail.events.length > 0 && (
        <section className="settlement-declaration__section" aria-label="办理记录">
          <SectionTitle title="记录" />
          <ol className="settlement-declaration__events">
            {detail.events.map((event, index) => (
              <li key={`${event.at}:${index}`}>
                <time dateTime={event.at}>{formatTime(event.at)}</time>
                <span>
                  {event.actor} · {event.description}
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}
      <footer className="settlement-declaration__footer">
        <span>提单、合同及资料包统一在所属范围办理</span>
        <Link className="ui-button ui-button--primary" to={target}>
          {item.route === "hk_transit"
            ? batch
              ? `去批次 ${batch.batchNo} 办理`
              : "去登记香港回款"
            : detail.documents.groupId
              ? "去资料组办理"
              : "去办理本单资料"}
        </Link>
      </footer>
    </div>
  );
}
