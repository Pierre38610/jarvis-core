"""Fix system_instruction string concatenation to use + operator instead of implicit concat with variable."""
import os

TARGET = os.path.join(os.path.dirname(__file__), "services", "slides_service.py")

with open(TARGET, encoding="utf-8") as f:
    lines = f.readlines()

# Find the system_instruction = ( line
for i, l in enumerate(lines):
    if 'system_instruction = (' in l:
        assign_start = i
        break
else:
    raise ValueError("system_instruction not found")

# Find the closing ) of the tuple
depth = 0
assign_end = None
for i in range(assign_start, len(lines)):
    for ch in lines[i]:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                assign_end = i
                break
    if assign_end is not None:
        break

print(f"system_instruction: lines {assign_start+1}..{assign_end+1}")

# Extract the block
block = lines[assign_start:assign_end+1]
block_str = ''.join(block)
print("Block preview:", block_str[:200])

# Replace: change from parenthesized implicit concat to explicit +
# Strategy: replace the whole block with equivalent using +
# Find the _metrics_rule line inside
for j, l in enumerate(block):
    if '_metrics_rule' in l and not ('_metrics_rule =' in l):
        metrics_line_in_block = j
        break
else:
    raise ValueError("_metrics_rule usage not found in block")

print(f"_metrics_rule usage is at block-relative line {metrics_line_in_block}")

# Build new block: replace ) with + _metrics_rule +, then continue
# Simplest: change the line with _metrics_rule to be + _metrics_rule +
# and add + at end of previous string literal

new_block = []
for j, l in enumerate(block):
    stripped = l.rstrip('\n\r')
    if j == metrics_line_in_block:
        # Replace with + _metrics_rule concatenation
        new_block.append('                        + _metrics_rule\n')
    elif j == metrics_line_in_block - 1:
        # Previous line is a string literal — need to close + before _metrics_rule
        # It already ends with \\n" — just keep as is; the + will concatenate
        new_block.append(l)
    else:
        new_block.append(l)

# Also: after the last string literal before _metrics_rule, we need to convert all
# implicit string concatenations to use +
# Actually, the cleanest fix is just to use one big f-string with .format or join
# Let's use a different approach: build system_instruction as a list and join

# NEW APPROACH: replace entire block with a simple join of parts list
indent = '                    '
new_instruction = f"""{indent}system_instruction = (
{indent}    "Tu es l'architecte de presentations Google Slides de J.A.R.V.I.S.\\n"
{indent}    "Tu concois un deck structure, esthetique, informatif et percutant.\\n\\n"
{indent}    "REGLES IMPERATIVES DE CONCEPTION :\\n"
{indent}    f"1. NOMBRE DE SLIDES : Produis EXACTEMENT {{target_count}} diapositives dans la liste 'slides'.\\n"
{indent}    "2. VARIETE DES LAYOUTS : Alterne dynamiquement entre les layouts :\\n"
{indent}    "   - hero_title, bullets_simple, cards_grid, split_compare, timeline_steps,\\n"
{indent}    "   - image_plus_text, table_data, section_divider, quote_highlight,\\n"
{indent}    "   - conclusion_call_to_action.\\n"
{indent}    "   - key_metrics : UNIQUEMENT SI LE SUJET COMPORTE DES CHIFFRES VERIFIES.\\n"
{indent}    + _metrics_rule
{indent}    + "4. CONTENU CONCRET SANS PLACEHOLDER : phrases riches, precises, informatives.\\n"
{indent}    + f"5. LANGUE : {{langue}}.\\n"
{indent}    + f"6. THEME ET TON : Ton {{ton or 'corporate'}} (theme '{{theme_key}}').\\n"
{indent}    + "7. FORMAT DE SORTIE : Renvoie UNIQUEMENT un JSON valide conforme au schema."
{indent})
"""

# Rebuild file lines
new_lines = lines[:assign_start] + [new_instruction] + lines[assign_end+1:]

with open(TARGET, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("OK — system_instruction rebuilt with explicit + concatenation")
