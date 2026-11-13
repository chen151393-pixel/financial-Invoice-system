import type { ReactNode } from "react";

/** 财务核对和海关审核共用列表工具栏，统一汇总、批量操作的位置与样式。 */
export function ReviewListToolbar({ summary, children }: { summary: ReactNode; children: ReactNode }) {
  return (
    <div className="fr-results">
      <p>{summary}</p>
      <div className="fr-results__actions" role="group" aria-label="列表操作">
        {children}
      </div>
    </div>
  );
}
