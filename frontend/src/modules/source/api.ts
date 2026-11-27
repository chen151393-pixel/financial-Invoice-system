import { http } from "../../shared/api/http";
import type { PlSearchCriteria } from "./types";
import type { SourceComparisonResult } from "./source-types";

export const queryPlSourceComparison = (criteria: PlSearchCriteria, signal?: AbortSignal) =>
  http<SourceComparisonResult>("/source/pl-comparison", "POST", criteria, signal);
