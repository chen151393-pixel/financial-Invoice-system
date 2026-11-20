import type { Action, Route } from "../types";
export interface SettlementStage {
  key: string;
  label: string;
  count: number;
  amount: string;
  receivedAmount: string;
  outstandingAmount: string;
  barWidth: string;
  tone: "warning" | "progress" | "info" | "success";
  note: string;
  select: Action;
}
export interface ProgressRoute {
  route: Route;
  label: string;
  amount: string;
  count: number;
  note: string;
  stages: SettlementStage[];
}
export interface ProgressCurrency {
  currency: string;
  amount: string;
  count: number;
  settledAmount: string;
  settledCount: number;
  unsettledAmount: string;
  unsettledCount: number;
  settledPercent: string;
  settledPercentText: string;
  barMaximum: string;
  routes: ProgressRoute[];
}
export interface SettlementProgress {
  currencies: ProgressCurrency[];
  excludedCount: number;
  asOf: string;
}
