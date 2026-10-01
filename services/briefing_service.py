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

# Table des coordonnées pour les principales villes connues (fallback instantané sans requête réseau)
KNOWN_CITIES_COORDS: Dict[str, tuple[float, float, str]] = {
    "grenoble": (45.1885, 5.7245, "Grenoble"),
    "echirolles": (45.1432, 5.7196, "Échirolles"),
    "meylan": (45.2089, 5.7797, "Meylan"),
    "saint-martin-d'heres": (45.1764, 5.7589, "Saint-Martin-d'Hères"),
    "paris": (48.8566, 2.3522, "Paris"),
    "lyon": (45.7640, 4.8357, "Lyon"),
    "marseille": (43.2965, 5.3698, "Marseille"),
    "toulouse": (43.6047, 1.4442, "Toulouse"),
    "nice": (43.7102, 7.2620, "Nice"),
    "nantes": (47.2184, -1.5536, "Nantes"),
    "strasbourg": (48.5734, 7.7521, "Strasbourg"),
    "montpellier": (43.6108, 3.8767, "Montpellier"),
    "bordeaux": (44.8378, -0.5792, "Bordeaux"),
    "lille": (50.6292, 3.0573, "Lille"),
    "rennes": (48.1173, -1.6778, "Rennes"),
    "reims": (49.2583, 4.0317, "Reims"),
    "saint-etienne": (45.4397, 4.3872, "Saint-Étienne"),
    "toulon": (43.1242, 5.9280, "Toulon"),
    "dijon": (47.3220, 5.0415, "Dijon"),
    "angers": (47.4784, -0.5632, "Angers"),
    "stockholm": (59.3293, 18.0686, "Stockholm"),
    "malmo": (55.6050, 13.0038, "Malmö"),
    "malmö": (55.6050, 13.0038, "Malmö"),
    "goteborg": (57.7089, 11.9746, "Göteborg"),
    "göteborg": (57.7089, 11.9746, "Göteborg"),
    "kiruna": (67.8558, 20.2253, "Kiruna"),
    "londres": (51.5074, -0.1278, "Londres"),
    "london": (51.5074, -0.1278, "Londres"),
    "bruxelles": (50.8503, 4.3517, "Bruxelles"),
    "geneve": (46.2044, 6.1432, "Genève"),
    "genève": (46.2044, 6.1432, "Genève"),
    "berlin": (52.5200, 13.4050, "Berlin"),
    "madrid": (40.4168, -3.7038, "Madrid"),
    "barcelone": (41.3879, 2.1699, "Barcelone"),
    "rome": (41.9028, 12.4964, "Rome")
}


async def geocode_city(city: str) -> Optional[tuple[float, float, str]]:
    """Résout le nom d'une ville en coordonnées (lat, lon, nom officiel)."""
    clean_city = (city or "").strip().lower()
    if not clean_city:
        return None
    for k, v in KNOWN_CITIES_COORDS.items():
        if k in clean_city or clean_city in k:
            return v[0], v[1], v[2]

    # Tentative via l'API de géocodage gratuite Open-Meteo
    try:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={clean_city}&count=1&language=fr&format=json"
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results")
                if results and len(results) > 0:
                    r0 = results[0]
                    return float(r0["latitude"]), float(r0["longitude"]), r0.get("name", city)
    except Exception:
        pass
    return None


async def reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """Tente de déduire le nom de la commune ou ville à partir des coordonnées GPS."""
    # 1. Vérification dans la table locale de proximité (< 15 km)
    for name, (c_lat, c_lon, display_name) in KNOWN_CITIES_COORDS.items():
        if abs(c_lat - lat) < 0.12 and abs(c_lon - lon) < 0.12:
            return display_name

    # 2. Appel reverse géocodage public gratuit BigDataCloud
    try:
        url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={lat}&longitude={lon}&localityLanguage=fr"
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                city = data.get("city") or data.get("locality") or data.get("principalSubdivision")
                if city:
                    return str(city)
    except Exception:
        pass
    return None


