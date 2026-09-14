import { http } from "../../shared/api/http";
import type { ComparisonResult } from "./types";

export const queryPlComparison = (criteria: { pl: string; company: string }) =>
  http<ComparisonResult>("/ns/pl-comparison", "POST", criteria);
