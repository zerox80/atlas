import { isAxiosError } from "axios";
import { getApiErrorMessage, getApiErrorStatus } from "../../utils/errorUtils";

export function reviewRequestError(error: unknown, fallback: string): string {
  const status = getApiErrorStatus(error);
  const code = status ? `HTTP ${status}` : isAxiosError(error) ? error.code || "Netzwerkfehler" : "Anfragefehler";
  return `${code}: ${getApiErrorMessage(error, fallback)}`;
}
