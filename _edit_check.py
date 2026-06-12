#!/usr/bin/env python3
"""Edit check script for ch155"""
import re

with open('projects/juedi_tiantong_v1/output/ch155_generated.txt', 'r', encoding='utf-8') as f:
    text = f.read()

# Split body from reference
parts = text.split('参考来源：')
body = parts[0]

# Count Chinese characters
chinese_chars = len(re.findall(r'[一-鿿]', body))
print(f'Chinese characters (body): {chinese_chars}')

# Check banned words
banned = ['恐怖', '阴森', '诡异', '突然', '忽然']
for word in banned:
    for m in re.finditer(word, body):
        start = max(0, m.start()-5)
        end = min(len(body), m.end()+5)
        context = body[start:end].replace('\n', ' ')
        print(f'BANNED "{word}" at pos {m.start()}: ...{context}...')

# Count negation patterns - look at every line with 不是
print("\n=== ALL '不是' occurrences ===")
for i, line in enumerate(body.split('\n'), 1):
    if '不是' in line:
        print(f"L{i}: {line.strip()[:120]}")

# Count em dashes with context
print(f"\n=== ALL '——' occurrences ({body.count('——')} total) ===")
for i, line in enumerate(body.split('\n'), 1):
    if '——' in line:
        print(f"L{i}: {line.strip()[:120]}")

# Count periods
period_count = body.count('。')
print(f'\nPeriods (。): {period_count}')
period_per_1k = period_count / (chinese_chars / 1000)
print(f'Periods per 1000 chars: {period_per_1k:.1f}')

# Check paragraph lengths (by sentence count)
print("\n=== Paragraph analysis ===")
for i, para in enumerate(body.strip().split('\n'), 1):
    para = para.strip()
    if not para:
        continue
    sentences = para.count('。')
    if sentences >= 5:
        print(f"Para L{i} ({sentences} sentences): {para[:100]}...")

# Check dialogue density - consecutive dialogue lines
lines = body.split('\n')
print("\n=== Consecutive dialogue check ===")
consecutive_dialogue = 0
for i, line in enumerate(lines):
    stripped = line.strip()
    is_dialogue = stripped.startswith('"') or stripped.startswith('"')
    if is_dialogue:
        consecutive_dialogue += 1
    else:
        if consecutive_dialogue >= 3:
            print(f"  {consecutive_dialogue} consecutive dialogue lines ending before L{i+1}")
        consecutive_dialogue = 0

# Find sentences that could be merged (short sentences)
print("\n=== Short sentences (potential merge candidates) ===")
# Split by periods and find very short sentences
all_sentences = re.split(r'[。]', body)
for i, sent in enumerate(all_sentences):
    chars = len(re.findall(r'[一-鿿]', sent))
    if 2 <= chars <= 8:
        print(f"  [{chars} chars]: {sent.strip()[:60]}")
