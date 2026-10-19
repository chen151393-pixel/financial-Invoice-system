import type { Capability } from "./task";

export interface DeliveryFile {
  filename: string;
  sha256: string;
  size: number;
}
export interface DeliveryPreview {
  revision: number;
  groupRevision: number;
  snapshotSha256: string;
  supplier: string;
  company: string;
  orderNumbers: string[];
  corpId: string;
  chatId: string;
  groupName: string;
  employee: string;
  userid: string;
  message: string;
  files: DeliveryFile[];
  submit: Capability;
}
export interface Delivery {
  id: string;
  revision: number;
  status: string;
  statusLabel: string;
  corpId: string;
  chatId: string;
  groupName: string;
  employee: string;
  userid: string;
  message: string;
  files: DeliveryFile[];
  createdAt: string;
  submittedAt: string | null;
  sentAt: string | null;
  lastCheckedAt: string | null;
  nextCheckAt: string | null;
  msgid: string;
  error: string;
  refresh: Capability;
  reconcile: Capability;
  autoPoll: boolean;
}
export interface Candidate {
  candidateId: string;
  evidenceSha256: string;
  description: string;
}
export interface Candidates {
  items: Candidate[];
  reason: string;
}
export interface DeliveryController {
  loading: boolean;
  busy: boolean;
  error: string;
  items: Delivery[];
  preview: DeliveryPreview | null;
  candidates: Candidates | null;
  prepare: (revision: number, groupRevision: number) => Promise<void>;
  closePreview: () => void;
  submit: () => Promise<void>;
  refresh: (id: string) => Promise<void>;
  reload: () => Promise<void>;
  findCandidates: (id: string) => Promise<void>;
  reconcile: (id: string, candidate: Candidate, reason: string) => Promise<void>;
}
