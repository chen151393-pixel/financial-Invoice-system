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
}

export interface OverviewCustomer extends OverviewRoute {
  consignee: string;
  currency: string;
  declarationCount: number;
}

export interface OverviewList {
  items: OverviewCustomer[];
  total: number;
  page: number;
  pageSize: number;
  totals: OverviewTotal[];
  currencies: string[];
  skipped: { declarationNo: string; consignee: string; reason: string }[];
}
