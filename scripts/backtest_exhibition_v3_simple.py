#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
展示スコアラーv3 簡易バックテスト

アプローチ:
1. 既存のrace_predictionsから信頼度A-Eのレースを取得
2. 各レースでBeforeInfoScorerV3を使い、展示スコアのみv3に置き換え
3. 他のスコア（ST、進入、前走など）は変えずに、総合スコアを再計算
4. 順位予測を更新して、的中率を測定

制約:
- 信頼度は元のrace_predictionsのものを使用（再判定しない）
- 展示スコアのみv3に置き換え（他のスコアは既存のまま）
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from datetime import datetime
from collections import defaultdict

DB_PATH = "data/boatrace.db"

# ベースライン（v2での精度）
BASELINE = {
    'A': {'total': 896, 'first_rate': 72.88, 'trifecta_rate': 10.22},
    'B': {'total': 5658, 'first_rate': 65.39, 'trifecta_rate': 9.06},
    'C': {'total': 8451, 'first_rate': 46.27, 'trifecta_rate': 5.86},
    'D': {'total': 2067, 'first_rate': 33.62, 'trifecta_rate': 3.90},
    'E': {'total': 72, 'first_rate': 34.72, 'trifecta_rate': 4.17}
}

def calculate_exhibition_score_v3_delta(race_id):
    """
    展示スコアv2→v3の差分を計算

    Returns:
        dict: {pit_number: delta_score, ...}
    """
    from src.scoring.exhibition_scorer_v2 import ExhibitionScorerV2
    from src.scoring.exhibition_scorer_v3 import ExhibitionScorerV3

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # レース情報取得
    cursor.execute("""
        SELECT
            r.venue_code,
            rd.pit_number,
            rd.exhibition_time,
            rd.st_time,
            rd.actual_course,
            e.racer_rank
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
        WHERE r.id = ?
        AND rd.exhibition_time IS NOT NULL
        ORDER BY rd.pit_number
    """, (race_id,))

    racers = []
    for row in cursor.fetchall():
        venue_code, pit, exh_time, st_time, course, racer_rank = row
        racers.append({
            'venue_code': venue_code,
            'pit': pit,
            'exh_time': exh_time,
            'st_time': st_time,
            'course': course,
            'racer_rank': racer_rank
        })

    conn.close()

    if len(racers) != 6:
        return {}

    # 展示タイムマップ
    exhibition_times = {r['pit']: r['exh_time'] for r in racers}
    beforeinfo = {'exhibition_times': exhibition_times}

    scorer_v2 = ExhibitionScorerV2()
    scorer_v3 = ExhibitionScorerV3()

    deltas = {}

    for racer in racers:
        pit = racer['pit']
        racer_data = {'rank': racer['racer_rank']}

        # v2スコア
        v2_result = scorer_v2.calculate_exhibition_score(
            racer['venue_code'],
            pit,
            beforeinfo,
            racer_data
        )
        v2_score = v2_result['exhibition_score']

        # v3スコア
        v3_result = scorer_v3.calculate_exhibition_score(
            racer['venue_code'],
            pit,
            beforeinfo,
            racer_data,
            actual_course=racer['course'],
            st_time=racer['st_time']
        )
        v3_score = v3_result['exhibition_score']

        # v2スコア範囲: -30 ~ +30 (60点幅)
        # v3スコア範囲: -30 ~ +50 (80点幅)
        # BeforeInfoScorerでは25点満点に正規化されるので、それぞれ変換
        v2_normalized = (v2_score + 30) / 60.0 * 25.0
        v3_normalized = (v3_score + 30) / 80.0 * 25.0

        # 差分
        delta = v3_normalized - v2_normalized

        deltas[pit] = delta

    return deltas

