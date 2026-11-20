import type { Route } from "../types";

export interface OverviewQuery {
  consignee: string;
  currency: string;
  page: number;
  pageSize: number;
}

export interface OverviewAmounts {
  declaredTotal: string;
  receivedTotal: string;
  outstanding: string;
  receivedFee: string;
}

export interface OverviewRoute extends OverviewAmounts {
  route: Route;
  routeLabel: string;
}

export interface OverviewTotal extends OverviewAmounts {
  currency: string;
  routes: OverviewRoute[];
  settledAmount?: string | null;
  settledCount?: number;
  declarationCount?: number;
}

export interface OverviewCustomer extends OverviewRoute {
  consignee: string;
  currency: string;
  declarationCount: number;
  receivedPercent?: number;
  receivedPercentText?: string;
  outstandingTone?: "warning" | "info" | "neutral";
  oldestPendingText?: string;
}

export interface OverviewList {
  items: OverviewCustomer[];
  total: number;
  page: number;
  pageSize: number;
  totals: OverviewTotal[];
  currencies: string[];
  insights?: OverviewInsight[];
  asOf?: string;
  skipped: { declarationNo: string; consignee: string; reason: string }[];
}

export interface OverviewAction {
  key: string;
  title: string;
  description: string;
  amount: string;
  tone: "danger" | "warning" | "progress" | "info";
  target: "declarations" | "hk" | "receipts" | "ledger";
  route: string;
  stage: string;
  consignee: string;
  batchNo: string;
}

export interface OverviewInsight {
  currency: string;
  aging: { label: string; amount: string; count: number; barWidth: string; tone: "info" | "warning" }[];
  unsettledAmount: string;
  unsettledCount: number;
  unknownDateCount: number;
  actions: OverviewAction[];
}
