#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
日次ベッティング実行スクリプト（パターンH対応版）

当日のレースを分析し、購入推奨レースをリストアップする
複数点買い（パターンH）対応
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus, MultiBetPattern

def main():
    today = datetime.now().strftime('%Y-%m-%d')

    print("=" * 100)
    print(f"日次ベッティング分析（パターンH）- {today}")
    print("=" * 100)
    print()

    # データベース接続
    conn = sqlite3.connect('data/boatrace.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 評価器初期化（パターンH有効化）
    evaluator = BetTargetEvaluator(
        use_multi_bet=True,
        multi_bet_pattern=MultiBetPattern.PATTERN_H
    )

    print("設定: パターンH（1-2軸3点傾斜配分）")
    print("  - 1-2-3: 200円")
    print("  - 1-2-4: 100円")
    print("  - 1-2-5: 100円")
    print("  合計: 400円/レース")
    print()

    # 当日のレースを取得
    cursor.execute("""
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date = ?
        ORDER BY r.venue_code, r.race_number
    """, (today,))
    races = cursor.fetchall()

    if not races:
        print(f"【注意】{today}のレースデータが見つかりません")
        print("データ収集を実行してください:")
        print("  python scripts/fetch_today_races.py")
        conn.close()
        return

    print(f"本日のレース数: {len(races)}件")
    print()

    # 購入推奨リスト
    targets = []

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0
        race_number = race['race_number']

        # 1コース級別
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

        # 予測情報（直前情報 = before）
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

        # 購入対象判定
        predictions_dict = {
            'confidence': confidence,
            'old_prediction': old_pred,
            'new_prediction': old_pred,
            'full_prediction': full_prediction,
        }
        race_data = {
            'venue_code': venue_code,
            'entries': [{'pit_number': 1, 'racer_rank': c1_rank}],
        }

        target = evaluator.evaluate_race(
            race_data=race_data,
            predictions=predictions_dict,
            odds_data=odds_dict,
            has_beforeinfo=True
        )

        if target.status == BetStatus.TARGET_CONFIRMED and target.multi_bet_result:
            targets.append({
                'venue_code': venue_code,
                'race_number': race_number,
                'confidence': confidence,
                'c1_rank': c1_rank,
                'target': target,
            })

    # 結果表示
    print("=" * 100)
    print(f"購入推奨レース（計{len(targets)}件）")
    print("=" * 100)
    print()

    if not targets:
        print("【結果】本日は購入推奨レースがありません")
        print()
    else:
        total_investment = 0

        for i, t in enumerate(targets, 1):
            venue_code = t['venue_code']
            race_number = t['race_number']
            target = t['target']
            multi_bet = target.multi_bet_result

            print(f"【{i}】会場{venue_code:02d} {race_number}R - 信頼度{t['confidence']} / 1C{t['c1_rank']}")
            print(f"  期待ROI: {target.expected_roi:.1f}%")
            print(f"  買い目:")

            race_investment = 0
            for bet in multi_bet.bets:
                print(f"    {bet.combination}: {bet.bet_amount}円（オッズ{bet.odds:.1f}倍）")
                race_investment += bet.bet_amount

            print(f"  投資額計: {race_investment}円")
            print()
            total_investment += race_investment

        print("=" * 100)
        print("【サマリー】")
        print(f"  総購入レース数: {len(targets)}件")
        print(f"  総投資額: {total_investment:,}円")
        print(f"  期待的中率: 約9.2%（年間実績ベース）")
        print(f"  期待ROI: 126.6%（年間実績ベース）")
        print(f"  期待収支: {int(total_investment * 0.266):+,}円")
        print("=" * 100)

    conn.close()
    print()
    print("分析完了")

if __name__ == '__main__':
    main()