def main():
    # UTF-8出力設定
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 80)
    print("展示スコアラーv3 簡易バックテスト")
    print("=" * 80)
    print()
    print("方法: 既存予測データに展示スコアv3の差分を適用")
    print("対象期間: 2025年1月1日～12月31日")
    print()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("[1/3] 予測データ取得中...")

    # 信頼度別のレースリスト取得
    cursor.execute("""
        SELECT DISTINCT
            rp.race_id,
            rp.confidence
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        AND rp.prediction_type = 'advance'
        AND rp.rank_prediction = 1
        ORDER BY r.race_date, rp.race_id
        LIMIT 1000
    """)

    race_confidences = {}
    for row in cursor.fetchall():
        race_id, confidence = row
        race_confidences[race_id] = confidence

    print(f"OK {len(race_confidences)}レース取得完了")
    print()

    print("[2/3] 展示スコア差分計算と予測更新中...")

    confidence_stats = defaultdict(lambda: {
        'total': 0,
        'v2_first_correct': 0,
        'v3_first_correct': 0
    })

    processed = 0
    for race_id, confidence in race_confidences.items():
        processed += 1
        if processed % 100 == 0:
            print(f"  処理中: {processed}/{len(race_confidences)}")

        # v2→v3の展示スコア差分
        deltas = calculate_exhibition_score_v3_delta(race_id)

        if not deltas or len(deltas) != 6:
            continue

        # 元の予測取得
        cursor.execute("""
            SELECT
                rp.pit_number,
                rp.total_score,
                res.rank as finish_rank
            FROM race_predictions rp
            LEFT JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
            WHERE rp.race_id = ?
            AND rp.prediction_type = 'advance'
            ORDER BY rp.pit_number
        """, (race_id,))

        predictions = []
        for row in cursor.fetchall():
            pit, v2_total_score, finish_rank = row

            # v3総合スコア = v2総合スコア + 展示スコア差分
            v3_total_score = v2_total_score + deltas.get(pit, 0)

            predictions.append({
                'pit': pit,
                'v2_total_score': v2_total_score,
                'v3_total_score': v3_total_score,
                'finish_rank': int(finish_rank) if finish_rank else None
            })

        if len(predictions) != 6:
            continue

        # v2予測（元の順位）
        v2_sorted = sorted(predictions, key=lambda x: x['v2_total_score'], reverse=True)
        v2_predicted_pit = v2_sorted[0]['pit']

        # v3予測（展示スコア差分適用後）
        v3_sorted = sorted(predictions, key=lambda x: x['v3_total_score'], reverse=True)
        v3_predicted_pit = v3_sorted[0]['pit']

        # 実際の1着
        actual_winner_pit = next((p['pit'] for p in predictions if p['finish_rank'] == 1), None)

        # 統計更新
        confidence_stats[confidence]['total'] += 1

        if v2_predicted_pit == actual_winner_pit:
            confidence_stats[confidence]['v2_first_correct'] += 1

        if v3_predicted_pit == actual_winner_pit:
            confidence_stats[confidence]['v3_first_correct'] += 1

    print(f"OK {processed}レース処理完了")
    print()

    print("[3/3] 結果集計...")

    # 的中率計算
    results = {}
    for conf, stats in confidence_stats.items():
        total = stats['total']
        if total > 0:
            results[conf] = {
                'total': total,
                'v2_first_rate': stats['v2_first_correct'] / total * 100,
                'v3_first_rate': stats['v3_first_correct'] / total * 100
            }

    print()
    print("=" * 80)
    print("【バックテスト結果】")
    print("=" * 80)
    print()

    print(f"{'信頼度':<8} {'レース数':>10} {'v2的中率':>12} {'v3的中率':>12} {'改善幅':>10}")
    print("-" * 70)

    total_improvement = 0
    valid_confidences = 0

    for conf in ['A', 'B', 'C', 'D', 'E']:
        if conf in results:
            stat = results[conf]
            improvement = stat['v3_first_rate'] - stat['v2_first_rate']

            print(f"{conf:<8} {stat['total']:>10} "
                  f"{stat['v2_first_rate']:>11.2f}% "
                  f"{stat['v3_first_rate']:>11.2f}% "
                  f"{improvement:>9.2f}pt")

            total_improvement += improvement
            valid_confidences += 1
        else:
            print(f"{conf:<8} {'N/A':>10} {'N/A':>12} {'N/A':>12} {'N/A':>10}")

    print()
    print("=" * 80)
    print("【総合評価】")
    print("=" * 80)

    if valid_confidences > 0:
        avg_improvement = total_improvement / valid_confidences

        print(f"平均改善幅: {avg_improvement:+.2f}pt")
        print()

        if avg_improvement > 3.0:
            print("[評価] ★★★ 大幅改善 - 展示スコアラーv3の本番導入を強く推奨")
        elif avg_improvement > 1.0:
            print("[評価] ★★☆ 明確な改善 - 展示スコアラーv3の本番導入を推奨")
        elif avg_improvement > 0:
            print("[評価] ★☆☆ 小幅改善 - 展示スコアラーv3の導入を検討")
        else:
            print("[評価] ☆☆☆ 改善なし - v2を維持")

        print()
        print("【特記事項】")

        # 信頼度A・Bの改善状況
        if 'A' in results and 'B' in results:
            a_improvement = results['A']['v3_first_rate'] - results['A']['v2_first_rate']
            b_improvement = results['B']['v3_first_rate'] - results['B']['v2_first_rate']

            print(f"- 信頼度A改善: {a_improvement:+.2f}pt")
            print(f"- 信頼度B改善: {b_improvement:+.2f}pt")

            if a_improvement > 0 and b_improvement > 0:
                print("- 主力信頼度（A・B）で改善確認 → ROI向上が期待できる")

    print()
    print("=" * 80)

    conn.close()

if __name__ == '__main__':
    main()
