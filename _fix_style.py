# -*- coding: utf-8 -*-
"""Fix em-dash and period density in 5 chapter files.
Run: python _fix_style.py
"""
import re

def analyze(text):
    parts = text.split('参考来源：')  # 参考来源：
    body = parts[0]
    body_chars = len(re.findall(r'[一-鿿]', body))
    body_periods = body.count('。')
    body_dashes = body.count('——')
    pd = body_periods / body_chars * 1000 if body_chars else 0
    dd = body_dashes / body_chars * 1000 if body_chars else 0
    return pd, dd, body_chars, body_periods, body_dashes

def apply_replacements(text, replacements, label):
    warnings = []
    for old, new in replacements:
        if old not in text:
            warnings.append(f"  WARNING [{label}]: not found: {old[:60]}...")
        else:
            count = text.count(old)
            if count > 1:
                warnings.append(f"  NOTE [{label}]: {count} occurrences: {old[:60]}...")
            text = text.replace(old, new, 1)
    for w in warnings:
        print(w)
    return text

base = 'D:/novel_test/projects/juedi_tiantong_v1/output'

# ============================================================
# CH08
# ============================================================
print("=== CH08 ===")
with open(f'{base}/ch08_generated.txt', 'r', encoding='utf-8') as f:
    text = f.read()
pd, dd, chars, periods, dashes = analyze(text)
print(f"  Before: {periods} periods ({pd:.1f}/千), {dashes} dashes ({dd:.1f}/千), {chars} chars")

fixes = [
    # --- em-dash removals ---
    ('然后推了一下门——门没锁，',
     '然后推了一下门，门没锁，'),
    ('有误——比对过原始档案。',
     '有误，比对过原始档案。'),
    ('林深把第一块石片——刻着两道交叉弧线的那块——推到',
     '林深把第一块石片，刻着两道交叉弧线的那块，推到'),
    ('放在桌上——《古文字诂林》第三册，',
     '放在桌上，《古文字诂林》第三册，'),
    ('近现代人刻的还是——"',
     '近现代人刻的还是……"'),
    ('出土报告中——要么',
     '出土报告中，要么'),
    ('分量比林深预想的重——你找过',
     '分量比林深预想的重，你找过'),
    ('苏然——被导师驳回的研究生，',
     '苏然，被导师驳回的研究生，'),
    ('一行字——明天联系苏然。',
     '一行字：明天联系苏然。'),
]

text = apply_replacements(text, fixes, 'ch08-dash')

# Period density fixes for ch08
fixes2 = [
    ('门牌号的字迹锈蚀得只剩下模糊的轮廓。林深按了门铃没有听到里面响，',
     '门牌号的字迹锈蚀得只剩下模糊的轮廓，林深按了门铃没有听到里面响，'),
    ('方正则坐在桌后面穿着深灰色开衫毛衣和白衬衫，眼镜换了一副金属细框的反光更明显。',
     '方正则坐在桌后面穿着深灰色开衫毛衣和白衬衫，眼镜换了一副金属细框的，反光更明显。'),
    # Merge dialogue fragments: "一个朋友，"他停了一下。"已经不在了。"
    ('“一个朋友，”他停了一下。“已经不在了。”林深没有追问，方正则把眼镜重新戴上看着桌面上的影印件，',
     '“一个朋友，”他停了一下，“已经不在了。”林深没有追问，方正则把眼镜重新戴上，看着桌面上的影印件，'),
    # "你认真想想。"林深想了十秒钟。" -> comma
    ('“你认真想想。”林深想了十秒钟。“第一种是运气问题，',
     '“你认真想想。”林深想了十秒钟，“第一种是运气问题，'),
    # "你觉得呢？"林深没有回答，他知道... -> comma
    ('方正则看着他沉默了大概五秒钟。“你觉得呢？”',
     '方正则看着他，沉默了大概五秒钟，“你觉得呢？”'),
    # Fix ***。-> ***\n\n
    ('***。林深等着他说下去，',
     '***\n\n林深等着他说下去，'),
]

text = apply_replacements(text, fixes2, 'ch08-period')

pd, dd, chars, periods, dashes = analyze(text)
print(f"  After:  {periods} periods ({pd:.1f}/千), {dashes} dashes ({dd:.1f}/千), {chars} chars")
with open(f'{base}/ch08_generated.txt', 'w', encoding='utf-8') as f:
    f.write(text)
print("  Written.")

# ============================================================
# CH25
# ============================================================
print("\n=== CH25 ===")
with open(f'{base}/ch25_generated.txt', 'r', encoding='utf-8') as f:
    text = f.read()
pd, dd, chars, periods, dashes = analyze(text)
print(f"  Before: {periods} periods ({pd:.1f}/千), {dashes} dashes ({dd:.1f}/千), {chars} chars")

fixes = [
    ('不是茫然的那种扫——林深见过灰蓝人茫然的样子，',
     '不是茫然的那种扫，林深见过灰蓝人茫然的样子，'),
    ('不是温度，不是气味——声音，下雨的声音',
     '不是温度，不是气味：声音，下雨的声音'),
    ('一道旧伤疤，和搬运无关——搬运留下的茧',
     '一道旧伤疤，和搬运无关，搬运留下的茧'),
    ('最关键的一个细节——掌心的共振。',
     '最关键的一个细节：掌心的共振。'),
    ('掌心的疤痕——\n\n如果穿越',
     '掌心的疤痕。\n\n如果穿越'),
    ('标记——\n\n那这就不只是',
     '标记。\n\n那这就不只是'),
    ('已经结束了——一次精确',
     '已经结束了，一次精确'),
    # Merge numbered layers (remove \n\n between them)
    ('第一层：说话的人知道“雨”是什么，在一个没有雨的世界里，这意味着他来自一个有雨的地方。\n\n第二层：他用的是“你”，说明他知道林深也知道“雨”，他不是在解释一个概念，而是在唤醒一段记忆。\n\n第三层：他用了“记得”，说明这件事发生在过去，雨是过去的事，他们共同的过去。\n\n第四层：他问的是“声音”，不是形状，不是温度，不是气味：声音，下雨的声音是人类最底层的感官记忆之一，没有人能伪造对雨声的记忆。',
     '第一层：说话的人知道“雨”是什么，在一个没有雨的世界里，这意味着他来自一个有雨的地方。第二层：他用的是“你”，说明他知道林深也知道“雨”，他不是在解释一个概念，而是在唤醒一段记忆。第三层：他用了“记得”，说明这件事发生在过去，雨是过去的事，他们共同的过去。第四层：他问的是“声音”，不是形状，不是温度，不是气味：声音，下雨的声音是人类最底层的感官记忆之一，没有人能伪造对雨声的记忆。'),
]

text = apply_replacements(text, fixes, 'ch25')
pd, dd, chars, periods, dashes = analyze(text)
print(f"  After:  {periods} periods ({pd:.1f}/千), {dashes} dashes ({dd:.1f}/千), {chars} chars")
with open(f'{base}/ch25_generated.txt', 'w', encoding='utf-8') as f:
    f.write(text)
print("  Written.")

print("\nDone. Run again with 'part2' for ch32, ch36, ch51.")
