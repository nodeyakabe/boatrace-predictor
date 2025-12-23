# -*- coding: utf-8 -*-
"""
P-3/P-6-2の効果をサンプルレースで確認

購入対象レースからサンプルを取り、新旧予測を比較
"""
import sys
import sqlite3
import io
import random
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import config.feature_flags as ff
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # フィーチャーフラグ設定
    ff.FEATURE_FLAGS['ab_rank_special_betting'] = True

    evaluator = BetTargetEvaluator()

    print("=" * 100)
    print("P-3/P-6-2 サンプル比較（ON/OFF切り替えによる効果測定）")
    print("=" * 100)
    print()

    # 購入対象レースを全件取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-11-30'
          AND EXISTS (SELECT 1 FROM race_predictions WHERE race_id = r.id AND prediction_type = 'before')
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id AND is_invalid = 0)
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    all_races = cursor.fetchall()

    print(f"全レース数: {len(all_races):,}件")

    # 各パターンで検証
    # 既存予測はP-3/P-6-2を含まないので、フラグをON/OFFしても結果は同じ
    # → 新規予測を生成して比較する必要がある

    # RacePredictorを読み込んで新規予測を生成
    print()
    print("新規予測を生成して効果を検証します...")
    print("（サンプル100件で検証）")
    print()

    from src.analysis.race_predictor import RacePredictor

    # サンプルレースを選択（購入対象になりそうなレースを優先）
    target_races = []
    for race in all_races:
        race_id = race['race_id']

        cursor.execute('''
            SELECT pit_number, confidence, total_score
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY total_score DESC
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        confidence = preds[0]['confidence']
        if confidence in ['A', 'B', 'C']:
            target_races.append(race)

    # サンプル選択
    sample_size = min(100, len(target_races))
    random.seed(42)
    sample_races = random.sample(target_races, sample_size)

    print(f"サンプルレース数: {sample_size}件")
    print()

    # P-3/P-6-2 OFF で予測生成
    print("【P-3/P-6-2 OFF で予測生成中...】")
    ff.FEATURE_FLAGS['kimarite_flow_prediction'] = False
    ff.FEATURE_FLAGS['makuri_risk_adjustment'] = False

    predictor_off = RacePredictor(str(db_path))

    results_off = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}
    predictions_off = {}

    for i, race in enumerate(sample_races):
        race_id = race['race_id']

        try:
            preds = predictor_off.predict_race(race_id, use_beforeinfo=True)
            if preds:
                predictions_off[race_id] = preds
        except Exception as e:
            pass

        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{sample_size}件完了")

    print(f"  予測成功: {len(predictions_off)}件")

    # P-3/P-6-2 ON で予測生成
    print()
    print("【P-3/P-6-2 ON で予測生成中...】")
    ff.FEATURE_FLAGS['kimarite_flow_prediction'] = True
    ff.FEATURE_FLAGS['makuri_risk_adjustment'] = True

    predictor_on = RacePredictor(str(db_path))

    predictions_on = {}

    for i, race in enumerate(sample_races):
        race_id = race['race_id']

        try:
            preds = predictor_on.predict_race(race_id, use_beforeinfo=True)
            if preds:
                predictions_on[race_id] = preds
        except Exception as e:
            pass

        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{sample_size}件完了")

    print(f"  予測成功: {len(predictions_on)}件")

    # 結果比較
    print()
    print("=" * 100)
    print("予測変化の分析")
    print("=" * 100)

    changed_count = 0
    total_compared = 0

    for race_id in predictions_off:
        if race_id not in predictions_on:
            continue

        preds_off = predictions_off[race_id]
        preds_on = predictions_on[race_id]

        if not preds_off or not preds_on:
            continue

        # Top3を比較
        top3_off = [p['pit_number'] for p in sorted(preds_off, key=lambda x: x.get('total_score', 0), reverse=True)[:3]]
        top3_on = [p['pit_number'] for p in sorted(preds_on, key=lambda x: x.get('total_score', 0), reverse=True)[:3]]

        total_compared += 1
        if top3_off != top3_on:
            changed_count += 1

    print(f"比較対象: {total_compared}件")
    if total_compared > 0:
        print(f"Top3変化: {changed_count}件 ({changed_count/total_compared*100:.1f}%)")
    else:
        print("Top3変化: 比較対象なし")

    # 収益比較
    print()
    print("=" * 100)
    print("収益比較")
    print("=" * 100)

    for label, predictions in [('OFF', predictions_off), ('ON', predictions_on)]:
        stats = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}

        for race in sample_races:
            race_id = race['race_id']
            venue_code = int(race['venue_code']) if race['venue_code'] else 0

            if race_id not in predictions:
                continue

            preds = predictions[race_id]
            sorted_preds = sorted(preds, key=lambda x: x.get('total_score', 0), reverse=True)

            if len(sorted_preds) < 3:
                continue

            confidence = sorted_preds[0].get('confidence', 'C')
            top3 = [p['pit_number'] for p in sorted_preds[:3]]
            combo = f"{top3[0]}-{top3[1]}-{top3[2]}"

            # 1コース級別
            cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
            c1 = cursor.fetchone()
            c1_rank = c1['racer_rank'] if c1 else 'B1'

            # オッズ
            cursor.execute(
                'SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                (race_id, combo))
            odds_row = cursor.fetchone()
            if not odds_row:
                continue

            odds = odds_row['odds']

            result = evaluator.evaluate(
                confidence=confidence,
                c1_rank=c1_rank,
                old_combo=combo,
                new_combo=combo,
                old_odds=odds,
                new_odds=odds,
                has_beforeinfo=True,
                venue_code=venue_code
            )

            if result.status not in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
                continue

            bet_amount = result.bet_amount
            stats['target'] += 1
            stats['bet'] += bet_amount

            # 的中判定
            cursor.execute('''
                SELECT pit_number FROM results
                WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                ORDER BY rank
            ''', (race_id,))
            actual_results = cursor.fetchall()

            if len(actual_results) >= 3:
                actual_combo = f"{actual_results[0]['pit_number']}-{actual_results[1]['pit_number']}-{actual_results[2]['pit_number']}"

                if combo == actual_combo:
                    cursor.execute('''
                        SELECT amount FROM payouts
                        WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                    ''', (race_id, actual_combo))
                    payout_row = cursor.fetchone()

                    if payout_row:
                        payout = (bet_amount / 100) * payout_row['amount']
                        stats['hit'] += 1
                        stats['payout'] += payout

        roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
        hit_rate = stats['hit'] / stats['target'] * 100 if stats['target'] > 0 else 0
        profit = stats['payout'] - stats['bet']

        print(f"\nP-3/P-6-2 {label}:")
        print(f"  購入対象: {stats['target']}件")
        print(f"  的中: {stats['hit']}件 ({hit_rate:.2f}%)")
        print(f"  ROI: {roi:.1f}%")
        print(f"  収支: {profit:+,.0f}円")

    conn.close()


if __name__ == "__main__":
    main()
