#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
展示スコアラーv3バックテスト

目的:
- 展示スコアv2→v3に変更した場合の予測精度変化を測定
- 信頼度別の改善効果を定量化
- ベースラインレポートとの比較

戦略:
1. 2025年レースに対してv3スコアで再予測
2. 信頼度A-Eの的中率を計算
3. ベースラインと比較
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from datetime import datetime
from collections import defaultdict
import statistics

from src.scoring.exhibition_scorer_v3 import ExhibitionScorerV3

DB_PATH = "data/boatrace.db"

# ベースライン（v2での精度）
BASELINE = {
    'A': {'total': 896, 'first_rate': 72.88, 'trifecta_rate': 10.22},
    'B': {'total': 5658, 'first_rate': 65.39, 'trifecta_rate': 9.06},
    'C': {'total': 8451, 'first_rate': 46.27, 'trifecta_rate': 5.86},
    'D': {'total': 2067, 'first_rate': 33.62, 'trifecta_rate': 3.90},
    'E': {'total': 72, 'first_rate': 34.72, 'trifecta_rate': 4.17}
}

def get_race_data_with_predictions(cursor, start_date='2025-01-01', end_date='2025-12-31', limit=None):
    """
    予測データ付きレース情報を取得

    Returns:
        dict: {race_id: {'racers': [...], 'predictions': {...}}}
    """

    # 予測データ取得
    query = """
        SELECT
            rp.race_id,
            rp.pit_number,
            rp.confidence,
            rp.rank_prediction,
            rp.total_score
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rp.prediction_type = 'advance'
        ORDER BY rp.race_id, rp.rank_prediction
    """

    if limit:
        query += f" LIMIT {limit * 6}"

    cursor.execute(query, (start_date, end_date))

    predictions = defaultdict(dict)
    for row in cursor.fetchall():
        race_id, pit, confidence, rank_pred, score = row
        if race_id not in predictions:
            predictions[race_id] = {'confidence': confidence, 'predictions': {}}
        predictions[race_id]['predictions'][pit] = {
            'rank_prediction': rank_pred,
            'original_score': score
        }

    # レース詳細取得
    race_ids = list(predictions.keys())
    if not race_ids:
        return {}

    race_ids_str = ','.join('?' * len(race_ids))

    cursor.execute(f"""
        SELECT
            r.id as race_id,
            r.venue_code,
            rd.pit_number,
            rd.exhibition_time,
            rd.st_time,
            rd.actual_course,
            e.racer_rank,
            res.rank as finish_rank
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
        LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.id IN ({race_ids_str})
        AND rd.exhibition_time IS NOT NULL
        ORDER BY r.id, rd.pit_number
    """, race_ids)

    races = defaultdict(lambda: {'racers': [], 'confidence': None, 'predictions': {}})

    for row in cursor.fetchall():
        race_id, venue_code, pit, exh_time, st_time, course, racer_rank, finish_rank = row

        races[race_id]['racers'].append({
            'pit_number': pit,
            'venue_code': venue_code,
            'exhibition_time': exh_time,
            'st_time': st_time,
            'actual_course': course,
            'racer_rank': racer_rank,
            'finish_rank': int(finish_rank) if finish_rank else None
        })

        races[race_id]['confidence'] = predictions[race_id]['confidence']
        races[race_id]['predictions'] = predictions[race_id]['predictions']

    # 6艇揃っているレースのみ
    valid_races = {rid: data for rid, data in races.items() if len(data['racers']) == 6}

    return valid_races

def calculate_v3_predictions(races):
    """
    展示スコアv3で予測を再計算

    Returns:
        dict: {race_id: {'confidence': 'A', 'predicted_pit': 1, 'actual_pit': 2, ...}}
    """
    scorer = ExhibitionScorerV3()

    results = {}

    for race_id, race_data in races.items():
        racers = race_data['racers']
        original_confidence = race_data['confidence']

        # 全艇の展示タイムマップ
        exhibition_times = {r['pit_number']: r['exhibition_time'] for r in racers}

        # 各艇のv3スコア計算
        v3_scores = []
        for racer in racers:
            beforeinfo = {'exhibition_times': exhibition_times}
            racer_data = {'rank': racer['racer_rank']}

            score_result = scorer.calculate_exhibition_score(
                racer['venue_code'],
                racer['pit_number'],
                beforeinfo,
                racer_data,
                actual_course=racer['actual_course'],
                st_time=racer['st_time']
            )

            v3_scores.append({
                'pit': racer['pit_number'],
                'score': score_result['exhibition_score'],
                'finish_rank': racer['finish_rank']
            })

        # スコア順にソート
        v3_scores.sort(key=lambda x: x['score'], reverse=True)

        # 1着予測
        predicted_pit = v3_scores[0]['pit']
        actual_winner = next((r['pit_number'] for r in racers if r['finish_rank'] == 1), None)

        # 三連単予測（上位3艇）
        predicted_top3 = [s['pit'] for s in v3_scores[:3]]
        actual_top3 = sorted(
            [r for r in racers if r['finish_rank'] and r['finish_rank'] <= 3],
            key=lambda x: x['finish_rank']
        )
        actual_top3_pits = [r['pit_number'] for r in actual_top3] if len(actual_top3) == 3 else []

        results[race_id] = {
            'confidence': original_confidence,  # 元の信頼度を使用（簡略化）
            'predicted_pit': predicted_pit,
            'actual_pit': actual_winner,
            'predicted_top3': predicted_top3,
            'actual_top3': actual_top3_pits,
            'v3_scores': v3_scores
        }

    return results

