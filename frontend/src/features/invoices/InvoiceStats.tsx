import React from "react";
import { FiTrendingUp } from "react-icons/fi";
import { formatGermanNumber } from "../../utils/formatUtils";
import type { InvoiceStats as InvoiceStatsData } from "./invoiceStats";

interface InvoiceStatsProps {
  invoiceCount: number;
  stats: InvoiceStatsData;
}

const InvoiceStats: React.FC<InvoiceStatsProps> = ({ invoiceCount, stats }) => (
  <section className="mb-5 grid gap-4 sm:grid-cols-3">
    <article className="surface p-5">
      <p className="eyebrow">Gesamtes Archiv</p>
      <p className="metric-value mt-3">{formatGermanNumber(stats.total)} €</p>
      <p className="mt-2 text-xs muted">aus {invoiceCount} Rechnungen</p>
    </article>
    <article className="surface p-5">
      <p className="eyebrow">Dieser Monat</p>
      <p className="metric-value mt-3 text-[#b8f15a]">
        {formatGermanNumber(stats.currentMonthTotal)} €
      </p>
      <p className="mt-2 text-xs muted">nach Rechnungsdatum</p>
    </article>
    <article className="surface p-5">
      <p className="eyebrow">Ø Rechnungswert</p>
      <p className="metric-value mt-3">
        {formatGermanNumber(invoiceCount ? stats.total / invoiceCount : 0)} €
      </p>
      <p className="mt-2 flex items-center gap-1.5 text-xs muted">
        <FiTrendingUp className="text-[#77a7ff]" /> automatisch berechnet
      </p>
    </article>
  </section>
);

export default InvoiceStats;
