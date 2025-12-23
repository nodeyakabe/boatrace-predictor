"""
決まり手別展開予測の効果測定

P-3タスク Phase 5: 3着予測精度の改善効果を検証

評価指標:
- 3着的中率
- 3連単的中率（パターンHの1-2-3, 1-2-4, 1-2-5）
- ROI改善
"""

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple
import random

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.prediction.kimarite_flow_predictor import KimariteFlowPredictor
from src.ml.third_place_specialized_model import ThirdPlaceSpecializedScorer

DATABASE_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"


def get_test_races(limit: int = 500) -> List[Dict]:
    """テスト用レースデータを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 2025年のレースで、結果と決まり手が揃っているもの
    # まずレースIDのリストを取得
    query = """
    SELECT DISTINCT r.id as race_id, r.race_date, r.venue_code
    FROM races r
    JOIN results res ON r.id = res.race_id
    WHERE res.rank = 1
      AND res.kimarite IS NOT NULL
      AND res.kimarite != ''
      AND r.race_date >= '2025-01-01'
      AND r.race_date <= '2025-11-30'
    """

    cursor.execute(query)
    all_races = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # ランダムサンプリング
    if len(all_races) > limit:
        random.shuffle(all_races)
        return all_races[:limit]
    return all_races


def get_race_result(race_id: int) -> Dict:
    """レースの実際の結果を取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1着、2着、3着の結果
    cursor.execute("""
        SELECT pit_number, rank, kimarite
        FROM results
        WHERE race_id = ?
        ORDER BY rank
    """, (race_id,))

    results = {}
    for row in cursor.fetchall():
        try:
            rank = int(row['rank'])
            if rank in [1, 2, 3]:
                results[rank] = {
                    'course': row['pit_number'],
                    'kimarite': row['kimarite']
                }
        except (ValueError, TypeError):
            continue

    conn.close()
    return results


def get_entry_scores(race_id: int) -> Dict[int, float]:
    """エントリーのスコアを簡易計算（ランクベース）"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pit_number, racer_rank, win_rate
        FROM entries
        WHERE race_id = ?
    """, (race_id,))

    scores = {}
    rank_scores = {'A1': 10, 'A2': 8, 'B1': 6, 'B2': 4}

    for row in cursor.fetchall():
        pit = row['pit_number']
        rank = row['racer_rank'] or 'B2'
        win_rate = row['win_rate'] or 0

        # コーススコア（1コース有利）
        course_score = (7 - pit) * 5

        # ランクスコア
        rank_s = rank_scores.get(rank, 4)

        # 勝率スコア
        wr_score = win_rate * 0.5 if win_rate else 0

        scores[pit] = course_score + rank_s * 3 + wr_score

    conn.close()
    return scores


def evaluate_baseline(races: List[Dict]) -> Dict:
    """ベースライン（スコア順）での評価"""
    results = {
        'total': 0,
        'first_hit': 0,
        'second_hit': 0,
        'third_hit': 0,
        'trifecta_hit': 0,
        'pattern_h_hit': 0,  # 1-2-3, 1-2-4, 1-2-5 のいずれか的中
    }

    for race in races:
        race_id = race['race_id']
        actual = get_race_result(race_id)

        if not actual or 1 not in actual or 2 not in actual or 3 not in actual:
            continue

        scores = get_entry_scores(race_id)
        if not scores or len(scores) < 6:
            continue

        # スコア順で予測
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        pred_first = sorted_scores[0][0]
        pred_second = sorted_scores[1][0]
        pred_third = sorted_scores[2][0]
        pred_fourth = sorted_scores[3][0]
        pred_fifth = sorted_scores[4][0]

        results['total'] += 1

        # 各着の的中判定
        if pred_first == actual[1]['course']:
            results['first_hit'] += 1
        if pred_second == actual[2]['course']:
            results['second_hit'] += 1
        if pred_third == actual[3]['course']:
            results['third_hit'] += 1

        # 3連単的中
        if (pred_first == actual[1]['course'] and
            pred_second == actual[2]['course'] and
            pred_third == actual[3]['course']):
            results['trifecta_hit'] += 1

        # パターンH的中（1-2軸で3着が3位/4位/5位のいずれか）
        if (pred_first == actual[1]['course'] and
            pred_second == actual[2]['course']):
            if actual[3]['course'] in [pred_third, pred_fourth, pred_fifth]:
                results['pattern_h_hit'] += 1

    return results


