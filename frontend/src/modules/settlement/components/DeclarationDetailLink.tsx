import { Link, useLocation } from "react-router";
import { settlementDeclarationDetailPath } from "../../../app/paths";

/** 详情用 URL 保存打开的报关单，不丢失原列表筛选。 */
export function DeclarationDetailLink({ number }: { number: string }) {
  const { pathname, search } = useLocation();
  return (
    <Link
      to={settlementDeclarationDetailPath(number, pathname, search)}
      aria-label={`查看报关单 ${number} 结汇详情`}
    >
      {number}
    </Link>
  );
}