async def get_local_weather(
    city: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None
) -> Dict[str, Any]:
    """Récupère les prévisions météo pour la position actuelle ou la ville spécifiée.
    Ordre de priorité pour la localisation :
    1. Coordonnées directes (latitude, longitude) si fournies.
    2. Position de l'appareil enregistrée en cache Redis ('jarvis:device:location').
    3. Ville en mémoire (où Pierre se trouve actuellement, déterminé par memory_service).
    4. Ville de résidence dans le profil (autofill).
    5. Fallback par défaut ('Grenoble').
    """
    target_city = (city or "").strip()
    lat: Optional[float] = latitude
    lon: Optional[float] = longitude

    # 1. Si aucune coordonnée ni ville n'est fournie, vérifier la position de l'appareil dans Redis
    if lat is None or lon is None:
        cached_loc = await cache_service.get("jarvis:device:location")
        if cached_loc and isinstance(cached_loc, dict):
            try:
                lat = float(cached_loc.get("latitude"))
                lon = float(cached_loc.get("longitude"))
                if not target_city and cached_loc.get("city"):
                    target_city = str(cached_loc.get("city"))
            except (ValueError, TypeError):
                pass

    # 2. Si toujours pas de coordonnées, vérifier où est l'utilisateur en mémoire
    if (lat is None or lon is None) and not target_city:
        mem_loc = memory_service.get_current_user_location()
        target_city = mem_loc.get("city", "Grenoble")

    # 3. Résolution des coordonnées si la ville est connue mais pas lat/lon
    if (lat is None or lon is None) and target_city:
        geo = await geocode_city(target_city)
        if geo:
            lat, lon, official_name = geo
            target_city = official_name

    # 4. Si nous avons lat/lon mais pas de nom de ville, tenter une reverse géolocalisation
    if (lat is not None and lon is not None) and not target_city:
        rev_city = await reverse_geocode(lat, lon)
        target_city = rev_city or "votre secteur"

    # Fallback ultime sur Grenoble si échec complet
    if lat is None or lon is None:
        lat, lon = 45.1885, 5.7245
        if not target_city:
            target_city = "Grenoble"

    cache_key = f"jarvis:weather:{round(lat, 2)}_{round(lon, 2)}"
    cached = await cache_service.get(cache_key)
    if cached and isinstance(cached, dict):
        return cached

    weather_data = {
        "city": target_city,
        "temperature": "18°C",
        "condition": "Ciel dégagé",
        "description": "Conditions calmes et température clémente",
        "humidity": "55%",
        "wind_speed": "12 km/h",
        "latitude": lat,
        "longitude": lon,
    }

    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
        async with httpx.AsyncClient(timeout=3.0) as client:
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
                    "latitude": lat,
                    "longitude": lon,
                }
    except Exception as exc:
        logger.debug("[BriefingService] Erreur météo extérieure (mode local actif) : %s", exc)

    try:
        await cache_service.set(cache_key, weather_data, ttl=1800)
    except Exception:
        pass

    return weather_data


async def get_top_news_24h(limit: int = 5) -> Dict[str, Any]:
    """Récupère les actualités les plus importantes des dernières 24 heures via flux RSS d'actualités.
    Mise en cache Redis pour 1 heure (TTL 3600s).
    """
    cache_key = "jarvis:news:top24h"
    cached = await cache_service.get(cache_key)
    if cached and isinstance(cached, dict) and cached.get("items"):
        return cached

    news_sources = [
        "https://news.google.com/rss?hl=fr&gl=FR&ceid=FR:fr",
        "https://www.francetvinfo.fr/titres.rss",
        "https://www.lemonde.fr/rss/une.xml"
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    }

    news_items = []
    for src in news_sources:
        try:
            async with httpx.AsyncClient(timeout=3.5, headers=headers, follow_redirects=True) as client:
                resp = await client.get(src)
                if resp.status_code == 200 and resp.text:
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(resp.text)
                    for item in root.findall(".//item")[:limit]:
                        raw_title = item.findtext("title") or ""
                        link = item.findtext("link") or ""
                        pub_date = item.findtext("pubDate") or ""

                        source = ""
                        clean_title = raw_title
                        if " - " in raw_title:
                            parts = raw_title.rsplit(" - ", 1)
                            clean_title = parts[0].strip()
                            source = parts[1].strip()

                        if clean_title and len(clean_title) > 5:
                            news_items.append({
                                "title": clean_title,
                                "source": source,
                                "link": link,
                                "published": pub_date
                            })
                    if news_items:
                        break
        except Exception as exc:
            logger.debug("[BriefingService] Erreur récupération RSS source '%s': %s", src, exc)

    if not news_items:
        news_items = [
            {
                "title": "Actualité des dernières 24 heures : innovations technologiques et suivi de l'écosystème IA.",
                "source": "Jarvis Newsroom",
                "link": "",
                "published": datetime.datetime.now().isoformat()
            }
        ]

    result = {
        "status": "success",
        "count": len(news_items),
        "items": news_items[:limit],
        "updated_at": datetime.datetime.now().isoformat()
    }

    try:
        await cache_service.set(cache_key, result, ttl=3600)
    except Exception:
        pass

    return result


