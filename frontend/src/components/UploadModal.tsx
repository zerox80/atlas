import React, { useCallback, useEffect, useState } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { AnimatePresence, motion } from "framer-motion";
import { FiFileText, FiUploadCloud, FiX } from "react-icons/fi";
import { useQueryClient } from "@tanstack/react-query";
import api from "../api";
import type {
  Contract,
  ContractAnalysisResult,
  DocumentType,
} from "../types";
import { getApiErrorMessage } from "../utils/errorUtils";
import { dateInputToApiDate } from "../utils/apiDate";
import { businessDateKey } from "../utils/contractPresentation";
import { invalidateDocumentAndTagQueries } from "../queryKeys";
import { formatGermanNumber, parseGermanNumber } from "../utils/formatUtils";
import UploadSourcePanel, {
  ACCEPTED_UPLOAD_TYPES,
  formatUploadSize,
  MAX_UPLOAD_SIZE,
} from "./UploadSourcePanel";

interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialData?: Contract | null;
  documentType?: DocumentType;
}

const dateForInput = (value?: string | null, timeZone?: string) => {
  if (!value) return "";
  return /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? value
    : businessDateKey(value, timeZone);
};

const UploadModal: React.FC<UploadModalProps> = ({
  isOpen,
  onClose,
  initialData,
  documentType = "contract",
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [value, setValue] = useState("");
  const [annualValue, setAnnualValue] = useState("");
  const [tags, setTags] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [noticePeriod, setNoticePeriod] = useState("");
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [fileError, setFileError] = useState("");
  const queryClient = useQueryClient();

  const isInvoice = (initialData?.document_type ?? documentType) === "invoice";
  const documentLabel = isInvoice ? "Rechnung" : "Vertrag";

  useEffect(() => {
    if (!isOpen) return;
    setTitle(initialData?.title || "");
    setDescription(initialData?.description || "");
    setValue(
      initialData?.value != null ? formatGermanNumber(initialData.value) : "",
    );
    setAnnualValue(
      initialData?.annual_value != null
        ? formatGermanNumber(initialData.annual_value)
        : "",
    );
    setTags(initialData?.tags.map((tag) => tag.name).join(", ") || "");
    setNoticePeriod(initialData?.notice_period?.toString() || "");
    setStartDate(
      dateForInput(initialData?.start_date, initialData?.business_timezone),
    );
    setEndDate(
      dateForInput(initialData?.end_date, initialData?.business_timezone),
    );
    setFile(null);
    setFileError("");
  }, [isOpen, initialData]);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (!acceptedFiles.length) return;
    setFileError("");
    setFile(acceptedFiles[0]);
  }, []);

  const onDropRejected = useCallback((rejections: FileRejection[]) => {
    const firstError = rejections[0]?.errors[0];
    if (!firstError) return;
    if (firstError.code === "file-too-large")
      setFileError(
        `Die Datei darf maximal ${formatUploadSize(MAX_UPLOAD_SIZE)} groß sein.`,
      );
    else if (firstError.code === "file-invalid-type")
      setFileError("Bitte laden Sie eine PDF-, Bild- oder Textdatei hoch.");
    else setFileError(firstError.message);
    setFile(null);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    onDropRejected,
    accept: ACCEPTED_UPLOAD_TYPES,
    maxFiles: 1,
    maxSize: MAX_UPLOAD_SIZE,
  });

  const handleAnalyze = async () => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      alert("KI-Analyse funktioniert nur mit PDF-Dateien.");
      return;
    }
    setAnalyzing(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("document_type", isInvoice ? "invoice" : "contract");
      const { data } = await api.post<ContractAnalysisResult>(
        "/contracts/analyze",
        formData,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      if (data.title) setTitle(data.title);
      if (data.description) setDescription(data.description);
      if (data.value != null) setValue(formatGermanNumber(data.value));
      if (data.annual_value != null)
        setAnnualValue(formatGermanNumber(data.annual_value));
      if (data.start_date) setStartDate(dateForInput(data.start_date));
      if (data.end_date) setEndDate(dateForInput(data.end_date));
      setNoticePeriod(
        data.notice_period != null ? data.notice_period.toString() : "",
      );
      if (data.tags?.length) setTags(data.tags.join(", "));
    } catch (error: unknown) {
      alert(
        `KI-Analyse fehlgeschlagen: ${getApiErrorMessage(error, "Unbekannter Fehler")}`,
      );
    } finally {
      setAnalyzing(false);
    }
  };

  const resetAndClose = () => {
    setFile(null);
    setTitle("");
    setDescription("");
    setValue("");
    setAnnualValue("");
    setTags("");
    setNoticePeriod("");
    setStartDate("");
    setEndDate("");
    setFileError("");
    onClose();
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if ((!initialData && !file) || !title) return;
    setUploading(true);
    try {
      const parsedValue = value ? parseGermanNumber(value) : null;
      const parsedAnnualValue = annualValue
        ? parseGermanNumber(annualValue)
        : null;
      if (value && (parsedValue === null || parsedValue < 0)) {
        alert("Bitte geben Sie einen gültigen nicht-negativen Gesamtwert ein.");
        return;
      }
      if (
        annualValue &&
        (parsedAnnualValue === null || parsedAnnualValue < 0)
      ) {
        alert(
          "Bitte geben Sie einen gültigen nicht-negativen jährlichen Preis ein.",
        );
        return;
      }

      const formData = new FormData();
      if (file) formData.append("file", file);
      formData.append("title", title);
      formData.append("description", description || "");
      formData.append(
        "value",
        parsedValue !== null ? parsedValue.toString() : "",
      );
      formData.append(
        "annual_value",
        parsedAnnualValue !== null ? parsedAnnualValue.toString() : "",
      );
      formData.append("notice_period", noticePeriod || "");
      formData.append("tags", tags || "");
      formData.append(
        "start_date",
        dateInputToApiDate(startDate),
      );
      formData.append(
        "end_date",
        dateInputToApiDate(endDate),
      );
      if (!initialData)
        formData.append("document_type", isInvoice ? "invoice" : "contract");
      if (initialData) {
        if (initialData.version === undefined)
          throw new Error("Die Dokumentversion fehlt. Bitte lade die Ansicht neu.");
        formData.append("version", initialData.version.toString());
      }


      if (initialData)
        await api.put(`/contracts/${initialData.id}`, formData, {
          headers: { "Content-Type": "multipart/form-data" },
        });
      else
        await api.post("/contracts", formData, {
          headers: { "Content-Type": "multipart/form-data" },
        });

      await invalidateDocumentAndTagQueries(queryClient);
      resetAndClose();
    } catch (error: unknown) {
      alert(
        `Vorgang fehlgeschlagen: ${getApiErrorMessage(error, "Unbekannter Fehler")}`,
      );
    } finally {
      setUploading(false);
    }
  };

  const FieldLabel = ({ children }: { children: React.ReactNode }) => (
    <span className="mb-2 block text-[10px] font-bold uppercase tracking-[0.14em] text-white/38">
      {children}
    </span>
  );

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[80] bg-black/75 backdrop-blur-md"
            onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.97, y: 18 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 18 }}
            transition={{ duration: 0.22 }}
            className="pointer-events-none fixed inset-0 z-[90] flex items-center justify-center p-2 sm:p-5"
          >
            <div
              className={[
                "pointer-events-auto flex max-h-[96vh] w-full max-w-4xl flex-col",
                "overflow-hidden rounded-[28px] border border-white/[0.1] bg-[#0c0f0d]",
                "shadow-[0_36px_120px_rgba(0,0,0,0.65)]",
              ].join(" ")}
            >
              <header className="flex items-center justify-between border-b border-white/[0.07] px-5 py-4 sm:px-7">
                <div className="flex items-center gap-3">
                  <div
                    className={[
                      "flex h-10 w-10 items-center justify-center rounded-2xl",
                      isInvoice
                        ? "bg-[#7397ff]/10 text-[#9ab1ff]"
                        : "bg-[#b8f15a]/10 text-[#b8f15a]",
                    ].join(" ")}
                  >
                    <FiFileText />
                  </div>
                  <div>
                    <p className="eyebrow">
                      {initialData ? "Document review" : "New intake"}
                    </p>
                    <h2 className="mt-1 text-lg font-semibold">
                      {initialData
                        ? `${documentLabel} bearbeiten`
                        : `${documentLabel} erfassen`}
                    </h2>
                  </div>
                </div>
                <button onClick={onClose} className="icon-btn">
                  <FiX size={18} />
                </button>
              </header>

              <form onSubmit={handleSubmit} className="overflow-y-auto">
                <div className="grid lg:grid-cols-[0.82fr_1.18fr]">
                  <UploadSourcePanel
                    file={file}
                    fileError={fileError}
                    initialData={initialData}
                    documentLabel={documentLabel}
                    isDragActive={isDragActive}
                    analyzing={analyzing}
                    uploading={uploading}
                    getRootProps={getRootProps}
                    getInputProps={getInputProps}
                    onAnalyze={handleAnalyze}
                  />

                  <section className="p-5 sm:p-7">
                    <div className="mb-5 flex items-center justify-between">
                      <p className="eyebrow">02 · Details prüfen</p>
                      <span className="chip">
                        {isInvoice ? "Invoice" : "Contract"}
                      </span>
                    </div>
                    <div className="space-y-5">
                      <label className="block">
                        <FieldLabel>
                          {isInvoice
                            ? "Lieferant / Rechnungstitel"
                            : "Vertragstitel"}
                        </FieldLabel>
                        <input
                          type="text"
                          value={title}
                          onChange={(event) => setTitle(event.target.value)}
                          className="field"
                          placeholder={
                            isInvoice
                              ? "z. B. Telekom · Juni 2026"
                              : "z. B. Cloud Hosting Enterprise"
                          }
                          required
                        />
                      </label>
                      <div
                        className={`grid gap-4 ${isInvoice ? "" : "sm:grid-cols-2"}`}
                      >
                        <label className="block">
                          <FieldLabel>
                            {isInvoice
                              ? "Rechnungsbetrag (€)"
                              : "Gesamtwert (€)"}
                          </FieldLabel>
                          <input
                            type="text"
                            value={value}
                            onChange={(event) => setValue(event.target.value)}
                            placeholder="z. B. 17.100,00"
                            className="field"
                          />
                        </label>
                        {!isInvoice && (
                          <label className="block">
                            <FieldLabel>Jährlicher Preis (€)</FieldLabel>
                            <input
                              type="text"
                              value={annualValue}
                              onChange={(event) =>
                                setAnnualValue(event.target.value)
                              }
                              placeholder="z. B. 2.500,00"
                              className="field"
                            />
                          </label>
                        )}
                      </div>
                      <label className="block">
                        <FieldLabel>Beschreibung</FieldLabel>
                        <textarea
                          value={description}
                          onChange={(event) =>
                            setDescription(event.target.value)
                          }
                          className="field min-h-20 resize-y"
                          placeholder="Worum geht es in diesem Dokument?"
                          rows={3}
                        />
                      </label>
                      <label className="block">
                        <FieldLabel>Tags</FieldLabel>
                        <input
                          type="text"
                          value={tags}
                          onChange={(event) => setTags(event.target.value)}
                          placeholder="Software, SaaS, 2026"
                          className="field"
                        />
                        <span className="mt-2 block text-[11px] text-white/28">
                          Mehrere Tags mit Komma trennen.
                        </span>
                      </label>
                      <div
                        className={`grid gap-4 ${isInvoice ? "" : "sm:grid-cols-2"}`}
                      >
                        <label className="block">
                          <FieldLabel>
                            {isInvoice ? "Rechnungsdatum" : "Startdatum"}
                          </FieldLabel>
                          <input
                            type="date"
                            value={startDate}
                            onChange={(event) =>
                              setStartDate(event.target.value)
                            }
                            className="field [color-scheme:dark]"
                          />
                        </label>
                        {!isInvoice && (
                          <label className="block">
                            <FieldLabel>Enddatum</FieldLabel>
                            <input
                              type="date"
                              value={endDate}
                              onChange={(event) =>
                                setEndDate(event.target.value)
                              }
                              className="field [color-scheme:dark]"
                            />
                          </label>
                        )}
                      </div>
                      {!isInvoice && (
                        <label className="block">
                          <FieldLabel>Kündigungsfrist (Tage)</FieldLabel>
                          <input
                            type="number"
                            min="0"
                            value={noticePeriod}
                            onChange={(event) =>
                              setNoticePeriod(event.target.value)
                            }
                            placeholder="30"
                            className="field"
                          />
                        </label>
                      )}
                    </div>
                  </section>
                </div>

                <footer
                  className={[
                    "flex flex-col-reverse gap-2 border-t border-white/[0.07] bg-black/15",
                    "px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-7",
                  ].join(" ")}
                >
                  <p className="text-xs text-white/28">
                    Pflichtfelder werden vor dem Speichern geprüft.
                  </p>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={onClose}
                      className="btn-ghost"
                    >
                      Abbrechen
                    </button>
                    <button
                      type="submit"
                      disabled={uploading || (!initialData && !file)}
                      className="btn-primary min-w-40"
                    >
                      <FiUploadCloud />{" "}
                      {uploading
                        ? initialData
                          ? "Speichern …"
                          : "Hochladen …"
                        : initialData
                          ? "Änderungen speichern"
                          : `${documentLabel} hochladen`}
                    </button>
                  </div>
                </footer>
              </form>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};

export default UploadModal;
