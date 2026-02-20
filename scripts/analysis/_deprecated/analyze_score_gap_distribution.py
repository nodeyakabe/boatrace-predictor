"""
スコア差分布の分析

- DBに保存されている予測データのスコア差分布を分析
- スコア差ベース信頼度判定の影響を推定
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3
from collections import defaultdict
import json

def analyze_score_gap_from_db(year: int = 2025):
    """DBの予測データからスコア差分布を分析"""

    db_path = "data/boatrace.db"

    # 予測データを取得（race_idごとに6選手分のスコアを取得）
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT race_id, pit_number, rank_prediction, total_score, confidence
            FROM race_predictions
            WHERE prediction_type = 'before'
            AND race_id LIKE ?
            ORDER BY race_id, rank_prediction
        """, (f"{year}%",))
        rows = cursor.fetchall()

    # race_idごとにグループ化
    from collections import defaultdict
    race_data = defaultdict(list)
    for race_id, pit_number, rank_pred, total_score, confidence in rows:
        race_data[race_id].append({
            'pit_number': pit_number,
            'rank_prediction': rank_pred,
            'total_score': total_score,
            'confidence': confidence
        })

    predictions = []
    for race_id, preds in race_data.items():
        if len(preds) >= 2:
            # スコア順にソート
            preds_sorted = sorted(preds, key=lambda x: x['total_score'], reverse=True)
            top1 = preds_sorted[0]
            top2 = preds_sorted[1]
            predictions.append({
                'race_id': race_id,
                'confidence': top1['confidence'],
                'top1_score': top1['total_score'],
                'top2_score': top2['total_score'],
                'top1_pit': top1['pit_number']
            })

    print(f"\n分析対象: {year}年のbefore予測 {len(predictions)}件")
    print("=" * 70)

    # 信頼度ごとの統計
    confidence_stats = defaultdict(lambda: {
        'count': 0,
        'score_gaps': [],
        'would_downgrade': 0,
        'original_confidence': defaultdict(int)
    })

    # スコア差の閾値（新しい判定基準）
    def new_confidence(score_gap, top1_score, is_course1):
        if score_gap >= 15 and top1_score >= 70:
            return 'A'
        elif score_gap >= 10 and top1_score >= 60:
            return 'B'
        elif score_gap >= 5 or (is_course1 and top1_score >= 55):
            return 'C'
        elif score_gap >= 2:
            return 'D'
        else:
            return 'E'

    confidence_order = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'E': 1}
    downgrade_counts = defaultdict(lambda: defaultdict(int))

    for pred in predictions:
        try:
            confidence = pred['confidence']
            top1_score = pred['top1_score']
            top2_score = pred['top2_score']
            score_gap = top1_score - top2_score
            is_course1 = (pred['top1_pit'] == 1)

            # 新しい信頼度を計算
            new_conf = new_confidence(score_gap, top1_score, is_course1)

            # 統計更新
            confidence_stats[confidence]['count'] += 1
            confidence_stats[confidence]['score_gaps'].append(score_gap)
            confidence_stats[confidence]['original_confidence'][confidence] += 1

            # ダウングレードされるかどうか
            if confidence_order[new_conf] < confidence_order[confidence]:
                confidence_stats[confidence]['would_downgrade'] += 1
                downgrade_counts[confidence][new_conf] += 1

        except Exception as e:
            continue

    # 結果出力
    print("\n" + "=" * 70)
    print("【信頼度別 スコア差分布】")
    print("=" * 70)
    print(f"{'信頼度':<8} {'件数':>8} {'平均差':>10} {'中央値':>10} {'標準偏差':>10} {'ダウングレード':>14}")
    print("-" * 70)

    for conf in ['A', 'B', 'C', 'D', 'E']:
        s = confidence_stats[conf]
        count = s['count']
        gaps = s['score_gaps']
        downgrade = s['would_downgrade']

        if count > 0:
            import statistics
            avg_gap = sum(gaps) / len(gaps)
            median_gap = statistics.median(gaps)
            std_gap = statistics.stdev(gaps) if len(gaps) > 1 else 0
            downgrade_rate = downgrade / count * 100
            print(f"{conf:<8} {count:>8} {avg_gap:>9.2f} {median_gap:>9.2f} {std_gap:>9.2f} {downgrade:>6}({downgrade_rate:.1f}%)")
        else:
            print(f"{conf:<8} {count:>8} {'N/A':>10} {'N/A':>10} {'N/A':>10} {'N/A':>14}")

    print("\n" + "=" * 70)
    print("【ダウングレード詳細（元の信頼度 → 新しい信頼度）】")
    print("=" * 70)

    for orig_conf in ['A', 'B', 'C', 'D']:
        if downgrade_counts[orig_conf]:
            print(f"\n{orig_conf} からのダウングレード:")
            for new_conf, count in sorted(downgrade_counts[orig_conf].items()):
                print(f"  → {new_conf}: {count}件")

    # スコア差の分布を確認
    print("\n" + "=" * 70)
    print("【スコア差の分布（全体）】")
    print("=" * 70)

    all_gaps = []
    for s in confidence_stats.values():
        all_gaps.extend(s['score_gaps'])

    if all_gaps:
        # 分布をヒストグラム風に表示
        gap_ranges = [
            (0, 2, 'E領域'),
            (2, 5, 'D領域'),
            (5, 10, 'C領域'),
            (10, 15, 'B領域'),
            (15, 100, 'A領域')
        ]

        for min_gap, max_gap, label in gap_ranges:
            count = sum(1 for g in all_gaps if min_gap <= g < max_gap)
            pct = count / len(all_gaps) * 100
            bar = '#' * int(pct / 2)
            print(f"  {label:8s} ({min_gap:2d}-{max_gap:>3d}): {count:>6} ({pct:5.1f}%) {bar}")

    return confidence_stats

if __name__ == "__main__":
    print("=" * 70)
    print("スコア差分布の分析")
    print("=" * 70)

    for year in [2025, 2024, 2023]:
        analyze_score_gap_from_db(year=year)
        print("\n")
