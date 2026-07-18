import type { Contract } from "../../types";

export interface InvoiceStats {
  currentMonthTotal: number;
  total: number;
}

export const getInvoiceStats = (
  invoices: Contract[],
  currentDate: Date = new Date(),
): InvoiceStats => ({
  total: invoices.reduce((sum, invoice) => sum + (invoice.value || 0), 0),
  currentMonthTotal: invoices
    .filter((invoice) => {
      const invoiceDate = new Date(invoice.start_date || invoice.uploaded_at);
      return (
        invoiceDate.getMonth() === currentDate.getMonth() &&
        invoiceDate.getFullYear() === currentDate.getFullYear()
      );
    })
    .reduce((sum, invoice) => sum + (invoice.value || 0), 0),
});