def evaluate_kimarite_flow(races: List[Dict]) -> Dict:
    """決まり手別展開予測での評価"""
    predictor = KimariteFlowPredictor()

    results = {
        'total': 0,
        'first_hit': 0,
        'second_hit': 0,
        'third_hit': 0,
        'trifecta_hit': 0,
        'pattern_h_hit': 0,
    }

    for race in races:
        race_id = race['race_id']
        actual = get_race_result(race_id)

        if not actual or 1 not in actual or 2 not in actual or 3 not in actual:
            continue

        scores = get_entry_scores(race_id)
        if not scores or len(scores) < 6:
            continue

        # 展開予測で順位予測
        prediction = predictor.predict_full_ranking(scores)

        pred_first = prediction['first']['course']
        pred_second = prediction['second']['course']
        pred_third = prediction['third']['course']

        # 4位、5位候補を計算
        remaining = [c for c in range(1, 7) if c not in [pred_first, pred_second, pred_third]]
        remaining_scores = {c: scores.get(c, 0) for c in remaining}
        sorted_remaining = sorted(remaining_scores.items(), key=lambda x: x[1], reverse=True)
        pred_fourth = sorted_remaining[0][0] if sorted_remaining else 4
        pred_fifth = sorted_remaining[1][0] if len(sorted_remaining) > 1 else 5

        results['total'] += 1

        # 各着の的中判定
        if pred_first == actual[1]['course']:
            results['first_hit'] += 1
        if pred_second == actual[2]['course']:
            results['second_hit'] += 1
        if pred_third == actual[3]['course']:
            results['third_hit'] += 1

        # 3連単的中
        if (pred_first == actual[1]['course'] and
            pred_second == actual[2]['course'] and
            pred_third == actual[3]['course']):
            results['trifecta_hit'] += 1

        # パターンH的中
        if (pred_first == actual[1]['course'] and
            pred_second == actual[2]['course']):
            if actual[3]['course'] in [pred_third, pred_fourth, pred_fifth]:
                results['pattern_h_hit'] += 1

    return results


def print_comparison(baseline: Dict, kimarite: Dict):
    """結果比較を表示"""
    print("=" * 70)
    print("P-3 決まり手別展開予測 効果測定結果")
    print("=" * 70)

    print(f"\n検証レース数: {baseline['total']}")

    headers = ['指標', 'ベースライン', '展開予測', '改善幅']
    print(f"\n{headers[0]:<20} {headers[1]:<15} {headers[2]:<15} {headers[3]:<15}")
    print("-" * 65)

    metrics = [
        ('1着的中率', 'first_hit'),
        ('2着的中率', 'second_hit'),
        ('3着的中率', 'third_hit'),
        ('3連単的中率', 'trifecta_hit'),
        ('パターンH的中率', 'pattern_h_hit'),
    ]

    for label, key in metrics:
        base_rate = baseline[key] / baseline['total'] * 100 if baseline['total'] > 0 else 0
        kima_rate = kimarite[key] / kimarite['total'] * 100 if kimarite['total'] > 0 else 0
        diff = kima_rate - base_rate
        sign = '+' if diff >= 0 else ''

        print(f"{label:<20} {base_rate:>12.2f}% {kima_rate:>12.2f}% {sign}{diff:>12.2f}pt")

    print("\n" + "=" * 70)

    # 3着予測の詳細分析
    print("\n【3着予測の詳細】")
    base_third = baseline['third_hit'] / baseline['total'] * 100 if baseline['total'] > 0 else 0
    kima_third = kimarite['third_hit'] / kimarite['total'] * 100 if kimarite['total'] > 0 else 0
    diff_third = kima_third - base_third

    print(f"  ベースライン3着的中率: {base_third:.2f}%")
    print(f"  展開予測3着的中率: {kima_third:.2f}%")
    print(f"  改善幅: {'+' if diff_third >= 0 else ''}{diff_third:.2f}pt")

    # 目標との比較
    target_third = 32.0  # 目標: 32%
    print(f"\n  目標3着的中率: {target_third:.1f}%")
    print(f"  目標達成度: {kima_third / target_third * 100:.1f}%")


def main():
    print("テストレースを取得中...")
    races = get_test_races(limit=500)
    print(f"取得レース数: {len(races)}")

    print("\nベースライン評価中...")
    baseline_results = evaluate_baseline(races)

    print("展開予測評価中...")
    kimarite_results = evaluate_kimarite_flow(races)

    print_comparison(baseline_results, kimarite_results)


if __name__ == "__main__":
    main()
