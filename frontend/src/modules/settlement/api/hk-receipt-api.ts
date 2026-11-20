import { http } from "../../../shared/api/http";
import type { BatchDetail } from "../types";
import type { HkRegistrationCheck, RegisterHkBody } from "../types/hk-receipt";
export const checkHkRegistration = (
  body: { declarationNos: string[]; receivedOn: string | null; receivedAmount: string; receivedFee: string },
  signal?: AbortSignal,
) => http<HkRegistrationCheck>("/settlement/hk-workbench/receipt-preview", "POST", body, signal);
export const registerHkReceipt = (body: RegisterHkBody) =>
  http<BatchDetail>("/settlement/hk-workbench/register", "POST", body);
