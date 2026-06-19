# tests/bedrock/test_review_flag.py
from src.bedrock.db.connection import get_connection
from src.bedrock.orchestration.review_flag import (
    mark_unresolved, mark_polish_broke_beat, mark_forced_persist_failed,
    mark_advisory_drift, get_review_flag, compute_has_flag,
)
from src.bedrock.checks.beat_fulfillment import BeatViolation
from src.bedrock.repositories.plot_tree import create_volume, create_chapter


def _seed(conn):
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    return vid, cid


def test_mark_unresolved(tmp_project):
    conn = get_connection(tmp_project)
    _, cid = _seed(conn)
    viols = [BeatViolation(beat_id=1, kind="missing_character", detail="林深未出场", fix_hint="加林深")]
    mark_unresolved(conn, cid, viols, likely_rule_or_model_issue=True)
    flag = get_review_flag(conn, cid)
    assert flag["l2_unresolved"] == 1
    assert flag["likely_rule_or_model_issue"] == 1
    import json
    pv = json.loads(flag["persisted_violations"])
    assert len(pv) == 1
    assert pv[0]["kind"] == "missing_character"
    conn.close()


def test_mark_polish_broke_beat(tmp_project):
    conn = get_connection(tmp_project)
    _, cid = _seed(conn)
    mark_polish_broke_beat(conn, cid)
    assert get_review_flag(conn, cid)["polish_broke_beat"] == 1
    conn.close()


def test_mark_forced_persist_failed(tmp_project):
    conn = get_connection(tmp_project)
    _, cid = _seed(conn)
    mark_forced_persist_failed(conn, cid)
    assert get_review_flag(conn, cid)["forced_persist_failed"] == 1
    conn.close()


def test_get_review_flag_none_when_absent(tmp_project):
    conn = get_connection(tmp_project)
    _, cid = _seed(conn)
    assert get_review_flag(conn, cid) is None
    conn.close()


def test_upsert_preserves_prior_flags(tmp_project):
    """多个 mark 调用应叠加，而非覆盖既有列。"""
    conn = get_connection(tmp_project)
    _, cid = _seed(conn)
    viols = [BeatViolation(beat_id=1, kind="missing_character", detail="d", fix_hint="f")]
    mark_unresolved(conn, cid, viols, likely_rule_or_model_issue=True)
    mark_polish_broke_beat(conn, cid)
    mark_forced_persist_failed(conn, cid)
    flag = get_review_flag(conn, cid)
    assert flag["l2_unresolved"] == 1
    assert flag["likely_rule_or_model_issue"] == 1
    assert flag["polish_broke_beat"] == 1
    assert flag["forced_persist_failed"] == 1
    conn.close()


def test_mark_advisory_drift_persists(tmp_project):
    """advisory_drift 落库（SP5 VolumeReview 读）。"""
    conn = get_connection(tmp_project)
    _, cid = _seed(conn)
    drift = {"word_count": {"declared": 9999, "recomputed": 10, "drifted": True}}
    mark_advisory_drift(conn, cid, drift)
    flag = get_review_flag(conn, cid)
    import json as _json
    persisted = _json.loads(flag["advisory_drift"])
    assert persisted["word_count"]["drifted"] is True
    assert persisted["word_count"]["declared"] == 9999
    conn.close()


def test_compute_has_flag_none():
    assert compute_has_flag(None) is False


def test_compute_has_flag_l2_unresolved():
    assert compute_has_flag({"l2_unresolved": 1, "polish_broke_beat": 0,
                             "forced_persist_failed": 0, "advisory_drift": "{}"}) is True


def test_compute_has_flag_advisory_empty():
    assert compute_has_flag({"l2_unresolved": 0, "polish_broke_beat": 0,
                             "forced_persist_failed": 0, "advisory_drift": "{}"}) is False


def test_compute_has_flag_advisory_nonempty():
    """有真实 drifted 内容的 advisory_drift → has_flag True。
    语义判空:仅 drifted/proper_noun_autoedit 非空才算 flag,
    纯指标快照(如 {"dash_count":99})不再触发(原字符串比对的 bug 修复)。"""
    assert compute_has_flag({"l2_unresolved": 0, "polish_broke_beat": 0,
                             "forced_persist_failed": 0,
                             "advisory_drift": '{"drifted":[{"metric":"m","delta":0.9}],"ok":false}'}) is True
    # 无 drifted/proper_noun_autoedit 的指标快照 → False
    assert compute_has_flag({"l2_unresolved": 0, "polish_broke_beat": 0,
                             "forced_persist_failed": 0,
                             "advisory_drift": '{"dash_count": 99}'}) is False


def test_compute_has_flag_likely_rule_or_model_not_counted():
    """likely_rule_or_model_issue 单独不计入（l2_unresolved 诊断子字段）。"""
    assert compute_has_flag({"l2_unresolved": 0, "polish_broke_beat": 0,
                             "forced_persist_failed": 0, "advisory_drift": "{}",
                             "likely_rule_or_model_issue": 1}) is False
