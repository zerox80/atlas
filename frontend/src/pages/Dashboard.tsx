import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  FiAlertCircle,
  FiArrowRight,
  FiCalendar,
  FiCheck,
  FiClock,
  FiFileText,
  FiShield,
  FiTrendingUp,
} from "react-icons/fi";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchDashboardData } from "../api";
import type { Contract, DashboardData } from "../types";
import { EmptyState, LoadingState, MetricCard, PageHeader } from "../components/ui";
import {
  getListIdFromSearchParams,
  withWorkspacePath,
} from "../features/documents/documentUtils";
import { queryKeys } from "../queryKeys";
import { formatGermanNumber } from "../utils/formatUtils";
import {
  DEFAULT_BUSINESS_TIMEZONE,
  formatBusinessDateKey,
  formatContractDate,
  getCancellationDeadline,
  getDaysUntilCancellation,
} from "../utils/contractPresentation";

const money = (value: number) =>
  value.toLocaleString("de-DE", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  });
const dateLabel = (value?: string | null, timeZone?: string) =>
  value
    ? formatContractDate(value, timeZone, {
        day: "2-digit",
        month: "short",
        year: "numeric",
      })
    : "Kein Datum";

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const listId = getListIdFromSearchParams(searchParams);

  const { data, isError, isLoading } = useQuery<DashboardData>(
    queryKeys.dashboard(listId),
    () => fetchDashboardData(listId),
  );

  const summary = data?.summary ?? {
    document_count: 0,
    total_value: 0,
    active_contract_count: 0,
    deadline_count: 0,
    protected_count: 0,
    invoice_count: 0,
  };
  const chartData = (data?.chart ?? []).map((point) => ({
    ...point,
    name: new Date(`${point.month}-01T12:00:00Z`).toLocaleDateString("de-DE", {
      month: "short",
    }),
  }));
  const upcoming = data?.upcoming ?? [];
  const displayedDocuments = data?.recent ?? [];
  const businessTimezone =
    data?.business_timezone ?? DEFAULT_BUSINESS_TIMEZONE;
  const documentRoute = (document: Contract) => {
    const path =
      document.document_type === "invoice" ? "/invoices" : "/contracts";
    return listId ? `${path}?list_id=${listId}` : path;
  };

  if (isLoading) return <LoadingState label="Dashboard wird geladen" />;
  if (isError)
    return (
      <div className="app-page">
        <EmptyState
          icon={FiAlertCircle}
          title="Dashboard konnte nicht geladen werden"
          description="Bitte versuche es erneut."
        />
      </div>
    );

  return (
    <div className="app-page">
      <PageHeader
        eyebrow={listId ? "Gefilterter Workspace" : "Workspace Intelligence"}
        title="Alles Wichtige. Auf einen Blick."
        description={[
          "Verträge, Rechnungen und Fristen in einem operativen Überblick –",
          "damit aus Dokumenten echte Entscheidungen werden.",
        ].join(" ")}
      />

      <section className="mb-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4 animate-enter">
        <MetricCard
          icon={FiTrendingUp}
          label="Dokumentenwert"
          value={money(summary.total_value)}
          meta={`${summary.document_count} Dokumente insgesamt`}
          tone="lime"
        />
        <MetricCard
          icon={FiFileText}
          label="Aktive Verträge"
          value={summary.active_contract_count}
          meta="inklusive unbefristeter Verträge"
          tone="blue"
        />
        <MetricCard
          icon={FiAlertCircle}
          label="Fristen · 60 Tage"
          value={summary.deadline_count}
          meta={
            summary.deadline_count
              ? "Aufmerksamkeit erforderlich"
              : "Alles entspannt"
          }
          tone="amber"
        />
        <MetricCard
          icon={FiShield}
          label="Geschützt"
          value={summary.protected_count}
          meta={`${summary.invoice_count} Rechnungen im Archiv`}
          tone="violet"
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(330px,.85fr)] animate-enter-delay">
        <article className="surface min-w-0 p-5 sm:p-6">
          <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="eyebrow">Finanzieller Verlauf</p>
              <h2 className="section-title mt-1">
                Dokumentenwert der letzten 6 Monate
              </h2>
            </div>
            <div className="flex gap-4 text-xs muted">
              <span className="flex items-center gap-2">
                <i className="h-2 w-2 rounded-full bg-[#77a7ff]" /> Verträge
              </span>
              <span className="flex items-center gap-2">
                <i className="h-2 w-2 rounded-full bg-[#b8f15a]" /> Rechnungen
              </span>
            </div>
          </div>
          <div className="h-[290px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} barGap={4}>
                <CartesianGrid
                  stroke="rgba(255,255,255,.055)"
                  vertical={false}
                />
                <XAxis
                  dataKey="name"
                  stroke="#687383"
                  tickLine={false}
                  axisLine={false}
                  fontSize={11}
                />
                <YAxis
                  stroke="#687383"
                  tickLine={false}
                  axisLine={false}
                  fontSize={11}
                  width={62}
                  tickFormatter={(value) =>
                    value >= 1000 ? `${Math.round(value / 1000)}k` : value
                  }
                />
                <Tooltip
                  cursor={{ fill: "rgba(255,255,255,.03)" }}
                  contentStyle={{
                    background: "#151a22",
                    border: "1px solid rgba(255,255,255,.1)",
                    borderRadius: 14,
                    color: "#fff",
                  }}
                  formatter={(value: number) => money(value)}
                />
                <Bar
                  dataKey="contracts"
                  name="Verträge"
                  fill="#77a7ff"
                  radius={[5, 5, 1, 1]}
                  maxBarSize={24}
                />
                <Bar
                  dataKey="invoices"
                  name="Rechnungen"
                  fill="#b8f15a"
                  radius={[5, 5, 1, 1]}
                  maxBarSize={24}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </article>

        <article className="surface overflow-hidden">
          <div className="flex items-start justify-between p-5 sm:p-6">
            <div>
              <p className="eyebrow">Nächste Schritte</p>
              <h2 className="section-title mt-1">Anstehende Fristen</h2>
            </div>
            <button
              onClick={() =>
                navigate(listId ? `/calendar?list_id=${listId}` : "/calendar")
              }
              className="icon-btn"
            >
              <FiCalendar />
            </button>
          </div>
          {upcoming.length ? (
            <div className="border-t border-white/[0.06]">
              {upcoming.map((contract) => {
                const cancellationDeadline = getCancellationDeadline(contract)!;
                const days = Math.max(0, getDaysUntilCancellation(contract));
                return (
                  <button
                    key={contract.id}
                    onClick={() =>
                      navigate(
                        listId ? `/contracts?list_id=${listId}` : "/contracts",
                      )
                    }
                    className={[
                      "flex w-full items-center gap-3 border-b border-white/[0.055] px-5 py-4",
                      "text-left transition last:border-0 hover:bg-white/[0.035]",
                    ].join(" ")}
                  >
                    <span
                      className={[
                        "flex h-10 w-10 shrink-0 flex-col items-center justify-center",
                        "rounded-xl border text-xs font-bold",
                        days <= 14
                          ? "border-red-400/20 bg-red-400/10 text-red-300"
                          : "border-amber-300/20 bg-amber-300/10 text-amber-200",
                      ].join(" ")}
                    >
                      <strong className="leading-none">{days}</strong>
                      <small className="mt-0.5 text-[8px] font-semibold uppercase">
                        Tage
                      </small>
                    </span>
                    <span className="min-w-0 flex-1">
                      <strong className="block truncate text-sm font-semibold text-white">
                        {contract.title}
                      </strong>
                      <small className="mt-1 block text-xs muted">
                        Kündbar bis {formatBusinessDateKey(cancellationDeadline)}
                      </small>
                    </span>
                    <FiArrowRight className="text-[#505a69]" />
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="flex min-h-[270px] flex-col items-center justify-center px-6 text-center">
              <span
                className={[
                  "mb-4 flex h-12 w-12 items-center justify-center rounded-2xl",
                  "bg-[#b8f15a]/10 text-[#b8f15a]",
                ].join(" ")}
              >
                <FiCheck size={22} />
              </span>
              <p className="font-semibold text-white">Keine nahen Fristen</p>
              <p className="mt-2 text-sm muted">
                In den nächsten 60 Tagen ist nichts fällig.
              </p>
            </div>
          )}
        </article>
      </section>

      <section className="surface mt-4 overflow-hidden animate-enter-delay">
        <div className="flex items-center justify-between px-5 py-5 sm:px-6">
          <div>
            <p className="eyebrow">
              {listId ? "Workspace" : "Zuletzt bearbeitet"}
            </p>
            <h2 className="section-title mt-1">
              {listId
                ? `Neueste ${displayedDocuments.length} von ${summary.document_count} Dokumenten`
                : "Dokumentenstrom"}
            </h2>
          </div>
          {listId ? (
            <button
              onClick={() => navigate(withWorkspacePath("/lists", listId))}
              className="btn-ghost"
            >
              Workspaces <FiArrowRight />
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={() => navigate("/contracts")}
                className="btn-ghost"
              >
                Verträge <FiArrowRight />
              </button>
              <button
                onClick={() => navigate("/invoices")}
                className="btn-ghost"
              >
                Rechnungen <FiArrowRight />
              </button>
            </div>
          )}
        </div>
        <div
          className={[
            "hidden grid-cols-[minmax(220px,1.5fr)_130px_150px_130px_32px] gap-3",
            "border-y border-white/[0.06] bg-white/[0.02] px-5 py-2.5 text-[10px]",
            "font-bold uppercase tracking-[.14em] text-[#5f6978] sm:grid",
          ].join(" ")}
        >
          <span>Dokument</span>
          <span>Typ</span>
          <span>Datum</span>
          <span>Wert</span>
          <span />
        </div>
        {displayedDocuments.length ? (
          displayedDocuments.map((item) => (
            <button
              key={item.id}
              onClick={() => navigate(documentRoute(item))}
              className="data-row w-full text-left sm:grid-cols-[minmax(220px,1.5fr)_130px_150px_130px_32px]"
            >
              <span className="flex min-w-0 items-center gap-3">
                <span
                  className={[
                    "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl",
                    item.document_type === "invoice"
                      ? "bg-[#b8f15a]/10 text-[#b8f15a]"
                      : "bg-[#77a7ff]/10 text-[#77a7ff]",
                  ].join(" ")}
                >
                  <FiFileText />
                </span>
                <span className="min-w-0">
                  <strong className="block truncate text-sm font-semibold text-white">
                    {item.title}
                  </strong>
                  <small className="block truncate text-xs muted">
                    {item.description || "Ohne Beschreibung"}
                  </small>
                </span>
              </span>
              <span className="chip w-fit">
                {item.document_type === "invoice" ? "Rechnung" : "Vertrag"}
              </span>
              <span className="text-sm muted">
                <FiClock className="mr-1.5 inline" />
                {dateLabel(item.start_date || item.uploaded_at, item.business_timezone ?? businessTimezone)}
              </span>
              <span className="text-sm font-semibold text-[#dbe2eb]">
                {item.value != null
                  ? `${formatGermanNumber(item.value)} €`
                  : "–"}
              </span>
              <FiArrowRight className="text-[#505a69]" />
            </button>
          ))
        ) : (
          <div className="px-6 py-12 text-center muted">
            Noch keine Dokumente vorhanden.
          </div>
        )}
      </section>
    </div>
  );
};

export default Dashboard;
