export interface OwnerVersion {
  id: string;
  memberId: string;
  memberName: string;
  effectiveDate: string;
  revision: number;
  reason: string;
  actor: string;
  createdAt: string;
}
export interface OwnerPair {
  supplierId: number;
  companyId: number;
  revision: number;
}
export interface OwnerItem extends OwnerPair {
  supplierName: string;
  nsInternalId: string;
  account: string;
  companyName: string;
  current: OwnerVersion | null;
  scheduled: OwnerVersion[];
  status: string;
}
export interface OwnerOption {
  id: number;
  name: string;
  account: string;
}
export interface OwnerOptions {
  suppliers: OwnerOption[];
  companies: OwnerOption[];
  members: OwnerOption[];
  today: string;
}
export interface OwnerQuery {
  supplierName: string;
  companyId: number | null;
  memberId: number | null;
  status: "all" | "assigned" | "unassigned" | "scheduled";
  page: number;
  pageSize: number;
}
export interface OwnerList {
  items: OwnerItem[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
  today: string;
}
export interface OwnerChange {
  items: OwnerPair[];
  memberId: number;
  effectiveDate: string;
  reason: string;
  transferOpenTasks: boolean;
}
export interface OwnerImpact {
  pairCount: number;
  openTaskCount: number;
  transferAllowed: boolean;
  transferReason: string;
  memberName: string;
  effectiveDate: string;
  previewToken: string;
}
