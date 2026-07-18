import {
  getApiErrorDetail,
  getApiErrorResponseData,
} from "../../utils/errorUtils";

const safeBackupFilename = (candidate?: string): string => {
  const filename = candidate
    ?.split(/[\\/]/)
    .pop()
    // Control characters and reserved Windows filename characters are unsafe in downloads.
    // eslint-disable-next-line no-control-regex
    ?.replace(/[\u0000-\u001f<>:"|?*]/g, "_")
    .trim();
  return filename?.toLowerCase().endsWith(".zip")
    ? filename
    : "atlas-datensicherung.zip";
};

export const getBackupFilenameFromHeader = (
  contentDisposition?: string,
): string => {
  if (!contentDisposition) return "atlas-datensicherung.zip";

  const encodedMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (encodedMatch) {
    try {
      return safeBackupFilename(decodeURIComponent(encodedMatch[1].trim()));
    } catch {
      // Fall through to the plain filename variant.
    }
  }

  const filenameMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
  return safeBackupFilename(filenameMatch?.[1]);
};

export const getBackupErrorMessage = async (error: unknown): Promise<string> => {
  const detail = getApiErrorDetail(error);
  if (typeof detail === "string") return detail;

  const responseData = getApiErrorResponseData(error);
  if (typeof responseData === "string") return responseData;

  if (responseData instanceof Blob) {
    try {
      const payload: unknown = JSON.parse(await responseData.text());
      if (
        typeof payload === "object" &&
        payload !== null &&
        "detail" in payload &&
        typeof payload.detail === "string"
      ) {
        return payload.detail;
      }
    } catch {
      // Use the stable message below for non-JSON error bodies.
    }
  }

  return "Datensicherung konnte nicht erstellt werden. Bitte versuchen Sie es erneut.";
};
