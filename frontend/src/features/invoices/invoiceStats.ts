import type { Contract } from "../../types";
import { businessDateKey } from "../../utils/contractPresentation";

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
      const timeZone = invoice.business_timezone;
      const invoiceMonth = businessDateKey(
        invoice.start_date || invoice.uploaded_at,
        timeZone,
      ).slice(0, 7);
      return invoiceMonth === businessDateKey(currentDate, timeZone).slice(0, 7);
    })
    .reduce((sum, invoice) => sum + (invoice.value || 0), 0),
});
