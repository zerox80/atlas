export interface ReviewRun {
  id: string;
  model: string;
  created_at: string;
  total: number;
  remaining: number;
  counts: Record<string, number>;
}

export interface ReviewChange {
  field: string;
  before: string | number | string[] | null;
  after: string | number | string[] | null;
  can_apply: boolean;
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
    changes: ReviewChange[];
    warnings: string[];
    notice_period_evidence?: string | null;
    checked_files: number;
    applied_fields?: string[];
  };
}

export interface ReviewPage extends ReviewRun {
  items: ReviewItem[];
}
