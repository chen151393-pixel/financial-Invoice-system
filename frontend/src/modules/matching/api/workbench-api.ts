import { http } from "../../../shared/api/http";
import type { Workbench, WorkbenchQuery } from "../types/workbench";

// 日期为空时提交 null，由后端按"不限"处理
const body = (query: WorkbenchQuery) => ({
  ...query,
  createdFrom: query.createdFrom || null,
  createdTo: query.createdTo || null,
});

export const queryWorkbench = (query: WorkbenchQuery) =>
  http<Workbench>("/matching/workbench/query", "POST", body(query));

export const exportWorkbench = (query: WorkbenchQuery) =>
  http<{ filename: string; content: string; count: number }>(
    "/matching/workbench/export",
    "POST",
    body(query),
  );
