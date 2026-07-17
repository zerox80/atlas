# Atlas

Dieses Projekt ist eine KI gestützte Plattform zur Verwaltung und Analyse von Verträgen. Es kombiniert ein modernes Web Interface mit leistungsstarken KI Funktionen zur automatischen Datenextraktion und Dokumenteninteraktion.

## Hauptfunktionen

Das System bietet umfassende Werkzeuge für das Vertragsmanagement:

* Automatisierte Vertragsanalyse: Mithilfe von Mistral Medium 3.5 werden wichtige Daten wie Laufzeiten, Beträge und Kündigungsfristen automatisch aus PDF Dokumenten extrahiert.
* Rechnungsverwaltung: Rechnungen können unabhängig von Verträgen hochgeladen, mit OCR/KI ausgelesen und separat verwaltet werden.
* Interaktiver Chat: Nutzer können spezifische Fragen zu Vertragsinhalten stellen und erhalten präzise Antworten basierend auf dem Dokument.
* Benutzer und Rollenmanagement: Eine integrierte Administration ermöglicht die Steuerung von Zugriffsrechten und Rollen.
* Sicherheit: Das System implementiert eine Zwei Faktor Authentifizierung (TOTP) sowie detaillierte Audit Logs zur Nachverfolgbarkeit aller Aktionen.
* Dashboard: Eine übersichtliche Darstellung bietet schnellen Zugriff auf alle Verträge sowie Filter und Tagging Funktionen.

## Technische Basis

Die Anwendung nutzt eine moderne Architektur:

* Backend: Entwickelt mit FastAPI und SQLModel für hohe Performance und einfache Datenbankinteraktion.
* Frontend: Eine reaktive Weboberfläche für optimale Benutzererfahrung.
* KI Service: Integration der Mistral AI API für fortgeschrittene Sprachverarbeitung.
* Infrastruktur: Containerisierung mittels Docker und Docker Compose für eine schnelle Bereitstellung.

## Installation

### Interaktives Nginx- und HTTPS-Setup

Auf Debian- und Ubuntu-Servern richtet das folgende Skript Docker auf
`127.0.0.1`, den Host-Nginx und optional HTTPS interaktiv ein:

```bash
sudo python3 scripts/setup_nginx_proxy.py
```

Zur Auswahl stehen ein internes LAN-Setup mit lokaler CA und IP-Zertifikat
sowie ein externes Setup mit Certbot/Let's Encrypt oder vorhandenen
Zertifikaten. Im lokalen Modus erkennt das Skript die Server-IP und das dazu
gehörende Netzwerkinterface automatisch, unabhängig davon, ob es beispielsweise
`eth0`, `ens18`, `enp1s0` oder anders heißt. Ist UFW aktiv, wird außerdem die
echte SSH-Client-IP erkannt und für die Nginx-Ports `80`/`443` freigegeben; der
Docker-Port `8080` bleibt ausschließlich an `127.0.0.1` gebunden. Die automatisch
erkannte Quell-IP kann bei der Abfrage durch ein CIDR-Netz ersetzt werden.
Vorhandene `.env`-, Compose- und Nginx-Dateien werden gesichert.

#### Lokale CA per Gruppenrichtlinie verteilen

Beim lokalen HTTPS-Modus müssen die Windows-Clients der von Atlas erzeugten CA
vertrauen. Verteilt wird ausschließlich das öffentliche CA-Zertifikat. Der
private Schlüssel `/etc/nginx/atlas-tls/atlas-local-ca.key` darf niemals den
Server verlassen.

Zunächst wird das PEM-Zertifikat auf dem Atlas-Server in eine für den
Windows-Import geeignete DER-Datei umgewandelt und für den Download lesbar
gemacht:

```bash
sudo openssl x509 \
  -in /etc/nginx/atlas-tls/atlas-local-ca.crt \
  -outform DER \
  -out /tmp/atlas-local-ca.cer
sudo chmod 0644 /tmp/atlas-local-ca.cer
```

Anschließend wird die Datei auf einem Windows-Administrationsrechner mit `scp`
in das aktuelle Verzeichnis kopiert. Benutzername und Server-IP sind bei Bedarf
anzupassen:

```powershell
scp dashboard@192.168.1.128:/tmp/atlas-local-ca.cer .
```

Die Datei liegt danach im aktuellen Verzeichnis. Soll stattdessen `C:\Temp`
verwendet werden, muss der Ordner vor dem Kopieren existieren:

