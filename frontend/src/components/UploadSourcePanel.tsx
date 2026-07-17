import React from "react";
import type { DropzoneInputProps, DropzoneRootProps } from "react-dropzone";
import { FiCheck, FiUploadCloud, FiZap } from "react-icons/fi";

export const MAX_UPLOAD_SIZE = 10 * 1024 * 1024;
export const ACCEPTED_UPLOAD_TYPES = {
  "application/pdf": [".pdf"],
  "image/png": [".png"],
  "image/jpeg": [".jpg", ".jpeg"],
  "text/plain": [".txt"],
};

export const formatUploadSize = (bytes: number) =>
  `${(bytes / 1024 / 1024).toFixed(0)} MB`;

interface UploadSourcePanelProps {
  file: File | null;
  fileError: string;
  initialData?: unknown;
  documentLabel: string;
  isDragActive: boolean;
  analyzing: boolean;
  uploading: boolean;
  getRootProps: () => DropzoneRootProps;
  getInputProps: () => DropzoneInputProps;
  onAnalyze: () => void;
}

const UploadSourcePanel: React.FC<UploadSourcePanelProps> = ({
  file,
  fileError,
  initialData,
  documentLabel,
  isDragActive,
  analyzing,
  uploading,
  getRootProps,
  getInputProps,
  onAnalyze,
}) => (
  <aside className="border-b border-white/[0.07] bg-black/15 p-5 sm:p-7 lg:border-b-0 lg:border-r">
    <p className="eyebrow">01 · Quelldatei</p>
    <div
      {...getRootProps()}
      className={[
        "mt-4 flex min-h-52 cursor-pointer flex-col items-center justify-center",
        "rounded-3xl border border-dashed p-6 text-center transition-all",
        isDragActive
          ? "border-[#b8f15a]/55 bg-[#b8f15a]/[0.07]"
          : file
            ? "border-emerald-300/25 bg-emerald-300/[0.035]"
            : "border-white/[0.12] bg-white/[0.018] hover:border-white/25 hover:bg-white/[0.03]",
      ].join(" ")}
    >
      <input {...getInputProps()} />
      <div
        className={[
          "mb-4 flex h-12 w-12 items-center justify-center rounded-2xl",
          file
            ? "bg-emerald-300/10 text-emerald-200"
            : "bg-white/[0.05] text-white/45",
        ].join(" ")}
      >
        {file ? <FiCheck size={22} /> : <FiUploadCloud size={23} />}
      </div>
      {file ? (
        <>
          <p className="max-w-full truncate text-sm font-semibold text-emerald-100">
            {file.name}
          </p>
          <p className="mt-2 text-xs text-white/34">
            {(file.size / 1024 / 1024).toFixed(1)} MB · Klicken zum Ersetzen
          </p>
        </>
      ) : (
        <>
          <p className="text-sm font-semibold">
            {initialData ? "Neue Datei ablegen" : `${documentLabel} hier ablegen`}
          </p>
          <p className="mt-2 max-w-56 text-xs leading-5 text-white/34">
            PDF, PNG, JPG oder TXT · maximal {formatUploadSize(MAX_UPLOAD_SIZE)}
          </p>
        </>
      )}
    </div>
    {fileError && (
      <p
        className={[
          "mt-3 rounded-xl border border-rose-300/15 bg-rose-300/[0.06] px-3 py-2",
          "text-xs text-rose-200",
        ].join(" ")}
        role="alert"
      >
        {fileError}
      </p>
    )}

    {file && !initialData && file.name.toLowerCase().endsWith(".pdf") && (
      <button
        type="button"
        onClick={onAnalyze}
        disabled={analyzing || uploading}
        className={[
          "mt-3 flex w-full items-center justify-center gap-2 rounded-2xl border",
          "border-[#977dff]/25 bg-[#977dff]/[0.08] px-4 py-3 text-sm font-semibold",
          "text-[#c9bcff] transition-colors hover:bg-[#977dff]/[0.13] disabled:opacity-50",
        ].join(" ")}
      >
        <FiZap className={analyzing ? "animate-pulse" : ""} />{" "}
        {analyzing ? `KI analysiert ${documentLabel} …` : "Mit KI automatisch ausfüllen"}
      </button>
    )}

    <div className="mt-7 space-y-3 text-xs text-white/36">
      <p className="eyebrow">So funktioniert’s</p>
      <p className="flex gap-2">
        <span className="text-[#b8f15a]">01</span> Datei sicher hochladen
      </p>
      <p className="flex gap-2">
        <span className="text-[#b8f15a]">02</span> Daten per KI extrahieren
      </p>
      <p className="flex gap-2">
        <span className="text-[#b8f15a]">03</span> Prüfen und speichern
      </p>
    </div>
  </aside>
);

export default UploadSourcePanel;
