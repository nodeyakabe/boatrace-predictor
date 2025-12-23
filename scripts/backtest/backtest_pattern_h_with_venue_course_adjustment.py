# -*- coding: utf-8 -*-
"""
パターンH + 会場コース調整 バックテストスクリプト

会場×コース別調整を適用した場合の効果を検証する。

検証内容:
1. 調整ON/OFF比較
2. 年度別（2024年/2025年）比較
3. 会場別効果分析
4. 調整による購入対象の変化

使用方法:
    python scripts/backtest_pattern_h_with_venue_course_adjustment.py

出力:
- 調整前後の収支比較
- 会場別効果サマリー
- 推奨設定
"""

import sqlite3
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional
from collections import defaultdict
import json

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from config.venue_course_adjustments import (
    VENUE_COURSE_ADJUSTMENTS,
    OVERALL_WIN_RATES,
    get_adjustment,
    get_all_adjustments,
    WEAK_IN_VENUES,
    STRONG_IN_VENUES,
)
from src.betting.venue_course_adjuster import VenueCourseAdjuster


def get_db_connection(db_path: str = None) -> sqlite3.Connection:
    """データベース接続を取得"""
    if db_path is None:
        db_path = project_root / "data" / "boatrace.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# 会場名マッピング
VENUE_NAMES = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
    '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
    '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
    '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
    '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村',
}


