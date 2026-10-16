import { http } from "../../shared/api/http";

type Action = { allowed: boolean; reason: string };
export type LemonBinding = {
  phase: "unbound" | "awaiting_authorization" | "awaiting_confirmation" | "binding" | "unknown" | "bound";
  message: string;
  mobile: string;
  confirmationMobile: string;
  verifiedAt: string | null;
  redirectUri: string;
  begin: Action;
  confirm: Action;
  verify: Action;
  sync: Action;
};

export const getLemonBinding = () => http<LemonBinding>("/sync/lemon/binding");
export const beginLemonBinding = (mobile: string) =>
  http<{ authorizationUrl: string }>("/sync/lemon/binding/start", "POST", { mobile });
export const confirmLemonBinding = (password: string) =>
  http<LemonBinding>("/sync/lemon/binding/confirm", "POST", { password });
export const verifyLemonBinding = () => http<LemonBinding>("/sync/lemon/binding/verify", "POST", {});
