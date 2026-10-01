"""services/deezer_migration_service.py
Service de migration intelligent Deezer -> Spotify pour J.A.R.V.I.S.

Fonctionnalités :
- Import des favoris et playlists Deezer (API publique Deezer ou fichier CSV export).
- Matching hybride : recherche par ISRC en priorité, puis recherche floue (titre + artiste + durée).
- Scoring de confiance [0, 1] :
    >= 0.85 (FUZZY_AUTO_ACCEPT) : match automatique
    0.72 à 0.85 (FUZZY_THRESHOLD) : confiance faible (liste de révision)
    < 0.72 : non trouvé (liste des introuvables)
- Création automatique des playlists sur Spotify et ajout par lots de 100.
- Persistance dans SQLite (migration_state) et génération de rapports :
    - JSON structuré avec deux listes distinctes : not_found et low_confidence
    - CSV pour révision rapide (not_found_{run_id}.csv, low_confidence_{run_id}.csv)
- Notification Telegram de synthèse via briefing_service.
"""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

import config
from services.briefing_service import briefing_service
from services.console_monitor import console_monitor
from services.spotify_service import (
    DB_PATH,
    FUZZY_AUTO_ACCEPT,
    FUZZY_THRESHOLD,
    _normalize,
    _similarity,
    spotify_service,
)

logger = logging.getLogger("DeezerMigrationService")

REPORTS_DIR = os.path.join(config.BASE_DIR, "data", "migration_reports")
DEEZER_API_BASE = "https://api.deezer.com"