def get_pattern_h_races(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
    confidence_list: List[str] = ['C', 'D'],
    odds_min: float = 30.0,
    odds_max: float = 50.0,
) -> List[Dict]:
    """
    パターンHの購入対象レースを取得

    Args:
        conn: データベース接続
        start_date: 開始日
        end_date: 終了日
        confidence_list: 信頼度条件
        odds_min: 最低オッズ
        odds_max: 最大オッズ

    Returns:
        パターンH対象レースのリスト
    """
    confidence_placeholder = ','.join(['?'] * len(confidence_list))

    query = f"""
    WITH race_predictions_ranked AS (
        SELECT
            rp.race_id,
            rp.pit_number,
            rp.rank_prediction,
            rp.total_score,
            rp.confidence,
            rp.racer_name,
            r.venue_code,
            r.race_date,
            r.race_number,
            e.racer_rank
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        JOIN entries e ON r.id = e.race_id AND rp.pit_number = e.pit_number
        WHERE rp.rank_prediction IN (1, 2, 3, 4, 5)
          AND rp.confidence IN ({confidence_placeholder})
          AND r.race_date BETWEEN ? AND ?
    ),
    race_top3 AS (
        SELECT
            race_id,
            venue_code,
            race_date,
            race_number,
            confidence,
            MAX(CASE WHEN rank_prediction = 1 THEN pit_number END) as pred_1st,
            MAX(CASE WHEN rank_prediction = 2 THEN pit_number END) as pred_2nd,
            MAX(CASE WHEN rank_prediction = 3 THEN pit_number END) as pred_3rd,
            MAX(CASE WHEN rank_prediction = 4 THEN pit_number END) as pred_4th,
            MAX(CASE WHEN rank_prediction = 5 THEN pit_number END) as pred_5th,
            MAX(CASE WHEN rank_prediction = 1 THEN racer_rank END) as c1_rank,
            MAX(CASE WHEN rank_prediction = 1 THEN total_score END) as score_1st
        FROM race_predictions_ranked
        GROUP BY race_id
    ),
    race_results AS (
        SELECT
            race_id,
            MAX(CASE WHEN rank = '1' THEN pit_number END) as result_1st,
            MAX(CASE WHEN rank = '2' THEN pit_number END) as result_2nd,
            MAX(CASE WHEN rank = '3' THEN pit_number END) as result_3rd
        FROM results
        WHERE is_invalid = 0 AND rank IN ('1', '2', '3')
        GROUP BY race_id
    ),
    actual_courses AS (
        SELECT
            race_id,
            MAX(CASE WHEN pit_number = 1 THEN actual_course END) as course_pit1,
            MAX(CASE WHEN pit_number = 2 THEN actual_course END) as course_pit2,
            MAX(CASE WHEN pit_number = 3 THEN actual_course END) as course_pit3,
            MAX(CASE WHEN pit_number = 4 THEN actual_course END) as course_pit4,
            MAX(CASE WHEN pit_number = 5 THEN actual_course END) as course_pit5,
            MAX(CASE WHEN pit_number = 6 THEN actual_course END) as course_pit6
        FROM race_details
        WHERE actual_course IS NOT NULL
        GROUP BY race_id
    )
    SELECT
        rt.race_id,
        rt.venue_code,
        rt.race_date,
        rt.race_number,
        rt.confidence,
        rt.pred_1st,
        rt.pred_2nd,
        rt.pred_3rd,
        rt.pred_4th,
        rt.pred_5th,
        rt.c1_rank,
        rt.score_1st,
        rr.result_1st,
        rr.result_2nd,
        rr.result_3rd,
        t.combination as combo_123,
        t.odds as odds_123,
        t4.odds as odds_124,
        t5.odds as odds_125,
        ac.course_pit1,
        ac.course_pit2,
        ac.course_pit3,
        ac.course_pit4,
        ac.course_pit5,
        ac.course_pit6
    FROM race_top3 rt
    LEFT JOIN race_results rr ON rt.race_id = rr.race_id
    LEFT JOIN actual_courses ac ON rt.race_id = ac.race_id
    LEFT JOIN trifecta_odds t ON rt.race_id = t.race_id
        AND t.combination = rt.pred_1st || '-' || rt.pred_2nd || '-' || rt.pred_3rd
    LEFT JOIN trifecta_odds t4 ON rt.race_id = t4.race_id
        AND t4.combination = rt.pred_1st || '-' || rt.pred_2nd || '-' || rt.pred_4th
    LEFT JOIN trifecta_odds t5 ON rt.race_id = t5.race_id
        AND t5.combination = rt.pred_1st || '-' || rt.pred_2nd || '-' || rt.pred_5th
    WHERE rt.c1_rank IN ('A1', 'A2', 'B1')
      AND rr.result_1st IS NOT NULL
    ORDER BY rt.race_date, rt.race_number
    """

    params = list(confidence_list) + [start_date, end_date]
    cursor = conn.execute(query, params)
    rows = cursor.fetchall()

    races = []
    for row in rows:
        # パターンH対象条件チェック
        odds_123 = row['odds_123'] or 0
        odds_124 = row['odds_124'] or 0
        odds_125 = row['odds_125'] or 0

        # 最低1つのオッズが条件範囲内
        has_valid_odds = any(odds_min <= o < odds_max for o in [odds_123, odds_124, odds_125])
        if not has_valid_odds:
            continue

        # 1着予測の実際のコースを取得
        pred_1st = row['pred_1st']
        actual_course_1st = None
        if pred_1st is not None:
            course_key = f'course_pit{pred_1st}'
            actual_course_1st = row[course_key]

        races.append({
            'race_id': row['race_id'],
            'venue_code': row['venue_code'],
            'venue_name': VENUE_NAMES.get(row['venue_code'], '不明'),
            'race_date': row['race_date'],
            'race_number': row['race_number'],
            'confidence': row['confidence'],
            'pred_1st': pred_1st,
            'pred_2nd': row['pred_2nd'],
            'pred_3rd': row['pred_3rd'],
            'pred_4th': row['pred_4th'],
            'pred_5th': row['pred_5th'],
            'c1_rank': row['c1_rank'],
            'score_1st': row['score_1st'],
            'result_1st': row['result_1st'],
            'result_2nd': row['result_2nd'],
            'result_3rd': row['result_3rd'],
            'odds_123': odds_123,
            'odds_124': odds_124,
            'odds_125': odds_125,
            'actual_course_1st': actual_course_1st or pred_1st,  # コース情報がなければpit_numberを使用
        })

    return races


