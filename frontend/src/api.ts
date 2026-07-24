import axios, { type AxiosRequestConfig } from "axios";
import {
  buildContractQueryParams,
  type ContractFilterState,
} from "./utils/filterParams";
import type {
  CalendarData,
  ContractPage,
  ContractProtectionBulkResult,
  DashboardData,
  DocumentType,
} from "./types";

export const API_BASE_URL = import.meta.env.VITE_API_URL || "/api";
const CSRF_COOKIE_NAME = "csrf_token";
const CSRF_HEADER_NAME = "X-CSRF-Token";
const CSRF_TOKEN_PATH = "/csrf-token";
const LOGIN_PATH = "/token";
const MUTATING_METHODS = new Set(["post", "put", "patch", "delete"]);

let csrfTokenRequest: Promise<string | null> | null = null;

export const buildApiUrl = (path: string): string => {
  const normalizedBase = API_BASE_URL.replace(/\/$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${normalizedBase}${normalizedPath}`;
};

const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // Required for HttpOnly cookie authentication
});

export const getCookieValue = (name: string): string | null => {
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : null;
};

const isMutatingMethod = (method?: string): boolean =>
  MUTATING_METHODS.has((method ?? "get").toLowerCase());

const isLoginRequest = (config: AxiosRequestConfig): boolean =>
  config.url === LOGIN_PATH;

export const ensureCsrfToken = async (): Promise<string | null> => {
  const existingToken = getCookieValue(CSRF_COOKIE_NAME);
  if (existingToken) return existingToken;

  if (!csrfTokenRequest) {
    csrfTokenRequest = api
      .get(CSRF_TOKEN_PATH)
      .then(() => getCookieValue(CSRF_COOKIE_NAME))
      .finally(() => {
        csrfTokenRequest = null;
      });
  }

  return csrfTokenRequest;
};

api.interceptors.request.use(async (config) => {
  if (isMutatingMethod(config.method) && !isLoginRequest(config)) {
    const csrfToken = await ensureCsrfToken();
    if (csrfToken) {
      config.headers.set(CSRF_HEADER_NAME, csrfToken);
    }
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  },
);

export const toggleContractProtection = (id: number, version: number) =>
  api.put(`/contracts/${id}/toggle-protection`, null, {
    params: { version },
  });

export const protectContracts = async (
  contractIds: number[],
): Promise<ContractProtectionBulkResult> =>
  (
    await api.put<ContractProtectionBulkResult>("/contracts/bulk-protect", {
      contract_ids: contractIds,
    })
  ).data;

export interface ContractPageParams {
  document_type?: DocumentType;
  include_summary?: boolean;
  is_protected?: boolean;
  limit?: number;
  list_id?: number;
  max_value?: number;
  min_value?: number;
  q?: string;
  sort_by?: "title" | "value" | "start_date" | "end_date" | "uploaded_at";
  sort_order?: "asc" | "desc";
  start_date_from?: string;
  start_date_to?: string;
  state?: "active" | "attention" | "expired";
  status?: "active" | "expired";
  tags?: string;
}

export type ContractCursor =
  | { kind: "keyset"; uploadedAt: string; id: number }
  | { kind: "offset"; offset: number };

export const getNextContractPageParam = (
  page: ContractPage,
): ContractCursor | undefined => {
  if (!page.has_more) return undefined;
  if (page.next_offset !== null && page.next_offset !== undefined) {
    return { kind: "offset", offset: page.next_offset };
  }
  if (page.next_cursor_uploaded_at && page.next_cursor_id !== null) {
    return {
      kind: "keyset",
      uploadedAt: page.next_cursor_uploaded_at,
      id: page.next_cursor_id,
    };
  }
  return undefined;
};

export const fetchContractPage = async (
  params: ContractPageParams = {},
  cursor?: ContractCursor,
): Promise<ContractPage> => {
  const response = await api.get<ContractPage>("/contracts/page", {
    params: {
      ...params,
      ...(cursor?.kind === "offset"
        ? { offset: cursor.offset }
        : cursor?.kind === "keyset"
          ? {
              cursor_uploaded_at: cursor.uploadedAt,
              cursor_id: cursor.id,
            }
          : {}),
    },
  });
  return response.data;
};

export const fetchDashboardData = async (
  listId: number | null,
): Promise<DashboardData> =>
  (await api.get<DashboardData>("/contracts/dashboard", {
    params: listId ? { list_id: listId } : undefined,
  })).data;

export const fetchCalendarData = async (
  start: string,
  end: string,
  listId: number | null = null,
): Promise<CalendarData> =>
  (
    await api.get<CalendarData>("/contracts/calendar", {
      params: {
        start,
        end,
        ...(listId !== null ? { list_id: listId } : {}),
      },
    })
  ).data;

export const exportContracts = (
  filters: ContractFilterState,
  format: "csv" | "excel",
  documentType: DocumentType = "contract",
) =>
  api.get<Blob>("/contracts/export", {
    params: {
      ...buildContractQueryParams(filters),
      document_type: documentType,
      format,
    },
    responseType: "blob",
  });

export default api;
