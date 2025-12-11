#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
展示スコアラーv3統合バックテスト

目的:
- BeforeInfoScorerV3を使った予測システムのバックテスト
- ベースライン（v2）との比較
- 信頼度別の改善効果測定

戦略:
1. race_predictionsテーブルのrace_idリストを取得
2. 各レースでBeforeInfoScorerV3を使ってスコア再計算
3. 信頼度を再判定（既存ロジックを簡略化）
4. 的中率を計算してベースラインと比較
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from datetime import datetime
from collections import defaultdict
import statistics

# v3スコアラーを使用するためにモンキーパッチ
from src.analysis import beforeinfo_scorer
from src.analysis.beforeinfo_scorer_v3 import BeforeInfoScorerV3

# BeforeInfoScorerをv3に置き換え
beforeinfo_scorer.BeforeInfoScorer = BeforeInfoScorerV3

DB_PATH = "data/boatrace.db"

# ベースライン（v2での精度）
BASELINE = {
    'A': {'total': 896, 'first_rate': 72.88, 'trifecta_rate': 10.22},
    'B': {'total': 5658, 'first_rate': 65.39, 'trifecta_rate': 9.06},
    'C': {'total': 8451, 'first_rate': 46.27, 'trifecta_rate': 5.86},
    'D': {'total': 2067, 'first_rate': 33.62, 'trifecta_rate': 3.90},
    'E': {'total': 72, 'first_rate': 34.72, 'trifecta_rate': 4.17}
}

def get_sample_races(cursor, start_date='2025-01-01', end_date='2025-12-31', limit=1000):
    """サンプルレース取得（計算時間短縮のため）"""

    cursor.execute("""
        SELECT DISTINCT r.id
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rp.prediction_type = 'advance'
        ORDER BY r.race_date, r.id
        LIMIT ?
    """, (start_date, end_date, limit))

    return [row[0] for row in cursor.fetchall()]

