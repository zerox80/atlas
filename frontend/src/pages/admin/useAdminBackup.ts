import { useState } from "react";
import api from "../../api";
import { triggerBlobDownload } from "../../utils/downloadUtils";
import { getBackupErrorMessage, getBackupFilenameFromHeader } from "./backupUtils";

export const useAdminBackup = () => {
  const [isBackupRunning, setIsBackupRunning] = useState(false);
  const [backupError, setBackupError] = useState<string | null>(null);

  const handleBackup = async () => {
    const confirmed = window.confirm(
      [
        "Diese Datensicherung enthält alle Verträge und Rechnungen",
        "einschließlich geschützter Dokumente. Die ZIP ist nicht",
        "passwortgeschützt. Jetzt erstellen?",
      ].join(" "),
    );
    if (!confirmed) return;

    setIsBackupRunning(true);
    setBackupError(null);

    try {
      const response = await api.post<Blob>("/admin/backup", undefined, {
        responseType: "blob",
      });
      triggerBlobDownload(
        response.data,
        getBackupFilenameFromHeader(response.headers?.["content-disposition"]),
      );
    } catch (error: unknown) {
      setBackupError(await getBackupErrorMessage(error));
    } finally {
      setIsBackupRunning(false);
    }
  };

  return { backupError, handleBackup, isBackupRunning };
};
