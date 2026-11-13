import { http } from "../../../shared/api/http";
import type {
  OwnerChange,
  OwnerImpact,
  OwnerList,
  OwnerOptions,
  OwnerQuery,
  OwnerVersion,
} from "../types/supplier-owner";

const root = "/task/supplier-owners";
export const getOwnerOptions = (signal?: AbortSignal) =>
  http<OwnerOptions>(`${root}/options`, "GET", undefined, signal);
export const queryOwners = (query: OwnerQuery, signal?: AbortSignal) =>
  http<OwnerList>(`${root}/query`, "POST", query, signal);
export const previewOwnerChange = (value: OwnerChange) => http<OwnerImpact>(`${root}/preview`, "POST", value);
export const saveOwnerChange = (value: OwnerChange, previewToken: string) =>
  http<{ saved: number; transferredTasks: number }>(`${root}/save`, "POST", { ...value, previewToken });
export const getOwnerHistory = (supplierId: number, companyId: number, signal?: AbortSignal) =>
  http<{ items: OwnerVersion[] }>(`${root}/${supplierId}/${companyId}/history`, "GET", undefined, signal);
