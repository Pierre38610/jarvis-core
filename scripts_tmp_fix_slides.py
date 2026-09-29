"""Fix SyntaxError on line 511 of services/slides_service.py."""
import os

TARGET = os.path.join(os.path.dirname(__file__), "services", "slides_service.py")

with open(TARGET, encoding="utf-8") as f:
    lines = f.readlines()

# Line 511 is index 510 (0-based)
idx = 510
# New line: use a conditional expression separated from f-string to avoid backslash-in-fstring
replacement = (
    '                        ("3. REGLE METRIQUES : Le sujet permet les chiffres, tu peux inclure 1 slide key_metrics.\\n"\n'
    '                         if has_metrics_relevance else\n'
    '                         "3. REGLE METRIQUES : INTERDICTION STRICTE d\'inserer un layout key_metrics ou d\'inventer des chiffres arbitraires.\\n")\n'
)

lines[idx] = replacement

with open(TARGET, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("OK — line 511 fixed")
