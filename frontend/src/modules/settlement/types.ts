// 结汇接口类型：与后端 settlement 模块 VO 一一对应；金额均为十进制字符串。
export type Route = "hk_transit" | "direct";
export type BatchStatus = "collected" | "documents_ready" | "settled" | "cancelled";
export type RouteFilter = "all" | Route;
export type StatusFilter = "all" | "open" | BatchStatus;

export interface Action {
  allowed: boolean;
  reason: string;
}

export interface Candidate {
  declarationNo: string;
  recordNo: string;
  consignee: string;
  exportDate: string;
  salesOrders: string[];
  currency: string;
  amount: string;
  route: Route;
  routeLabel: string;
  routeBasis: string;
  blockedReason: string;
  batchNo: string;
}

export interface RouteTotal {
  route: Route;
  routeLabel: string;
  count: number;
  currency: string;
  amount: string;
}

export interface CandidateList {
  items: Candidate[];
  unsettled: RouteTotal[];
  suggestion: string[] | null;
  suggestionNote: string;
}

export interface CandidateQuery {
  consignee: string;
  declarationNo: string;
  route: RouteFilter;
  targetAmount: string;
}

export interface Balance {
  stage: "received" | "remitted";
  label: string;
  arrived: string;
  fee: string;
  difference: string;
  balanced: boolean;
  warnings: string[];
}

export interface BatchSummary {
  id: number;
  batchNo: string;
  route: Route;
  routeLabel: string;
  status: BatchStatus;
  statusLabel: string;
  consignee: string;
  currency: string;
  declaredTotal: string;
  receivedOn: string;
  receivedAmount: string;
  receivedFee: string;
  remittedOn: string;
  remittedAmount: string;
  remittedFee: string;
  declarationCount: number;
  balances: Balance[];
  actions: { documentsReady: Action; settle: Action; cancel: Action };
}

export interface BatchItem {
  declarationNo: string;
  recordNo: string;
  salesOrders: string;
  consignee: string;
  exportDate: string;
  currency: string;
  amount: string;
}

export interface BatchDetail extends BatchSummary {
  payer: string;
  receivingAccount: string;
  receivedReference: string;
  remittedReference: string;
  note: string;
  createdBy: string;
  createdAt: string;
  documentsReadyBy: string;
  documentsReadyAt: string;
  settledBy: string;
  settledAt: string;
  cancelledBy: string;
  cancelReason: string;
  items: BatchItem[];
}

export interface StatusCount {
  route: Route;
  status: BatchStatus;
  label: string;
  count: number;
}

export interface BatchList {
  items: BatchSummary[];
  total: number;
  page: number;
  pageSize: number;
  counts: StatusCount[];
}

export interface BatchQuery {
  route: RouteFilter;
  status: StatusFilter;
  consignee: string;
  batchNo: string;
  declarationNo: string;
  page: number;
  pageSize: number;
}

export interface CreateBatchBody {
  requestId: string;
  declarationNos: string[];
  receivedOn: string;
  receivedAmount: string;
  receivedFee: string;
  payer: string;
  receivingAccount: string;
  receivedReference: string;
  note: string;
}

export interface RemittanceBody {
  remittedOn: string;
  remittedAmount: string;
  remittedFee: string;
  remittedReference: string;
}

// ---- 结汇资料（提单、销售合同、资料包）----

export interface Bill {
  id: number;
  fileName: string;
  fileUrl: string;
  blNo: string;
  portOfLoading: string;
  portOfDischarge: string;
  onBoardDate: string;
  declarationNos: string[];
  missing: string[];
  parseNote: string;
  uploadedBy: string;
  uploadedAt: string;
}

export interface Contract {
  id: number;
  contractNo: string;
  fileUrl: string;
  contractDate: string;
  currency: string;
  amount: string;
  declarationNos: string[];
  sellerName: string;
  tradeTerm: string;
  portOfLoading: string;
  portOfDestination: string;
  stale: boolean;
  stampNote: string;
  generatedBy: string;
  generatedAt: string;
}

export interface PlannedContract {
  contractNo: string;
  currency: string;
  amount: string;
  declarationNos: string[];
}

export interface PartyOption {
  id: number;
  name: string;
  hasStamp: boolean;
}

export interface BatchDocuments {
  batchId: number;
  declarationNos: string[];
  bills: Bill[];
  planned: PlannedContract[];
  contracts: Contract[];
  buyerName: string;
  buyerReady: boolean;
  sellers: PartyOption[];
  defaults: {
    sellerPartyId: number | null;
    tradeTerm: string;
    paymentTermsCn: string;
    paymentTermsEn: string;
  };
  complete: boolean;
  issues: string[];
  warnings: string[];
  notIncluded: string[];
  edit: Action;
  generate: Action;
  package: Action;
  packageUrl: string;
}

export interface BillFields {
  blNo: string;
  portOfLoading: string;
  portOfDischarge: string;
  onBoardDate: string | null;
  declarationNos: string[];
}

export interface GenerateContractsBody {
  sellerPartyId: number;
  tradeTerm: string;
  paymentTermsCn: string;
  paymentTermsEn: string;
}

export interface Party {
  id: number;
  name: string;
  nameCn: string;
  nameEn: string;
  addressCn: string;
  addressEn: string;
  phone: string;
  hasStamp: boolean;
  stampUrl: string;
  updatedBy: string;
  updatedAt: string;
}

export interface PartyBody {
  id: number | null;
  name: string;
  nameCn: string;
  nameEn: string;
  addressCn: string;
  addressEn: string;
  phone: string;
}
