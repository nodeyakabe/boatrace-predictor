
# ==================================================
# 新規パターン定義（pattern_scorer.py に追加）
# ==================================================

# 絶対値評価パターン（会場補正済みZ-score使用）
EXHIBITION_ABSOLUTE_PATTERNS = [
    {
        'name': 'ex_very_fast',
        'description': '展示タイム非常に速い（会場補正Z<-1.5）',
        'multiplier': 1.10,
        'target_rank': 1,
        'condition': lambda z_score: z_score < -1.5,
    },
    {
        'name': 'ex_fast',
        'description': '展示タイム速い（会場補正-1.5<Z<-1.0）',
        'multiplier': 1.05,
        'target_rank': 1,
        'condition': lambda z_score: -1.5 <= z_score < -1.0,
    },
    {
        'name': 'ex_slow',
        'description': '展示タイム遅い（会場補正Z>1.0）',
        'multiplier': 0.90,
        'target_rank': 1,
        'condition': lambda z_score: z_score > 1.0,
    },
]

# 相対差評価パターン
EXHIBITION_RELATIVE_PATTERNS = [
    {
        'name': 'ex1_dominate',
        'description': '展示1位独走（2位と0.2秒以上差）',
        'multiplier': 1.15,
        'target_rank': 1,
        'condition': lambda ex_rank, diff_1st_2nd: ex_rank == 1 and diff_1st_2nd >= 0.2,
    },
    {
        'name': 'ex1_dango',
        'description': '展示団子（1-3位差が0.05秒以内）',
        'multiplier': 0.95,
        'target_rank': 1,
        'condition': lambda ex_rank, diff_1st_3rd: diff_1st_3rd < 0.05,
    },
]

# ST × 展示複合パターン
ST_EXHIBITION_COMPOSITE_PATTERNS = [
    {
        'name': 'st1_ex4_6_mismatch',
        'description': 'ST1位 & 展示4-6位（ミスマッチ）',
        'multiplier': 1.05,
        'target_rank': 1,
        'condition': lambda st_rank, ex_rank: st_rank == 1 and ex_rank >= 4,
    },
    {
        'name': 'st4_6_ex1_mismatch',
        'description': 'ST4-6位 & 展示1位（ミスマッチ）',
        'multiplier': 0.95,
        'target_rank': 1,
        'condition': lambda st_rank, ex_rank: st_rank >= 4 and ex_rank == 1,
    },
    {
        'name': 'st1_2_ex1_2_double_top',
        'description': 'ST1-2位 & 展示1-2位（両方上位）',
        'multiplier': 1.20,
        'target_rank': 'top3',
        'condition': lambda st_rank, ex_rank: st_rank <= 2 and ex_rank <= 2,
    },
    {
        'name': 'st5_6_ex5_6_double_bottom',
        'description': 'ST5-6位 & 展示5-6位（両方下位）',
        'multiplier': 0.80,
        'target_rank': 'top3',
        'condition': lambda st_rank, ex_rank: st_rank >= 5 and ex_rank >= 5,
    },
]

# ==================================================
# 会場別展示タイム基準値（YAML設定用）
# ==================================================
VENUE_EXHIBITION_BASELINES = {
    # venue_code: {'mean': 平均, 'std': 標準偏差, 'weight': 重み調整}
    # weight: 1.0 = 標準, >1.0 = 展示重視, <1.0 = 展示軽視
}

# ==================================================
# Z-score計算ヘルパー関数
# ==================================================
def calculate_exhibition_zscore(exhibition_time: float, venue_code: str) -> float:
    """
    会場補正済みのZ-scoreを計算

    Args:
        exhibition_time: 展示タイム（秒）
        venue_code: 会場コード

    Returns:
        Z-score（負=速い、正=遅い）
    """
    baseline = VENUE_EXHIBITION_BASELINES.get(venue_code, {'mean': 6.80, 'std': 0.10})
    return (exhibition_time - baseline['mean']) / baseline['std']


def calculate_exhibition_diff(race_exhibition_times: dict) -> dict:
    """
    レース内の展示タイム差を計算

    Args:
        race_exhibition_times: {pit_number: exhibition_time} の辞書

    Returns:
        {'diff_1st_2nd': 差, 'diff_1st_3rd': 差, ...}
    """
    sorted_times = sorted(race_exhibition_times.values())
    if len(sorted_times) < 3:
        return {}

    return {
        'diff_1st_2nd': sorted_times[1] - sorted_times[0],
        'diff_1st_3rd': sorted_times[2] - sorted_times[0],
    }


def get_venue_exhibition_weight(venue_code: str) -> float:
    """
    会場別の展示タイム重み係数を取得

    Args:
        venue_code: 会場コード

    Returns:
        重み係数（1.0 = 標準）
    """
    baseline = VENUE_EXHIBITION_BASELINES.get(venue_code, {'weight': 1.0})
    return baseline.get('weight', 1.0)
