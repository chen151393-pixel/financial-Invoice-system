import { Link } from "react-router";
import { directDocumentGroupPath } from "../../../app/paths";
import { Alert, Badge, EmptyState, SectionTitle } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { DeclarationDetail } from "../types/declaration-detail";

export function DeclarationReadOnlyDocuments({ documents }: { documents: DeclarationDetail["documents"] }) {
  const original = documents.original;
  return (
    <section className="settlement-declaration__section" aria-label="结汇资料只读概况">
      <SectionTitle title="资料（只读）" count={documents.scopeLabel} />
      <p className="settlement-declaration__note">{documents.note}</p>
      {documents.groupId && (
        <Link to={directDocumentGroupPath(documents.groupId)}>进入资料组 {documents.scopeLabel}</Link>
      )}
      <div className="settlement-declaration__documents">
        <article className="settlement-declaration__document">
          <div>
            <strong>报关单原件</strong>
            <p>
              {original.statusLabel}
              {original.files.length ? ` · ${original.files.map((f) => f.name).join("、")}` : ""}
            </p>
            {original.note && <p>{original.note}</p>}
          </div>
          <div className="settlement-declaration__file-actions">
            {original.files.map((file) => (
              <a key={file.url} href={file.url} target="_blank" rel="noreferrer">
                查看 {file.name}
              </a>
            ))}
          </div>
        </article>
        {documents.bills.length ? (
          documents.bills.map((bill) => (
            <article key={bill.id} className="settlement-declaration__document">
              <div>
                <strong>提单 {bill.blNo || "编号待补"}</strong>
                <p>
                  {bill.portOfLoading || "装运口岸待补"} → {bill.portOfDischarge || "目的口岸待补"} · 装船{" "}
                  {bill.onBoardDate || "日期待补"}
                </p>
                <p>覆盖报关单：{bill.declarationNos.join("、")}</p>
                {bill.parseNote && <p>{bill.parseNote}</p>}
                {bill.missing.length > 0 && <p>待补：{bill.missing.join("、")}</p>}
              </div>
              <div className="settlement-declaration__file-actions">
                <Badge tone={bill.missing.length ? "warning" : "success"}>
                  {bill.missing.length ? "待补齐" : "信息完整"}
                </Badge>
                <a href={bill.fileUrl} target="_blank" rel="noreferrer">
                  查看提单
                </a>
              </div>
            </article>
          ))
        ) : (
          <article className="settlement-declaration__document">
            <div>
              <strong>提单</strong>
              <p>当前资料范围内，没有关联本报关单的提单。</p>
            </div>
            <Badge tone="warning">待上传</Badge>
          </article>
        )}
        <article className="settlement-declaration__document settlement-declaration__contracts">
          <strong>销售合同（按销售订单）</strong>
          {documents.contracts.length ? (
            documents.contracts.map((row, index) => {
              const source = row.planned ?? row.contract;
              return (
                <div
                  key={source?.key || source?.contractNo || index}
                  className="settlement-declaration__contract"
                >
                  <div>
                    <strong>{source?.contractNo || "合同号待补"}</strong>
                    <p>
                      {source?.currency} {source ? money(source.amount) : "—"} · {row.label}
                    </p>
                    <p>资料范围：{source?.declarationNos.join("、")}</p>
                  </div>
                  {row.contract ? (
                    <a href={row.contract.fileUrl} target="_blank" rel="noreferrer">
                      查看合同
                    </a>
                  ) : (
                    <Badge tone="warning">未生成</Badge>
                  )}
                </div>
              );
            })
          ) : (
            <EmptyState
              title="暂无可生成的合同依据"
              description="请核对海关回执销售订单；香港未建批次时先登记回款。"
            />
          )}
        </article>
      </div>
      {documents.issues.length > 0 && (
        <details className="settlement-declaration__issues">
          <summary>需要处理的资料缺项（{documents.issues.length} 项）</summary>
          <ul>
            {documents.issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </details>
      )}
      {documents.warnings.length > 0 && (
        <Alert tone="warning" title="资料包提醒">
          <ul>
            {documents.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </Alert>
      )}
    </section>
  );
}
