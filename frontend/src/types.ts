export interface Tag {
  id?: number;
  name: string;
  color: string;
}

export type DocumentType = "contract" | "invoice";

export interface ContractList {
  id: number;
  name: string;
  description: string | null;
  color: string;
  created_at: string;
  contract_count: number;
}

export interface Contract {
  id: number;
  title: string;
  description?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  uploaded_at: string;
  value?: number | null;
  annual_value?: number | null;
  tags: Tag[];
  lists?: ContractList[];
  version?: number;
  notice_period?: number | null;
  file_extension: string;
  document_type: DocumentType;
  is_protected: boolean;
  business_timezone?: string;
  can_read: boolean;
  can_write: boolean;
  can_delete: boolean;
  can_manage_protection: boolean;
}

export interface ContractCollectionSummary {
  all: number;
  active: number;
  attention: number;
  expired: number;
  total_value: number;
  current_month_value: number;
}

export interface ContractPage {
  items: Contract[];
  summary: ContractCollectionSummary | null;
  has_more: boolean;
  next_cursor_uploaded_at: string | null;
  next_cursor_id: number | null;
}

export interface DashboardData {
  business_timezone?: string;
  summary: {
    document_count: number;
    total_value: number;
    active_contract_count: number;
    deadline_count: number;
    protected_count: number;
    invoice_count: number;
  };
  chart: Array<{
    month: string;
    contracts: number;
    invoices: number;
  }>;
  upcoming: Contract[];
  recent: Contract[];
}

export interface CalendarData {
  business_timezone?: string;
  items: Contract[];
  truncated: boolean;
}

export interface ContractAnalysisResult {
  title?: string | null;
  description?: string | null;
  value?: number | null;
  annual_value?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  notice_period?: number | null;
  tags?: string[];
}
