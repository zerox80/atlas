export interface ReviewRun {
  id: string;
  model: string;
  created_at: string;
  total: number;
  remaining: number;
  counts: Record<string, number>;
  running?: boolean;
  run_error?: string | null;
}

export interface ReviewChange {
  field: string;
  before: string | number | string[] | null;
  after: string | number | string[] | null;
  can_apply: boolean;
  status?: "CONFIRMED" | "EXPLICIT_CONFLICT" | "NOT_EVIDENCED" | "NEW_INFORMATION" | "AMBIGUOUS" | "DERIVED" | "WRONG_SCOPE";
  reason?: string;
  confidence?: number | null;
  currency?: string | null;
  stored_scope?: string;
  document_scope?: string | null;
  document_name?: string;
  document_type?: string | null;
  evidence?: { page: number; quote: string } | null;
  evidence_verified?: boolean;
  alternatives?: { value: ReviewChange["after"]; scope: string; document_name: string; evidence?: ReviewChange["evidence"]; currency?: string | null }[];
}

export interface ReviewItem {
  id: number;
  contract_id?: number;
  title: string;
  document_type?: string;
  status: string;
  error?: string;
  can_write?: boolean;
  result?: {
    schema_version?: number;
    legacy_report?: boolean;
    decision?: "accepted" | "rejected";
    split_declined?: boolean;
    split_created?: { id: number; title: string; document_type: string }[];
    split_proposals?: {
      title: string;
      document_type: "contract" | "invoice";
      pages: { document: number; page: number }[];
      reason: string;
      values: Record<string, ReviewChange["after"]>;
      evidence: { document: number; page: number; quote: string };
    }[];
    changes?: ReviewChange[];
    checks?: ReviewChange[];
    warnings?: string[];
    notice_period_evidence?: string | null;
    checked_files?: number;
    applied_fields?: string[];
    model?: string;
    ocr_model?: string;
    reasoning_effort?: string;
    progress?: {
      stage?: string;
      completed_pages?: number;
      total_pages?: number;
      completed_sections?: number;
      total_sections?: number;
      document_name?: string;
      first_page?: number;
      last_page?: number;
      files?: { name: string; pages: number }[];
      ocr_completed_pages?: number;
      stage_started_at?: string;
      heartbeat_at?: string;
      request_timeout_seconds?: number;
      retry_attempt?: number;
      retry_at?: string;
    };
    diagnostic?: { code: string; stage: string; message: string; exception_type?: string; http_status?: number | null; validation_issues?: string[] };
    observations?: { scope: string; value: ReviewChange["after"]; kind: string; reason: string;
      document_name: string; evidence?: ReviewChange["evidence"]; evidence_verified: boolean; currency?: string | null }[];
  };
}

export interface ReviewPage extends ReviewRun {
  items: ReviewItem[];
}
