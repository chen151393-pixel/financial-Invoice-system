import type { RecoveryQuery, RecoveryView } from "../types/recovery";

const VIEWS: readonly RecoveryView[] = ["due", "collected", "outstanding", "overdue"];
const TEXT_KEYS = ["month", "memberId", "companyId", "supplierName", "orderNo"] as const;
export const RECOVERY_PAGE_SIZE = 10;

export const initialRecoveryQuery: RecoveryQuery = {
  month: "",
  view: "outstanding",
  memberId: "",
  companyId: "",
  supplierName: "",
  orderNo: "",
  page: 1,
  pageSize: RECOVERY_PAGE_SIZE,
};

function pageNumber(value: string | null, fallback: number) {
  const number = Number(value);
  return Number.isSafeInteger(number) && number > 0 ? number : fallback;
}

/** 地址只保存查询与分页状态；参数合法性与业务口径由后端判定。 */
export function readRecoveryQuery(params: URLSearchParams): RecoveryQuery {
  return {
    ...initialRecoveryQuery,
    ...Object.fromEntries(TEXT_KEYS.filter((key) => params.has(key)).map((key) => [key, params.get(key)])),
    view: VIEWS.find((view) => view === params.get("view")) ?? "outstanding",
    page: pageNumber(params.get("page"), 1),
    pageSize: pageNumber(params.get("pageSize"), RECOVERY_PAGE_SIZE),
  };
}

export function writeRecoveryQuery(query: RecoveryQuery): URLSearchParams {
  const params = new URLSearchParams();
  for (const key of TEXT_KEYS) if (query[key]) params.set(key, query[key]);
  if (query.view !== "outstanding") params.set("view", query.view);
  if (query.page !== 1) params.set("page", String(query.page));
  if (query.pageSize !== RECOVERY_PAGE_SIZE) params.set("pageSize", String(query.pageSize));
  return params;
}
