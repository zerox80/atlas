#!/usr/bin/env python3
"""Interactive host-Nginx setup for Atlas on Debian/Ubuntu."""

from __future__ import annotations

import ipaddress
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SITE = Path("/etc/nginx/sites-available/atlas")
SITE_LINK = Path("/etc/nginx/sites-enabled/atlas")
TLS_DIR = Path("/etc/nginx/atlas-tls")
ACME_ROOT = Path("/var/www/certbot")


def fail(message: str) -> None:
    print(f"\nAbbruch: {message}", file=sys.stderr)
    raise SystemExit(1)


def ask(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default


def choose(label: str, options: dict[str, str], default: str) -> str:
    rendered = "/".join(f"{key}={value}" for key, value in options.items())
    while True:
        value = ask(f"{label} ({rendered})", default).lower()
        if value in options:
            return value
        print(f"Bitte wählen: {', '.join(options)}")


def confirm(label: str, default: bool = False) -> bool:
    hint = "J/n" if default else "j/N"
    value = input(f"{label} [{hint}]: ").strip().lower()
    return default if not value else value in {"j", "ja", "y", "yes"}


def command(args: list[str], cwd: Path | None = None) -> None:
    print(f"\n→ {' '.join(args)}")
    subprocess.run(args, cwd=cwd, check=True)


def command_output(args: list[str]) -> str:
    environment = dict(os.environ)
    environment["LC_ALL"] = "C"
    completed = subprocess.run(
        args,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        env=environment,
    )
    return completed.stdout.strip()


def detected_ssh_client_ip() -> str | None:
    for variable in ("SSH_CONNECTION", "SSH_CLIENT"):
        fields = os.environ.get(variable, "").split()
        if not fields:
            continue
        try:
            return str(ipaddress.ip_address(fields[0].strip("[]")))
        except ValueError:
            pass

    who = command_output(["who", "-m"])
    match = re.search(r"\(([^()]+)\)\s*$", who)
    if match:
        try:
            return str(ipaddress.ip_address(match.group(1).strip("[]")))
        except ValueError:
            pass
    return None


def detected_server_ip() -> str | None:
    fields = os.environ.get("SSH_CONNECTION", "").split()
    if len(fields) >= 3:
        try:
            address = ipaddress.ip_address(fields[2].strip("[]"))
            if address.version == 4 and not address.is_loopback:
                return str(address)
        except ValueError:
            pass

    route = command_output(["ip", "-o", "-4", "route", "get", "1.1.1.1"])
    match = re.search(r"\bsrc\s+(\S+)", route)
    if match:
        try:
            address = ipaddress.ip_address(match.group(1))
            if address.version == 4 and not address.is_loopback:
                return str(address)
        except ValueError:
            pass

    for line in command_output(["ip", "-o", "-4", "addr", "show", "scope", "global"]).splitlines():
        match = re.match(r"^\d+:\s+\S+\s+inet\s+(\S+)", line)
        if not match:
            continue
        try:
            address = ipaddress.ip_interface(match.group(1)).ip
            if not address.is_loopback:
                return str(address)
        except ValueError:
            pass
    return None


def normalized_ufw_source(value: str) -> str:
    value = value.strip()
    if value.lower() in {"any", "alle"}:
        return "any"
    try:
        if "/" in value:
            return str(ipaddress.ip_network(value, strict=False))
        return str(ipaddress.ip_address(value))
    except ValueError:
        fail("Ungültige UFW-Quell-IP bzw. ungültiges CIDR-Netz.")


def interface_for_ip(address: str) -> str | None:
    for line in command_output(["ip", "-o", "-4", "addr", "show"]).splitlines():
        match = re.match(r"^\d+:\s+(\S+)\s+inet\s+(\S+)", line)
        if not match:
            continue
        try:
            interface_address = ipaddress.ip_interface(match.group(2)).ip
        except ValueError:
            continue
        if str(interface_address) == address:
            return match.group(1).split("@", 1)[0]
    return None


def ufw_state() -> str:
    if shutil.which("ufw") is None:
        return "nicht installiert"
    status = command_output(["ufw", "status"])
    if re.search(r"^Status:\s+active\b", status, flags=re.MULTILINE):
        return "aktiv"
    return "inaktiv"


def allow_ufw_ports(ports: tuple[int, ...], source: str, interface: str | None) -> None:
    for public_port in ports:
        args = ["ufw", "allow", "in"]
        if interface is not None:
            args.extend(["on", interface])
        args.extend([
            "proto", "tcp", "from", source, "to", "any", "port", str(public_port),
            "comment", "Atlas Nginx",
        ])
        command(args)


def backup(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = path.with_name(f"{path.name}.backup-{stamp}")
    if path.is_symlink():
        target.symlink_to(os.readlink(path))
    else:
        shutil.copy2(path, target)
    print(f"Sicherung: {target}")


def write(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.chmod(mode)
    temporary.replace(path)


def update_env(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(values)
    result: list[str] = []
    for line in lines:
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", line)
        if match and match.group(1) in remaining:
            key = match.group(1)
            result.append(f"{key}={remaining.pop(key)}")
        else:
            result.append(line)
    if remaining:
        result.extend(["", "# Managed by setup_nginx_proxy.py"])
        result.extend(f"{key}={value}" for key, value in remaining.items())
    write(path, "\n".join(result) + "\n", 0o600)


def set_loopback_mapping(path: Path, port: int) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    frontend = next((i for i, line in enumerate(lines) if line.rstrip() == "  frontend:"), None)
    if frontend is None:
        fail("Service 'frontend' fehlt in docker-compose.yml.")
    end = next(
        (i for i in range(frontend + 1, len(lines)) if re.match(r"^  \w[\w-]*:\s*$", lines[i])),
        len(lines),
    )
    ports = next(
        (i for i in range(frontend + 1, end) if lines[i].rstrip() == "    ports:"),
        None,
    )
    if ports is None:
        fail("ports-Block des Frontends fehlt.")
    mapping = next(
        (i for i in range(ports + 1, end) if re.match(r"^\s{6}-\s+", lines[i])),
        None,
    )
    if mapping is None:
        fail("Frontend-Port-Mapping fehlt.")
    lines[mapping] = f'      - "127.0.0.1:{port}:80"'
    write(path, "\n".join(lines) + "\n")


def proxy_block(port: int, scheme: str) -> str:
    return f"""    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        # Public trust boundary: never append a client-controlled forwarding chain.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto {scheme};
        proxy_buffering off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }}"""


def http_site(host: str, port: int, acme: bool = False) -> str:
    challenge = (
        f"\n    location /.well-known/acme-challenge/ {{\n        root {ACME_ROOT};\n    }}\n"
        if acme
        else ""
    )
    return f"""server {{
    listen 80;
    server_name {host};
    client_max_body_size 11M;
{challenge}
{proxy_block(port, '$scheme')}
}}
"""


def https_site(host: str, port: int, cert: Path, key: Path) -> str:
    return f"""server {{
    listen 80;
    server_name {host};
    location /.well-known/acme-challenge/ {{ root {ACME_ROOT}; }}
    location / {{ return 301 https://$host$request_uri; }}
}}

server {{
    listen 443 ssl;
    server_name {host};
    ssl_certificate {cert};
    ssl_certificate_key {key};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:AtlasTLS:10m;
    ssl_session_tickets off;
    client_max_body_size 11M;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

{proxy_block(port, 'https')}
}}
"""


def enable_site() -> None:
    SITE_LINK.parent.mkdir(parents=True, exist_ok=True)
    if SITE_LINK.is_symlink() and SITE_LINK.resolve() == SITE:
        return
    if SITE_LINK.exists() or SITE_LINK.is_symlink():
        backup(SITE_LINK)
        SITE_LINK.unlink()
    SITE_LINK.symlink_to(SITE)


def local_certificate(ip: str) -> tuple[Path, Path, Path]:
    TLS_DIR.mkdir(parents=True, exist_ok=True)
    TLS_DIR.chmod(0o700)
    ca_key, ca_cert = TLS_DIR / "atlas-local-ca.key", TLS_DIR / "atlas-local-ca.crt"
    key, csr, cert = TLS_DIR / "atlas.key", TLS_DIR / "atlas.csr", TLS_DIR / "atlas.crt"
    if not ca_key.exists() or not ca_cert.exists():
        command([
            "openssl", "req", "-x509", "-newkey", "rsa:4096", "-nodes", "-sha256",
            "-days", "3650", "-keyout", str(ca_key), "-out", str(ca_cert),
            "-subj", "/CN=Atlas Local CA", "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign",
        ])
    for path in (key, csr, cert):
        backup(path)
    command([
        "openssl", "req", "-newkey", "rsa:3072", "-nodes", "-sha256",
        "-keyout", str(key), "-out", str(csr), "-subj", f"/CN={ip}",
    ])
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as extensions:
        extensions.write(
            "basicConstraints=critical,CA:FALSE\n"
            "keyUsage=critical,digitalSignature,keyEncipherment\n"
            "extendedKeyUsage=serverAuth\n"
            f"subjectAltName=IP:{ip}\n"
        )
        ext_path = Path(extensions.name)
    try:
        command([
            "openssl", "x509", "-req", "-in", str(csr), "-CA", str(ca_cert),
            "-CAkey", str(ca_key), "-CAcreateserial", "-out", str(cert),
            "-days", "825", "-sha256", "-extfile", str(ext_path),
        ])
    finally:
        ext_path.unlink(missing_ok=True)
        csr.unlink(missing_ok=True)
    ca_key.chmod(0o600)
    key.chmod(0o600)
    return cert, key, ca_cert


def main() -> None:
    print("Atlas – interaktives Nginx-Reverse-Proxy-Setup")
    print("================================================")
    if not sys.platform.startswith("linux") or os.geteuid() != 0:
        fail("Bitte auf dem Linux-Server als root oder mit sudo ausführen.")
    if shutil.which("apt-get") is None:
        fail("Automatische Installation unterstützt Debian/Ubuntu mit apt-get.")

    default_project = Path(__file__).resolve().parents[1]
    project = Path(ask("Atlas-Projektverzeichnis", str(default_project))).expanduser().resolve()
    compose = project / "docker-compose.yml"
    env_file = project / ".env"
    if not compose.is_file():
        fail(f"Keine docker-compose.yml in {project} gefunden.")

    mode = choose("Betriebsart", {"lokal": "LAN/IP", "extern": "Domain"}, "lokal")
    port = int(ask("Atlas-Port auf 127.0.0.1", "8080"))
    if not 1 <= port <= 65535:
        fail("Ungültiger Port.")

    email: str | None = None
    cert: Path | None = None
    key: Path | None = None
    if mode == "lokal":
        detected_host = detected_server_ip()
        if detected_host is None:
            print("\nDie interne Server-IP konnte nicht automatisch erkannt werden.")
            host = ask("Interne Server-IP")
        else:
            print(f"\nInterne Server-IP automatisch erkannt: {detected_host}")
            host = ask("Interne Server-IP", detected_host)
        try:
            if ipaddress.ip_address(host).version != 4:
                fail("Bitte eine IPv4-Adresse verwenden.")
        except ValueError:
            fail("Ungültige IPv4-Adresse.")
        tls = choose("Verschlüsselung", {"local": "lokale CA", "none": "HTTP"}, "local")
    else:
        host = ask("Öffentliche Domain").lower().rstrip(".")
        if not re.fullmatch(r"(?=.{1,253}$)(?:[\w](?:[\w-]{0,61}[\w])?\.)+[A-Za-z]{2,63}", host):
            fail("Ungültiger Domainname.")
        tls = choose(
            "Verschlüsselung",
            {"certbot": "Let's Encrypt", "existing": "vorhandenes Zertifikat", "none": "HTTP"},
            "certbot",
        )
        if tls == "certbot":
            email = ask("E-Mail für Let's Encrypt")
            print(f"\n{host} muss auf diesen Server zeigen; Port 80 muss öffentlich erreichbar sein.")
            if not confirm("DNS und Port 80 sind vorbereitet?"):
                fail("Certbot nicht gestartet.")
        elif tls == "existing":
            cert = Path(ask("Pfad zu fullchain.pem")).expanduser().resolve()
            key = Path(ask("Pfad zu privkey.pem")).expanduser().resolve()
            if not cert.is_file() or not key.is_file():
                fail("Zertifikat oder Schlüssel nicht gefunden.")

    origin = f"{'https' if tls != 'none' else 'http'}://{host}"
    public_ports = (80,) if tls == "none" else (80, 443)
    firewall_state = ufw_state()
    firewall_source = "any"
    firewall_interface: str | None = None
    if firewall_state == "aktiv" and mode == "lokal":
        detected_source = detected_ssh_client_ip()
        if detected_source is None:
            print("\nUFW: Die SSH-Client-IP konnte nicht automatisch erkannt werden.")
            firewall_source = normalized_ufw_source(
                ask("Client-IP oder Clientnetz für Atlas (z. B. 10.212.134.200 oder 10.212.134.0/24)")
            )
        else:
            print(f"\nUFW: SSH-Client automatisch erkannt: {detected_source}")
            firewall_source = normalized_ufw_source(
                ask("Erlaubte Client-IP bzw. erlaubtes CIDR-Netz", detected_source)
            )
        firewall_interface = interface_for_ip(host)

    print(f"\nAdresse:         {origin}")
    print(f"Docker:          127.0.0.1:{port}")
    print(f"TLS-Modus:       {tls}")
    print(f"Nginx-Site:      {SITE}")
    if firewall_state == "aktiv":
        interface_text = firewall_interface or "alle passenden Interfaces"
        ports_text = ", ".join(f"TCP/{value}" for value in public_ports)
        print(f"UFW:             aktiv; {firewall_source} → {ports_text} auf {interface_text}")
        print(f"                  TCP/{port} bleibt ausschließlich auf 127.0.0.1")
    else:
        print(f"UFW:             {firewall_state}; keine Firewall-Regeln werden geändert")
    print("Vorhandene Projekt- und Nginx-Dateien werden vorher gesichert.")
    if not confirm("Jetzt anwenden?"):
        fail("Keine Änderungen vorgenommen.")

    try:
        backup(compose)
        backup(env_file)
        backup(SITE)
        set_loopback_mapping(compose, port)
        update_env(env_file, {
            "FRONTEND_PORT": str(port),
            "PRODUCTION": "true" if tls != "none" else "false",
            "SECURE_COOKIES": "true" if tls != "none" else "false",
            "CORS_ALLOWED_ORIGINS": origin,
        })

        packages = ["nginx"]
        if tls == "local":
            packages.append("openssl")
        elif tls == "certbot":
            packages.extend(["certbot", "python3-certbot-nginx"])
        command(["apt-get", "update"])
        command(["apt-get", "install", "-y", *packages])

        if firewall_state == "aktiv":
            allow_ufw_ports(public_ports, firewall_source, firewall_interface)

        ca_cert: Path | None = None
        if tls == "local":
            cert, key, ca_cert = local_certificate(host)
        elif tls == "certbot":
            assert email is not None
            ACME_ROOT.mkdir(parents=True, exist_ok=True)
            write(SITE, http_site(host, port, acme=True))
            enable_site()
            command(["systemctl", "enable", "--now", "nginx"])
            command(["systemctl", "reload", "nginx"])
            command([
                "certbot", "certonly", "--webroot", "--webroot-path", str(ACME_ROOT),
                "--domain", host, "--email", email, "--agree-tos", "--no-eff-email",
                "--non-interactive",
            ])
            live = Path("/etc/letsencrypt/live") / host
            cert, key = live / "fullchain.pem", live / "privkey.pem"
            write(
                Path("/etc/letsencrypt/renewal-hooks/deploy/reload-nginx"),
                "#!/bin/sh\nsystemctl reload nginx\n",
                0o755,
            )

        if tls == "none":
            write(SITE, http_site(host, port))
        else:
            assert cert is not None and key is not None
            write(SITE, https_site(host, port, cert, key))
        enable_site()
        command(["systemctl", "enable", "--now", "nginx"])
        command(["systemctl", "reload", "nginx"])
        command(
            ["docker", "compose", "up", "-d", "--force-recreate", "backend", "frontend"],
            cwd=project,
        )
    except subprocess.CalledProcessError as error:
        fail(f"Befehl fehlgeschlagen (Exit-Code {error.returncode}); Sicherungen bleiben erhalten.")

    print(f"\nFertig: {origin}")
    print(f"Atlas-Docker-Port bleibt intern: 127.0.0.1:{port}")
    if firewall_state == "aktiv":
        print(f"UFW wurde für {firewall_source} auf den Nginx-Ports angepasst.")
    if ca_cert is not None:
        print(f"Lokale CA für die Client-Vertrauensstellung: {ca_cert}")
        print("Den privaten CA-Schlüssel niemals vom Server kopieren.")

if __name__ == "__main__":
    main()