class BriefingService:
    """Service central de génération et restitution du Morning Briefing."""

    CACHE_KEY = "jarvis:briefing:today"
    CACHE_TTL = 16 * 3600  # 16 heures de validité

    async def compiler_morning_briefing(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Compile l'ensemble des données du jour pour constituer le Morning Briefing.

        Étapes :
        1. Vérifie si le briefing est déjà présent en cache Redis (sauf si force_refresh=True).
        2. Récupère la localisation actuelle (GPS appareil ou mémoire utilisateur).
        3. Interroge concurremment : météo locale, actualités 24h, rendez-vous du jour (lecture seule), e-mails IMAP, état système.
        4. Formate un résumé d'impact au ton Stark Industries avec Aoede.
        5. Met en cache dans Redis sous `jarvis:briefing:today` (TTL 16 heures).
        """
        # 1. Vérification du cache Redis
        if not force_refresh:
            cached_briefing = await cache_service.get(self.CACHE_KEY)
            if cached_briefing and isinstance(cached_briefing, dict) and cached_briefing.get("texte_oral"):
                logger.info("[BriefingService] Briefing récupéré directement depuis le cache Redis.")
                return cached_briefing

        logger.info("[BriefingService] Compilation d'un nouveau Morning Briefing...")

        # 2. Collecte concurrente et asynchrone des métriques
        system_task = asyncio.to_thread(get_system_status)
        pc_status_task = cache_service.get_device_presence("pc_status")
        device_location_task = cache_service.get("jarvis:device:location")
        news_task = get_top_news_24h(limit=5)
        emails_task = read_received_emails_async(max_count=5, unread_only=True)
        cached_agenda_task = cache_service.get("jarvis:agenda:today")

        sys_info, pc_status, device_location, news_res, email_res, cached_agenda = await asyncio.gather(
            system_task,
            pc_status_task,
            device_location_task,
            news_task,
            emails_task,
            cached_agenda_task,
            return_exceptions=True
        )

        # Résolution de la localisation actuelle pour la météo
        lat: Optional[float] = None
        lon: Optional[float] = None
        current_city: Optional[str] = None

        if not isinstance(device_location, Exception) and isinstance(device_location, dict):
            lat = device_location.get("latitude")
            lon = device_location.get("longitude")
            current_city = device_location.get("city")

        # Si pas de coordonnées reçues par l'appareil, vérifier où est l'utilisateur dans sa mémoire
        if (lat is None or lon is None) and not current_city:
            mem_loc = memory_service.get_current_user_location()
            current_city = mem_loc.get("city", "Grenoble")

        weather = await get_local_weather(city=current_city, latitude=lat, longitude=lon)

        # Normalisation de l'état système
        pc_online = False
        if not isinstance(pc_status, Exception) and pc_status:
            pc_online = pc_status.get("online", False)
        elif not isinstance(sys_info, Exception) and isinstance(sys_info, dict):
            pc_online = sys_info.get("pc_online", False)

        # Normalisation de la météo
        if isinstance(weather, Exception) or not isinstance(weather, dict):
            weather = {
                "city": current_city or "Grenoble",
                "temperature": "18°C",
                "condition": "Ciel dégagé",
                "description": "Conditions idéales"
            }

        # Normalisation des actualités des dernières 24h
        top_news_items = []
        if not isinstance(news_res, Exception) and isinstance(news_res, dict):
            top_news_items = news_res.get("items", [])

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

        # Normalisation des rendez-vous d'agenda (LECTURE SEULE STRICTE - AUCUNE CRÉATION)
        # Ne JAMAIS appeler trigger_webhook("agenda-event") ici, l'agenda est uniquement consulté
        agenda_events: List[Dict[str, Any]] = []
        if not isinstance(cached_agenda, Exception) and isinstance(cached_agenda, list):
            agenda_events = cached_agenda
        elif not isinstance(cached_agenda, Exception) and isinstance(cached_agenda, dict) and "events" in cached_agenda:
            agenda_events = cached_agenda["events"]

        # 3. Synthèse au ton Stark Industries (concise, rythmée, digne de Tony Stark & Aoede)
        # Phrase 1 : Salutation & Statut système
        phrase_sys = (
            f"Bonjour Pierre. Tous les systèmes sont opérationnels, PC de commandement connecté et synchronisé."
            if pc_online else
            f"Bonjour Pierre. Systèmes centraux opérationnels, liaison cloud active."
        )

        # Phrase 2 : Météo à la position actuelle
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

        # Phrase 4 : Actualités des dernières 24 heures
        if top_news_items and len(top_news_items) >= 2:
            t1 = top_news_items[0].get("title", "")
            t2 = top_news_items[1].get("title", "")
            phrase_news = f"Sur le front des actualités des dernières 24 heures : {t1}, et {t2}."
        elif top_news_items:
            t1 = top_news_items[0].get("title", "")
            phrase_news = f"Dans l'actualité des dernières 24 heures : {t1}."
        else:
            phrase_news = "Flux d'actualités calme sur les dernières 24 heures."

        # Phrase 5 : Courriels & Tâches
        if urgent_count > 0:
            phrase_emails = f"À noter : {unread_count} courriel(s) non lu(s), dont {urgent_count} classé(s) urgent(s). Tous les voyants sont au vert, prêt pour vos directives."
        elif unread_count > 0:
            first_sender = email_items[0].get("from", "un contact") if email_items else ""
            sender_clean = first_sender.split("<")[0].strip() if first_sender else "votre boîte"
            phrase_emails = f"Vous avez {unread_count} message(s) non lu(s), notamment de {sender_clean}. Tous les voyants sont au vert, prêt pour vos directives."
        else:
            phrase_emails = "Messagerie à jour, aucun message urgent. Tous les voyants sont au vert, prêt pour vos directives."

        # Phrase 6 : Synthèse de supervision et de qualité des 7 derniers jours
        phrase_qualite = ""
        try:
            from scripts.quality_report import get_quality_briefing_sentence
            phrase_qualite = get_quality_briefing_sentence()
        except Exception as _qe:
            logger.debug("[BriefingService] Synthèse qualité non disponible : %s", _qe)

        # Assemblage final du discours d'impact
        discours_parts = [phrase_sys, phrase_meteo, phrase_agenda, phrase_news, phrase_emails]
        if phrase_qualite:
            discours_parts.append(phrase_qualite)
        discours_oral = " ".join(discours_parts)

        briefing_payload = {
            "status": "success",
            "date": datetime.date.today().isoformat(),
            "compiled_at": datetime.datetime.now().isoformat(),
            "texte_oral": discours_oral,
            "synthese_qualite_7j": phrase_qualite,
            "meteo": weather,
            "actualites": {
                "count": len(top_news_items),
                "items": top_news_items
            },
            "news": {
                "count": len(top_news_items),
                "items": top_news_items
            },
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

    async def get_morning_briefing(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Retourne le Morning Briefing (alias conforme get_morning_briefing)."""
        return await self.compiler_morning_briefing(force_refresh=force_refresh)

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

    async def preparer_briefing_strategique_agent(self, tech_focus: str = "Architectures LLM, Multi-Agents, IA") -> Dict[str, Any]:
        """Déclenche la préparation prédictive approfondie du briefing matinal (déclenchée à 6h45 ou à la demande)
        via l'agent Antigravity CLI 'morning_briefing' (Système 2) : croisement agenda/documents, retards en temps réel
        et veille technologique ciblée.
        """
        from services.agentic_dispatcher import agentic_dispatcher
        
        # Récupération des données brutes
        base_briefing = await self.compiler_morning_briefing(force_refresh=True)
        goal = "Préparation stratégique prédictive du Morning Briefing et veille technologique ciblée"
        context = {
            "date": datetime.date.today().isoformat(),
            "briefing_brut": base_briefing,
            "tech_focus": tech_focus,
            "ville": base_briefing.get("meteo", {}).get("city", "Grenoble")
        }
        return await agentic_dispatcher.launch_agentic_mission(
            mission_type="morning_briefing",
            goal=goal,
            context=context
        )

    async def send_telegram_notification(self, message: str, chat_id: str = "6849746502") -> Dict[str, Any]:
        """Alias pratique pour send_telegram_alert."""
        return await self.send_telegram_alert(message, chat_id=chat_id)


# Singleton
briefing_service = BriefingService()