class DeezerMigrationService:
    """Orchestrateur de la migration de bibliothèque Deezer vers Spotify."""

    def __init__(self) -> None:
        self._current_run: Dict[str, Any] = {
            "status": "idle",
            "run_id": "",
            "progress": 0.0,
            "current_track": "",
            "summary": {},
            "report_path": "",
            "error": "",
        }
        self._lock = asyncio.Lock()
        os.makedirs(REPORTS_DIR, exist_ok=True)

    def get_status(self) -> Dict[str, Any]:
        """Retourne l'état courant de la migration (pour /api/media/spotify/migration/status)."""
        return dict(self._current_run)

    # ── Récupération des données Deezer ───────────────────────────────────────

    async def fetch_deezer_user_tracks(self, user_id: str | int) -> List[Dict[str, Any]]:
        """Récupère les morceaux favoris d'un utilisateur Deezer via l'API publique."""
        tracks: List[Dict[str, Any]] = []
        url = f"{DEEZER_API_BASE}/user/{user_id}/tracks"
        async with httpx.AsyncClient(timeout=15.0) as client:
            while url:
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        logger.warning(f"[DeezerMigration] Erreur API Deezer user/tracks: {resp.status_code}")
                        break
                    data = resp.json()
                    for item in data.get("data", []):
                        tracks.append({
                            "deezer_track_id": item.get("id"),
                            "deezer_title": item.get("title", ""),
                            "deezer_artist": (item.get("artist") or {}).get("name", ""),
                            "deezer_album": (item.get("album") or {}).get("title", ""),
                            "deezer_isrc": item.get("isrc", ""),
                            "deezer_duration_s": float(item.get("duration", 0)),
                            "source_playlist": "Coups de Cœur Deezer",
                        })
                    url = data.get("next")
                except Exception as exc:
                    logger.error(f"[DeezerMigration] Exception récupération Deezer favoris: {exc}")
                    break
        return tracks

    async def fetch_deezer_playlist_tracks(self, playlist_id: str | int, playlist_name: str = "") -> List[Dict[str, Any]]:
        """Récupère les morceaux d'une playlist Deezer via l'API publique."""
        tracks: List[Dict[str, Any]] = []
        url = f"{DEEZER_API_BASE}/playlist/{playlist_id}/tracks"
        async with httpx.AsyncClient(timeout=15.0) as client:
            while url:
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        break
                    data = resp.json()
                    p_name = playlist_name or f"Playlist Deezer {playlist_id}"
                    for item in data.get("data", []):
                        tracks.append({
                            "deezer_track_id": item.get("id"),
                            "deezer_title": item.get("title", ""),
                            "deezer_artist": (item.get("artist") or {}).get("name", ""),
                            "deezer_album": (item.get("album") or {}).get("title", ""),
                            "deezer_isrc": item.get("isrc", ""),
                            "deezer_duration_s": float(item.get("duration", 0)),
                            "source_playlist": p_name,
                        })
                    url = data.get("next")
                except Exception as exc:
                    logger.error(f"[DeezerMigration] Exception récupération Deezer playlist {playlist_id}: {exc}")
                    break
        return tracks

    def load_from_csv(self, file_path: str) -> List[Dict[str, Any]]:
        """Parse un export CSV (Soundiiz, TuneMyMusic ou format standard)."""
        tracks: List[Dict[str, Any]] = []
        if not os.path.exists(file_path):
            return tracks

        with open(file_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, start=1):
                # Détection tolérante des colonnes
                title = row.get("title") or row.get("Title") or row.get("Track Name") or row.get("Titre") or ""
                artist = row.get("artist") or row.get("Artist") or row.get("Artist Name") or row.get("Artiste") or ""
                album = row.get("album") or row.get("Album") or row.get("Album Name") or ""
                isrc = row.get("isrc") or row.get("ISRC") or ""
                playlist = row.get("playlist") or row.get("Playlist") or row.get("Playlist Name") or "Favoris Deezer"
                dur_raw = row.get("duration") or row.get("Duration") or row.get("Durée") or "0"
                try:
                    duration_s = float(dur_raw)
                except ValueError:
                    duration_s = 0.0

                if title:
                    tracks.append({
                        "deezer_track_id": row.get("id") or idx,
                        "deezer_title": title.strip(),
                        "deezer_artist": artist.strip(),
                        "deezer_album": album.strip(),
                        "deezer_isrc": isrc.strip(),
                        "deezer_duration_s": duration_s,
                        "source_playlist": playlist.strip(),
                    })
        return tracks

    # ── Résolution intelligente d'un titre sur Spotify ───────────────────────

    async def _match_track(self, deezer_item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cherche le morceau correspondant sur Spotify :
        1. ISRC exact
        2. Recherche 'track:X artist:Y' + score de similarité
        3. Recherche libre 'X Y'
        """
        isrc = deezer_item.get("deezer_isrc", "").strip()
        title = deezer_item.get("deezer_title", "").strip()
        artist = deezer_item.get("deezer_artist", "").strip()
        duration_s = deezer_item.get("deezer_duration_s", 0.0)

        # 1. Tentative par ISRC
        if isrc:
            try:
                sp_track = await spotify_service.find_track_by_isrc(isrc)
                if sp_track:
                    sp_dur = (sp_track.get("duration_ms", 0) or 0) / 1000.0
                    return {
                        "matched": True,
                        "spotify_track_id": sp_track.get("id", ""),
                        "spotify_uri": sp_track.get("uri", ""),
                        "spotify_title": sp_track.get("name", ""),
                        "spotify_artist": ", ".join(a["name"] for a in sp_track.get("artists", [])),
                        "confidence_score": 1.0,
                        "duration_delta_s": round(abs(duration_s - sp_dur), 1) if duration_s else 0.0,
                        "match_method": "isrc",
                        "status": "matched",
                    }
            except Exception as e:
                logger.debug(f"[DeezerMigration] Recherche ISRC échouée pour {isrc}: {e}")

        # 2. Recherche ciblée sur Spotify
        candidates: List[Dict[str, Any]] = []
        queries = []
        if artist:
            queries.append(f"track:{title} artist:{artist}")
            queries.append(f"{title} {artist}")
        else:
            queries.append(title)

        for q in queries:
            try:
                data = await spotify_service.search(q, stype="track", limit=5)
                tracks = (data.get("tracks") or {}).get("items", [])
                if tracks:
                    candidates.extend(tracks)
                    break
            except Exception as e:
                logger.warning(f"[DeezerMigration] Erreur recherche Spotify pour '{q}': {e}")

        if not candidates:
            return {
                "matched": False,
                "spotify_track_id": "",
                "spotify_uri": "",
                "spotify_title": "",
                "spotify_artist": "",
                "confidence_score": 0.0,
                "duration_delta_s": 0.0,
                "match_method": "none",
                "status": "not_found",
            }

        # 3. Calcul du score de similarité
        def evaluate(t: Dict[str, Any]) -> Tuple[float, float]:
            t_name = t.get("name", "")
            t_artists = ", ".join(a["name"] for a in t.get("artists", []))
            sim_title = _similarity(t_name, title)
            sim_artist = _similarity(t_artists, artist) if artist else 1.0
            score = sim_title * 0.65 + sim_artist * 0.35

            # Pénalité de durée si écart > 12s
            sp_dur = (t.get("duration_ms", 0) or 0) / 1000.0
            delta_dur = abs(duration_s - sp_dur) if duration_s > 0 else 0.0
            if duration_s > 0 and delta_dur > 12.0 and score < 0.95:
                score -= 0.15

            return max(0.0, min(1.0, score)), delta_dur

        best_track = None
        best_score = -1.0
        best_delta = 0.0

        for cand in candidates:
            score, delta = evaluate(cand)
            if score > best_score:
                best_score = score
                best_track = cand
                best_delta = delta

        if not best_track or best_score < FUZZY_THRESHOLD:
            return {
                "matched": False,
                "spotify_track_id": best_track.get("id", "") if best_track else "",
                "spotify_uri": best_track.get("uri", "") if best_track else "",
                "spotify_title": best_track.get("name", "") if best_track else "",
                "spotify_artist": ", ".join(a["name"] for a in best_track.get("artists", [])) if best_track else "",
                "confidence_score": round(best_score, 2),
                "duration_delta_s": round(best_delta, 1),
                "match_method": "fuzzy_rejected",
                "status": "not_found",
            }

        # Distinction match automatique vs confiance faible
        is_auto = best_score >= FUZZY_AUTO_ACCEPT
        status_code = "matched" if is_auto else "low_confidence"

        return {
            "matched": is_auto,
            "spotify_track_id": best_track.get("id", ""),
            "spotify_uri": best_track.get("uri", ""),
            "spotify_title": best_track.get("name", ""),
            "spotify_artist": ", ".join(a["name"] for a in best_track.get("artists", [])),
            "confidence_score": round(best_score, 2),
            "duration_delta_s": round(best_delta, 1),
            "match_method": "fuzzy",
            "status": status_code,
        }

    # ── Sauvegarde en SQLite ──────────────────────────────────────────────────

    def _persist_state(self, run_id: str, item: Dict[str, Any], match: Dict[str, Any], status: str) -> None:
        """Enregistre ou met à jour l'état de matching dans SQLite."""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                """
                INSERT INTO migration_state (
                    run_id, source_playlist, deezer_track_id, deezer_title,
                    deezer_artist, deezer_album, deezer_isrc, deezer_duration_s,
                    spotify_track_id, spotify_title, spotify_artist,
                    confidence_score, duration_delta_s, match_method, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, source_playlist, deezer_track_id) DO UPDATE SET
                    spotify_track_id=excluded.spotify_track_id,
                    spotify_title=excluded.spotify_title,
                    spotify_artist=excluded.spotify_artist,
                    confidence_score=excluded.confidence_score,
                    duration_delta_s=excluded.duration_delta_s,
                    match_method=excluded.match_method,
                    status=excluded.status,
                    updated_at=datetime('now')
                """,
                (
                    run_id,
                    item.get("source_playlist", "Défaut"),
                    item.get("deezer_track_id", 0),
                    item.get("deezer_title", ""),
                    item.get("deezer_artist", ""),
                    item.get("deezer_album", ""),
                    item.get("deezer_isrc", ""),
                    item.get("deezer_duration_s", 0.0),
                    match.get("spotify_track_id", ""),
                    match.get("spotify_title", ""),
                    match.get("spotify_artist", ""),
                    match.get("confidence_score", 0.0),
                    match.get("duration_delta_s", 0.0),
                    match.get("match_method", ""),
                    status,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error(f"[DeezerMigration] Erreur SQLite persist_state : {exc}")

    # ── Exécution du pipeline complet ────────────────────────────────────────

    async def run(
        self,
        dry_run: bool = False,
        run_id: str = "",
        deezer_user_id: str = "",
        csv_path: str = "",
        tracks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Point d'entrée principal de la migration :
        - Récupère les données sources
        - Match chaque titre
        - Crée les playlists Spotify et injecte les tracks
        - Génère le rapport final avec not_found et low_confidence séparés
        - Notifie Telegram
        """
        async with self._lock:
            run_id = run_id or f"mig_{int(time.time())}_{uuid.uuid4().hex[:6]}"
            start_time = time.time()

            self._current_run = {
                "status": "running",
                "run_id": run_id,
                "progress": 0.0,
                "current_track": "Chargement des titres sources...",
                "summary": {},
                "report_path": "",
                "error": "",
            }

            try:
                # 1. Collecte des morceaux
                source_tracks: List[Dict[str, Any]] = []
                if tracks:
                    source_tracks = list(tracks)
                elif csv_path and os.path.exists(csv_path):
                    source_tracks = self.load_from_csv(csv_path)
                elif deezer_user_id:
                    source_tracks = await self.fetch_deezer_user_tracks(deezer_user_id)
                else:
                    # Recherche d'un fichier CSV présent dans data/ ou downloads/
                    auto_csv = os.path.join(config.BASE_DIR, "data", "deezer_export.csv")
                    if os.path.exists(auto_csv):
                        source_tracks = self.load_from_csv(auto_csv)
                    else:
                        down_csv = os.path.join(config.BASE_DIR, "downloads", "deezer_export.csv")
                        if os.path.exists(down_csv):
                            source_tracks = self.load_from_csv(down_csv)

                if not source_tracks:
                    msg = "Aucun titre Deezer à migrer (ni CSV fourni, ni ID utilisateur Deezer)."
                    self._current_run.update({"status": "failed", "error": msg})
                    return {"status": "failed", "message": msg}

                total_tracks = len(source_tracks)
                matched_items: List[Dict[str, Any]] = []
                low_confidence_items: List[Dict[str, Any]] = []
                not_found_items: List[Dict[str, Any]] = []
                uris_by_playlist: Dict[str, List[str]] = {}

                # 2. Matching progressif
                for idx, track_item in enumerate(source_tracks, start=1):
                    title = track_item.get("deezer_title", "")
                    artist = track_item.get("deezer_artist", "")
                    self._current_run["current_track"] = f"{title} - {artist}"
                    self._current_run["progress"] = round((idx / total_tracks) * 100, 1)

                    try:
                        match_res = await asyncio.wait_for(
                            self._match_track(track_item), timeout=15.0
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"[DeezerMigration] Timeout 15s sur '{title}' - titre ignoré")
                        match_res = {
                            "matched": False, "spotify_track_id": "", "spotify_uri": "",
                            "spotify_title": "", "spotify_artist": "", "confidence_score": 0.0,
                            "duration_delta_s": 0.0, "match_method": "timeout",
                            "status": "not_found",
                        }
                    except Exception as exc:
                        logger.warning(f"[DeezerMigration] Erreur sur '{title}': {exc}")
                        match_res = {
                            "matched": False, "spotify_track_id": "", "spotify_uri": "",
                            "spotify_title": "", "spotify_artist": "", "confidence_score": 0.0,
                            "duration_delta_s": 0.0, "match_method": "error",
                            "status": "not_found",
                        }

                    status = match_res["status"]
                    self._persist_state(run_id, track_item, match_res, status)

                    if status == "matched":
                        matched_items.append({**track_item, **match_res})
                        p_name = track_item.get("source_playlist", "Coups de Cœur Deezer")
                        uris_by_playlist.setdefault(p_name, []).append(match_res["spotify_uri"])
                    elif status == "low_confidence":
                        low_confidence_items.append({**track_item, **match_res})
                    else:
                        not_found_items.append({**track_item, **match_res})

                    # Petit répit pour éviter les rate-limits
                    if idx % 10 == 0:
                        await asyncio.sleep(0.2)


                # 3. Création playlists Spotify et ajout des titres (si non dry_run)
                created_playlists: List[str] = []
                migrated_count = 0

                if not dry_run:
                    for p_name, uris in uris_by_playlist.items():
                        if not uris:
                            continue
                        try:
                            target_p_name = f"{p_name} (Migré Deezer)"
                            desc = f"Playlist importée depuis Deezer le {datetime.now(timezone.utc).strftime('%Y-%m-%d')} par J.A.R.V.I.S."
                            created = await spotify_service.create_playlist(name=target_p_name, description=desc, public=False)
                            p_id = created.get("id")
                            if p_id:
                                await spotify_service.add_tracks_to_playlist(p_id, uris)
                                created_playlists.append(target_p_name)
                                migrated_count += len(uris)
                        except Exception as e:
                            logger.error(f"[DeezerMigration] Erreur création playlist '{p_name}': {e}")

                # 4. Rapport structuré
                duration_s = round(time.time() - start_time, 1)
                summary = {
                    "total_deezer_tracks": total_tracks,
                    "matched_auto": len(matched_items),
                    "low_confidence_count": len(low_confidence_items),
                    "not_found_count": len(not_found_items),
                    "added_to_spotify": migrated_count if not dry_run else 0,
                    "playlists_created": created_playlists,
                    "duration_seconds": duration_s,
                    "dry_run": dry_run,
                }

                report = {
                    "run_id": run_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "completed",
                    "dry_run": dry_run,
                    "summary": summary,
                    "not_found": [
                        {
                            "deezer_track_id": item.get("deezer_track_id"),
                            "title": item.get("deezer_title"),
                            "artist": item.get("deezer_artist"),
                            "album": item.get("deezer_album"),
                            "playlist": item.get("source_playlist"),
                        }
                        for item in not_found_items
                    ],
                    "low_confidence": [
                        {
                            "deezer_track_id": item.get("deezer_track_id"),
                            "deezer_title": item.get("deezer_title"),
                            "deezer_artist": item.get("deezer_artist"),
                            "spotify_track_id": item.get("spotify_track_id"),
                            "spotify_title": item.get("spotify_title"),
                            "spotify_artist": item.get("spotify_artist"),
                            "confidence_score": item.get("confidence_score"),
                            "duration_delta_s": item.get("duration_delta_s"),
                            "playlist": item.get("source_playlist"),
                        }
                        for item in low_confidence_items
                    ],
                }

                # 5. Écriture des fichiers de rapport (JSON + CSVs)
                json_path = os.path.join(REPORTS_DIR, f"migration_report_{run_id}.json")
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)

                # CSV Not Found
                csv_not_found = os.path.join(REPORTS_DIR, f"not_found_{run_id}.csv")
                with open(csv_not_found, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["deezer_track_id", "title", "artist", "album", "playlist"])
                    for nf in report["not_found"]:
                        writer.writerow([nf["deezer_track_id"], nf["title"], nf["artist"], nf["album"], nf["playlist"]])

                # CSV Low Confidence
                csv_low_conf = os.path.join(REPORTS_DIR, f"low_confidence_{run_id}.csv")
                with open(csv_low_conf, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["deezer_track_id", "deezer_title", "deezer_artist", "spotify_track_id", "spotify_title", "spotify_artist", "confidence_score", "duration_delta_s", "playlist"])
                    for lc in report["low_confidence"]:
                        writer.writerow([
                            lc["deezer_track_id"], lc["deezer_title"], lc["deezer_artist"],
                            lc["spotify_track_id"], lc["spotify_title"], lc["spotify_artist"],
                            lc["confidence_score"], lc["duration_delta_s"], lc["playlist"]
                        ])

                self._current_run.update({
                    "status": "completed",
                    "progress": 100.0,
                    "summary": summary,
                    "report_path": json_path,
                })

                # 6. Notification Telegram de synthèse
                mode_str = " (Mode Simulation)" if dry_run else ""
                tg_msg = (
                    f"🎵 *Migration Deezer ➔ Spotify Terminée*{mode_str}\n\n"
                    f"📊 *Statistiques :*\n"
                    f"• Total analysé : `{total_tracks}` titres\n"
                    f"• Correspondances exactes : `✅ {len(matched_items)}`\n"
                    f"• Confiance faible (à vérifier) : `⚠️ {len(low_confidence_items)}`\n"
                    f"• Non trouvés : `❌ {len(not_found_items)}`\n"
                    f"• Titres injectés Spotify : `✨ {migrated_count}`\n"
                    f"• Durée : `{duration_s}s`\n\n"
                    f"📁 *Rapport généré :*\n"
                    f"`{json_path}`"
                )
                try:
                    await briefing_service.send_telegram_alert(message=tg_msg, chat_id="6849746502")
                except Exception as tg_err:
                    logger.warning(f"[DeezerMigration] Erreur envoi Telegram : {tg_err}")

                return report

            except Exception as exc:
                logger.error(f"[DeezerMigration] Échec de la migration : {exc}", exc_info=True)
                console_monitor.log_exception("DeezerMigrationService.run", exc)
                self._current_run.update({
                    "status": "failed",
                    "error": str(exc),
                })
                return {"status": "error", "message": str(exc)}


deezer_migration_service = DeezerMigrationService()