def simulate_pattern_h(
    races: List[Dict],
    with_adjustment: bool = False,
    adjuster: Optional[VenueCourseAdjuster] = None,
    adjustment_threshold: int = -5,  # このデバフ以下なら購入を減額/スキップ
    buff_threshold: int = 5,         # このバフ以上なら購入を増額
) -> Dict[str, Any]:
    """
    パターンHのシミュレーション

    Args:
        races: レースデータ
        with_adjustment: 調整を適用するか
        adjuster: VenueCourseAdjusterインスタンス
        adjustment_threshold: デバフ閾値
        buff_threshold: バフ閾値

    Returns:
        シミュレーション結果
    """
    # パターンH: 1-2-3:200円, 1-2-4:100円, 1-2-5:100円
    BASE_BET = {'123': 200, '124': 100, '125': 100}

    stats = {
        'total_races': 0,
        'purchased_races': 0,
        'skipped_races': 0,
        'hit_count': 0,
        'total_bet': 0,
        'total_payout': 0,
        'hits': [],
        'by_venue': defaultdict(lambda: {
            'races': 0, 'purchased': 0, 'hits': 0, 'bet': 0, 'payout': 0
        }),
        'by_adjustment': defaultdict(lambda: {
            'races': 0, 'hits': 0, 'bet': 0, 'payout': 0
        }),
    }

    for race in races:
        stats['total_races'] += 1
        venue_code = race['venue_code']
        venue_name = race['venue_name']

        # 調整値を計算
        adjustment = 0
        if with_adjustment and adjuster:
            course = race['actual_course_1st'] or race['pred_1st']
            if course:
                adjustment = adjuster.get_adjustment(venue_code, course)

        # 購入判定
        skip_race = False
        bet_multiplier = 1.0

        if with_adjustment:
            if adjustment <= adjustment_threshold:
                # 強いデバフ: 購入をスキップ
                skip_race = True
            elif adjustment >= buff_threshold:
                # 強いバフ: 購入を増額（1.5倍）
                bet_multiplier = 1.5
            elif adjustment < 0:
                # 軽いデバフ: 購入を減額（0.7倍）
                bet_multiplier = 0.7

        if skip_race:
            stats['skipped_races'] += 1
            continue

        stats['purchased_races'] += 1
        stats['by_venue'][venue_code]['races'] += 1
        stats['by_venue'][venue_code]['purchased'] += 1

        # 調整値カテゴリ
        adj_category = f"{adjustment:+d}pt" if adjustment != 0 else "0pt"
        stats['by_adjustment'][adj_category]['races'] += 1

        # 実際の結果
        result_combo = f"{race['result_1st']}-{race['result_2nd']}-{race['result_3rd']}"

        # 各買い目の結果
        pred_1st = race['pred_1st']
        pred_2nd = race['pred_2nd']
        pred_3rd = race['pred_3rd']
        pred_4th = race['pred_4th']
        pred_5th = race['pred_5th']

        combos = [
            (f"{pred_1st}-{pred_2nd}-{pred_3rd}", '123', race['odds_123']),
            (f"{pred_1st}-{pred_2nd}-{pred_4th}", '124', race['odds_124']),
            (f"{pred_1st}-{pred_2nd}-{pred_5th}", '125', race['odds_125']),
        ]

        race_bet = 0
        race_payout = 0

        for combo, key, odds in combos:
            bet_amount = int(BASE_BET[key] * bet_multiplier)
            race_bet += bet_amount

            if combo == result_combo and odds > 0:
                payout = int(bet_amount * odds / 100) * 100  # 100円単位
                race_payout += payout
                stats['hit_count'] += 1
                stats['hits'].append({
                    'race': race,
                    'combo': combo,
                    'odds': odds,
                    'payout': payout,
                    'adjustment': adjustment,
                })
                stats['by_venue'][venue_code]['hits'] += 1
                stats['by_adjustment'][adj_category]['hits'] += 1

        stats['total_bet'] += race_bet
        stats['total_payout'] += race_payout
        stats['by_venue'][venue_code]['bet'] += race_bet
        stats['by_venue'][venue_code]['payout'] += race_payout
        stats['by_adjustment'][adj_category]['bet'] += race_bet
        stats['by_adjustment'][adj_category]['payout'] += race_payout

    # 統計計算
    stats['profit'] = stats['total_payout'] - stats['total_bet']
    stats['roi'] = (stats['total_payout'] / stats['total_bet'] * 100) if stats['total_bet'] > 0 else 0
    stats['hit_rate'] = (stats['hit_count'] / stats['purchased_races'] * 100) if stats['purchased_races'] > 0 else 0

    return stats