def analyze_by_confidence(predictions):
    """信頼度別の精度分析"""

    confidence_stats = defaultdict(lambda: {
        'total': 0,
        'first_correct': 0,
        'trifecta_correct': 0
    })

    for race_id, pred in predictions.items():
        conf = pred['confidence']

        confidence_stats[conf]['total'] += 1

        # 1着的中
        if pred['predicted_pit'] == pred['actual_pit']:
            confidence_stats[conf]['first_correct'] += 1

        # 三連単的中
        if (len(pred['actual_top3']) == 3 and
            pred['predicted_top3'] == pred['actual_top3']):
            confidence_stats[conf]['trifecta_correct'] += 1

    # 的中率計算
    results = {}
    for conf, stats in confidence_stats.items():
        total = stats['total']
        if total > 0:
            results[conf] = {
                'total': total,
                'first_correct': stats['first_correct'],
                'first_rate': stats['first_correct'] / total * 100,
                'trifecta_correct': stats['trifecta_correct'],
                'trifecta_rate': stats['trifecta_correct'] / total * 100
            }

    return results

def main():
    # UTF-8出力設定
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 80)
    print("展示スコアラーv3 バックテスト")
    print("=" * 80)
    print()
    print("対象期間: 2025年1月1日～12月31日")
    print("比較対象: ベースラインレポート（v2使用時の精度）")
    print()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("[1/3] レースデータ取得中...")
    races = get_race_data_with_predictions(cursor)
    print(f"OK {len(races)}レース取得完了")
    print()

    print("[2/3] 展示スコアv3で予測再計算中...")
    predictions = calculate_v3_predictions(races)
    print(f"OK {len(predictions)}レース予測完了")
    print()

    print("[3/3] 信頼度別精度分析中...")
    v3_stats = analyze_by_confidence(predictions)

    print()
    print("=" * 80)
    print("【バックテスト結果: 展示スコアv3】")
    print("=" * 80)
    print()

    print(f"{'信頼度':<8} {'レース数':>10} {'1着的中':>10} {'1着的中率':>12} {'三連単的中率':>14}")
    print("-" * 80)

    for conf in ['A', 'B', 'C', 'D', 'E']:
        if conf in v3_stats:
            stat = v3_stats[conf]
            print(f"{conf:<8} {stat['total']:>10} "
                  f"{stat['first_correct']:>10} "
                  f"{stat['first_rate']:>11.2f}% "
                  f"{stat['trifecta_rate']:>13.2f}%")
        else:
            print(f"{conf:<8} {'N/A':>10} {'N/A':>10} {'N/A':>12} {'N/A':>14}")

    print()
    print("=" * 80)
    print("【ベースライン比較】")
    print("=" * 80)
    print()

    print(f"{'信頼度':<8} {'v2 1着':>12} {'v3 1着':>12} {'改善幅':>10} "
          f"{'v2 三連単':>12} {'v3 三連単':>12} {'改善幅':>10}")
    print("-" * 90)

    total_improvement_first = 0
    total_improvement_trifecta = 0
    valid_confidences = 0

    for conf in ['A', 'B', 'C', 'D', 'E']:
        if conf in v3_stats and conf in BASELINE:
            v2_first = BASELINE[conf]['first_rate']
            v3_first = v3_stats[conf]['first_rate']
            diff_first = v3_first - v2_first

            v2_trifecta = BASELINE[conf]['trifecta_rate']
            v3_trifecta = v3_stats[conf]['trifecta_rate']
            diff_trifecta = v3_trifecta - v2_trifecta

            print(f"{conf:<8} {v2_first:>11.2f}% {v3_first:>11.2f}% {diff_first:>9.2f}pt "
                  f"{v2_trifecta:>11.2f}% {v3_trifecta:>11.2f}% {diff_trifecta:>9.2f}pt")

            total_improvement_first += diff_first
            total_improvement_trifecta += diff_trifecta
            valid_confidences += 1
        else:
            print(f"{conf:<8} {'N/A':>12} {'N/A':>12} {'N/A':>10} "
                  f"{'N/A':>12} {'N/A':>12} {'N/A':>10}")

    print()
    print("=" * 80)
    print("【総合評価】")
    print("=" * 80)

    if valid_confidences > 0:
        avg_improvement_first = total_improvement_first / valid_confidences
        avg_improvement_trifecta = total_improvement_trifecta / valid_confidences

        print(f"平均改善幅（1着的中率）: {avg_improvement_first:+.2f}pt")
        print(f"平均改善幅（三連単的中率）: {avg_improvement_trifecta:+.2f}pt")
        print()

        if avg_improvement_first > 3.0:
            print("[評価] ★★★ 大幅改善 - v3導入を強く推奨")
        elif avg_improvement_first > 1.0:
            print("[評価] ★★☆ 明確な改善 - v3導入を推奨")
        elif avg_improvement_first > 0:
            print("[評価] ★☆☆ 小幅改善 - v3導入を検討")
        else:
            print("[評価] ☆☆☆ 改善なし - v2を維持")

        print()
        print("【特記事項】")

        # 信頼度A・Bの改善状況
        if 'A' in v3_stats and 'B' in v3_stats:
            a_improvement = v3_stats['A']['first_rate'] - BASELINE['A']['first_rate']
            b_improvement = v3_stats['B']['first_rate'] - BASELINE['B']['first_rate']

            print(f"- 信頼度A改善: {a_improvement:+.2f}pt ({BASELINE['A']['first_rate']:.2f}% → {v3_stats['A']['first_rate']:.2f}%)")
            print(f"- 信頼度B改善: {b_improvement:+.2f}pt ({BASELINE['B']['first_rate']:.2f}% → {v3_stats['B']['first_rate']:.2f}%)")

            if a_improvement > 0 and b_improvement > 0:
                print("- 主力信頼度（A・B）で改善確認 → ROI向上が期待できる")

    print()
    print("=" * 80)

    conn.close()

if __name__ == '__main__':
    main()
