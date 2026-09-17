import type { ReviewChange, ReviewItem } from "./reviewTypes";
import { checkLabels, labels, scopeLabels, sourceLabels, valueText } from "./reviewPresentation";

export function FieldFinding({ change }: { change: ReviewChange }) {
  return <>
    <p className="font-medium" style={{ color: change.status === "EXPLICIT_CONFLICT" ? "var(--danger)"
      : change.status === "AMBIGUOUS" ? "var(--warning)" : "var(--muted)" }}>{checkLabels[change.status || ""] || "Älterer Prüfbericht"}</p>
    <p className="mt-1">{change.reason}</p>
    <p className="mt-1 text-xs muted">
      Gespeichert: {scopeLabels[change.stored_scope || ""] || labels[change.field]}<br />
      Dokument: {scopeLabels[change.document_scope || ""] || "Keine entsprechende Angabe"}
      {change.document_type && ` · ${sourceLabels[change.document_type] || change.document_type}`}
      {change.confidence != null && ` · KI-Sicherheit: ${Math.round(change.confidence * 100)} %`}
    </p>
    {change.evidence && <blockquote className="mt-2 border-l-2 border-[var(--line-strong)] pl-2 text-xs">
      <p>{change.document_name} · Seite {change.evidence.page}{!change.evidence_verified && " · Beleg nicht verifiziert"}</p>
      <p className="mt-1">„{change.evidence.quote}“</p>
    </blockquote>}
    {Boolean(change.alternatives?.length) && <details className="mt-2 text-xs muted">
      <summary>Weitere Dokumentangaben</summary>
      {change.alternatives!.map((item, index) => <p key={index} className="mt-2">
        {scopeLabels[item.scope] || item.scope}: {valueText(item.value, change.field, item.currency)} · {item.document_name}
        {item.evidence && <> · Seite {item.evidence.page}<br />„{item.evidence.quote}“</>}
      </p>)}
    </details>}
  </>;
}

export function ReviewComponents({ result }: { result: ReviewItem["result"] }) {
  return <>
    {Boolean(result?.components?.length) && <section className="mt-5 break-words rounded-xl border border-[var(--line)] p-4">
      <h3 className="font-semibold">Vorgeschlagene Vertragsbestandteile</h3>
      <p className="mt-1 text-sm muted">Diese Positionen bleiben dem Hauptvertrag zugeordnet. Es wird nichts automatisch angelegt.</p>
      <ul className="mt-3 space-y-3">{result!.components!.map((component, index) => <li key={index}>
        <p className="font-medium">{component.name}{component.amount_net != null && ` · ${valueText(component.amount_net, "amount")} ${component.currency || "Währung unbekannt"} netto`}</p>
        <p className="text-xs muted">{component.document_name} · Seite {component.evidence.page}
          {!component.evidence_verified && " · Beleg nicht verifiziert"}</p>
        <p className="mt-1 text-xs muted">„{component.evidence.quote}“</p>
        {component.separate_contract_reasons.length > 0 && <p className="mt-1 text-sm text-[var(--warning)]">
          Mögliche eigenständige Vertragseinheit – Vertragsnummer, Partner, Laufzeit und Kündigungsrechte manuell prüfen.
        </p>}
      </li>)}</ul>
    </section>}
    {Boolean(result?.observations?.length) && <details className="mt-4 text-sm">
      <summary>Alle erkannten Beträge, Daten und Angaben</summary>
      <ul className="mt-3 space-y-3">{result!.observations!.map((fact, index) => <li key={index}>
        <p>{scopeLabels[fact.scope] || fact.scope}: <strong>{valueText(fact.value, fact.scope)}</strong>{fact.currency && ` ${fact.currency}`}</p>
        <p className="text-xs muted">{fact.reason} · {fact.document_name}{fact.evidence && ` · Seite ${fact.evidence.page}`}
          {!fact.evidence_verified && " · Beleg nicht verifiziert"}</p>
      </li>)}</ul>
    </details>}
  </>;
}
