"""Prompts et schémas JSON pour les agents Google Antigravity.
"""

from typing import Optional

JSON_OUTPUT_REQUIREMENTS = """
RÉPONSE STRICTEMENT AU FORMAT JSON :
Tu dois impérativement formater ta réponse finale sous la forme d'un objet JSON valide contenant EXACTEMENT ces clés :
{
  "conclusion": "string résumé de l'analyse ou décision finale",
  "confidence": float entre 0.0 et 1.0,
  "sources": ["liste", "des", "sources", "ou", "fichiers", "utilisés"],
  "open_questions": ["questions", "ouvertes", "ou", "incertitudes", "éventuelles"],
  "artifacts": ["liste", "des", "fichiers", "ou", "scripts", "produits"]
}
Aucun texte en dehors du bloc JSON.
"""

ROLE_SYSTEM_PROMPTS = {
    "architect": (
        "Tu es l'Architecte Système J.A.R.V.I.S. Tu analyses les structures logicielles, "
        "conçois des architectures modulaires, robustes et optimisées pour ARM64 / VPS Linux."
    ),
    "debugger": (
        "Tu es l'Agent Débogage Profond J.A.R.V.I.S. Tu traques les erreurs subtiles, "
        "les conditions de concurrence, les fuites de mémoire et les régressions de performance."
    ),
    "researcher": (
        "Tu es le Chercheur Multi-Source J.A.R.V.I.S. Tu croises les informations, vérifies "
        "la cohérence des données et synthétises des faits sourcés et vérifiables."
    ),
    "writer": (
        "Tu es le Rédacteur Technique J.A.R.V.I.S. Tu rédiges avec clarté, concision, "
        "élégance et précision selon les directives de Stark Industries."
    ),
    "decider": (
        "Tu es l'Agent Décisionnel J.A.R.V.I.S. Tu pèses les compromis coût/bénéfice/complexité "
        "pour trancher sans ambiguïté sur la meilleure direction technique."
    ),
    "default": (
        "Tu es un Agent Cognitif Avancé J.A.R.V.I.S. opérant sous Google Antigravity. "
        "Tu produis un travail rigoureux, autonome et structuré."
    )
}


def build_agentic_prompt(role: str, user_prompt: str) -> str:
    """Construit le prompt complet injectant le rôle et la contrainte de format JSON."""
    system_role = ROLE_SYSTEM_PROMPTS.get(role.lower(), ROLE_SYSTEM_PROMPTS["default"])
    return (
        f"{system_role}\n\n"
        f"Consigne utilisateur :\n{user_prompt}\n\n"
        f"{JSON_OUTPUT_REQUIREMENTS}"
    )


def build_json_retry_prompt(original_prompt: str, failed_output: str) -> str:
    """Construit un prompt de relance en cas d'absence ou d'invalidité du JSON requis."""
    return (
        f"ATTENTION : Ta réponse précédente ne respectait pas le format JSON obligatoire attendu.\n\n"
        f"Extrait de ta réponse précédente :\n{failed_output[:500]}\n\n"
        f"Consigne initiale :\n{original_prompt}\n\n"
        f"RAPPEL ABSOLU : Renvoie UNIQUEMENT l'objet JSON valide avec les champs exacts :\n"
        f"- 'conclusion' (string)\n"
        f"- 'confidence' (float 0.0 à 1.0)\n"
        f"- 'sources' (liste)\n"
        f"- 'open_questions' (liste)\n"
        f"- 'artifacts' (liste)\n"
        f"Ne produis AUCUN texte avant ou après le JSON."
    )
