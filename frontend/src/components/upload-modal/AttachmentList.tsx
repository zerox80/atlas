import { useState } from "react";
import { FiDownload, FiX } from "react-icons/fi";
import api from "../../api";
import type { ContractAttachment } from "../../types";
import { triggerBlobDownload } from "../../utils/downloadUtils";
import { getApiErrorMessage } from "../../utils/errorUtils";
import { formatUploadSize } from "./useUploadFiles";

interface AttachmentListProps {
  contractId: number;
  attachments: ContractAttachment[];
  removedIds?: number[];
  onToggleRemoval?: (id: number) => void;
  disabled?: boolean;
}

const AttachmentList = ({ contractId, attachments, removedIds = [], onToggleRemoval, disabled }: AttachmentListProps) => {
  const [downloading, setDownloading] = useState<number | null>(null);
  const [error, setError] = useState("");
  if (!attachments.length) return null;

  const download = async (attachment: ContractAttachment) => {
    setDownloading(attachment.id);
    setError("");
    try {
      const response = await api.get<Blob>(`/contracts/${contractId}/attachments/${attachment.id}/download`, { responseType: "blob" });
      triggerBlobDownload(response.data, attachment.filename);
    } catch (cause) {
      setError(getApiErrorMessage(cause, "Anhang konnte nicht heruntergeladen werden."));
    } finally {
      setDownloading(null);
    }
  };

  return (
    <section className="mt-5 min-w-0" aria-label="Gespeicherte Anhänge">
      <p className="eyebrow">Anhänge ({attachments.length - removedIds.length})</p>
      <ul className="mt-3 min-w-0 space-y-2">
        {attachments.map((attachment) => {
          const removed = removedIds.includes(attachment.id);
          return (
            <li key={attachment.id} className="flex min-w-0 flex-wrap items-center gap-2 rounded-xl border border-white/10 p-3">
              <div className="min-w-0 flex-1">
                <p className={`truncate text-sm ${removed ? "line-through text-white/30" : "text-[var(--ink-soft)]"}`} title={attachment.filename}>{attachment.filename}</p>
                <p className="mt-1 text-xs text-white/40">{removed ? "Wird beim Speichern entfernt" : formatUploadSize(attachment.size)}</p>
              </div>
              <button type="button" aria-label={`${attachment.filename} herunterladen`} onClick={() => void download(attachment)} disabled={downloading !== null || disabled || removed} className="icon-btn shrink-0 disabled:opacity-40">
                <FiDownload size={16} />
              </button>
              {onToggleRemoval && (
                <button type="button" aria-label={removed ? `${attachment.filename} behalten` : `${attachment.filename} entfernen`} disabled={disabled} onClick={() => onToggleRemoval(attachment.id)} className="btn-ghost shrink-0 px-2 text-xs">
                  {removed ? "Behalten" : <FiX size={16} />}
                </button>
              )}
            </li>
          );
        })}
      </ul>
      {error && <p role="alert" className="mt-2 text-xs text-rose-200">{error}</p>}
    </section>
  );
};

export default AttachmentList;
