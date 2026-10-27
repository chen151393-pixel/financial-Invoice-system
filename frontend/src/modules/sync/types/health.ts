// 与后端 SyncHealth 一致；状态与文字由后端给出
export type HealthStatus = "success" | "partial" | "failed" | "running" | "none";
export interface SyncHealth {
  dates: string[];
  rows: {
    key: string;
    label: string;
    days: { date: string; status: HealthStatus; label: string; runs: number; failed: number }[];
  }[];
}
