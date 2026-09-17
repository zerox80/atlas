import { useState } from "react";
import { FiDownload, FiX } from "react-icons/fi";
import api from "../../api";
import type { ContractAttachment } from "../../types";
import { triggerBlobDownload } from "../../utils/downloadUtils";
import { getApiErrorMessage } from "../../utils/errorUtils";
import { formatUploadSize } from "./useUploadFiles";
import ReplaceFileButton from "./ReplaceFileButton";

interface AttachmentListProps {
  contractId: number;
  attachments: ContractAttachment[];
  removedIds?: number[];
  replacements?: Record<number, File>;
  onToggleRemoval?: (id: number) => void;
  onReplace?: (id: number, file: File) => void;
  onKeepOriginal?: (id: number) => void;
  onError?: (message: string) => void;
  disabled?: boolean;
}

const AttachmentList = ({
  contractId, attachments, removedIds = [], replacements = {}, onToggleRemoval,
  onReplace, onKeepOriginal, onError, disabled,
}: AttachmentListProps) => {
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
          const replacement = replacements[attachment.id];
          return (
            <li key={attachment.id} className="flex min-w-0 flex-wrap items-center gap-2 rounded-xl border border-white/10 p-3">
              <div className="min-w-0 flex-1 basis-full">
                <p className={`truncate text-sm ${removed || replacement ? "line-through text-white/30" : "text-[var(--ink-soft)]"}`} title={attachment.filename}>{attachment.filename}</p>
                {replacement && <p className="mt-1 truncate text-sm font-semibold text-emerald-100" title={replacement.name}>{replacement.name}</p>}
                <p className="mt-1 text-xs text-white/40">
                  {removed ? "Wird beim Speichern entfernt" : replacement
                    ? `${formatUploadSize(replacement.size)} · Wird beim Speichern ersetzt`
                    : formatUploadSize(attachment.size)}
                </p>
              </div>
              <button type="button" aria-label={`${attachment.filename} herunterladen`} title="Gespeicherte Datei herunterladen" onClick={() => void download(attachment)} disabled={downloading !== null || disabled || removed} className="icon-btn shrink-0 disabled:opacity-40">
                <FiDownload size={16} />
              </button>
              {onReplace && onError && !removed && (
                <ReplaceFileButton name={attachment.filename} disabled={disabled} onReplace={(file) => onReplace(attachment.id, file)} onError={onError} />
              )}
              {replacement && onKeepOriginal && (
                <button type="button" aria-label={`${attachment.filename} beibehalten`} disabled={disabled} onClick={() => onKeepOriginal(attachment.id)} className="btn-ghost shrink-0 px-2 text-xs disabled:opacity-40">
                  Original behalten
                </button>
              )}
              {onToggleRemoval && (
                <button type="button" aria-label={removed ? `${attachment.filename} behalten` : `${attachment.filename} entfernen`} title={removed ? "Entfernen rückgängig machen" : "Anhang entfernen"} disabled={disabled} onClick={() => onToggleRemoval(attachment.id)} className="btn-ghost ml-auto shrink-0 px-2 text-xs disabled:opacity-40">
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
