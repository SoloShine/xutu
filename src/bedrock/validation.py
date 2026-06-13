# src/bedrock/validation.py
import sqlite3


class ValidationError(Exception):
    pass


_PRONOUN_GENDER = {
    "他": {"男"},
    "她": {"女"},
    "它": {"无", "未知", "其他"},
    "祂": {"无", "未知", "其他"},
    "TA": {"男", "女", "无", "未知", "其他"},
}


def validate_pronoun_gender_consistency(conn):
    """gender 非 null 时，必须与 pronoun 语义一致。gender=未知 豁免。"""
    rows = conn.execute(
        "SELECT id, name, pronoun, gender FROM character WHERE gender IS NOT NULL AND gender != '未知'"
    ).fetchall()
    for r in rows:
        allowed = _PRONOUN_GENDER.get(r["pronoun"], set())
        if r["gender"] not in allowed:
            raise ValidationError(
                f"character {r['name']}(id={r['id']}): pronoun={r['pronoun']} 与 gender={r['gender']} 不一致")


def detect_cycle(conn, entity):
    """检测 faction/location 的 parent 自引用环。"""
    table = entity
    col = f"parent_{entity}_id"
    rows = conn.execute(f"SELECT id, {col} FROM {table}").fetchall()
    parent_of = {r["id"]: r[col] for r in rows}
    for start in parent_of:
        seen = set()
        cur = start
        while cur is not None:
            if cur in seen:
                raise ValidationError(f"{entity} 出现环：起点 id={start}")
            seen.add(cur)
            cur = parent_of.get(cur)


def validate_resolved_thread_consistency(conn):
    """resolved 状态必须有 resolved_at_beat（触发器兜底，这里二次校验）。"""
    rows = conn.execute(
        "SELECT id FROM suspense_thread WHERE status='resolved' AND resolved_at_beat IS NULL"
    ).fetchall()
    if rows:
        raise ValidationError(f"{len(rows)} 条悬链 status=resolved 但缺 resolved_at_beat")


def validate_all(conn):
    """跑全部跨字段校验，返回问题列表（不抛异常，便于聚合报告）。"""
    issues = []
    for fn in (validate_pronoun_gender_consistency,):
        try:
            fn(conn)
        except ValidationError as e:
            issues.append(str(e))
    try:
        detect_cycle(conn, "faction")
    except ValidationError as e:
        issues.append(str(e))
    try:
        detect_cycle(conn, "location")
    except ValidationError as e:
        issues.append(str(e))
    try:
        validate_resolved_thread_consistency(conn)
    except ValidationError as e:
        issues.append(str(e))
    return issues
