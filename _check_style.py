# -*- coding: utf-8 -*-
import re

with open('D:/novel_test/projects/juedi_tiantong_v1/output/ch83_generated.txt', 'r', encoding='utf-8') as f:
    text = f.read()

hanzi = sum(1 for c in text if '一' <= c <= '鿿')
periods = text.count('。')
dashes = text.count('——')

results = []
results.append(f'汉字数: {hanzi}')
results.append(f'句号数: {periods}')
results.append(f'句号密度: {periods/(hanzi/1000):.1f}/千字')
results.append(f'破折号数: {dashes}')
results.append(f'破折号密度: {dashes/(hanzi/1000):.1f}/千字')

# 否定转折句式「不是X，是Y」
patterns = re.findall(r'不是.{1,20}[，,]是', text)
results.append(f'否定转折句式: {len(patterns)}处')
for p in patterns:
    results.append(f'  - {p}')

# 也检查单独的「不是」用法（包括句末的"不是修辞"等）
all_bushi = [(m.start(), text[max(0,m.start()-10):m.end()+20]) for m in re.finditer(r'不是', text)]
results.append(f'所有"不是"出现: {len(all_bushi)}处')
for pos, ctx in all_bushi:
    results.append(f'  @pos {pos}: ...{ctx}...')

# 禁止词
forbidden = ['恐怖的', '阴森的', '诡异的']
for w in forbidden:
    cnt = text.count(w)
    if cnt > 0:
        results.append(f'禁止词「{w}」: {cnt}处')

# 突然/忽然
for w in ['突然', '忽然']:
    cnt = text.count(w)
    if cnt > 0:
        results.append(f'「{w}」: {cnt}处')

# 对话标签（可替换的 他说/她问/他道）
dialog_tags = re.findall(r'[“”][，,]?(?:他|她|林深|银灰制服|深蓝长袍|女古神|偏瘦古神)(?:说|道|问|答|喊|叫|嚷)', text)
results.append(f'对话标签(可替换): {len(dialog_tags)}处')
for t in dialog_tags:
    results.append(f'  - {t}')

# 检查长段落（超过6句）
paragraphs = text.split('\n\n')
for i, p in enumerate(paragraphs):
    sents = p.count('。') + p.count('”')
    if sents > 6 and len(p) > 50:
        preview = p[:80].replace('\n', ' ')
        results.append(f'长段落(约{sents}句): 第{i+1}段 - {preview}...')

with open('D:/novel_test/_style_report.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
print('Done')