```powershell
mkdir C:\Temp
scp dashboard@192.168.1.128:/tmp/atlas-local-ca.cer C:\Temp\atlas-local-ca.cer
```

Die Verteilung erfolgt anschließend über die Gruppenrichtlinienverwaltung:

1. `gpmc.msc` öffnen und eine neue GPO, beispielsweise `Atlas Local CA Trust`,
   erstellen.
2. Die GPO mit der OU verknüpfen, in der sich die **Computerobjekte** der
   Zielgeräte befinden. Eine Verknüpfung auf Domänenebene gilt entsprechend für
   alle einbezogenen Domänencomputer.
3. Die GPO bearbeiten und zu
   `Computerkonfiguration > Richtlinien > Windows-Einstellungen >`
   `Sicherheitseinstellungen > Richtlinien für öffentliche Schlüssel >`
   `Vertrauenswürdige Stammzertifizierungsstellen` navigieren.
4. Dort `atlas-local-ca.cer` über **Importieren** hinzufügen. Nicht das
   Serverzertifikat `atlas.crt` importieren.
5. Auf einem Client die Richtlinie sofort aktualisieren und danach den Browser
   vollständig neu starten:

   ```powershell
   gpupdate /force
   ```

6. Die Installation auf dem Client kontrollieren:

   ```powershell
   Get-ChildItem Cert:\LocalMachine\Root |
       Where-Object Subject -eq 'CN=Atlas Local CA' |
       Format-List Subject, Thumbprint, NotAfter
   ```

Chrome und Edge verwenden den Windows-Zertifikatsspeicher. Aktuelle
Firefox-Versionen übernehmen durch Windows beziehungsweise GPO installierte
Root-CAs ebenfalls. Die aufgerufene IP muss weiterhin exakt mit der IP im
Atlas-Serverzertifikat übereinstimmen, beispielsweise `https://192.168.1.128`.
Der offizielle Ablauf ist außerdem in der
[Microsoft-Dokumentation zur Zertifikatsverteilung per GPO](https://learn.microsoft.com/en-us/windows-server/identity/ad-fs/deployment/distribute-certificates-to-client-computers-by-using-group-policy)
beschrieben.

Für den Betrieb ist die Konfiguration der Umgebungsvariablen in einer .env Datei erforderlich, insbesondere der MISTRAL_API_KEY.

### Mistral OCR 4

Die KI Analyse nutzt standardmäßig Mistral OCR 4 über das Modell `mistral-ocr-4-0`. Der OCR Aufruf extrahiert Markdown, Tabellen im Markdown Format, strukturierte OCR 4 Blöcke sowie Seiten Konfidenzwerte. Diese Defaults können per `.env` angepasst werden:

```env
MISTRAL_CHAT_MODEL=mistral-medium-3-5
MISTRAL_OCR_MODEL=mistral-ocr-4-0
MISTRAL_OCR_TABLE_FORMAT=markdown
MISTRAL_OCR_INCLUDE_BLOCKS=true
MISTRAL_OCR_CONFIDENCE_GRANULARITY=page
MISTRAL_DOCUMENT_PROCESSING_ENABLED=true
```

Setzen Sie `MISTRAL_DOCUMENT_PROCESSING_ENABLED=false`, um die externe KI Dokumentverarbeitung vollständig zu deaktivieren.

Starten Sie die Anwendung mit folgendem Befehl im Hauptverzeichnis:

docker-compose up -d

Vor dem ersten Start müssen Sie eine `.env` aus `.env.example` erstellen und
mindestens `SECRET_KEY` sowie ein `ADMIN_PASSWORD` mit mindestens 12 Zeichen
setzen. Das initiale Passwort wird nicht erzeugt oder ausgegeben.

Docker veröffentlicht Atlas ausschließlich auf `127.0.0.1:8080`. Für den
Produktivbetrieb konfigurieren Sie einen TLS-Reverse-Proxy davor; eine sichere
Vorlage mit HTTP-zu-HTTPS-Weiterleitung liegt in `nginx-external-sample.conf`.
Für lokale HTTP-Entwicklung müssen `PRODUCTION=false` und
`SECURE_COOKIES=false` bewusst in der lokalen `.env` gesetzt werden.

Nach dem Start ist Atlas über den konfigurierten Nginx Proxy erreichbar. Die Datenbank wird beim ersten Start automatisch initialisiert.
