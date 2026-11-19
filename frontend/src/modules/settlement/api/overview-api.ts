import { http } from "../../../shared/api/http";
import type { OverviewList, OverviewQuery } from "../types/overview";

export const queryOverview = (query: OverviewQuery, signal?: AbortSignal) =>
  http<OverviewList>("/settlement/overview/query", "POST", query, signal);
