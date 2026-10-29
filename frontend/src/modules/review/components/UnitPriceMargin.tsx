import type { UnitPriceMargin as Margin } from "../types";
import { Badge } from "../../../shared/components/ui";

export function UnitPriceMargin({ line }: { line: Margin & { priceEstimated?: boolean } }) {
  return (
    <div className={`fr-margin fr-margin--${line.marginStatus ?? "unavailable"}`}>
      <strong>{line.margin || "—"}</strong>
      {line.marginStatus === "ok" && line.marginNote && <small>{line.marginNote}</small>}
      {line.marginStatus === "negative" && (
        <>
          <Badge tone="danger" dot={false}>
            单价异常
          </Badge>
          <small>{line.marginNote || "申报单价低于采购折算报关单价"}</small>
        </>
      )}
      {line.marginStatus === "unavailable" || !line.marginStatus ? (
        <small>{line.marginNote || "无法计算"}</small>
      ) : (
        <small>
          报关单价 {line.declaredUnitPriceCny}
          {line.priceEstimated && "（试算）"} / 采购金额折算报关单价 {line.combinedPurchaseUnitPrice} 元
        </small>
      )}
    </div>
  );
}