def calculate_v3_scores_for_race(race_id):
    """
    レースの全艇にv3スコアを計算

    Returns:
        list: [{'pit': 1, 'v3_score': 85.3, 'finish_rank': 1}, ...]
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # レース詳細取得
    cursor.execute("""
        SELECT
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
        WHERE r.id = ?
        AND rd.exhibition_time IS NOT NULL
        ORDER BY rd.pit_number
    """, (race_id,))

    racers = []
    for row in cursor.fetchall():
        venue_code, pit, exh_time, st_time, course, racer_rank, finish_rank = row
        racers.append({
            'venue_code': venue_code,
            'pit': pit,
            'exh_time': exh_time,
            'st_time': st_time,
            'course': course,
            'racer_rank': racer_rank,
            'finish_rank': int(finish_rank) if finish_rank else None
        })

    conn.close()

    if len(racers) != 6:
        return []

    # BeforeInfoScorerV3でスコア計算
    scorer = BeforeInfoScorerV3()

    # 展示タイムマップ作成
    exhibition_times = {r['pit']: r['exh_time'] for r in racers}
    st_times = {r['pit']: r['st_time'] for r in racers if r['st_time']}

    # 簡易的なbeforeinfo_data作成
    beforeinfo_data = {
        'is_published': True,
        'exhibition_times': exhibition_times,
        'start_timings': st_times,
        'exhibition_courses': {r['pit']: r['course'] for r in racers if r['course']},
        'tilt_angles': {},
        'weather': {},
        'parts_replacements': {},
        'adjusted_weights': {},
        'previous_race': {}
    }

    scores = []
    for racer in racers:
        try:
            score_result = scorer.calculate_beforeinfo_score(
                race_id=race_id,
                pit_number=racer['pit'],
                beforeinfo_data=beforeinfo_data
            )

            scores.append({
                'pit': racer['pit'],
                'v3_total_score': score_result['total_score'],
                'v3_exhibition_score': score_result['exhibition_time_score'],
                'finish_rank': racer['finish_rank']
            })
        except Exception as e:
            # エラー時は0点
            scores.append({
                'pit': racer['pit'],
                'v3_total_score': 0.0,
                'v3_exhibition_score': 0.0,
                'finish_rank': racer['finish_rank']
            })

    return scores

def estimate_confidence_simple(total_score):
    """
    簡易的な信頼度推定

    直前情報スコア（0-100点）から信頼度を推定
    ※緩和版: より多くのレースを高信頼度に分類
    """
    if total_score >= 70:
        return 'A'
    elif total_score >= 55:
        return 'B'
    elif total_score >= 40:
        return 'C'
    elif total_score >= 25:
        return 'D'
    else:
        return 'E'

def main():
    # UTF-8出力設定
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 80)
    print("展示スコアラーv3統合バックテスト")
    print("=" * 80)
    print()
    print("対象期間: 2025年1月1日～12月31日")
    print("方法: BeforeInfoScorerV3を使用してスコア再計算")
    print()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("[1/3] サンプルレース取得中...")
    race_ids = get_sample_races(cursor, limit=1000)
    print(f"OK {len(race_ids)}レース取得完了")
    print()

    print("[2/3] 各レースでv3スコア計算中...")

    confidence_stats = defaultdict(lambda: {
        'total': 0,
        'first_correct': 0,
        'trifecta_correct': 0
    })

    processed = 0
    for race_id in race_ids:
        processed += 1
        if processed % 100 == 0:
            print(f"  処理中: {processed}/{len(race_ids)}")

        scores = calculate_v3_scores_for_race(race_id)

        if not scores or len(scores) != 6:
            continue

        # スコア順にソート
        sorted_scores = sorted(scores, key=lambda x: x['v3_total_score'], reverse=True)

        # 1着予測
        predicted_pit = sorted_scores[0]['pit']
        predicted_score = sorted_scores[0]['v3_total_score']

        # 信頼度推定
        confidence = estimate_confidence_simple(predicted_score)

        # 実際の1着
        actual_winner_pit = next((s['pit'] for s in scores if s['finish_rank'] == 1), None)

        # 三連単予測
        predicted_top3 = [s['pit'] for s in sorted_scores[:3]]
        actual_top3 = sorted(
            [s for s in scores if s['finish_rank'] and s['finish_rank'] <= 3],
            key=lambda x: x['finish_rank']
        )
        actual_top3_pits = [s['pit'] for s in actual_top3] if len(actual_top3) == 3 else []

        # 統計更新
        confidence_stats[confidence]['total'] += 1

        if predicted_pit == actual_winner_pit:
            confidence_stats[confidence]['first_correct'] += 1

        if predicted_top3 == actual_top3_pits:
            confidence_stats[confidence]['trifecta_correct'] += 1

    print(f"OK {processed}レース処理完了")
    print()

    print("[3/3] 結果集計...")

    # 的中率計算
    v3_results = {}
    for conf, stats in confidence_stats.items():
        total = stats['total']
        if total > 0:
            v3_results[conf] = {
                'total': total,
                'first_correct': stats['first_correct'],
                'first_rate': stats['first_correct'] / total * 100,
                'trifecta_correct': stats['trifecta_correct'],
                'trifecta_rate': stats['trifecta_correct'] / total * 100
            }

    print()
    print("=" * 80)
    print("【バックテスト結果: 展示スコアラーv3統合】")
    print("=" * 80)
    print()

    print(f"{'信頼度':<8} {'レース数':>10} {'1着的中':>10} {'1着的中率':>12} {'三連単的中率':>14}")
    print("-" * 80)

    for conf in ['A', 'B', 'C', 'D', 'E']:
        if conf in v3_results:
            stat = v3_results[conf]
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
        if conf in v3_results and conf in BASELINE:
            v2_first = BASELINE[conf]['first_rate']
            v3_first = v3_results[conf]['first_rate']
            diff_first = v3_first - v2_first

            v2_trifecta = BASELINE[conf]['trifecta_rate']
            v3_trifecta = v3_results[conf]['trifecta_rate']
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
            print("[評価] ★★★ 大幅改善 - 展示スコアラーv3の本番導入を強く推奨")
        elif avg_improvement_first > 1.0:
            print("[評価] ★★☆ 明確な改善 - 展示スコアラーv3の本番導入を推奨")
        elif avg_improvement_first > 0:
            print("[評価] ★☆☆ 小幅改善 - 展示スコアラーv3の導入を検討")
        else:
            print("[評価] ☆☆☆ 改善なし - v2を維持")

        print()
        print("【特記事項】")

        # 信頼度A・Bの改善状況
        if 'A' in v3_results and 'B' in v3_results:
            a_improvement = v3_results['A']['first_rate'] - BASELINE['A']['first_rate']
            b_improvement = v3_results['B']['first_rate'] - BASELINE['B']['first_rate']

            print(f"- 信頼度A改善: {a_improvement:+.2f}pt ({BASELINE['A']['first_rate']:.2f}% → {v3_results['A']['first_rate']:.2f}%)")
            print(f"- 信頼度B改善: {b_improvement:+.2f}pt ({BASELINE['B']['first_rate']:.2f}% → {v3_results['B']['first_rate']:.2f}%)")

            if a_improvement > 0 and b_improvement > 0:
                print("- 主力信頼度（A・B）で改善確認 → ROI向上が期待できる")

    print()
    print("=" * 80)

    conn.close()

if __name__ == '__main__':
    main()
