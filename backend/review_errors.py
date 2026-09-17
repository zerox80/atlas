"""Useful diagnostics without leaking document text or API credentials."""

import httpx
from pydantic import ValidationError

from ai_errors import AIProcessingCapacityError, InvalidStructuredAIResponse
from review_analysis import ReviewProcessingError
from review_response import validation_issues


def error_details(exc: Exception, stage: str, timeout: int) -> dict:
    code, message = "PROCESSING_ERROR", "Unerwarteter Verarbeitungsfehler. Fehlerklasse und Schritt an den Administrator weitergeben."
    if isinstance(exc, ReviewProcessingError):
        code, message = exc.code, str(exc)
    elif isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        code, message = "TIMEOUT", f"Zeitlimit überschritten (Anfrage bis {timeout} Sekunden). Bereits abgeschlossene Abschnitte bleiben gespeichert."
    elif isinstance(exc, (InvalidStructuredAIResponse, ValidationError)):
        code, message = "INVALID_AI_RESPONSE", "Die KI-Antwort war unvollständig oder entsprach nicht dem erwarteten JSON-Schema."
    elif isinstance(exc, AIProcessingCapacityError):
        code, message = "CAPACITY", "Die lokale KI-Verarbeitung ist ausgelastet. Später erneut versuchen."
    elif isinstance(exc, FileNotFoundError):
        code, message = "FILE_MISSING", "Die gespeicherte Dokumentdatei fehlt auf dem Server."
    elif isinstance(exc, PermissionError):
        code, message = "FILE_ACCESS", "Der Server kann die Dokumentdatei nicht lesen (Dateiberechtigung)."
    elif isinstance(exc, httpx.NetworkError):
        code, message = "NETWORK", "Mistral ist vom Backend nicht erreichbar. Verbindung, DNS und Proxy prüfen."
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        code = f"PROVIDER_HTTP_{status}"
        message = {
            400: "Mistral lehnt die Anfrage ab. Modellkennung, Reasoning-Konfiguration und Anfragegrenzen prüfen.",
            401: "Mistral hat den API-Schlüssel abgelehnt.",
            403: "Mistral verweigert den Zugriff. Schlüsselrechte und Modellfreigabe prüfen.",
            404: "Mistral hat Modell oder Endpunkt nicht gefunden. Die konfigurierte Modellkennung prüfen.",
            413: "Die Anfrage ist für Mistral zu groß. Abschnittsgröße reduzieren.",
            422: "Mistral akzeptiert die Anfrageparameter nicht. Modell und Reasoning-Konfiguration prüfen.",
            429: "Mistrals Raten- oder Kontingentlimit wurde auch nach Wiederholungen erreicht.",
            504: "Das Gateway des KI-Anbieters hat beim Warten auf die Antwort sein Zeitlimit überschritten (HTTP 504). "
                 "Ein höheres Atlas-Zeitlimit verlängert dieses Anbieter-Limit nicht. Fertige Abschnitte bleiben gespeichert.",
        }.get(status, "Mistral meldet einen Server- oder API-Fehler. Später erneut versuchen.")
    result: dict = {"code": code, "stage": stage, "message": message, "exception_type": type(exc).__name__, "http_status": status if isinstance(status, int) else None}
    if isinstance(exc, ValidationError):
        result["validation_issues"] = validation_issues(exc)
    return result
