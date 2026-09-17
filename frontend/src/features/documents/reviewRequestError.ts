import { isAxiosError } from "axios";
import { getApiErrorMessage, getApiErrorResponseData, getApiErrorStatus } from "../../utils/errorUtils";

export function reviewRequestError(error: unknown, fallback: string): string {
  const status = getApiErrorStatus(error);
  if (status === 429) {
    const data = getApiErrorResponseData(error);
    const detail = typeof data === "object" && data !== null && "error" in data && typeof data.error === "string" ? data.error : null;
    return `HTTP 429: ${detail || getApiErrorMessage(error, "Das Anfrage-Limit der Anwendung wurde erreicht. Den gespeicherten Prüflauf fortsetzen oder später erneut versuchen.")} · Diese Anfrage wurde vor dem Start einer neuen KI-Auswertung abgewiesen.`;
  }
  const code = status ? `HTTP ${status}` : isAxiosError(error) ? error.code || "Netzwerkfehler" : "Anfragefehler";
  return `${code}: ${getApiErrorMessage(error, fallback)}`;
}
