import type { ReviewChange } from "./reviewTypes";
import { formatGermanNumber } from "../../utils/formatUtils";

export const labels: Record<string, string> = {
  title: "Titel", description: "Beschreibung", value: "Betrag / Gesamtwert",
  annual_value: "Jahreswert", start_date: "Bisheriges Start-/Rechnungsdatum", end_date: "Enddatum",
  notice_period: "Kündigungsfrist (Tage)", tags: "Kategorien",
};
export const scopeLabels: Record<string, string> = {
  ...labels, legacy_amount: "Bisheriger Betrag – Bedeutung unbekannt", legacy_date: "Bisheriges Datum – Bedeutung unbekannt",
  contract_value_net: "Vertragswert netto", contract_value_gross: "Vertragswert brutto",
  invoice_total_net: "Rechnungssumme netto", invoice_total_gross: "Rechnungssumme brutto",
  recurring_amount: "Wiederkehrendes Entgelt", line_item_net: "Positionsbetrag netto", line_item_gross: "Positionsbetrag brutto",
  unit_price: "Einzelpreis", currency: "Währung", tax_rate: "Umsatzsteuer (%)", billing_interval: "Abrechnungsintervall",
  contract_start_date: "Vertragsbeginn", service_start_date: "Leistungsbeginn", invoice_date: "Rechnungsdatum",
  order_date: "Bestelldatum", delivery_date: "Liefer-/Lieferscheindatum", contract_end_date: "Laufzeitende",
};
export const checkLabels: Record<string, string> = {
  CONFIRMED: "Bestätigt", EXPLICIT_CONFLICT: "Echter Widerspruch", NOT_EVIDENCED: "Im Dokument nicht belegt",
  NEW_INFORMATION: "Ergänzung verfügbar", AMBIGUOUS: "Manuell prüfen", DERIVED: "Abgeleiteter Vorschlag", WRONG_SCOPE: "Anderer Geltungsbereich",
};
export const stageLabels: Record<string, string> = {
  read: "Datei lesen", prepare: "PDF vorbereiten", ocr: "OCR-Texterkennung", analysis: "KI-Auswertung",
  waiting: "Nächster Abschnitt ausstehend", complete: "Abgeschlossen", unknown: "Unbekannter Schritt",
};
export const sourceLabels: Record<string, string> = {
  invoice: "Rechnung", contract: "Vertrag", amendment: "Nachtrag", order_confirmation: "Auftragsbestätigung",
  delivery_note: "Lieferschein", unknown: "Unbekannter Dokumenttyp",
};
export function canApply(change: ReviewChange): boolean {
  return change.can_apply && change.after != null && ["EXPLICIT_CONFLICT", "NEW_INFORMATION", "DERIVED"].includes(change.status || "");
}
export function valueText(value: ReviewChange["before"], field: string, currency: string | null = "EUR"): string {
  if (value == null) return "Keine Angabe";
  if (Array.isArray(value)) return value.join(", ") || "Keine";
  if (typeof value === "string" && field.endsWith("date") && /^\d{4}-\d{2}-\d{2}$/.test(value)) return value.split("-").reverse().join(".");
  const unit = field === "value" || field === "annual_value" ? ` ${currency === "EUR" ? "€" : currency || "(Währung unbekannt)"}` : "";
  return typeof value === "number" ? `${formatGermanNumber(value)}${unit}` : value;
}