def print_comparison_report(
    stats_without: Dict,
    stats_with: Dict,
    year: str
):
    """比較レポートを出力"""
    print(f"\n{'='*80}")
    print(f"{year} パターンH + 会場コース調整 バックテスト結果")
    print(f"{'='*80}")

    print(f"\n{'='*50}")
    print("1. 全体比較")
    print(f"{'='*50}")

    print(f"\n{'項目':<20} {'調整なし':>15} {'調整あり':>15} {'差分':>15}")
    print("-" * 70)

    metrics = [
        ('対象レース数', 'total_races', '', 0),
        ('購入レース数', 'purchased_races', '', 0),
        ('スキップ数', 'skipped_races', '', 0),
        ('的中数', 'hit_count', '回', 0),
        ('的中率', 'hit_rate', '%', 1),
        ('投資額', 'total_bet', '円', 0),
        ('払戻額', 'total_payout', '円', 0),
        ('収支', 'profit', '円', 0),
        ('ROI', 'roi', '%', 1),
    ]

    for name, key, unit, decimals in metrics:
        val_without = stats_without.get(key, 0)
        val_with = stats_with.get(key, 0)
        diff = val_with - val_without

        if decimals > 0:
            print(f"{name:<20} {val_without:>12.{decimals}f}{unit:<3} {val_with:>12.{decimals}f}{unit:<3} {diff:>+12.{decimals}f}{unit}")
        else:
            print(f"{name:<20} {val_without:>12,}{unit:<3} {val_with:>12,}{unit:<3} {diff:>+12,}{unit}")

    print(f"\n{'='*50}")
    print("2. 会場別効果")
    print(f"{'='*50}")

    # 会場別の効果を計算
    venue_effects = []
    for venue_code in VENUE_NAMES.keys():
        v_without = stats_without['by_venue'].get(venue_code, {})
        v_with = stats_with['by_venue'].get(venue_code, {})

        races_without = v_without.get('races', 0)
        races_with = v_with.get('purchased', 0)
        profit_without = v_without.get('payout', 0) - v_without.get('bet', 0)
        profit_with = v_with.get('payout', 0) - v_with.get('bet', 0)

        if races_without > 0 or races_with > 0:
            # 調整値を取得
            adj = get_adjustment(venue_code, 1)

            venue_effects.append({
                'code': venue_code,
                'name': VENUE_NAMES[venue_code],
                'adj_c1': adj,
                'races_without': races_without,
                'races_with': races_with,
                'profit_without': profit_without,
                'profit_with': profit_with,
                'profit_diff': profit_with - profit_without,
            })

    # 効果順にソート
    venue_effects.sort(key=lambda x: x['profit_diff'], reverse=True)

    print(f"\n{'会場':<8} {'調整':>6} {'レース(前)':>10} {'レース(後)':>10} {'収支(前)':>12} {'収支(後)':>12} {'差分':>12}")
    print("-" * 80)

    for v in venue_effects:
        if v['races_without'] > 0:
            adj_str = f"{v['adj_c1']:+d}pt"
            print(f"{v['name']:<8} {adj_str:>6} {v['races_without']:>10} {v['races_with']:>10} "
                  f"{v['profit_without']:>+12,} {v['profit_with']:>+12,} {v['profit_diff']:>+12,}")

    print(f"\n{'='*50}")
    print("3. 調整値別効果（調整あり時）")
    print(f"{'='*50}")

    adj_stats = list(stats_with['by_adjustment'].items())
    adj_stats.sort(key=lambda x: int(x[0].replace('pt', '').replace('+', '')))

    print(f"\n{'調整値':<10} {'レース数':>10} {'的中数':>10} {'投資額':>12} {'払戻額':>12} {'ROI':>10}")
    print("-" * 70)

    for adj_val, data in adj_stats:
        if data['races'] > 0:
            roi = (data['payout'] / data['bet'] * 100) if data['bet'] > 0 else 0
            print(f"{adj_val:<10} {data['races']:>10} {data['hits']:>10} "
                  f"{data['bet']:>12,} {data['payout']:>12,} {roi:>9.1f}%")

    # 改善効果サマリー
    improvement = stats_with['profit'] - stats_without['profit']
    print(f"\n{'='*50}")
    print("4. サマリー")
    print(f"{'='*50}")
    print(f"\n収支改善額: {improvement:+,}円")
    print(f"ROI改善: {stats_with['roi'] - stats_without['roi']:+.1f}%")

    if improvement > 0:
        print("\n[結論] 会場コース調整は効果的です。")
    else:
        print("\n[結論] 会場コース調整の効果は限定的です。パラメータ調整を検討してください。")


