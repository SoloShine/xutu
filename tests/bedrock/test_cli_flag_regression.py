import json
import sys
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import create_volume, create_chapter
from src.bedrock.orchestration.review_flag import (
    mark_unresolved, mark_advisory_drift, get_review_flag, compute_has_flag, _upsert)
from src.bedrock.checks.beat_fulfillment import BeatViolation


def test_get_review_flag_cli_has_flag_output(tmp_project, capsys):
    """重构后 CLI get-review-flag 输出 JSON 仍含正确 has_flag。"""
    from src.bedrock.__main__ import main
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    mark_unresolved(conn, cid, [BeatViolation(beat_id=1, kind="unwritten_beat",
                                              detail="d", fix_hint="h")],
                    likely_rule_or_model_issue=False)
    conn.commit()
    conn.close()
    old = sys.argv
    sys.argv = ["bedrock", "get-review-flag", "--project", str(tmp_project), "--chapter", "1"]
    try:
        main()
    finally:
        sys.argv = old
    out = json.loads(capsys.readouterr().out)
    assert out["has_flag"] is True
    assert out["flag"]["l2_unresolved"] == 1


def _mk_chapter(tmp_project):
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    cid = create_chapter(conn, volume_id=vid, global_number=1, title="t")
    conn.commit()
    conn.close()
    return cid


def test_compute_has_flag_clean_advisory_drift_is_false(tmp_project):
    """clean style-drift ({drifted:[],ok:true}) 不应触发 has_flag。"""
    cid = _mk_chapter(tmp_project)
    conn = get_connection(tmp_project)
    mark_advisory_drift(conn, cid, {"target_source": "x", "drifted": [], "ok": True,
                                    "metrics": {}, "target": {}})
    conn.commit()
    flag = get_review_flag(conn, cid)
    conn.close()
    assert compute_has_flag(flag) is False


def test_compute_has_flag_drifted_advisory_drift_is_true(tmp_project):
    """有真实 drift 的 advisory_drift → has_flag True。"""
    cid = _mk_chapter(tmp_project)
    conn = get_connection(tmp_project)
    mark_advisory_drift(conn, cid, {"drifted": [{"metric": "sentiment", "delta": 0.9}],
                                    "ok": False})
    conn.commit()
    flag = get_review_flag(conn, cid)
    conn.close()
    assert compute_has_flag(flag) is True


def test_compute_has_flag_proper_noun_autoedit_is_true(tmp_project):
    """proper_noun_autoedit 非空 → has_flag True。"""
    cid = _mk_chapter(tmp_project)
    conn = get_connection(tmp_project)
    _upsert(conn, cid, {"advisory_drift": json.dumps(
        {"proper_noun_autoedit": [{"para_id": 1, "variant": "v", "canonical": "c"}]})})
    conn.commit()
    flag = get_review_flag(conn, cid)
    conn.close()
    assert compute_has_flag(flag) is True


def test_mark_advisory_drift_preserves_proper_noun_autoedit(tmp_project):
    """专名自动改先写、style-drift 后写 → 两键共存(读改合并不覆盖)。"""
    cid = _mk_chapter(tmp_project)
    conn = get_connection(tmp_project)
    # phase 4b2: 专名自动改先落
    _upsert(conn, cid, {"advisory_drift": json.dumps(
        {"proper_noun_autoedit": [{"para_id": 1, "variant": "v", "canonical": "c"}]})})
    # phase 5: finalize 的 mark-advisory-drift 后落
    mark_advisory_drift(conn, cid, {"drifted": [{"metric": "m", "delta": 0.5}], "ok": False})
    conn.commit()
    flag = get_review_flag(conn, cid)
    conn.close()
    blob = json.loads(flag["advisory_drift"])
    assert "proper_noun_autoedit" in blob  # 未被覆盖
    assert blob["proper_noun_autoedit"][0]["canonical"] == "c"
    assert "drifted" in blob
    assert blob["drifted"][0]["metric"] == "m"
    assert compute_has_flag(flag) is True


def test_check_proper_nouns_preserves_existing_style_drift(tmp_project):
    """_check_proper_nouns 写 proper_noun_autoedit 时保留既有 style-drift。"""
    cid = _mk_chapter(tmp_project)
    conn = get_connection(tmp_project)
    # 先有一个 style-drift 快照
    mark_advisory_drift(conn, cid, {"drifted": [{"metric": "m", "delta": 0.5}], "ok": False})
    conn.commit()
    # 模拟 _check_proper_nouns 的写法(读改合并)
    autoedit = [{"para_id": 1, "variant": "v", "canonical": "c"}]
    cur = conn.execute(
        "SELECT advisory_drift FROM chapter_review_flag WHERE chapter_id=?",
        (cid,)).fetchone()
    drift = json.loads(cur["advisory_drift"]) if cur and cur["advisory_drift"] != "{}" else {}
    drift["proper_noun_autoedit"] = autoedit
    _upsert(conn, cid, {"advisory_drift": json.dumps(drift, ensure_ascii=False)})
    conn.commit()
    flag = get_review_flag(conn, cid)
    conn.close()
    blob = json.loads(flag["advisory_drift"])
    assert "drifted" in blob and blob["drifted"][0]["metric"] == "m"
    assert "proper_noun_autoedit" in blob
