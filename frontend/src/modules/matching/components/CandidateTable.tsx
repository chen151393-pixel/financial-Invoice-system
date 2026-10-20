import { tierLabels, type Candidate } from "../types/matching";

/** 手动关联的候选子采购行；不可关联的原因由后端 block 给出，对应行不可选。 */
export function CandidateTable({
  rows,
  name,
  chosenId,
  onChoose,
}: {
  rows: Candidate[];
  name: string;
  chosenId: string | null;
  onChoose: (candidate: Candidate) => void;
}) {
  return (
    <div
      className="matching-table-wrap"
      role="region"
      aria-label="候选子采购行，可横向滚动"
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 宽表容器支持键盘聚焦滚动。
      tabIndex={0}
    >
      <table className="matching-table">
        <thead>
          <tr>
            <th scope="col">选择</th>
            <th scope="col">子采购单 / 品名</th>
            <th scope="col">供应商</th>
            <th scope="col">报关单</th>
            <th scope="col" className="matching-number">
              剩余应开（数量 / 含税）
            </th>
            <th scope="col">置信度</th>
            <th scope="col">限制</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((candidate) => {
            const purchase = candidate.purchase;
            return (
              <tr key={purchase.purchaseLineId}>
                <td>
                  <input
                    type="radio"
                    name={name}
                    aria-label={`选择 ${purchase.orderNo} ${purchase.item}`}
                    disabled={Boolean(candidate.block)}
                    checked={chosenId === purchase.purchaseLineId}
                    onChange={() => onChoose(candidate)}
                  />
                </td>
                <td>
                  {purchase.orderNo || "—"}
                  <small>
                    {purchase.item || "—"} · {purchase.unit || "单位缺失"}
                  </small>
                </td>
                <td>{purchase.supplier || "—"}</td>
                <td>{purchase.recordNumber || "—"}</td>
                <td className="matching-number">
                  {purchase.remainingQuantity ?? "—"} / {purchase.remainingAmount ?? "金额缺失"}
                </td>
                <td>
                  <span className="matching-badge" data-tier={candidate.tier}>
                    {candidate.confidence} · {tierLabels[candidate.tier]}
                  </span>
                </td>
                <td className={candidate.block ? "matching-warning" : undefined}>{candidate.block || "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