def run_parameter_search(
    conn: sqlite3.Connection,
    races_2024: List[Dict],
    races_2025: List[Dict],
):
    """パラメータ最適化探索"""
    adjuster = VenueCourseAdjuster(enabled=True, adjustment_scale=1.0)

    print(f"\n{'='*80}")
    print("パラメータ最適化探索")
    print(f"{'='*80}")

    results = []
    threshold_values = [-12, -10, -8, -5]
    buff_values = [3, 5, 8, 10]

    for skip_thresh in threshold_values:
        for buff_thresh in buff_values:
            # 2024年
            stats_2024 = simulate_pattern_h(
                races_2024,
                with_adjustment=True,
                adjuster=adjuster,
                adjustment_threshold=skip_thresh,
                buff_threshold=buff_thresh,
            )
            # 2025年
            stats_2025 = simulate_pattern_h(
                races_2025,
                with_adjustment=True,
                adjuster=adjuster,
                adjustment_threshold=skip_thresh,
                buff_threshold=buff_thresh,
            )

            total_profit = stats_2024['profit'] + stats_2025['profit']
            total_bet = stats_2024['total_bet'] + stats_2025['total_bet']
            total_roi = (stats_2024['total_payout'] + stats_2025['total_payout']) / total_bet * 100 if total_bet > 0 else 0

            results.append({
                'skip_thresh': skip_thresh,
                'buff_thresh': buff_thresh,
                'profit_2024': stats_2024['profit'],
                'profit_2025': stats_2025['profit'],
                'total_profit': total_profit,
                'total_roi': total_roi,
                'skipped_2024': stats_2024['skipped_races'],
                'skipped_2025': stats_2025['skipped_races'],
            })

    # ベースライン（調整なし）
    stats_2024_base = simulate_pattern_h(races_2024, with_adjustment=False)
    stats_2025_base = simulate_pattern_h(races_2025, with_adjustment=False)
    base_profit = stats_2024_base['profit'] + stats_2025_base['profit']
    base_total_bet = stats_2024_base['total_bet'] + stats_2025_base['total_bet']
    base_roi = (stats_2024_base['total_payout'] + stats_2025_base['total_payout']) / base_total_bet * 100

    print(f"\nベースライン（調整なし）: 収支 {base_profit:+,}円, ROI {base_roi:.1f}%")
    print(f"\n{'スキップ閾値':>12} {'バフ閾値':>10} {'2024収支':>12} {'2025収支':>12} {'合計収支':>12} {'ROI':>8} {'改善額':>12}")
    print("-" * 90)

    results.sort(key=lambda x: x['total_profit'], reverse=True)

    for r in results:
        improvement = r['total_profit'] - base_profit
        print(f"{r['skip_thresh']:>12}pt {r['buff_thresh']:>10}pt "
              f"{r['profit_2024']:>+12,} {r['profit_2025']:>+12,} "
              f"{r['total_profit']:>+12,} {r['total_roi']:>7.1f}% {improvement:>+12,}")

    # 最適パラメータ
    best = results[0]
    print(f"\n最適パラメータ: スキップ閾値={best['skip_thresh']}pt, バフ閾値={best['buff_thresh']}pt")
    print(f"  改善額: {best['total_profit'] - base_profit:+,}円")

    return best


