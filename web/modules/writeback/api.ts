import { http } from "../../shared/api/http";

export type Operation = "create" | "update";
export type Job = { id: string; target: string; operation: string; expires: number; state: string };
export type Preview = Job & {
  payload: unknown;
  before: unknown;
  result: unknown;
  stateLabel: string;
  actions: { execute: { allowed: boolean; reason: string | null } };
};
export type PreviewInput = { type: string; id: string; operation: Operation; payloadText: string };
export const listJobs = () => http<Job[]>("/ns/jobs");
export const getPreview = (id: string) => http<Preview>(`/ns/jobs/${encodeURIComponent(id)}/view`);
export const createPreview = (value: PreviewInput) => http<Preview>("/ns/preview-text", "POST", value);
export const execute = (previewId: string, confirm: boolean) =>
  http<Job>("/ns/execute", "POST", { previewId, confirm });
