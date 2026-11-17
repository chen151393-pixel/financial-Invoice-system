import type { NsBatch } from "./ns-plan";

type Common = {
  /** 后端给出的来源与日期口径说明，前端不自行推断。 */
  sourceLabel: string;
  kindLabel: string;
  rangeLabel: string;
};
export type SyncRecord =
  | (NsBatch & Common & { source: "ns" })
  | (Omit<NsBatch, "recordType" | "kind"> &
      Common & { source: "lemon"; recordType: "lemon"; businessTypes: string[] });
export type PlanState = { enabled: boolean; nextRunAt: string | null };
export type SyncRecordList = {
  items: SyncRecord[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
  counts: Record<string, number>;
  plans: { ns: PlanState; lemon: PlanState };
};
export type SyncSource = "" | "ns" | "lemon";
export const sourceOptions: readonly (readonly [SyncSource, string])[] = [
  ["", "全部来源"],
  ["ns", "NetSuite"],
  ["lemon", "柠檬云发票"],
];
