import type { BoardNodeKey, TaskBoardQuery } from "../types/board";

const NODE_KEYS: readonly BoardNodeKey[] = [
  "documents",
  "notification",
  "invoices",
  "comparison",
  "completion",
  "done",
];
const TEXT_KEYS = [
  "keyword",
  "supplierId",
  "supplierName",
  "recordNo",
  "purchaseOrderNo",
  "stage",
  "createdFrom",
  "createdTo",
] as const;

function pageNumber(value: string | null, fallback: number) {
  const number = Number(value);
  return Number.isSafeInteger(number) && number > 0 ? number : fallback;
}

/** 地址只保存查询与分页状态；业务过滤和参数合法性由后端处理。 */
export function readBoardQuery(params: URLSearchParams): TaskBoardQuery {
  return {
    keyword: params.get("keyword") || "",
    supplierId: params.get("supplierId") || "",
    ...Object.fromEntries(TEXT_KEYS.filter((key) => params.has(key)).map((key) => [key, params.get(key)])),
    node: NODE_KEYS.find((key) => key === params.get("node")) ?? "",
    page: pageNumber(params.get("page"), 1),
    pageSize: pageNumber(params.get("pageSize"), 20),
  };
}

export function writeBoardQuery(query: TaskBoardQuery): URLSearchParams {
  const params = new URLSearchParams();
  for (const key of TEXT_KEYS) if (query[key]) params.set(key, query[key]);
  if (query.node) params.set("node", query.node);
  if (query.page !== 1) params.set("page", String(query.page));
  if (query.pageSize !== 20) params.set("pageSize", String(query.pageSize));
  return params;
}
