// 结汇接口类型：与后端 settlement 模块 VO 一一对应；金额均为十进制字符串。
export type Route = "hk_transit" | "direct";
export type BatchStatus = "collected" | "documents_ready" | "settled" | "cancelled";
export type RouteFilter = "all" | Route;
export type StatusFilter = "all" | "open" | BatchStatus;
// 处理方式：香港中转登记回款建批次；直接收汇进直接收汇明细（总账）
export type Handling = "batch" | "ledger";

export interface Action {
  allowed: boolean;
  reason: string;
}

export interface Candidate {
  declarationNo: string;
  recordNo: string;
  consignee: string;
  exportCompany: string;
  exportDate: string;
  salesOrders: string[];
  currency: string;
  amount: string;
  route: Route;
  routeLabel: string;
  routeBasis: string;
  handling: Handling;
  handlingLabel: string;
  // 报关单本身的问题或占用；handling 为 batch 且此项为空才可选入批次
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

export interface CurrencyTotal {
  count: number;
  currency: string;
  amount: string;
}

/** 一家境外收货人（按币种分开）的应收汇汇总。 */
export interface ConsigneeTotal {
  consignee: string;
  currency: string;
  route: Route;
  routeLabel: string;
  routeBasis: string;
  handling: Handling;
  handlingLabel: string;
  exportCompanies: string[];
  count: number;
  firstExportDate: string;
  lastExportDate: string;
  amount: string;
  batchedCount: number;
  pendingCount: number;
  issueCount: number;
}

export interface CandidateList {
  // 最多列出 500 张；total 为符合筛选的全部张数
  items: Candidate[];
  total: number;
  truncated: boolean;
  // 汇总按符合筛选的全部报关单计算
  totals: RouteTotal[];
  combinedTotals: CurrencyTotal[];
  unsettled: RouteTotal[];
  consignees: ConsigneeTotal[];
  suggestion: string[] | null;
  suggestionNote: string;
}

export interface CandidateQuery {
  batchStatus?: "all" | "unbatched";
  consignee: string;
  declarationNo: string;
  route: RouteFilter;
  exportFrom: string | null;
  exportTo: string | null;
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

/** 批次内一张报关单的文件（NS 报关资料归档）现状。 */
export interface DeclarationFile {
  declarationNo: string;
  recordNo: string;
  status: string;
  statusLabel: string;
  archived: boolean;
  fileNames: string[];
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
  declarationFiles: DeclarationFile[];
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

// ---- 银行收汇明细 ----

export type ThirdPartyFilter = "all" | "yes" | "no";

export interface BankReceipt {
  id: number;
  receiptDate: string;
  receiptTime: string;
  receivingCompany: string;
  receivingAccount: string;
  payerName: string;
  // 实际客户，即境外收货人（取导入表格）
  customerName: string;
  thirdParty: boolean;
  currency: string;
  amount: string;
  reference: string;
  route: Route;
  routeLabel: string;
}

export interface BankReceiptImportResult {
  imported: number;
  duplicates: number;
  ignored: number;
}

export interface BankReceiptTotal {
  receivingCompany: string;
  featuredCompany: boolean;
  currency: string;
  count: number;
  amount: string;
  thirdPartyCount: number;
  thirdPartyAmount: string;
}

export interface BankReceiptList {
  items: BankReceipt[];
  total: number;
  page: number;
  pageSize: number;
  totals: BankReceiptTotal[];
}

export interface BankReceiptQuery {
  customer: string;
  receivingCompany: string;
  receiptFrom: string | null;
  receiptTo: string | null;
  thirdParty: ThirdPartyFilter;
  page: number;
  pageSize: number;
}

// ---- 直接收汇明细（总账）----

export type LedgerStatus = "outstanding" | "settled" | "overpaid";
export type LedgerStatusFilter = "all" | LedgerStatus;

export interface LedgerEntry {
  kind: "export" | "receipt";
  kindLabel: string;
  exportCompany: string;
  exportDate: string;
  exportAmount: string;
  receiptCompany: string;
  receiptDate: string;
  receiptAmount: string;
  sourceNo: string;
  balance: string;
  thirdParty: boolean;
  payerName: string;
}

export interface LedgerGroup {
  consignee: string;
  receivingCompany: string;
  openingBalance: string;
  currency: string;
  exportTotal: string;
  receiptTotal: string;
  balance: string;
  status: LedgerStatus;
  statusLabel: string;
  entries: LedgerEntry[];
}

export interface LedgerTotal {
  currency: string;
  openingBalance: string;
  exportTotal: string;
  receiptTotal: string;
  balance: string;
  outstanding: string;
  overpaid: string;
  consigneeCount: number;
  exportCount: number;
  receiptCount: number;
}

export interface LedgerSkipped {
  declarationNo: string;
  consignee: string;
  reason: string;
}

export interface LedgerList {
  groups: LedgerGroup[];
  total: number;
  page: number;
  pageSize: number;
  totals: LedgerTotal[];
  skipped: LedgerSkipped[];
}

export interface LedgerQuery {
  consignee: string;
  company: string;
  receivingCompany?: string;
  byRecipient?: boolean;
  startDate?: string | null;
  endDate?: string | null;
  status: LedgerStatusFilter;
  page: number;
  pageSize: number;
}
