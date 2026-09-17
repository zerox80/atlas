import { FiCheck, FiUploadCloud, FiX, FiZap } from "react-icons/fi";
import type { Contract } from "../types";
import AttachmentList from "./upload-modal/AttachmentList";
import {
  formatUploadSize, MAX_DOCUMENT_FILES, MAX_UPLOAD_SIZE,
  type UploadFilesController,
} from "./upload-modal/useUploadFiles";

interface UploadSourcePanelProps {
  controller: UploadFilesController;
  initialData?: Contract | null;
  documentLabel: string;
  analyzing: boolean;
  uploading: boolean;
  onAnalyze: () => void;
}

const UploadSourcePanel = ({
  controller, initialData, documentLabel, analyzing, uploading, onAnalyze,
}: UploadSourcePanelProps) => {
  const { files, file, fileError, dropzone, selectedAnalysisFile } = controller;
  const busy = analyzing || uploading;
  const pdfFiles = files.filter((item) => item.name.toLowerCase().endsWith(".pdf"));

  return (
    <aside className="min-w-0 border-b border-white/[0.07] bg-black/15 p-5 sm:p-7 lg:border-b-0 lg:border-r">
      <p className="eyebrow">01 · Dateien</p>
      <div
        {...dropzone.getRootProps()}
        className={[
          "mt-4 flex min-h-40 min-w-0 flex-col items-center justify-center",
          "rounded-3xl border border-dashed p-5 text-center transition-all",
          busy ? "cursor-wait opacity-50" : "cursor-pointer",
          dropzone.isDragActive
            ? "border-[#b8f15a]/55 bg-[#b8f15a]/[0.07]"
            : files.length
              ? "border-emerald-300/25 bg-emerald-300/[0.035]"
              : "border-white/[0.12] bg-white/[0.018] hover:border-white/25 hover:bg-white/[0.03]",
        ].join(" ")}
      >
        <input {...dropzone.getInputProps({ "aria-label": "Dateien auswählen" })} />
        <div className="mb-3 flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-emerald-300/10 text-emerald-200">
          {files.length ? <FiCheck size={22} /> : <FiUploadCloud size={23} />}
        </div>
        <p className="text-sm font-semibold">
          {files.length || initialData ? "Weitere Dateien hinzufügen" : `${documentLabel} und Anhänge hier ablegen`}
        </p>
        <p className="mt-2 max-w-full text-xs leading-5 text-white/40">
          Mehrere Dateien auswählen oder hierher ziehen.
          <br />PDF, PNG, JPG oder TXT · maximal {formatUploadSize(MAX_UPLOAD_SIZE)} pro Datei
          <br />Bis zu {MAX_DOCUMENT_FILES} Dateien pro {documentLabel}.
        </p>
      </div>

      {initialData && (
        <div className="mt-4 min-w-0 rounded-2xl border border-white/10 p-3 text-xs">
          <p className="font-semibold">Gespeichertes Hauptdokument</p>
          <p className="mt-1 truncate text-white/50" title={initialData.title}>{initialData.title}</p>
          {file && (
            <button type="button" disabled={busy} onClick={controller.keepOriginal} className="mt-2 text-amber-200 underline">
              Wird ersetzt · Original behalten
            </button>
          )}
        </div>
      )}

      {files.length > 0 && (
        <ul aria-label="Neue Dateien" className="mt-4 min-w-0 space-y-2">
          {files.map((item) => (
            <li key={`${item.name}-${item.size}-${item.lastModified}`} className="flex min-w-0 items-start gap-2 rounded-2xl border border-white/10 bg-white/[0.025] p-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-emerald-100" title={item.name}>{item.name}</p>
                <p className="mt-1 text-xs text-white/40">
                  {formatUploadSize(item.size)} · {item === file ? "Hauptdokument" : "Anhang"}
                </p>
                {item !== file && (
                  <button type="button" disabled={busy} onClick={() => controller.makePrimary(item)} className="mt-2 text-xs text-[#b8f15a] hover:underline disabled:opacity-50">
                    Als Hauptdokument verwenden
                  </button>
                )}
              </div>
              <button type="button" aria-label={`${item.name} entfernen`} disabled={busy} onClick={() => controller.removeFile(item)} className="icon-btn shrink-0 disabled:opacity-50">
                <FiX size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {initialData && (
        <AttachmentList
          contractId={initialData.id}
          attachments={controller.existingAttachments}
          removedIds={controller.removedAttachmentIds}
          onToggleRemoval={controller.toggleAttachmentRemoval}
          disabled={busy}
        />
      )}

      {fileError && (
        <p className="mt-3 break-words rounded-xl border border-rose-300/15 bg-rose-300/[0.06] px-3 py-2 text-xs text-rose-200 [overflow-wrap:anywhere]" role="alert">{fileError}</p>
      )}

      {selectedAnalysisFile && (
        <div className="mt-5 min-w-0">
          {files.length > 1 && (
            <label className="block min-w-0 text-xs font-semibold text-[var(--muted)]">
              KI-Quelldatei
              <select
                className="field mt-2 min-w-0 max-w-full truncate"
                value={files.indexOf(selectedAnalysisFile)}
                disabled={busy}
                onChange={(event) => controller.setAnalysisFile(files[Number(event.target.value)])}
              >
                {pdfFiles.map((item) => <option key={files.indexOf(item)} value={files.indexOf(item)}>{item.name}</option>)}
              </select>
            </label>
          )}
          <p className="mt-2 text-xs leading-5 text-white/40">Nur diese PDF wird zum automatischen Ausfüllen genutzt.</p>
          <p className="truncate text-xs text-[var(--muted)]" title={selectedAnalysisFile.name}>{selectedAnalysisFile.name}</p>
          <button
            type="button" onClick={onAnalyze} disabled={busy}
            className="mt-3 flex w-full min-w-0 items-center justify-center gap-2 rounded-2xl border border-[#977dff]/25 bg-[#977dff]/[0.08] px-4 py-3 text-sm font-semibold text-[#c9bcff] transition-colors hover:bg-[#977dff]/[0.13] disabled:opacity-50"
          >
            <FiZap className={`shrink-0 ${analyzing ? "animate-pulse" : ""}`} />
            {analyzing ? "KI analysiert die ausgewählte PDF …" : "Mit KI automatisch ausfüllen"}
          </button>
        </div>
      )}
      <div className="mt-7 space-y-3 text-xs text-white/40">
        <p className="eyebrow">So funktioniert’s</p>
        <p>01 · Hauptdokument und Anhänge auswählen</p>
        <p>02 · Optional Details aus einer PDF mit KI übernehmen</p>
        <p>03 · Details prüfen und gemeinsam speichern</p>
      </div>
    </aside>
  );
};

export default UploadSourcePanel;
