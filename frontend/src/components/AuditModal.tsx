import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FiX, FiActivity, FiUser } from "react-icons/fi";
import api from "../api";

interface AuditLog {
  id: number;
  user_id: number | null;
  username?: string | null;
  action: string;
  details: string;
  timestamp: string;
  ip_address?: string | null;
}

interface AuditModalProps {
  isOpen: boolean;
  onClose: () => void;
  contractId: number | null;
  contractTitle: string;
}

export default function AuditModal({
  isOpen,
  onClose,
  contractId,
  contractTitle,
}: AuditModalProps) {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen && contractId) {
      void fetchLogs(contractId);
    }
  }, [isOpen, contractId]);

  const fetchLogs = async (id: number) => {
    setLoading(true);
    try {
      const res = await api.get<AuditLog[]>(`/contracts/${id}/audit`);
      setLogs(res.data);
    } catch (error) {
      console.error("Failed to fetch audit logs", error);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-[#05070b]/80 p-4 backdrop-blur-md"
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.95, opacity: 0 }}
          className="surface-raised flex max-h-[82vh] w-full max-w-4xl flex-col overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-start justify-between border-b border-white/[0.07] p-6">
            <div>
              <p className="eyebrow">
                <FiActivity /> Nachvollziehbarkeit
              </p>
              <h2 className="mt-2 text-xl font-semibold text-white">
                Aktivitäten · {contractTitle}
              </h2>
              <p className="mt-1 text-sm muted">
                Chronologische Historie aller dokumentierten Aktionen.
              </p>
            </div>
            <button
              onClick={onClose}
              className="icon-btn"
              aria-label="Dialog schließen"
            >
              <FiX size={19} />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-4 sm:p-6">
            {loading ? (
              <div className="flex justify-center items-center h-full">
                <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/10 border-t-[#b8f15a]"></div>
              </div>
            ) : logs.length === 0 ? (
              <div className="py-12 text-center muted">
                Keine Aktivitäten protokolliert.
              </div>
            ) : (
              <div className="relative overflow-x-auto rounded-2xl border border-white/[0.07]">
                <table className="w-full text-left text-sm text-[#8b95a5]">
                  <thead className="bg-white/[0.035] text-[10px] font-bold uppercase tracking-[.13em] text-[#7f8999]">
                    <tr>
                      <th className="px-6 py-3">Zeitpunkt</th>
                      <th className="px-6 py-3">Benutzer</th>
                      <th className="px-6 py-3">Aktion</th>
                      <th className="px-6 py-3">Details</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.06]">
                    {logs.map((log) => (
                      <tr
                        key={log.id}
                        className="transition-colors hover:bg-white/[0.025]"
                      >
                        <td className="px-6 py-4 whitespace-nowrap">
                          {new Date(log.timestamp).toLocaleString("de-DE")}
                        </td>
                        <td className="flex items-center gap-2 px-6 py-4 text-white">
                          <div className="rounded-full bg-white/[0.07] p-1">
                            <FiUser size={12} />
                          </div>
                          {log.username || `User ${log.user_id}`}
                        </td>
                        <td className="px-6 py-4">
                          <span
                            className={`px-2 py-1 rounded text-xs font-bold ${
                              log.action === "UPLOAD"
                                ? "bg-green-900/50 text-green-400"
                                : log.action === "DOWNLOAD"
                                  ? "bg-[#77a7ff]/10 text-[#93b9ff]"
                                  : log.action === "UPDATE_CONTRACT"
                                    ? "bg-amber-300/10 text-amber-200"
                                    : "bg-white/[0.06] text-[#c7ced8]"
                            }`}
                          >
                            {log.action}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-xs font-mono whitespace-pre-wrap break-words max-w-lg">
                          {log.details.replace(/\[CID:\d+\]\s*/, "")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
