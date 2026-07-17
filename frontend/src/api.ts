import axios, { type AxiosRequestConfig } from "axios";
import {
  buildContractQueryParams,
  type ContractFilterState,
} from "./utils/filterParams";
import type { Contract } from "./types";

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

export const toggleContractProtection = (id: number) =>
  api.put(`/contracts/${id}/toggle-protection`);

export const fetchAllContracts = async (
  params: Record<string, unknown> = {},
): Promise<Contract[]> => {
  const pageSize = 200;
  const contracts: Contract[] = [];
  let cursor: Pick<Contract, "id" | "uploaded_at"> | null = null;

  for (;;) {
    const response = await api.get<Contract[]>("/contracts", {
      params: {
        ...params,
        limit: pageSize,
        ...(cursor
          ? {
              cursor_uploaded_at: cursor.uploaded_at,
              cursor_id: cursor.id,
            }
          : {}),
      },
    });
    contracts.push(...response.data);
    if (response.data.length < pageSize) return contracts;
    cursor = response.data[response.data.length - 1];
  }
};

export const exportContracts = (
  filters: ContractFilterState,
  format: "csv" | "excel",
) =>
  api.get<Blob>("/contracts/export", {
    params: { ...buildContractQueryParams(filters), format },
    responseType: "blob",
  });

export default api;
