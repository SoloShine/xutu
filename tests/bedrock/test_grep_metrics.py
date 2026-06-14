from src.bedrock.checks.grep_metrics import compute_grep_metrics


def test_empty_returns_zeros():
    m = compute_grep_metrics([])
    assert m == {"notXisY_per_kchar": 0.0, "dash_per_kchar": 0.0, "period_density": 0.0}


def test_notXisY_counted():
    m = compute_grep_metrics(["不是因为他累，是因为他想家。不是因为天黑，是因为下雨。"])
    assert m["notXisY_per_kchar"] > 0


def test_dash_counted():
    m = compute_grep_metrics(["一段——带破折号——的文字。"])
    assert m["dash_per_kchar"] > 0


def test_period_density():
    m = compute_grep_metrics(["他来了。她走了。天黑了。"])
    assert 0 < m["period_density"] < 1


def test_no_chinese_zero_density():
    m = compute_grep_metrics(["abc 123"])
    assert m["notXisY_per_kchar"] == 0.0
    assert m["dash_per_kchar"] == 0.0
    assert m["period_density"] == 0.0
