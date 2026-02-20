"""
スコア差ベース信頼度判定の効果分析

- 従来のスコアベースと改良版スコア差ベースの信頼度分布を比較
- C,D予想の1着的中率変化を測定
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3
from collections import defaultdict
from src.analysis.race_predictor import RacePredictor
from config.feature_flags import FEATURE_FLAGS

def analyze_confidence_distribution(year: int = 2025, sample_size: int = 500):
    """信頼度分布を分析"""

    db_path = "data/boatrace.db"

    # レースIDを取得
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT race_id
            FROM race_predictions
            WHERE prediction_type = 'before'
            AND race_id LIKE ?
            ORDER BY race_id DESC
            LIMIT ?
        """, (f"{year}%", sample_size))
        race_ids = [row[0] for row in cursor.fetchall()]

    print(f"\n分析対象: {year}年のbefore予測 {len(race_ids)}件")
    print("=" * 70)

    # 信頼度ごとの統計
    stats = defaultdict(lambda: {'count': 0, 'hit': 0, 'score_gap_applied': 0})
    score_gap_changes = defaultdict(int)

    predictor = RacePredictor(db_path)

    for i, race_id in enumerate(race_ids):
        if i % 100 == 0:
            print(f"処理中: {i}/{len(race_ids)}...")

        try:
            predictions = predictor.predict_race(race_id, use_beforeinfo=True)
            if not predictions:
                continue

            # 1位予測の信頼度を取得
            top_pred = predictions[0]
            confidence = top_pred.get('confidence', 'E')
            confidence_reason = top_pred.get('confidence_reason', 'original')

            # 統計更新
            stats[confidence]['count'] += 1

            # スコア差ベースで変更されたかどうか
            if 'score_gap' in confidence_reason:
                stats[confidence]['score_gap_applied'] += 1
                # どの信頼度から変わったか（confidence_reasonからは取得困難なので概算）

            # 実際の結果を取得
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT rank1 FROM race_results WHERE race_id = ?
                """, (race_id,))
                row = cursor.fetchone()
                if row:
                    actual_first = row[0]
                    predicted_first = top_pred.get('pit_number')
                    if actual_first == predicted_first:
                        stats[confidence]['hit'] += 1

        except Exception as e:
            continue

    # 結果出力
    print("\n" + "=" * 70)
    print("【信頼度別 1着的中率（スコア差ベース判定適用後）】")
    print("=" * 70)
    print(f"{'信頼度':<8} {'件数':>8} {'的中':>8} {'的中率':>10} {'スコア差適用':>12}")
    print("-" * 70)

    total_count = 0
    total_hit = 0

    for conf in ['A', 'B', 'C', 'D', 'E']:
        s = stats[conf]
        count = s['count']
        hit = s['hit']
        gap_applied = s['score_gap_applied']

        total_count += count
        total_hit += hit

        if count > 0:
            hit_rate = hit / count * 100
            gap_rate = gap_applied / count * 100
            print(f"{conf:<8} {count:>8} {hit:>8} {hit_rate:>9.2f}% {gap_applied:>8}({gap_rate:.1f}%)")
        else:
            print(f"{conf:<8} {count:>8} {hit:>8} {'N/A':>10} {gap_applied:>12}")

    print("-" * 70)
    if total_count > 0:
        print(f"{'合計':<8} {total_count:>8} {total_hit:>8} {total_hit/total_count*100:>9.2f}%")

    print("\n" + "=" * 70)
    print("【参考: 従来の信頼度別1着的中率（2025年before予測）】")
    print("=" * 70)
    print("信頼度A: 72.99% (896件)")
    print("信頼度B: 65.60% (5,700件)")
    print("信頼度C: 46.01% (8,630件)")
    print("信頼度D: 32.93% (2,162件)")
    print("信頼度E: 32.47% (77件)")

    return stats

if __name__ == "__main__":
    # フラグ状態を確認
    print("=" * 70)
    print("スコア差ベース信頼度判定の効果分析")
    print("=" * 70)
    print(f"score_gap_confidence フラグ: {FEATURE_FLAGS.get('score_gap_confidence', False)}")

    analyze_confidence_distribution(year=2025, sample_size=1000)
