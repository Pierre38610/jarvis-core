"""Gestion de l'authentification et des appareils autorisés pour J.A.R.V.I.S."""

import os
import json
import secrets
import datetime
from config import AUTH_FILE, ACCESS_PASSWORD

def load_authorized_devices() -> dict:
    if os.path.exists(AUTH_FILE):
        try:
            with open(AUTH_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("tokens", {})
        except Exception as e:
            print(f"[Auth] Erreur lecture authorized_devices.json: {e}")
            return {}
    return {}

def save_authorized_device(token: str, info: dict):
    tokens = load_authorized_devices()
    tokens[token] = info
    try:
        with open(AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump({"tokens": tokens}, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Auth] Erreur écriture authorized_devices.json: {e}")

def is_device_authorized(token: str | None) -> bool:
    if not token:
        return False
    tokens = load_authorized_devices()
    return token in tokens

QR_TICKETS_FILE = os.path.join(os.path.dirname(AUTH_FILE), "qr_tickets.json")

def load_qr_tickets() -> dict:
    if os.path.exists(QR_TICKETS_FILE):
        try:
            with open(QR_TICKETS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_qr_tickets(tickets: dict):
    try:
        with open(QR_TICKETS_FILE, "w", encoding="utf-8") as f:
            json.dump(tickets, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Auth] Erreur écriture qr_tickets.json: {e}")

def create_qr_ticket() -> str:
    """Génère un ticket unique pour enregistrer l'appareil ayant scanné le QR Code."""
    ticket = secrets.token_urlsafe(32)
    tickets = load_qr_tickets()
    # Nettoyage tickets expirés (> 24h)
    now = datetime.datetime.now()
    valid_tickets = {}
    for k, v in tickets.items():
        try:
            created = datetime.datetime.fromisoformat(v.get("created_at", ""))
            if (now - created).total_seconds() < 86400:
                valid_tickets[k] = v
        except Exception:
            pass
    valid_tickets[ticket] = {
        "created_at": now.isoformat(),
        "used": False
    }
    save_qr_tickets(valid_tickets)
    return ticket

def register_device_via_qr(ticket: str, client_ip: str = "unknown", user_agent: str = "unknown") -> str | None:
    """Enregistre l'appareil sans mot de passe si le ticket QR est valide."""
    if not ticket:
        return None
    tickets = load_qr_tickets()
    if ticket in tickets:
        t_data = tickets[ticket]
        # Optionnel: on peut autoriser plusieurs reconnexions ou usage unique
        # Ici on valide le ticket pour autoriser l'appareil définitivement
        token = secrets.token_hex(32)
        save_authorized_device(token, {
            "created_at": datetime.datetime.now().isoformat(),
            "client_ip": client_ip,
            "user_agent": user_agent,
            "registered_via": "qr_code"
        })
        return token
    return None

def verify_and_generate_token(password: str, client_ip: str = "unknown", user_agent: str = "unknown") -> str | None:
    if password == ACCESS_PASSWORD:
        token = secrets.token_hex(32)
        save_authorized_device(token, {
            "created_at": datetime.datetime.now().isoformat(),
            "client_ip": client_ip,
            "user_agent": user_agent,
            "registered_via": "password"
        })
        return token
    return None

