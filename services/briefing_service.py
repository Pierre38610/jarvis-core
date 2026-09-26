"""services/briefing_service.py
Service Morning Briefing pour J.A.R.V.I.S. - Stark Industries
Compile chaque matin (à 7h00 via cron n8n ou sur demande) :
- La météo locale
- Les rendez-vous du jour (Agenda Samsung / Google Calendar)
- Les e-mails urgents non lus (IMAP Gmail)
- L'état des systèmes et des tâches
Stocke le résultat dans Redis sous la clé 'jarvis:briefing:today' (TTL 16 heures)
pour une restitution vocale instantanée au premier "Bonjour" de la journée.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any, Dict, List, Optional

import httpx

from services.cache import cache_service
from services.email_service import read_received_emails_async
from services.system_service import get_system_status
from services.memory_service import memory_service

logger = logging.getLogger(__name__)

# Code météo WMO standard
WMO_WEATHER_CODES: Dict[int, str] = {
    0: "Ciel dégagé",
    1: "Ensoleillé et principalement dégagé",
    2: "Partiellement voilé",
    3: "Ciel couvert",
    45: "Brouillard",
    48: "Brouillard givrant",
    51: "Bruine légère",
    53: "Bruine modérée",
    55: "Bruine soutenue",
    61: "Pluie légère",
    63: "Pluie modérée",
    65: "Pluie soutenue",
    71: "Chutes de neige légères",
    73: "Neige modérée",
    75: "Fortes chutes de neige",
    80: "Averses éparses",
    81: "Averses modérées",
    82: "Fortes averses orageuses",
    95: "Conditions orageuses",
    96: "Orage avec grêle modérée",
    99: "Orage violent avec grêle",
}


async def get_local_weather(city: Optional[str] = None) -> Dict[str, Any]:
    """Récupère les prévisions météo locales avec dégradation gracieuse et mise en cache."""
    cache_key = "jarvis:weather:current"
    cached = await cache_service.get(cache_key)
    if cached and isinstance(cached, dict):
        return cached

    target_city = (city or "Grenoble").strip()
    # Coordonnées par défaut : Grenoble / Isère (Pierre38610)
    lat, lon = 45.1885, 5.7245

    # Si Paris
    if "paris" in target_city.lower():
        lat, lon = 48.8566, 2.3522

    weather_data = {
        "city": target_city,
        "temperature": "18°C",
        "condition": "Ciel dégagé",
        "description": "Conditions calmes et température clémente",
        "humidity": "55%",
        "wind_speed": "12 km/h",
    }

    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
        async with httpx.AsyncClient(timeout=2.5) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                current = data.get("current", {})
                temp = current.get("temperature_2m")
                code = current.get("weather_code", 0)
                humidity = current.get("relative_humidity_2m")
                wind = current.get("wind_speed_10m")

                weather_data = {
                    "city": target_city,
                    "temperature": f"{round(temp)}°C" if temp is not None else "18°C",
                    "condition": WMO_WEATHER_CODES.get(code, "Ciel calme"),
                    "description": f"{WMO_WEATHER_CODES.get(code, 'Ciel dégagé')} avec vent à {round(wind)} km/h" if wind else "Conditions optimales",
                    "humidity": f"{humidity}%" if humidity is not None else "50%",
                    "wind_speed": f"{round(wind)} km/h" if wind is not None else "10 km/h",
                }
    except Exception as exc:
        logger.debug("[BriefingService] Erreur météo extérieure (mode local actif) : %s", exc)

    # Cache météo pour 1 heure (3600 secondes)
    try:
        await cache_service.set(cache_key, weather_data, ttl=3600)
    except Exception:
        pass

    return weather_data


class BriefingService:
    """Service central de génération et restitution du Morning Briefing."""

    CACHE_KEY = "jarvis:briefing:today"
    CACHE_TTL = 16 * 3600  # 16 heures de validité

    async def compiler_morning_briefing(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Compile l'ensemble des données du jour pour constituer le Morning Briefing.

        Étapes :
        1. Vérifie si le briefing est déjà présent en cache Redis (sauf si force_refresh=True).
        2. Interroge CacheService pour l'état système et les rendez-vous mis en cache.
        3. Récupère la météo locale et les non-lus IMAP via EmailService.
        4. Formate un résumé concis au ton Stark Industries (3-4 phrases d'impact).
        5. Stocke le résultat dans Redis sous `jarvis:briefing:today` (TTL 16 heures).
        """
        # 1. Vérification du cache Redis
        if not force_refresh:
            cached_briefing = await cache_service.get(self.CACHE_KEY)
            if cached_briefing and isinstance(cached_briefing, dict) and cached_briefing.get("texte_oral"):
                logger.info("[BriefingService] Briefing récupéré directement depuis le cache Redis.")
                return cached_briefing

        logger.info("[BriefingService] Compilation d'un nouveau Morning Briefing...")

        # Profil utilisateur pour la ville de résidence
        autofill = memory_service.get_user_autofill_profile()
        city = autofill.get("city") or "Grenoble"

        # 2. Collecte concurrente et asynchrone des métriques
        system_task = asyncio.to_thread(get_system_status)
        pc_status_task = cache_service.get_device_presence("pc_status")
        weather_task = get_local_weather(city)
        emails_task = read_received_emails_async(max_count=5, unread_only=True)
        cached_agenda_task = cache_service.get("jarvis:agenda:today")

        sys_info, pc_status, weather, email_res, cached_agenda = await asyncio.gather(
            system_task,
            pc_status_task,
            weather_task,
            emails_task,
            cached_agenda_task,
            return_exceptions=True
        )

        # Normalisation de l'état système
        pc_online = False
        if not isinstance(pc_status, Exception) and pc_status:
            pc_online = pc_status.get("online", False)
        elif not isinstance(sys_info, Exception) and isinstance(sys_info, dict):
            pc_online = sys_info.get("pc_online", False)

        # Normalisation de la météo
        if isinstance(weather, Exception) or not isinstance(weather, dict):
            weather = {
                "city": city,
                "temperature": "18°C",
                "condition": "Ciel dégagé",
                "description": "Conditions idéales"
            }

        # Normalisation des e-mails
        unread_count = 0
        urgent_count = 0
        email_items = []
        if not isinstance(email_res, Exception) and isinstance(email_res, dict):
            unread_count = email_res.get("count", 0)
            email_items = email_res.get("emails", [])
            for em in email_items:
                subj = (em.get("subject") or "").lower()
                if any(w in subj for w in ["urgent", "important", "alerte", "rappel", "sécurité", "action requise"]):
                    urgent_count += 1

        # Normalisation des rendez-vous d'agenda
        agenda_events: List[Dict[str, Any]] = []
        if not isinstance(cached_agenda, Exception) and isinstance(cached_agenda, list):
            agenda_events = cached_agenda
        elif not isinstance(cached_agenda, Exception) and isinstance(cached_agenda, dict) and "events" in cached_agenda:
            agenda_events = cached_agenda["events"]
        else:
            # Tentative rapide via le webhook n8n agenda si disponible
            try:
                from services.automation import trigger_webhook
                agenda_fetch = await asyncio.wait_for(
                    trigger_webhook("agenda-event", {"action": "consulter", "filtre": "aujourdhui"}),
                    timeout=2.0
                )
                if isinstance(agenda_fetch, dict) and "events" in agenda_fetch:
                    agenda_events = agenda_fetch["events"]
                    await cache_service.set("jarvis:agenda:today", agenda_events, ttl=7200)
            except Exception:
                pass

        # 3. Synthèse au ton Stark Industries (3-4 phrases percutantes, digne de Tony Stark & Aoede)
        # Phrase 1 : Salutation & Statut système
        phrase_sys = (
            f"Bonjour Pierre. Tous les systèmes sont opérationnels, PC de commandement connecté et synchronisé."
            if pc_online else
            f"Bonjour Pierre. Systèmes centraux opérationnels, liaison cloud active."
        )

        # Phrase 2 : Météo locale
        ville_label = weather.get("city", "votre secteur")
        condition_label = weather.get("condition", "dégagé").lower()
        temp_label = weather.get("temperature", "tempérée")
        phrase_meteo = f"Côté météo à {ville_label}, prévoyez un {condition_label} avec {temp_label}."

        # Phrase 3 : Agenda & Rendez-vous
        if agenda_events:
            first_event = agenda_events[0]
            first_title = first_event.get("titre") or first_event.get("summary") or "votre premier point"
            first_time = first_event.get("heure") or first_event.get("start") or "la matinée"
            phrase_agenda = f"Vous avez {len(agenda_events)} rendez-vous à l'agenda, à commencer par '{first_title}' à {first_time}."
        else:
            phrase_agenda = "Votre agenda est entièrement dégagé pour aujourd'hui."

        # Phrase 4 : Courriels & Tâches
        if urgent_count > 0:
            phrase_emails = f"À noter : {unread_count} courriel(s) non lu(s), dont {urgent_count} classé(s) urgent(s). Tous les voyants sont au vert, prêt pour vos directives."
        elif unread_count > 0:
            first_sender = email_items[0].get("from", "un contact") if email_items else ""
            sender_clean = first_sender.split("<")[0].strip() if first_sender else "votre boîte"
            phrase_emails = f"Vous avez {unread_count} message(s) non lu(s), notamment de {sender_clean}. Tous les voyants sont au vert, prêt pour vos directives."
        else:
            phrase_emails = "Messagerie à jour, aucun message urgent. Tous les voyants sont au vert, prêt pour vos directives."

        # Assemblage final du discours d'impact
        discours_oral = f"{phrase_sys} {phrase_meteo} {phrase_agenda} {phrase_emails}"

        briefing_payload = {
            "status": "success",
            "date": datetime.date.today().isoformat(),
            "compiled_at": datetime.datetime.now().isoformat(),
            "texte_oral": discours_oral,
            "meteo": weather,
            "agenda": {
                "count": len(agenda_events),
                "events": agenda_events,
            },
            "emails": {
                "unread_count": unread_count,
                "urgent_count": urgent_count,
                "items": email_items[:3],
            },
            "systeme": {
                "pc_online": pc_online,
                "cpu_percent": sys_info.get("cpu_percent", 0) if isinstance(sys_info, dict) else 0,
            }
        }

        # 4. Stockage dans Redis avec TTL 16 heures
        try:
            await cache_service.set(self.CACHE_KEY, briefing_payload, ttl=self.CACHE_TTL)
            logger.info("[BriefingService] Morning Briefing mis en cache sous '%s' (TTL 16h).", self.CACHE_KEY)
        except Exception as e:
            logger.warning("[BriefingService] Erreur mise en cache Redis : %s", e)

        return briefing_payload

    async def get_today_briefing(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Retourne le briefing du jour depuis le cache ou le génère immédiatement."""
        return await self.compiler_morning_briefing(force_refresh=force_refresh)

    async def send_telegram_alert(
        self,
        message: str,
        chat_id: str = "6849746502",
        echeance: str = "maintenant",
        priorite: str = "haute"
    ) -> Dict[str, Any]:
        """Envoie une notification push / message sur le Stark Bot Telegram de Pierre (chatId: 6849746502)."""
        logger.info(f"[BriefingService] Envoi push Telegram (chatId: {chat_id}) : {message[:80]}...")
        try:
            from services.automation import trigger_webhook
            payload = {
                "message": message,
                "text": message,
                "chatId": chat_id,
                "chat_id": chat_id,
                "echeance": echeance,
                "priorite": priorite,
                "source": "jarvis-deep-research",
                "device": "smartphone"
            }
            res = await trigger_webhook("schedule-push-reminder", payload)
            logger.info(f"[BriefingService] Push Telegram transmis avec succès : {res}")
            return {"status": "success", "result": res}
        except Exception as e:
            logger.error(f"[BriefingService] Erreur lors de l'envoi de l'alerte Telegram: {e}")
            return {"status": "error", "error": str(e)}

    async def send_telegram_notification(self, message: str, chat_id: str = "6849746502") -> Dict[str, Any]:
        """Alias pratique pour send_telegram_alert."""
        return await self.send_telegram_alert(message, chat_id=chat_id)


# Singleton
briefing_service = BriefingService()

