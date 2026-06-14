from src.bedrock.db.connection import get_connection
from src.bedrock.orchestration.cross_volume_gate import check_cross_volume_debt, CrossVolumeDebtReport
from src.bedrock.repositories.plot_tree import create_volume


def _plant_thread(conn, tid, planned_resolve_volume_number, status, importance="high"):
    """planned_resolve_volume 用卷 number（非 id）。
    resolved 需 resolved_at_beat（schema trigger），故先备好 beat 供引用。"""
    resolved_at = None
    if status == "resolved":
        beat_row = conn.execute("SELECT id FROM beat LIMIT 1").fetchone()
        if beat_row is None:
            ch = conn.execute(
                "SELECT id FROM chapter LIMIT 1").fetchone()
            ch_id = ch["id"] if ch else conn.execute(
                "INSERT INTO chapter(volume_id,global_number,title,status) VALUES(?,?,?,?)",
                (1, 999, "seed", "planned")).lastrowid
            resolved_at = conn.execute(
                "INSERT INTO beat(chapter_id,sequence,purpose,status) VALUES(?,?,?,?)",
                (ch_id, 1, "seed-purpose-min-len", "planned")).lastrowid
        else:
            resolved_at = beat_row["id"]
    conn.execute(
        "INSERT INTO suspense_thread(id,content,thread_type,importance,origin,status,"
        "planned_resolve_volume,resolved_at_beat) VALUES(?,?,?,?,?,?,?,?)",
        (tid, "c", "mystery", importance, "scheduled", status,
         planned_resolve_volume_number, resolved_at))
    conn.commit()


def test_no_debt_when_all_resolved(tmp_project):
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")  # number=1
    _plant_thread(conn, 1, 1, "resolved")
    _plant_thread(conn, 2, 1, "abandoned")
    report = check_cross_volume_debt(conn, vid)
    assert report.blocking is False
    assert len(report.unresolved_threads) == 0
    conn.close()


def test_debt_blocks_when_unresolved_high(tmp_project):
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    _plant_thread(conn, 1, 1, "resolved")
    _plant_thread(conn, 2, 1, "developing", importance="high")
    _plant_thread(conn, 3, 1, "planted", importance="high")
    report = check_cross_volume_debt(conn, vid)
    assert report.blocking is True
    assert len(report.unresolved_threads) == 2
    conn.close()


def test_medium_importance_does_not_block(tmp_project):
    """仅 high BLOCKING；medium/low 未兑现不阻断（与 SP2 单一真相）。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")
    _plant_thread(conn, 1, 1, "developing", importance="medium")
    _plant_thread(conn, 2, 1, "planted", importance="low")
    report = check_cross_volume_debt(conn, vid)
    assert report.blocking is False
    assert len(report.unresolved_threads) == 0
    conn.close()


def test_leq_catches_earlier_volume_debt(tmp_project):
    """<= 累积：planned_resolve_volume < 本卷 number 的 high 未兑现也捕获。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 5, "v", 1, 3, "opening")  # number=5
    _plant_thread(conn, 1, 3, "developing", importance="high")
    _plant_thread(conn, 2, 5, "resolved")
    report = check_cross_volume_debt(conn, vid)
    assert report.blocking is True
    assert len(report.unresolved_threads) == 1
    conn.close()


def test_ignores_future_volumes(tmp_project):
    """planned_resolve_volume > 本卷 number 不算本卷欠债。"""
    conn = get_connection(tmp_project)
    vid = create_volume(conn, 1, "v", 1, 3, "opening")  # number=1
    _plant_thread(conn, 1, 1, "developing", importance="high")
    _plant_thread(conn, 2, 2, "developing", importance="high")
    report = check_cross_volume_debt(conn, vid)
    assert report.blocking is True
    assert len(report.unresolved_threads) == 1
    conn.close()


def test_uses_volume_number_not_id(tmp_project):
    """回归：volume.id != volume.number 时，比较器必须用 number（非 autoincrement id）。
    构造 id≠number：先建卷 number=2（id=1），再建 number=1（id=2）。查 number=1 的卷
    （其 id=2）：一条 planned_resolve_volume=2 的 high 未兑现悬链——按 number 比较 2<=1
    为假（不阻断）；若错用 id 比较 2<=2 为真（会误阻断）。锁 SP5 用 number。"""
    conn = get_connection(tmp_project)
    create_volume(conn, 2, "v2", 4, 6, "opening")        # number=2, id=1
    vid_num1 = create_volume(conn, 1, "v1", 1, 3, "opening")  # number=1, id=2
    assert vid_num1 != 1   # 确认 id≠number（id=2, number=1）
    _plant_thread(conn, 1, 2, "developing", importance="high")  # planned_resolve_volume=2
    report = check_cross_volume_debt(conn, vid_num1)     # 本卷 number=1
    # 2 <= 1 为假 → 不阻断（若错用 id=2 比较：2<=2 真 → 误阻断，此测试会失败）
    assert report.blocking is False
    assert len(report.unresolved_threads) == 0
    conn.close()
