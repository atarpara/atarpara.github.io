#!/usr/bin/env python3
"""Convert $...$ inline math to \\(...\\) for kramdown compatibility.
Display math $$...$$ on own lines is left as-is (kramdown handles it fine with math_engine: null).
Code blocks and inline code are protected."""

import re, sys

path = sys.argv[1]
with open(path, 'r') as f:
    lines = f.readlines()

result = []
in_code_block = False
in_display_math = False

for line in lines:
    # Track code blocks
    if line.strip().startswith('```'):
        in_code_block = not in_code_block
        result.append(line)
        continue

    if in_code_block:
        result.append(line)
        continue

    # Track display math ($$  on own line)
    stripped = line.strip()
    if stripped == '$$':
        in_display_math = not in_display_math
        result.append(line)
        continue

    if in_display_math:
        result.append(line)
        continue

    # Skip lines that are display math ($$...$$ on single line)
    if stripped.startswith('$$') and stripped.endswith('$$') and len(stripped) > 4:
        result.append(line)
        continue

    # For remaining lines, convert inline $...$ to \(...\)
    # First protect inline code `...`
    codes = []
    def save_code(m):
        codes.append(m.group(0))
        return f'\x00CODE{len(codes)-1}\x00'

    processed = re.sub(r'`[^`]+`', save_code, line)

    # Convert $...$ (not $$) to \(...\)
    # Match $ followed by non-$ non-space, then content, then non-space non-$ followed by $
    processed = re.sub(
        r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)',
        lambda m: '\\\\(' + m.group(1) + '\\\\)',
        processed
    )

    # Restore inline code
    for i, code in enumerate(codes):
        processed = processed.replace(f'\x00CODE{i}\x00', code)

    result.append(processed)

with open(path, 'w') as f:
    f.writelines(result)

# Count changes
original = ''.join(lines)
converted = ''.join(result)
orig_count = len(re.findall(r'(?<!\$)\$(?!\$)', original))
new_count = converted.count('\\\\(')
print(f"Converted {new_count} inline math expressions from $ to \\\\(...\\\\)")
