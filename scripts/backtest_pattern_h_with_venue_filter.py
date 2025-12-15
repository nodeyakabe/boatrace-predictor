#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
パターンH複数点買いバックテスト（風速・会場フィルター比較版）

2024-2025年データで風速・会場フィルターの効果を検証
"""
import sys
from pathlib import Path
import sqlite3

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus, MultiBetPattern

def run_backtest(year: int, enable_venue_wind_filter: bool):
    """
    指定年のバックテストを実行

    Args:
        year: 対象年（2024 or 2025）
        enable_venue_wind_filter: 風速・会場フィルターを有効化するか

    Returns:
        統計情報の辞書
    """
    # データベース接続
    conn = sqlite3.connect('data/boatrace.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 評価器初期化
    evaluator = BetTargetEvaluator(
        use_multi_bet=True,
        multi_bet_pattern=MultiBetPattern.PATTERN_H,
        enable_venue_wind_filter=enable_venue_wind_filter
    )

    # 対象年のレースを取得
    cursor.execute("""
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= ? AND r.race_date <= ?
        ORDER BY r.race_date, r.venue_code, r.race_number
    """, (f'{year}-01-01', f'{year}-12-31'))
    races = cursor.fetchall()

    # 統計情報
    stats = {
        'target_count': 0,
        'total_investment': 0,
        'total_return': 0,
        'hit_count': 0,
        'excluded_by_venue_wind': 0,
        'excluded_by_other': 0,
    }

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0

        # 1コース級別
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

        # 予測情報
        cursor.execute('''
            SELECT pit_number, confidence, rank_prediction
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY rank_prediction
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        confidence = preds[0]['confidence']
        old_pred = [preds[0]['pit_number'], preds[1]['pit_number'], preds[2]['pit_number']]
        full_prediction = [p['pit_number'] for p in preds]

        # オッズ取得
        cursor.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id = ?', (race_id,))
        odds_rows = cursor.fetchall()
        odds_dict = {row['combination']: row['odds'] for row in odds_rows}

        if not odds_dict:
            continue

        # 気象データ取得（venue_code + race_dateで結合）
        race_date = race['race_date']
        cursor.execute('''
            SELECT wind_speed
            FROM weather
            WHERE venue_code = ? AND weather_date = ?
        ''', (f"{venue_code:02d}", race_date))
        weather = cursor.fetchone()
        wind_speed = weather['wind_speed'] if weather and weather['wind_speed'] is not None else 0.0

        # 購入対象判定
        predictions_dict = {
            'confidence': confidence,
            'old_prediction': old_pred,
            'new_prediction': old_pred,
            'full_prediction': full_prediction,
        }
        race_data = {
            'venue_code': venue_code,
            'wind_speed': wind_speed,
            'entries': [{'pit_number': 1, 'racer_rank': c1_rank}],
        }

        target = evaluator.evaluate_race(
            race_data=race_data,
            predictions=predictions_dict,
            odds_data=odds_dict,
            has_beforeinfo=True
        )

        # 除外理由を記録
        if target.status == BetStatus.EXCLUDED:
            if '風速・会場除外' in target.reason:
                stats['excluded_by_venue_wind'] += 1
            else:
                stats['excluded_by_other'] += 1
            continue

        if target.status != BetStatus.TARGET_CONFIRMED or not target.multi_bet_result:
            continue

        # 結果取得
        cursor.execute('''
            SELECT pit_number, rank
            FROM results
            WHERE race_id = ? AND is_invalid = 0
            ORDER BY CAST(rank AS INTEGER)
            LIMIT 3
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) < 3:
            continue

        actual = [results[0]['pit_number'], results[1]['pit_number'], results[2]['pit_number']]
        actual_combo = f"{actual[0]}-{actual[1]}-{actual[2]}"

        # 統計更新
        stats['target_count'] += 1

        # 各買い目を処理
        for bet in target.multi_bet_result.bets:
            stats['total_investment'] += bet.bet_amount

            if bet.combination == actual_combo:
                stats['total_return'] += bet.bet_amount * bet.odds
                stats['hit_count'] += 1

    conn.close()
    return stats

# メイン処理
print("=" * 100)
print("パターンH 風速・会場フィルター効果検証（2024-2025年）")
print("=" * 100)
print()

for year in [2024, 2025]:
    print(f"{'=' * 100}")
    print(f"{year}年バックテスト結果")
    print(f"{'=' * 100}")
    print()

    # フィルター無効版
    print(f"【{year}年 - フィルター無効】")
    stats_no_filter = run_backtest(year, enable_venue_wind_filter=False)

    print(f"  購入レース数: {stats_no_filter['target_count']:,}件")
    print(f"  総投資額: {stats_no_filter['total_investment']:,}円")
    print(f"  総払戻額: {stats_no_filter['total_return']:,.0f}円")
    balance_no_filter = stats_no_filter['total_return'] - stats_no_filter['total_investment']
    print(f"  収支: {balance_no_filter:+,.0f}円")

    if stats_no_filter['total_investment'] > 0:
        roi_no_filter = stats_no_filter['total_return'] / stats_no_filter['total_investment'] * 100
        print(f"  ROI: {roi_no_filter:.1f}%")

    if stats_no_filter['target_count'] > 0:
        hit_rate_no_filter = stats_no_filter['hit_count'] / stats_no_filter['target_count'] * 100
        print(f"  的中数: {stats_no_filter['hit_count']}回")
        print(f"  的中率: {hit_rate_no_filter:.2f}%")
    print()

    # フィルター有効版
    print(f"【{year}年 - フィルター有効】")
    stats_filter = run_backtest(year, enable_venue_wind_filter=True)

    print(f"  購入レース数: {stats_filter['target_count']:,}件")
    print(f"  総投資額: {stats_filter['total_investment']:,}円")
    print(f"  総払戻額: {stats_filter['total_return']:,.0f}円")
    balance_filter = stats_filter['total_return'] - stats_filter['total_investment']
    print(f"  収支: {balance_filter:+,.0f}円")

    if stats_filter['total_investment'] > 0:
        roi_filter = stats_filter['total_return'] / stats_filter['total_investment'] * 100
        print(f"  ROI: {roi_filter:.1f}%")

    if stats_filter['target_count'] > 0:
        hit_rate_filter = stats_filter['hit_count'] / stats_filter['target_count'] * 100
        print(f"  的中数: {stats_filter['hit_count']}回")
        print(f"  的中率: {hit_rate_filter:.2f}%")

    print()
    print(f"  除外レース数（風速・会場）: {stats_filter['excluded_by_venue_wind']}件")
    print(f"  除外レース数（その他）: {stats_filter['excluded_by_other']}件")
    print()

    # 改善効果
    if stats_no_filter['total_investment'] > 0 and stats_filter['total_investment'] > 0:
        print("【改善効果】")
        race_diff = stats_filter['target_count'] - stats_no_filter['target_count']
        balance_diff = balance_filter - balance_no_filter
        roi_diff = roi_filter - roi_no_filter
        hit_rate_diff = hit_rate_filter - hit_rate_no_filter

        print(f"  購入レース数変化: {race_diff:+,}件")
        print(f"  収支改善: {balance_diff:+,.0f}円")
        print(f"  ROI改善: {roi_diff:+.1f}pt")
        print(f"  的中率改善: {hit_rate_diff:+.2f}pt")
    print()

print("=" * 100)
print("バックテスト完了")
print("=" * 100)
