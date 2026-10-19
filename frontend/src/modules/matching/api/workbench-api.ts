import { http } from "../../../shared/api/http";
import type { Workbench, WorkbenchQuery } from "../types/workbench";

export const queryWorkbench = (query: WorkbenchQuery) =>
  http<Workbench>("/matching/workbench/query", "POST", query);

export const exportWorkbench = (query: WorkbenchQuery) =>
  http<{ filename: string; content: string; count: number }>("/matching/workbench/export", "POST", query);
