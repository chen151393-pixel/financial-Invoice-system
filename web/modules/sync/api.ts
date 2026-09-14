import { http } from "../../shared/api/http";

export type ConnectionStatus = {
  configured: boolean;
  missing: string[];
  account: string;
  writeEnabled: boolean;
  recordTypes: string[];
  writeFields: Record<string, string[]>;
  lastConnection: { at: string } | null;
};
export const getStatus = () => http<ConnectionStatus>("/ns/status");
export const connect = () => http<{ message: string }>("/ns/connect", "POST", {});
