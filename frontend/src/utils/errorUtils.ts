import axios from "axios";

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

const messageFromDetail = (detail: unknown): string | null => {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (!Array.isArray(detail)) return null;

  const messages = detail.flatMap((item) => {
    if (typeof item === "string" && item.trim()) return [item];
    if (isRecord(item) && typeof item.msg === "string" && item.msg.trim()) {
      return [item.msg];
    }
    return [];
  });
  return messages.length > 0 ? messages.join("; ") : null;
};

export const getApiErrorResponseData = (error: unknown): unknown => {
  if (axios.isAxiosError(error)) return error.response?.data;
  if (!isRecord(error) || !isRecord(error.response)) return undefined;
  return error.response.data;
};

export const getApiErrorStatus = (error: unknown): number | undefined => {
  if (axios.isAxiosError(error)) return error.response?.status;
  if (!isRecord(error) || !isRecord(error.response)) return undefined;
  return typeof error.response.status === "number"
    ? error.response.status
    : undefined;
};

export const getApiErrorDetail = (error: unknown): unknown => {
  const responseData = getApiErrorResponseData(error);
  return isRecord(responseData) ? responseData.detail : undefined;
};

export const getErrorMessage = (error: unknown, fallback: string): string =>
  error instanceof Error && error.message.trim() ? error.message : fallback;

export const getApiErrorMessage = (
  error: unknown,
  fallback: string,
): string => {
  const detailMessage = messageFromDetail(getApiErrorDetail(error));
  if (detailMessage) return detailMessage;

  const responseData = getApiErrorResponseData(error);
  if (typeof responseData === "string" && responseData.trim()) {
    return responseData;
  }

  if (axios.isAxiosError(error) && error.response) return fallback;
  return getErrorMessage(error, fallback);
};
