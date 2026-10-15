import { resultLabels, type Check } from "../types/matching";

export function ChecksTable({ checks, caption }: { checks: Check[]; caption: string }) {
  if (!checks.length) return <p className="matching-help">人工新建的分配没有系统比对记录。</p>;
  return (
    <div
      className="matching-table-wrap"
      role="region"
      aria-label={`${caption}，可横向滚动`}
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 宽表容器支持键盘聚焦滚动。
      tabIndex={0}
    >
      <table className="matching-table">
        <caption className="matching-help">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">比对项</th>
            <th scope="col">发票</th>
            <th scope="col">子采购</th>
            <th scope="col">结果</th>
            <th scope="col">差额 / 说明</th>
          </tr>
        </thead>
        <tbody>
          {checks.map((check) => (
            <tr key={check.key}>
              <th scope="row">{check.label}</th>
              <td>{check.invoiceValue ?? "—"}</td>
              <td>{check.purchaseValue ?? "—"}</td>
              <td className={check.result === "match" ? "matching-ok" : "matching-warning"}>
                {resultLabels[check.result]}
              </td>
              <td>
                {check.difference ?? ""}
                {check.note && <small>{check.note}</small>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
