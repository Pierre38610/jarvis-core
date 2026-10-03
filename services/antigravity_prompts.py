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
    "critic": (
        "Tu es l'Agent Critique & Logique J.A.R.V.I.S. Tu évalues la robustesse des hypothèses, "
        "traques les failles logiques, les contradictions et exiges des preuves matérielles vérifiables."
    ),
    "prospector": (
        "Tu es l'Agent Prospecteur J.A.R.V.I.S. Tu collectes exhaustivement les données, "
        "les sources vérifiées, les faits objectifs et les signaux faibles pertinents."
    ),
    "synthesis": (
        "Tu es l'Agent Synthèse & Décision J.A.R.V.I.S. Tu consolides les résultats multi-sources, "
        "résous les ambiguïtés et rédiges une synthèse exécutive structurée et percutante."
    ),
    "general_agent": (
        "Tu es un Agent Polyvalent J.A.R.V.I.S. Tu exécutes les missions techniques avec rigueur, "
        "autonomie et précision."
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

L2_JSON_OUTPUT_REQUIREMENTS = """
RÉPONSE STRICTEMENT AU FORMAT JSON :
Tu dois impérativement formater ta réponse finale sous la forme d'un objet JSON valide contenant EXACTEMENT ces clés :
{
  "facts": ["faits précis, vérifiés et appuyés par des sources"],
  "sources": ["sources ou documents appuyant chaque fait"],
  "hypotheses": ["hypothèses de travail"],
  "uncertainties": ["incertitudes, limites ou points ouverts"],
  "conclusion": "synthèse et conclusion claire et directe",
  "confidence": 0.95,
  "artifacts": []
}
Aucun texte en dehors du bloc JSON.
"""


def build_agentic_prompt(role: str, user_prompt: str) -> str:
    """Construit le prompt complet injectant le rôle et la contrainte de format JSON."""
    system_role = ROLE_SYSTEM_PROMPTS.get(role.lower(), ROLE_SYSTEM_PROMPTS["default"])
    return (
        f"{system_role}\n\n"
        f"Consigne utilisateur :\n{user_prompt}\n\n"
        f"{JSON_OUTPUT_REQUIREMENTS}"
    )


def build_l2_agentic_prompt(role: str, mission: str, context: str = "") -> str:
    """Construit le prompt pour un agent de palier L2 (faits, sources, hypothèses, incertitudes, conclusion)."""
    system_role = ROLE_SYSTEM_PROMPTS.get(role.lower(), ROLE_SYSTEM_PROMPTS["default"])
    prompt = f"{system_role}\n\nMission spécialisée :\n{mission}\n"
    if context:
        prompt += f"\nContexte général :\n{context}\n"
    prompt += f"\n{L2_JSON_OUTPUT_REQUIREMENTS}"
    return prompt


def build_json_retry_prompt(original_prompt: str, failed_output: str, issues: Optional[list] = None) -> str:
    """Construit un prompt de relance en cas d'absence ou d'invalidité du JSON requis."""
    issues_text = f"\nProblèmes identifiés :\n" + "\n".join(f"- {i}" for i in issues) if issues else ""
    return (
        f"ATTENTION : Ta réponse précédente ne respectait pas le format JSON obligatoire attendu.{issues_text}\n\n"
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


def build_l2_synthesis_prompt(goal: str, findings: list, contradictions: Optional[list] = None) -> str:
    """Construit le prompt pour l'étape REDUCE de synthèse finale L2."""
    import json
    contr_block = ""
    if contradictions:
        contr_block = f"\nPoints de contradiction ou d'attention relevés par le cross-check :\n" + "\n".join(f"- {c}" for c in contradictions) + "\n"

    return (
        f"{ROLE_SYSTEM_PROMPTS['synthesis']}\n\n"
        f"Objectif global de la mission :\n{goal}\n\n"
        f"Résultats consolidés des agents spécialisés :\n"
        f"{json.dumps(findings, ensure_ascii=False, indent=2)}\n"
        f"{contr_block}\n"
        f"Consigne de synthèse :\n"
        f"Rédige une conclusion limpide et structurée intégrant tous les faits vérifiés, "
        f"résolvant les incertitudes et formulant les recommandations concrètes.\n\n"
        f"{L2_JSON_OUTPUT_REQUIREMENTS}"
    )

