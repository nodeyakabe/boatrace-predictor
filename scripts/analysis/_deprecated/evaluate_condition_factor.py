"""
選手調子係数の効果測定

P-2タスク: 直近20走の調子係数が予測精度に与える影響を検証
"""

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis.extended_scorer import ExtendedScorer

DATABASE_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"


def get_test_races(start_date: str, end_date: str, limit: int = 1000):
    """テスト用レースデータを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
    SELECT DISTINCT r.id as race_id, r.race_date, r.venue_code
    FROM races r
    JOIN results res ON r.id = res.race_id
    WHERE r.race_date BETWEEN ? AND ?
      AND res.rank = 1
    ORDER BY r.race_date
    LIMIT ?
    """

    cursor.execute(query, (start_date, end_date, limit))
    races = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return races


def get_race_entries_and_result(race_id: int):
    """レースの出走情報と結果を取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # エントリー情報
    cursor.execute("""
        SELECT e.pit_number, e.racer_number, e.racer_rank
        FROM entries e
        WHERE e.race_id = ?
        ORDER BY e.pit_number
    """, (race_id,))
    entries = [dict(row) for row in cursor.fetchall()]

    # 1着結果
    cursor.execute("""
        SELECT pit_number
        FROM results
        WHERE race_id = ? AND rank = 1
    """, (race_id,))
    result = cursor.fetchone()
    winner_pit = result['pit_number'] if result else None

    conn.close()
    return entries, winner_pit


def evaluate_condition_factor_effect():
    """調子係数の効果を測定"""
    scorer = ExtendedScorer()

    # 2025年データで検証
    start_date = "2025-06-01"
    end_date = "2025-11-30"

    print(f"検証期間: {start_date} ~ {end_date}")
    print("テストレースを取得中...")

    races = get_test_races(start_date, end_date, limit=1000)
    print(f"取得レース数: {len(races)}")

    # 結果集計
    results = {
        'total': 0,
        'baseline_hit': 0,      # 級別のみで予測
        'with_factor_hit': 0,   # 調子係数適用で予測
    }

    # トレンド別の集計
    trend_stats = defaultdict(lambda: {'total': 0, 'hit': 0})

    print("\n評価中...")
    for i, race in enumerate(races):
        if i % 100 == 0:
            print(f"  処理中: {i}/{len(races)}")

        race_id = race['race_id']
        race_date = race['race_date']
        entries, winner_pit = get_race_entries_and_result(race_id)

        if not entries or winner_pit is None or len(entries) != 6:
            continue

        # 各艇のスコアを計算
        baseline_scores = {}
        factor_scores = {}

        for entry in entries:
            pit = entry['pit_number']
            racer_number = entry['racer_number']
            racer_rank = entry['racer_rank'] or 'B1'

            # ベースライン: 級別スコアのみ
            class_result = scorer.calculate_class_score(racer_rank)
            baseline_scores[pit] = class_result['score']

            # 調子係数適用
            condition = scorer.calculate_condition_factor(racer_number, race_date, recent_races=20)
            factor_scores[pit] = class_result['score'] * condition['factor']

            # 1着の調子トレンドを記録
            if pit == winner_pit:
                trend = condition['trend']
                trend_stats[trend]['total'] += 1
                trend_stats[trend]['hit'] += 1

        # 予測（スコア最高の艇）
        baseline_pred = max(baseline_scores, key=baseline_scores.get)
        factor_pred = max(factor_scores, key=factor_scores.get)

        results['total'] += 1
        if baseline_pred == winner_pit:
            results['baseline_hit'] += 1
        if factor_pred == winner_pit:
            results['with_factor_hit'] += 1

    return results, trend_stats


def print_results(results, trend_stats):
    """結果を表示"""
    print("\n" + "=" * 70)
    print("P-2 選手調子係数（直近20走）効果測定結果")
    print("=" * 70)

    total = results['total']
    baseline_rate = results['baseline_hit'] / total * 100 if total > 0 else 0
    factor_rate = results['with_factor_hit'] / total * 100 if total > 0 else 0
    diff = factor_rate - baseline_rate

    print(f"\n検証レース数: {total}")
    print(f"\n{'方式':<25} {'的中数':>10} {'的中率':>12}")
    print("-" * 50)
    print(f"{'ベースライン（級別のみ）':<25} {results['baseline_hit']:>10} {baseline_rate:>11.2f}%")
    print(f"{'調子係数適用':<25} {results['with_factor_hit']:>10} {factor_rate:>11.2f}%")
    print("-" * 50)
    print(f"{'改善幅':<25} {'':<10} {diff:>+11.2f}pt")

    # トレンド別分析
    print("\n【1着選手のトレンド分析】")
    print(f"{'トレンド':<15} {'レース数':>10} {'割合':>10}")
    print("-" * 40)

    total_winners = sum(s['total'] for s in trend_stats.values())
    for trend in ['hot', 'good', 'normal', 'cold', 'slump', 'unknown']:
        if trend in trend_stats:
            count = trend_stats[trend]['total']
            pct = count / total_winners * 100 if total_winners > 0 else 0
            trend_label = {
                'hot': '絶好調',
                'good': '好調',
                'normal': '普通',
                'cold': '不調',
                'slump': '低迷',
                'unknown': '不明',
            }.get(trend, trend)
            print(f"{trend_label:<15} {count:>10} {pct:>9.1f}%")


def main():
    results, trend_stats = evaluate_condition_factor_effect()
    print_results(results, trend_stats)


if __name__ == "__main__":
    main()
