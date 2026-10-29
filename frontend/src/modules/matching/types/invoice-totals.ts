export type InvoiceTotals = {
  amounts: {
    currency: string;
    count: number;
    gross: string | null;
    tax: string | null;
    pendingAmount: string;
    pendingCount: number;
    reviewAmount: string;
    reviewCount: number;
  }[];
};

export type InvoiceTotalsFilters = {
  q?: string;
  invoice_no?: string;
  seller_name?: string;
  seller_tax_no?: string;
  account: string;
  status: string;
  date_from: string;
  date_to: string;
};
