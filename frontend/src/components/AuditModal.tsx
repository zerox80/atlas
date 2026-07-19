import React, { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { FiActivity, FiUser, FiX } from "react-icons/fi";
import api from "../api";
import { parseApiDate } from "../utils/apiDate";

interface AuditLog {
  id: number;
  user_id: number | null;
  username?: string | null;
  action: string;
  details: string;
  timestamp: string;
  ip_address?: string | null;
}

interface AuditLogPage {
  items: AuditLog[];
  has_more: boolean;
  next_cursor_timestamp: string | null;
  next_cursor_id: number | null;
}

interface AuditCursor {
  timestamp: string;
  id: number;
}

interface AuditModalProps {
  isOpen: boolean;
  onClose: () => void;
  contractId: number | null;
  contractTitle: string;
}

const AUDIT_PAGE_SIZE = 50;

const cursorFromPage = (page: AuditLogPage): AuditCursor | null =>
  page.has_more && page.next_cursor_timestamp && page.next_cursor_id
    ? {
        timestamp: page.next_cursor_timestamp,
        id: page.next_cursor_id,
      }
    : null;

const fetchAuditPage = async (
  contractId: number,
  cursor: AuditCursor | null,
  signal: AbortSignal,
): Promise<AuditLogPage> =>
  (
    await api.get<AuditLogPage>(`/contracts/${contractId}/audit`, {
      params: {
        limit: AUDIT_PAGE_SIZE,
        ...(cursor
          ? {
              cursor_timestamp: cursor.timestamp,
              cursor_id: cursor.id,
            }
          : {}),
      },
      signal,
    })
  ).data;

export default function AuditModal({
  isOpen,
  onClose,
  contractId,
  contractTitle,
}: AuditModalProps) {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<AuditCursor | null>(null);
  const [reloadVersion, setReloadVersion] = useState(0);
  const requestVersion = useRef(0);
  const loadMoreRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    const version = ++requestVersion.current;
    const controller = new AbortController();
    loadMoreRequest.current?.abort();
    loadMoreRequest.current = null;
    setLogs([]);
    setNextCursor(null);
    setError(null);
    setLoadingMore(false);

    if (!isOpen || contractId === null) {
      setLoading(false);
      return () => controller.abort();
    }

    setLoading(true);
    void fetchAuditPage(contractId, null, controller.signal)
      .then((page) => {
        if (controller.signal.aborted || requestVersion.current !== version) {
          return;
        }
        setLogs(page.items);
        setNextCursor(cursorFromPage(page));
      })
      .catch(() => {
        if (controller.signal.aborted || requestVersion.current !== version) {
          return;
        }
        setError("Aktivitäten konnten nicht geladen werden.");
      })
      .finally(() => {
        if (!controller.signal.aborted && requestVersion.current === version) {
          setLoading(false);
        }
      });

    return () => {
      controller.abort();
      loadMoreRequest.current?.abort();
    };
  }, [contractId, isOpen, reloadVersion]);

  const loadMore = async () => {
    if (contractId === null || nextCursor === null || loadingMore) return;

    const version = requestVersion.current;
    const controller = new AbortController();
    loadMoreRequest.current?.abort();
    loadMoreRequest.current = controller;
    setLoadingMore(true);
    setError(null);
    try {
      const page = await fetchAuditPage(
        contractId,
        nextCursor,
        controller.signal,
      );
      if (requestVersion.current !== version || controller.signal.aborted) {
        return;
      }
      setLogs((current) => {
        const knownIds = new Set(current.map((log) => log.id));
        return [...current, ...page.items.filter((log) => !knownIds.has(log.id))];
      });
      setNextCursor(cursorFromPage(page));
    } catch {
      if (!controller.signal.aborted && requestVersion.current === version) {
        setError("Ältere Aktivitäten konnten nicht geladen werden.");
      }
    } finally {
      if (!controller.signal.aborted && requestVersion.current === version) {
        setLoadingMore(false);
      }
      if (loadMoreRequest.current === controller) {
        loadMoreRequest.current = null;
      }
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
          onClick={(event) => event.stopPropagation()}
        >
          <div className="flex items-start justify-between border-b border-white/[0.07] p-6">
            <div>
              <p className="eyebrow">
                <FiActivity /> Nachvollziehbarkeit
              </p>
              <h2 className="mt-2 text-xl font-semibold text-white">
                Aktivitäten · {contractTitle}
              </h2>
              <p className="mt-1 text-sm muted">
                Neueste Aktionen zuerst; ältere Einträge können nachgeladen werden.
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

          <div className="flex-1 overflow-y-auto p-4 sm:p-6">
            {loading ? (
              <div className="flex h-full items-center justify-center">
                <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/10 border-t-[#b8f15a]" />
              </div>
            ) : error && logs.length === 0 ? (
              <div className="py-12 text-center">
                <p className="text-sm text-rose-300">{error}</p>
                <button
                  type="button"
                  className="btn-secondary mt-4"
                  onClick={() => setReloadVersion((current) => current + 1)}
                >
                  Erneut versuchen
                </button>
              </div>
            ) : logs.length === 0 ? (
              <div className="py-12 text-center muted">
                Keine Aktivitäten protokolliert.
              </div>
            ) : (
              <>
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
                          <td className="whitespace-nowrap px-6 py-4">
                            {parseApiDate(log.timestamp).toLocaleString("de-DE")}
                          </td>
                          <td className="flex items-center gap-2 px-6 py-4 text-white">
                            <div className="rounded-full bg-white/[0.07] p-1">
                              <FiUser size={12} />
                            </div>
                            {log.username || `User ${log.user_id}`}
                          </td>
                          <td className="px-6 py-4">
                            <span
                              className={`rounded px-2 py-1 text-xs font-bold ${
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
                          <td className="max-w-lg whitespace-pre-wrap break-words px-6 py-4 font-mono text-xs">
                            {log.details.replace(/\[CID:\d+\]\s*/, "")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {error && (
                  <p className="mt-4 text-center text-sm text-rose-300">{error}</p>
                )}
                {nextCursor && (
                  <div className="mt-4 flex justify-center">
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={loadingMore}
                      onClick={() => void loadMore()}
                    >
                      {loadingMore ? "Wird geladen …" : "Ältere Einträge laden"}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
