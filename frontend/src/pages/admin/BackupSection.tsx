import React from "react";
import { motion } from "framer-motion";
import {
  FiAlertTriangle,
  FiArchive,
  FiCheck,
  FiDownload,
  FiLoader,
} from "react-icons/fi";

interface BackupSectionProps {
  error: string | null;
  isRunning: boolean;
  onBackup: () => void;
}

const BackupSection: React.FC<BackupSectionProps> = ({
  error,
  isRunning,
  onBackup,
}) => (
  <motion.div
    initial={{ opacity: 0, y: 10 }}
    animate={{ opacity: 1, y: 0 }}
    className="surface overflow-hidden"
  >
    <div className="grid gap-8 p-6 lg:grid-cols-[1fr_0.8fr] lg:p-8">
      <div>
        <div
          className={[
            "mb-5 flex h-12 w-12 items-center justify-center rounded-2xl border",
            "border-[#b8f15a]/20 bg-[#b8f15a]/10 text-xl text-[#b8f15a]",
          ].join(" ")}
        >
          <FiArchive />
        </div>
        <p className="eyebrow">Vollständiger Dokumentexport</p>
        <h2 className="mt-3 text-2xl font-semibold text-white">
          Verträge und Rechnungen sichern
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-white/50">
          Erstellt eine ZIP mit allen Verträgen und Rechnungen. Für jeden
          Datensatz enthält sie eine lesbare Info-PDF sowie die hinterlegte
          Originaldatei, sofern diese auf dem Server verfügbar ist.
        </p>

        <ul className="mt-6 space-y-3 text-sm text-white/55">
          <li className="flex items-start gap-3">
            <FiCheck className="mt-0.5 shrink-0 text-[#b8f15a]" /> Geschützte
            Dokumente werden ebenfalls gesichert.
          </li>
          <li className="flex items-start gap-3">
            <FiCheck className="mt-0.5 shrink-0 text-[#b8f15a]" /> Fehlende
            Dateien werden im Sicherungsbericht aufgeführt.
          </li>
          <li className="flex items-start gap-3">
            <FiCheck className="mt-0.5 shrink-0 text-[#b8f15a]" />
            Benutzerkonten und die vollständige Datenbank sind nicht enthalten.
          </li>
        </ul>
      </div>

      <div className="flex flex-col justify-between rounded-2xl border border-white/[0.08] bg-black/20 p-5">
        <div>
          <div
            className={[
              "flex items-start gap-3 rounded-xl border border-amber-400/20",
              "bg-amber-400/[0.07] p-4 text-amber-100/80",
            ].join(" ")}
          >
            <FiAlertTriangle className="mt-0.5 shrink-0 text-amber-300" />
            <p className="text-sm leading-5">
              Die ZIP enthält vertrauliche Daten und ist nicht passwortgeschützt.
              Legen Sie sie ausschließlich an einem geschützten Ort ab.
            </p>
          </div>

          {error && (
            <div
              role="alert"
              className="mt-4 rounded-xl border border-red-400/20 bg-red-500/[0.08] p-4 text-sm text-red-200"
            >
              {error}
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={onBackup}
          disabled={isRunning}
          aria-busy={isRunning}
          className="btn-primary mt-6 w-full justify-center disabled:cursor-wait disabled:opacity-60"
        >
          {isRunning ? <FiLoader className="animate-spin" /> : <FiDownload />}
          {isRunning ? "Sicherung wird erstellt …" : "Alles sichern"}
        </button>
      </div>
    </div>
  </motion.div>
);

export default BackupSection;
