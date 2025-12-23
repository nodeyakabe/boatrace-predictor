#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
展示スコアラーv3 実データテストスクリプト

目的:
- 2025年実レースデータでv2とv3を比較
- スコア分布の変化を確認
- 的中率・ROIへの影響を検証
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from datetime import datetime
from collections import defaultdict
from src.scoring.exhibition_scorer_v2 import ExhibitionScorerV2
from src.scoring.exhibition_scorer_v3 import ExhibitionScorerV3

DB_PATH = "data/boatrace.db"

def get_test_races(cursor, limit=1000):
    """テスト用レースデータ取得（2025年から1000レース）"""
    cursor.execute("""
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
        WHERE r.race_date >= '2025-01-01'
        AND rd.exhibition_time IS NOT NULL
        AND res.rank IS NOT NULL
        ORDER BY r.race_date, r.id, rd.pit_number
        LIMIT ?
    """, (limit * 6,))  # 1レース6艇

    races = defaultdict(list)
    for row in cursor.fetchall():
        races[row[0]].append({
            'race_id': row[0],
            'venue_code': row[1],
            'pit_number': row[2],
            'exhibition_time': row[3],
            'st_time': row[4],
            'actual_course': row[5],
            'racer_rank': row[6],
            'finish_rank': int(row[7])
        })

    return races

def compare_scorers(races):
    """v2とv3のスコアを比較"""
    scorer_v2 = ExhibitionScorerV2()
    scorer_v3 = ExhibitionScorerV3()

    v2_scores = []
    v3_scores = []
    score_diffs = []

    v2_top1_correct = 0
    v3_top1_correct = 0
    v2_top3_hits = 0
    v3_top3_hits = 0
    total_races = 0

    for race_id, racers in races.items():
        if len(racers) != 6:
            continue

        total_races += 1

        # 全艇の展示タイムマップ作成（v2用）
        exhibition_times = {r['pit_number']: r['exhibition_time'] for r in racers}

        # v2スコア計算
        v2_results = []
        for racer in racers:
            beforeinfo = {
                'exhibition_times': exhibition_times
            }
            racer_data = {'rank': racer['racer_rank']}

            score_v2 = scorer_v2.calculate_exhibition_score(
                racer['venue_code'],
                racer['pit_number'],
                beforeinfo,
                racer_data
            )

            v2_results.append({
                'pit': racer['pit_number'],
                'score': score_v2['exhibition_score'],
                'finish_rank': racer['finish_rank']
            })
            v2_scores.append(score_v2['exhibition_score'])

        # v3スコア計算
        v3_results = []
        for racer in racers:
            beforeinfo = {
                'exhibition_times': exhibition_times
            }
            racer_data = {'rank': racer['racer_rank']}

            score_v3 = scorer_v3.calculate_exhibition_score(
                racer['venue_code'],
                racer['pit_number'],
                beforeinfo,
                racer_data,
                actual_course=racer['actual_course'],
                st_time=racer['st_time']
            )

            v3_results.append({
                'pit': racer['pit_number'],
                'score': score_v3['exhibition_score'],
                'finish_rank': racer['finish_rank'],
                'bonuses': score_v3.get('bonuses', {})
            })
            v3_scores.append(score_v3['exhibition_score'])

        # スコア差分計算
        for v2_r, v3_r in zip(v2_results, v3_results):
            score_diffs.append(v3_r['score'] - v2_r['score'])

        # v2予測（スコア最高を1着予測）
        v2_sorted = sorted(v2_results, key=lambda x: x['score'], reverse=True)
        if v2_sorted[0]['finish_rank'] == 1:
            v2_top1_correct += 1
        if any(r['finish_rank'] <= 3 for r in v2_sorted[:3]):
            v2_top3_hits += 1

        # v3予測
        v3_sorted = sorted(v3_results, key=lambda x: x['score'], reverse=True)
        if v3_sorted[0]['finish_rank'] == 1:
            v3_top1_correct += 1
        if any(r['finish_rank'] <= 3 for r in v3_sorted[:3]):
            v3_top3_hits += 1

    return {
        'total_races': total_races,
        'v2_scores': v2_scores,
        'v3_scores': v3_scores,
        'score_diffs': score_diffs,
        'v2_top1_correct': v2_top1_correct,
        'v3_top1_correct': v3_top1_correct,
        'v2_top3_hits': v2_top3_hits,
        'v3_top3_hits': v3_top3_hits
    }

