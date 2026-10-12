"""Fix SyntaxError on lines 511-514 of services/slides_service.py — ternary inside implicit string concat."""
import os

TARGET = os.path.join(os.path.dirname(__file__), "services", "slides_service.py")

with open(TARGET, encoding="utf-8") as f:
    content = f.read()

OLD = (
    '                        (\"3. REGLE METRIQUES : Le sujet permet les chiffres, tu peux inclure 1 slide key_metrics.\\n\"\n'
    '                         if has_metrics_relevance else\n'
    '                         \"3. REGLE METRIQUES : INTERDICTION STRICTE d\'inserer un layout key_metrics ou d\'inventer des chiffres arbitraires.\\n\")\n'
    '                        \"4. CONTENU CONCRET ET SANS PLACEHOLDER : R'
)

# Just find and replace the ternary block in lines 511-513
lines = content.split('\n')

# Find the target lines
for i, l in enumerate(lines):
    if '3. REGLE METRIQUES' in l and 'permet les chiffres' in l:
        start = i
        break
else:
    print("TARGET NOT FOUND — dumping nearby lines:")
    for i2, l2 in enumerate(lines[508:516], 509):
        print(f"{i2}: {repr(l2)}")
    raise SystemExit(1)

print(f"Found ternary at line {start+1}: {repr(lines[start])}")

# Replace lines start, start+1, start+2 with a variable assignment just before the string
# We'll insert the variable before system_instruction and use it inline
# Since it's inside a tuple concatenation we need to assign before
# Strategy: extract ternary to variable, replace with simple string ref

# Find the line with 'system_instruction = ('
for j in range(start, -1, -1):
    if 'system_instruction = (' in lines[j]:
        assign_line = j
        break
else:
    print("Could not find 'system_instruction = (' above")
    raise SystemExit(1)

print(f"system_instruction starts at line {assign_line+1}")

# Insert variable before system_instruction
indent = '                    '  # same indent as system_instruction
var_line = (
    f"{indent}_metrics_rule = (\n"
    f"{indent}    \"3. REGLE METRIQUES : Le sujet permet les chiffres, tu peux inclure 1 slide key_metrics.\\n\"\n"
    f"{indent}    if has_metrics_relevance else\n"
    f"{indent}    \"3. REGLE METRIQUES : INTERDICTION STRICTE d'inserer un layout key_metrics ou d'inventer des chiffres arbitraires.\\n\"\n"
    f"{indent})\n"
)

# Now build replacement for lines[start], [start+1], [start+2]
# These should become a simple string ref
replacement_middle = f"                        _metrics_rule\n"

# Build new lines list
new_lines = []
for i, l in enumerate(lines):
    if i == assign_line:
        new_lines.append(var_line)
        new_lines.append(l)
    elif i == start:
        new_lines.append(replacement_middle)
    elif i == start + 1 or i == start + 2:
        pass  # skip the ternary continuation lines
    else:
        new_lines.append(l)

with open(TARGET, 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))

print("OK — fixed")