def main():
    """メイン処理"""
    print("パターンH + 会場コース調整 バックテストを開始します...")

    conn = get_db_connection()
    adjuster = VenueCourseAdjuster(enabled=True, adjustment_scale=1.0)

    try:
        # 2024年のテスト
        print("\n2024年データを分析中...")
        races_2024 = get_pattern_h_races(
            conn,
            start_date="2024-01-01",
            end_date="2024-12-31",
            confidence_list=['C', 'D'],
            odds_min=30.0,
            odds_max=50.0,
        )
        print(f"  対象レース数: {len(races_2024)}")

        stats_2024_without = simulate_pattern_h(races_2024, with_adjustment=False)
        stats_2024_with = simulate_pattern_h(
            races_2024,
            with_adjustment=True,
            adjuster=adjuster,
            adjustment_threshold=-10,  # -10pt以下でスキップ（緩めに設定）
            buff_threshold=8,          # +8pt以上で増額（控えめに設定）
        )

        print_comparison_report(stats_2024_without, stats_2024_with, "2024年")

        # 2025年のテスト
        print("\n2025年データを分析中...")
        races_2025 = get_pattern_h_races(
            conn,
            start_date="2025-01-01",
            end_date="2025-12-31",
            confidence_list=['C', 'D'],
            odds_min=30.0,
            odds_max=50.0,
        )
        print(f"  対象レース数: {len(races_2025)}")

        stats_2025_without = simulate_pattern_h(races_2025, with_adjustment=False)
        stats_2025_with = simulate_pattern_h(
            races_2025,
            with_adjustment=True,
            adjuster=adjuster,
            adjustment_threshold=-10,
            buff_threshold=8,
        )

        print_comparison_report(stats_2025_without, stats_2025_with, "2025年")

        # パラメータ最適化探索
        best_params = run_parameter_search(conn, races_2024, races_2025)

        # 総合サマリー
        print(f"\n{'='*80}")
        print("総合サマリー（2024-2025年）")
        print(f"{'='*80}")

        total_improvement = (
            (stats_2024_with['profit'] - stats_2024_without['profit']) +
            (stats_2025_with['profit'] - stats_2025_without['profit'])
        )
        print(f"\n2年間総合収支改善額: {total_improvement:+,}円")

        # 最も効果のあった会場
        print("\n[インが弱い会場での効果]")
        for venue_code in WEAK_IN_VENUES:
            adj = get_adjustment(venue_code, 1)
            print(f"  {VENUE_NAMES[venue_code]}({venue_code}): 1コース調整 {adj:+d}pt")

        print("\n[インが強い会場での効果]")
        for venue_code in STRONG_IN_VENUES:
            adj = get_adjustment(venue_code, 1)
            print(f"  {VENUE_NAMES[venue_code]}({venue_code}): 1コース調整 {adj:+d}pt")

    finally:
        conn.close()

    print("\nバックテスト完了！")


if __name__ == "__main__":
    main()
