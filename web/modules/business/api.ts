import { http } from "../../shared/api/http";

export const queryRecords = (type: string, id: string, mode: "list" | "detail") =>
  http<{ data: unknown }>("/ns/query", "POST", { type, id, mode });
