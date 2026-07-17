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
  can_read: boolean;
  can_write: boolean;
  can_delete: boolean;
  can_manage_protection: boolean;
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
