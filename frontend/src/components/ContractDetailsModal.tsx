import { AnimatePresence, motion } from "framer-motion";
import {
  FiCalendar,
  FiDownload,
  FiEdit3,
  FiFileText,
  FiTag,
  FiX,
} from "react-icons/fi";
import type { Contract } from "../types";
import { formatGermanNumber } from "../utils/formatUtils";
import { formatContractDate } from "../utils/contractPresentation";

interface ContractDetailsModalProps {
  contract: Contract | null;
  onClose: () => void;
  onDownload: (contract: Contract) => void;
  onEdit?: (contract: Contract) => void;
}

const formatDate = (value?: string | null, timeZone?: string) =>
  value ? formatContractDate(value, timeZone) : "Nicht hinterlegt";
const formatMoney = (value?: number | null) =>
  value != null ? `${formatGermanNumber(value)} €` : "Nicht hinterlegt";

const ContractDetailsModal: React.FC<ContractDetailsModalProps> = ({
  contract,
  onClose,
  onDownload,
  onEdit,
}) => {
  if (!contract) return null;

  const fields = [
    { label: "Startdatum", value: formatDate(contract.start_date, contract.business_timezone) },
    {
      label: "Enddatum",
      value: contract.end_date ? formatDate(contract.end_date, contract.business_timezone) : "Unbefristet",
    },
    {
      label: "Kündigungsfrist",
      value:
        contract.notice_period != null
          ? `${contract.notice_period} Tage`
          : "Nicht hinterlegt",
    },
    { label: "Gesamtwert", value: formatMoney(contract.value) },
    { label: "Jährlicher Preis", value: formatMoney(contract.annual_value) },
    { label: "Hochgeladen am", value: formatDate(contract.uploaded_at, contract.business_timezone) },
  ];

  return (
    <AnimatePresence>
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
        <section
          role="dialog"
          aria-modal="true"
          aria-labelledby="contract-details-title"
          className={[
            "pointer-events-auto flex max-h-[96vh] w-full max-w-2xl flex-col",
            "overflow-hidden rounded-[28px] border border-white/[0.1] bg-[#0c0f0d]",
            "shadow-[0_36px_120px_rgba(0,0,0,0.65)]",
          ].join(" ")}
        >
          <header className="flex items-start justify-between gap-4 border-b border-white/[0.07] px-5 py-4 sm:px-7">
            <div className="flex min-w-0 items-center gap-3">
              <span
                className={[
                  "flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl",
                  "bg-[#b8f15a]/10 text-[#b8f15a]",
                ].join(" ")}
              >
                <FiFileText />
              </span>
              <div className="min-w-0">
                <p className="eyebrow">Vertragsdetails</p>
                <h2
                  id="contract-details-title"
                  className="mt-1 truncate text-lg font-semibold"
                >
                  {contract.title}
                </h2>
              </div>
            </div>
            <button
              onClick={onClose}
              className="icon-btn shrink-0"
              aria-label="Details schließen"
            >
              <FiX size={18} />
            </button>
          </header>

          <div className="overflow-y-auto p-5 sm:p-7">
            <div className="rounded-2xl border border-white/[0.07] bg-black/15 p-4">
              <p className="eyebrow">
                <FiFileText className="mr-1 inline" /> Beschreibung
              </p>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-[#d8dee7]">
                {contract.description || "Keine Beschreibung hinterlegt."}
              </p>
            </div>

            <div
              className={[
                "mt-5 grid gap-px overflow-hidden rounded-2xl border border-white/[0.07]",
                "bg-white/[0.07] sm:grid-cols-2",
              ].join(" ")}
            >
              {fields.map((field) => (
                <div key={field.label} className="bg-[#0d1117] px-4 py-3.5">
                  <p className="text-[10px] font-bold uppercase tracking-[.12em] text-[#596474]">
                    {field.label}
                  </p>
                  <p className="mt-1 text-sm font-semibold text-[#d8dee7]">
                    {field.value}
                  </p>
                </div>
              ))}
            </div>

            <div className="mt-5 flex flex-wrap gap-2">
              <span className="chip">
                <FiCalendar />{" "}
                {contract.file_extension?.replace(/^\./, "").toUpperCase() ||
                  "Dokument"}
              </span>
              {contract.is_protected && (
                <span className="chip border-[#b28cff]/15 bg-[#b28cff]/10 text-[#c9adff]">
                  Geschützt
                </span>
              )}
              {contract.tags.map((tag) => (
                <span key={tag.id ?? tag.name} className="chip">
                  <FiTag /> {tag.name}
                </span>
              ))}
            </div>
          </div>

          <footer
            className={[
              "flex flex-col-reverse gap-2 border-t border-white/[0.07] bg-black/15",
              "px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-7",
            ].join(" ")}
          >
            <button type="button" onClick={onClose} className="btn-ghost">
              Schließen
            </button>
            <div className="flex flex-wrap gap-2">
              {contract.can_write && onEdit && (
                <button
                  type="button"
                  onClick={() => onEdit(contract)}
                  className="btn-secondary"
                >
                  <FiEdit3 /> Bearbeiten
                </button>
              )}
              <button
                type="button"
                onClick={() => onDownload(contract)}
                className="btn-primary"
              >
                <FiDownload /> Herunterladen
              </button>
            </div>
          </footer>
        </section>
      </motion.div>
    </AnimatePresence>
  );
};

export default ContractDetailsModal;