def analyze_bonus_impact(races):
    """v3のボーナス影響分析"""
    scorer_v3 = ExhibitionScorerV3()

    bonus_stats = {
        'course_coef': defaultdict(list),
        'time_gap': defaultdict(int),
        'rank_exh': defaultdict(int),
        'triple': defaultdict(int)
    }

    for race_id, racers in races.items():
        if len(racers) != 6:
            continue

        # 全艇の展示タイムマップ作成
        exhibition_times = {r['pit_number']: r['exhibition_time'] for r in racers}

        for racer in racers:
            beforeinfo = {
                'exhibition_times': exhibition_times
            }
            racer_data = {'rank': racer['racer_rank']}

            result = scorer_v3.calculate_exhibition_score(
                racer['venue_code'],
                racer['pit_number'],
                beforeinfo,
                racer_data,
                actual_course=racer['actual_course'],
                st_time=racer['st_time']
            )

            bonuses = result.get('bonuses', {})

            # コース係数
            course = racer['actual_course']
            if course and 'course_coefficient' in bonuses:
                bonus_stats['course_coef'][course].append(bonuses['course_coefficient'])

            # 時間差ボーナス
            if 'time_gap_bonus' in bonuses and bonuses['time_gap_bonus'] > 0:
                bonus_stats['time_gap'][bonuses['time_gap_bonus']] += 1

            # 級別×展示ボーナス
            if 'rank_exhibition_bonus' in bonuses and bonuses['rank_exhibition_bonus'] > 0:
                bonus_stats['rank_exh'][bonuses['rank_exhibition_bonus']] += 1

            # 三重複合ボーナス
            if 'triple_bonus' in bonuses and bonuses['triple_bonus'] > 0:
                bonus_stats['triple'][bonuses['triple_bonus']] += 1

    return bonus_stats

def main():
    # UTF-8出力設定
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 60)
    print("展示スコアラーv3 実データテスト")
    print("=" * 60)
    print()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("[1/3] テストレースデータ取得中...")
    races = get_test_races(cursor, limit=1000)
    print(f"OK {len(races)}レース取得完了")
    print()

    print("[2/3] v2 vs v3 スコア比較中...")
    comparison = compare_scorers(races)

    print(f"対象レース数: {comparison['total_races']}")
    print()

    print("【スコア分布統計】")
    import statistics
    print(f"v2 平均: {statistics.mean(comparison['v2_scores']):.2f}")
    print(f"v2 標準偏差: {statistics.stdev(comparison['v2_scores']):.2f}")
    print(f"v2 範囲: {min(comparison['v2_scores']):.2f} ～ {max(comparison['v2_scores']):.2f}")
    print()
    print(f"v3 平均: {statistics.mean(comparison['v3_scores']):.2f}")
    print(f"v3 標準偏差: {statistics.stdev(comparison['v3_scores']):.2f}")
    print(f"v3 範囲: {min(comparison['v3_scores']):.2f} ～ {max(comparison['v3_scores']):.2f}")
    print()
    print(f"スコア差分（v3-v2）平均: {statistics.mean(comparison['score_diffs']):.2f}")
    print(f"スコア差分 標準偏差: {statistics.stdev(comparison['score_diffs']):.2f}")
    print()

    print("【的中率比較】")
    v2_top1_rate = comparison['v2_top1_correct'] / comparison['total_races'] * 100
    v3_top1_rate = comparison['v3_top1_correct'] / comparison['total_races'] * 100
    v2_top3_rate = comparison['v2_top3_hits'] / comparison['total_races'] * 100
    v3_top3_rate = comparison['v3_top3_hits'] / comparison['total_races'] * 100

    print(f"v2 1着的中率: {v2_top1_rate:.2f}% ({comparison['v2_top1_correct']}/{comparison['total_races']})")
    print(f"v3 1着的中率: {v3_top1_rate:.2f}% ({comparison['v3_top1_correct']}/{comparison['total_races']})")
    print(f"差分: {v3_top1_rate - v2_top1_rate:+.2f}pt")
    print()
    print(f"v2 三連単圏内率: {v2_top3_rate:.2f}% ({comparison['v2_top3_hits']}/{comparison['total_races']})")
    print(f"v3 三連単圏内率: {v3_top3_rate:.2f}% ({comparison['v3_top3_hits']}/{comparison['total_races']})")
    print(f"差分: {v3_top3_rate - v2_top3_rate:+.2f}pt")
    print()

    print("[3/3] ボーナス影響分析中...")
    bonus_stats = analyze_bonus_impact(races)

    print("【コース係数適用状況】")
    for course in sorted(bonus_stats['course_coef'].keys()):
        count = len(bonus_stats['course_coef'][course])
        avg_coef = statistics.mean(bonus_stats['course_coef'][course])
        print(f"コース{course}: {count}回適用（平均係数: {avg_coef:.2f}）")
    print()

    print("【時間差ボーナス適用状況】")
    for bonus_val, count in sorted(bonus_stats['time_gap'].items(), reverse=True):
        print(f"+{bonus_val:.1f}点: {count}回")
    print()

    print("【級別×展示ボーナス適用状況】")
    for bonus_val, count in sorted(bonus_stats['rank_exh'].items(), reverse=True):
        print(f"+{bonus_val:.1f}点: {count}回")
    print()

    print("【三重複合ボーナス適用状況】")
    for bonus_val, count in sorted(bonus_stats['triple'].items(), reverse=True):
        print(f"+{bonus_val:.1f}点: {count}回")
    print()

    print("=" * 60)
    print("テスト完了")
    print("=" * 60)

    # 判定
    if v3_top1_rate > v2_top1_rate:
        print(f"[OK] v3が{v3_top1_rate - v2_top1_rate:.2f}pt改善しました")
    elif v3_top1_rate == v2_top1_rate:
        print("[=] v3とv2の精度は同等です")
    else:
        print(f"[NG] v3がv2より{v2_top1_rate - v3_top1_rate:.2f}pt低下しました")

    conn.close()

if __name__ == '__main__':
    main()
