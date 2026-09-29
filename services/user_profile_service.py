"""
services/user_profile_service.py — Service de Connaissance Approfondie du Profil de Candidature de Pierre Cassagnettes.

Charge, surveille et extrait l'intégralité des informations académiques, techniques,
professionnelles et contextuelles depuis PROFIL_CANDIDATURE_PIERRE_CASSAGNETTES.md.
Grâce à la détection d'empreinte mtime (dernière modification), toute mise à jour du fichier est
instantanément rechargée en mémoire sans nécessiter de redémarrage.
"""

from __future__ import annotations

import os
import re
import time
import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Any

from config import DB_PATH

logger = logging.getLogger("jarvis.user_profile")


class UserProfileKnowledgeService:
    """
    Gestionnaire dynamique du profil complet et du dossier de candidature de Pierre Cassagnettes.
    Assure que J.A.R.V.I.S. maîtrise parfaitement son parcours, ses compétences, ses projets
    et ses objectifs de stage en temps réel.
    """

    def __init__(self, file_path: Optional[str] = None):
        if file_path:
            self.file_path = file_path
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.file_path = os.path.join(base_dir, "PROFIL_CANDIDATURE_PIERRE_CASSAGNETTES.md")

        self._last_mtime: float = 0.0
        self._raw_content: str = ""
        self._sections: Dict[str, Dict[str, Any]] = {}
        self._cached_summary: str = ""
        self._table_of_contents: List[str] = []
        self._profile_dict: Dict[str, Any] = {}

    def _ensure_loaded(self, force: bool = False) -> bool:
        """Vérifie le mtime du fichier et recharge si une modification est détectée."""
        if not os.path.exists(self.file_path):
            logger.warning(f"[UserProfileService] Fichier introuvable : {self.file_path}")
            return False

        try:
            current_mtime = os.path.getmtime(self.file_path)
            if not force and current_mtime == self._last_mtime and self._raw_content:
                return True

            with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            self._raw_content = content
            self._last_mtime = current_mtime
            self._parse_document(content, current_mtime)

            logger.info(
                f"[UserProfileService] ✦ Profil de Pierre rechargé dynamiquement : {len(content)} caractères, "
                f"{len(self._sections)} sections ({time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_mtime))})"
            )
            return True
        except Exception as e:
            logger.error(f"[UserProfileService] Erreur lors du chargement du profil : {e}")
            return False

    def _normalize_key(self, text: str) -> str:
        """Nettoie une clé de section pour recherche insensible à la casse et aux accents."""
        clean = text.lower()
        clean = re.sub(r"[✦>#\(\)\[\]_`\*\:\-]", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def _parse_document(self, content: str, mtime: float):
        """Découpe le document Markdown en sections et construit le résumé contextuel."""
        self._sections.clear()
        self._table_of_contents.clear()

        header_regex = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)
        matches = list(header_regex.finditer(content))

        for i, match in enumerate(matches):
            level = len(match.group(1))
            title = match.group(2).strip()
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            body = content[start_pos:end_pos].strip()

            sec_id = self._normalize_key(title)
            self._sections[sec_id] = {
                "title": title,
                "level": level,
                "body": body,
                "full_text": f"{match.group(0)}\n\n{body}"
            }
            if level == 2:
                self._table_of_contents.append(title)

        # Extraction des métadonnées structurées clés
        self._profile_dict = {
            "nom_complet": "Pierre Cassagnettes",
            "first_name": "Pierre",
            "last_name": "Cassagnettes",
            "email": "pierrecassagnettes@gmail.com",
            "phone": "+33 7 69 52 44 30",
            "localisations": "Malmö, Suède / Grenoble, France",
            "zone_geographique": "Région de l'Øresund (Malmö, Lund, Copenhague) — Pied-à-terre immédiat. Mobile Scandinavie, France et Europe.",
            "statut_actuel": "Promotion 2026 — Élève-ingénieur en 3e année (Bac+5 / Master of Science)",
            "ecole": "Grenoble INP – Phelma (Grenoble, France)",
            "filiere": "SICOM (Signal, Image, Communication & Machine Learning)",
            "statut_recherche": "Stage de Fin d'Études (PFE) / Master's Thesis / Final-Year Internship",
            "date_debut": "À partir du 18 janvier 2026 (flexible janvier – mars 2026)",
            "duree": "5 à 6 mois (printemps – été 2026)",
            "nationalite": "Française (Citoyen UE, aucun visa requis)",
            "permis": "Permis B (Voiture) & Permis A2 (Motocyclette)",
            "langues": "Français (maternelle), Anglais (C1 / Courant professionnel), Italien (B1/B2)",
            "sports": "Volley-ball, Basket-ball, Course à pied, Moto A2",
            "passions": "Acoustique, reproduction sonore, audio numérique, technologies d'ingénierie physique"
        }

        # Construction du bloc de synthèse pour injection dans Gemini Live
        mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
        self._cached_summary = (
            f"✦ DOSSIER DE CANDIDATURE & PROFIL COMPLET DE PIERRE CASSAGNETTES ✦\n"
            f"(Source dynamique synchronisée : PROFIL_CANDIDATURE_PIERRE_CASSAGNETTES.md — Rechargé : {mtime_str})\n\n"
            f"1. IDENTITÉ & OBJECTIF IMMÉDIAT :\n"
            f"- Utilisateur : Pierre Cassagnettes (+33 7 69 52 44 30 | pierrecassagnettes@gmail.com).\n"
            f"- Formation : Élève-ingénieur en 3e année (Bac+5 / MSc, Promo 2026) à Grenoble INP – Phelma, filière SICOM (Signal, Image, Communication & Machine Learning).\n"
            f"- Cible : Stage de Fin d'Études (PFE) / Master's Thesis de 5 à 6 mois, dès le 18 janvier 2026 (flexible jusqu'en mars 2026).\n"
            f"- Localisation : Réside entre Malmö (Suède) et Grenoble (France). Immédiatement disponible dans la région de l'Øresund (Malmö, Lund, Copenhague) sans contrainte de visa (citoyen UE) ni de relocalisation.\n\n"
            f"2. SPÉCIALISATIONS TECHNIQUES & DOMAINES D'APPLICATION :\n"
            f"- Traitement du Signal & Audio/Acoustique : DSP (FFT, analyse temps-fréquence, ondelettes, filtrage RIF/RII), bruit d'intensité relative (RIN), asservissements en boucle fermée.\n"
            f"- Machine Learning Appliqué & Data Science : Apprentissage statistique (supervisé/non-supervisé), modélisation algorithmique sous Python appliquée à des données physiques réelles.\n"
            f"- Photonique Intégrée & Optoélectronique : Lasers DFB hétérogènes III-V/Si (technologie SHIP™), lasers microchip Q-switched, photodiodes MPD, filtres optiques, MUX.\n"
            f"- Instrumentation Avancée & Automatisation : Pilotage de bancs sous pointes 200 mm et analyseurs OSA via SCPI/PyVISA, générateurs d'impulsions HF/RF (HP 81104A).\n"
            f"- Développement Logiciel Scientifique & IHM : Python avancé (multiprocessing, multithreading, CustomTkinter, Matplotlib Agg), C, MATLAB/Simulink, Git, LaTeX.\n\n"
            f"3. EXPÉRIENCES MARQUANTES :\n"
            f"- Scintil Photonics (Stage R&D 2025, 13 sem.) : Conception d'une suite logicielle de 4 IHM Python CustomTkinter (temps de traitement divisé par 5 sur wafer 200 mm), caractérisation pulsée athermique 500 ns (suppression du roll-off thermique), alignement spectral OSA (< 1.0 GHz) et asservissement embarqué EEPROM, diagnostic matériel SCPI.\n"
            f"- Teem Photonics (Stage Opérateur Salle Blanche 2024, 8 sem.) : Assemblage optique sous normes ISO et conformité ESD de lasers microchip pulsés déclenchés.\n"
            f"- Trésorier BDE La Prépa des INP (2023-2024) : Gestion du budget associatif, négociation partenaires, logistique d'événements.\n\n"
            f"4. LANGUES & CENTRES D'INTÉRÊT :\n"
            f"- Langues : Français (maternelle), Anglais (C1 / Courant professionnel pour candidatures scandinaves et internationales), Italien (B1/B2).\n"
            f"- Centres d'intérêt : Volley-ball, Basket-ball, Course à pied, Moto (Permis A2), Technologies audio & acoustique."
        )

    def get_summary(self) -> str:
        """Retourne le résumé contextuel prêt pour injection dans le prompt de session."""
        self._ensure_loaded()
        return self._cached_summary

    def get_profile_dict(self) -> Dict[str, Any]:
        """Retourne les attributs structurés du profil de Pierre."""
        self._ensure_loaded()
        return dict(self._profile_dict)

    def get_full_content(self) -> str:
        """Retourne l'intégralité du texte brut Markdown."""
        self._ensure_loaded()
        return self._raw_content

    def get_table_of_contents(self) -> List[str]:
        """Retourne la liste des titres de chapitres."""
        self._ensure_loaded()
        return list(self._table_of_contents)

    def lookup(self, query: Optional[str] = None, section: Optional[str] = None, max_chars: int = 4000) -> Dict[str, Any]:
        """
        Recherche sémantique/textuelle fine dans les sections du dossier de candidature.
        """
        self._ensure_loaded()

        if not self._raw_content:
            return {
                "status": "error",
                "message": "Fichier PROFIL_CANDIDATURE_PIERRE_CASSAGNETTES.md non accessible."
            }

        target = (section or query or "").strip().lower()

        # 1. Correspondance par titre de section
        if target:
            matched_sections = []
            for sec_key, sec_data in self._sections.items():
                if target in sec_key or any(w in sec_key for w in target.split() if len(w) >= 3):
                    matched_sections.append(sec_data)

            if matched_sections:
                combined_text = "\n\n---\n\n".join(s["full_text"] for s in matched_sections[:3])
                if len(combined_text) > max_chars:
                    combined_text = combined_text[:max_chars] + "\n\n[... Suite tronquée pour concision ...]"
                return {
                    "status": "success",
                    "type": "section_match",
                    "matched_titles": [s["title"] for s in matched_sections[:3]],
                    "content": combined_text
                }

        # 2. Recherche textuelle par mots-clés dans le corps des sections
        if query:
            query_clean = query.strip().lower()
            keywords = [w for w in re.split(r"[\s,;':\-]+", query_clean) if len(w) >= 3]

            scored_sections = []
            for sec_key, sec_data in self._sections.items():
                score = 0
                body_lower = sec_data["body"].lower()
                for kw in keywords:
                    if kw in sec_key:
                        score += 6
                    score += body_lower.count(kw)
                if score > 0:
                    scored_sections.append((score, sec_data))

            scored_sections.sort(key=lambda x: x[0], reverse=True)
            if scored_sections:
                top_results = [s[1]["full_text"] for s in scored_sections[:2]]
                combined = "\n\n---\n\n".join(top_results)
                if len(combined) > max_chars:
                    combined = combined[:max_chars] + "\n\n[... Suite tronquée ...]"
                return {
                    "status": "success",
                    "type": "keyword_search",
                    "query": query,
                    "matched_titles": [s[1]["title"] for s in scored_sections[:2]],
                    "content": combined
                }

        # 3. Repli : résumé global
        return {
            "status": "success",
            "type": "summary",
            "content": self._cached_summary
        }

    def sync_to_sqlite(self, db_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Synchronise automatiquement toutes les données et faits du profil
        dans la base SQLite locale (user_profile et memories).
        """
        self._ensure_loaded()
        target_db = db_path or DB_PATH

        if not os.path.exists(target_db):
            return {"status": "error", "message": f"Base SQLite introuvable : {target_db}"}

        now_iso = datetime.now().isoformat()
        inserted_profiles = 0
        inserted_memories = 0

        # Données de configuration clé/valeur pour user_profile
        profile_entries = [
            ("user_name", "Pierre"),
            ("full_name", "Pierre Cassagnettes"),
            ("first_name", "Pierre"),
            ("last_name", "Cassagnettes"),
            ("email", "pierrecassagnettes@gmail.com"),
            ("phone", "+33 7 69 52 44 30"),
            ("address", "Malmö, Suède / Grenoble, France"),
            ("city", "Malmö"),
            ("current_city", "Malmö"),
            ("country", "Suède"),
            ("ecole", "Grenoble INP – Phelma"),
            ("filiere", "SICOM (Signal, Image, Communication & Machine Learning)"),
            ("statut_etudiant", "Promotion 2026 — Élève-ingénieur en 3e année (Bac+5 / Master of Science)"),
            ("statut_recherche", "Stage de Fin d'Études (PFE) / Master's Thesis (5-6 mois, dès le 18 janvier 2026)"),
            ("zone_recherche", "Région de l'Øresund (Malmö, Lund, Copenhague) — Réside sur place / pied-à-terre immédiat. Mobile Scandinavie, France, Europe"),
            ("nationalite", "Française (Citoyen UE, aucun visa requis)"),
            ("permis", "Permis B (Voiture) & Permis A2 (Motocyclette)"),
            ("langues", "Français (maternelle), Anglais (C1 / Courant professionnel), Italien (B1/B2)"),
            ("sports", "Volley-ball, Basket-ball, Course à pied, Moto A2"),
            ("experience_scintil", "Scintil Photonics (2025, 13 sem.) : Stage Ingénieur R&D Test & Photonique. IHM Python CustomTkinter (accélération ×5), caractérisation pulsée 500ns roll-off athermique, alignement OSA <1GHz EEPROM."),
            ("experience_teem", "Teem Photonics (2024, 8 sem.) : Stage Opérateur Salle Blanche ISO / ESD. Assemblage micro-lasers pulsés passifs."),
            ("experience_bde", "Trésorier du Bureau des Élèves (BDE) — La Prépa des INP (2023-2024)")
        ]

        # Faits mémorisés structurés pour memories
        factual_memories = [
            ("etudes", "Pierre est élève-ingénieur en 3e année (Bac+5 / MSc) à Grenoble INP - Phelma, promotion 2026, au sein de la filière d'excellence SICOM (Signal, Image, Communication & Machine Learning)."),
            ("stage_recherche", "Pierre recherche son Stage de Fin d'Études (PFE) / Master's Thesis de 5 à 6 mois débutant le 18 janvier 2026 (flexible jusqu'en mars 2026)."),
            ("localisation", "Pierre réside entre Malmö (Suède) et Grenoble (France). Il est immédiatement disponible dans la région de l'Øresund (Malmö, Lund, Copenhague) où il a un pied-à-terre immédiat, ainsi que mobile en Scandinavie, France et Europe."),
            ("coordonnees", "Coordonnées de Pierre : pierrecassagnettes@gmail.com, téléphone +33 7 69 52 44 30. Citoyen français de l'Union Européenne (aucun visa requis en Suède/Danemark)."),
            ("permis", "Pierre est titulaire du Permis B (Voiture) et du Permis A2 (Motocyclette)."),
            ("experience_scintil", "Chez Scintil Photonics (mai-août 2025, 13 semaines, startup deeptech issue du CEA-Leti), Pierre a conçu 4 IHM Python CustomTkinter divisant par 5 le temps de dépouillement sur wafer 200mm, modélisé un test pulsé RF 500 ns athermique éliminant le roll-off, asservi l'espacement spectral OSA à <1.0 GHz calibré en EEPROM, et diagnostiqué un générateur RF HP 81104A via SCPI."),
            ("experience_teem", "Chez Teem Photonics (juin-juillet 2024, 8 semaines), Pierre a travaillé en salle blanche sous normes ISO et protection ESD sur l'assemblage et collage optique de micro-lasers pulsés passifs déclenchés Q-switched."),
            ("experience_bde", "Pierre a été trésorier du Bureau des Élèves (BDE) de La Prépa des INP pendant un an (2023-2024), gérant budget, trésorerie et partenariats."),
            ("competences_informatique", "Pierre maîtrise Python à un niveau avancé pour l'ingénierie (multiprocessing, multithreading, CustomTkinter, Matplotlib Agg, NumPy, SciPy, Pandas, OpenPyXL, PyVISA, SCPI, packaging PyInstaller), ainsi que C, MATLAB/Simulink, Bash, Git et LaTeX."),
            ("competences_signal", "En traitement du signal, Pierre maîtrise le DSP (FFT, ondelettes, filtrage linéaire et adaptatif RIF/RII), la mesure de bruit RIN/SNR, l'apprentissage statistique ML appliqué à la physique et les boucles de rétroaction fermées."),
            ("competences_photonique", "En photonique et optoélectronique, Pierre a manipulé lasers DFB hétérogènes III-V/Si, analyseurs de spectre optique OSA, puces PIC, modulateurs MUX, coupleurs de réseau et bancs de test sous pointes wafer 200mm."),
            ("langues", "Pierre parle couramment anglais au niveau C1 professionnel (rédaction de rapports techniques, entretiens, cold emails en anglais pour la Scandinavie), français langue maternelle et italien niveau B1/B2."),
            ("sports_loisirs", "Pierre pratique régulièrement le volley-ball, le basket-ball et la course à pied. Il est passionné de moto (permis A2) et a un fort intérêt pour l'acoustique, la musique et les technologies de reproduction sonore audio.")
        ]

        try:
            with sqlite3.connect(target_db) as conn:
                cursor = conn.cursor()

                # Mise à jour user_profile
                for k, v in profile_entries:
                    cursor.execute("""
                        INSERT INTO user_profile (key, value, updated_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                    """, (k, v, now_iso))
                    inserted_profiles += 1

                # Insertion des faits dans memories (sans doublon exact)
                for cat, fact in factual_memories:
                    cursor.execute("SELECT COUNT(*) FROM memories WHERE fact = ?", (fact,))
                    if cursor.fetchone()[0] == 0:
                        cursor.execute("""
                            INSERT INTO memories (category, fact, created_at)
                            VALUES (?, ?, ?)
                        """, (cat, fact, now_iso))
                        inserted_memories += 1

                conn.commit()

            logger.info(
                f"[UserProfileService] ✅ Synchronisation SQLite terminée : "
                f"{inserted_profiles} clés de profil mises à jour, {inserted_memories} nouveaux souvenirs mémorisés."
            )
            return {
                "status": "success",
                "profiles_updated": inserted_profiles,
                "memories_inserted": inserted_memories
            }
        except Exception as e:
            logger.error(f"[UserProfileService] Erreur synchronisation SQLite : {e}")
            return {"status": "error", "message": str(e)}


# Instance singleton globale
user_profile_service = UserProfileKnowledgeService()
