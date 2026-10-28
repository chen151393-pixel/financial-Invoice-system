import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { Alert } from "../../../shared/components/ui";
import type { Workbench } from "../types/workbench";

/** 待通知任务的供应商没绑企微开票群时无法通知开票；数字来自后端，点击进入供应商档案“未绑定”筛选。 */
export function WorkbenchUnboundNotify({ data }: { data: NonNullable<Workbench["unboundNotify"]> }) {
  if (data.suppliers === 0) return null;
  const more = data.suppliers - data.names.length;
  return (
    <Alert
      tone="warning"
      title={`${data.suppliers} 家供应商未绑定企微开票群，${data.tasks} 个待通知任务无法发出`}
    >
      <p className="wb-unbound-names">
        {data.names.join("、")}
        {more > 0 && ` 等 ${data.suppliers} 家`}
      </p>
      <Link className="wb-unbound-link" to={`${paths.supplierGroups}?status=unbound`}>
        去供应商档案绑定开票群（未绑定）
      </Link>
    </Alert>
  );
}
