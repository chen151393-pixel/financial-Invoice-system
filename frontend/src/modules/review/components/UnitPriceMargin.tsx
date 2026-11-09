import type { UnitPriceMargin as Margin } from "../types";
import { Badge } from "../../../shared/components/ui";

const MISMATCH = { unit_mismatch: "单位不一致", quantity_mismatch: "数量不一致" } as const;

export function UnitPriceMargin({ line }: { line: Margin & { priceEstimated?: boolean } }) {
  if (line.marginStatus === "unit_mismatch" || line.marginStatus === "quantity_mismatch") {
    // 报关行原始口径与报关口径不一致：后端不计算幅度，按需人工核对展示
    return (
      <div className="fr-margin fr-margin--negative">
        <strong>—</strong>
        <Badge tone="warning" dot={false}>
          {MISMATCH[line.marginStatus]}
        </Badge>
        <small>{line.marginNote}</small>
      </div>
    );
  }
  return (
    <div className={`fr-margin fr-margin--${line.marginStatus ?? "unavailable"}`}>
      <strong>{line.margin || "—"}</strong>
      {line.marginStatus === "ok" && line.marginNote && <small>{line.marginNote}</small>}
      {line.marginStatus === "negative" && (
        <>
          <Badge tone="danger" dot={false}>
            单价异常
          </Badge>
          <small>{line.marginNote || "报关单价低于报关行单价"}</small>
        </>
      )}
      {line.marginStatus === "unavailable" || !line.marginStatus ? (
        <small>{line.marginNote || "无法计算"}</small>
      ) : (
        <small>
          报关单价 {line.declaredUnitPriceCny} 元/{line.declaredPriceUnit || "单位未提供"}
          {line.priceEstimated && "（试算）"}
          <br />
          报关行单价 {line.originalUnitPriceCny} 元/{line.originalPriceUnit || "单位未提供"}
        </small>
      )}
    </div>
  );
}
