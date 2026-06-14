import json
import sys
from src.bedrock.db.connection import get_connection
from src.bedrock.repositories.plot_tree import create_volume, create_chapter
from src.bedrock.orchestration.review_flag import mark_unresolved
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
