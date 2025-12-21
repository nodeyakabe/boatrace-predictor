# -*- coding: utf-8 -*-
"""
P-3, P-6-1, P-6-2 の個別効果検証（RacePredictor使用版）

ab_rank_special_betting = ON の状態で、
各機能を個別にON/OFFして効果を測定。

注意: RacePredictorを使うため時間がかかる。
サンプリングして検証（全レースの約10%）
"""
import sys
import sqlite3
import io
import random
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import config.feature_flags as ff
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def run_backtest_with_flags(flag_settings, sample_races, cursor):
    """指定したフラグ設定でバックテスト実行"""
    # 共通設定
    ff.FEATURE_FLAGS['ab_rank_special_betting'] = True
    ff.FEATURE_FLAGS['forward_mover_filter'] = False  # P-1は無効化済み

    # 個別設定
    for flag_name, value in flag_settings.items():
        ff.FEATURE_FLAGS[flag_name] = value

    evaluator = BetTargetEvaluator()
    stats = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}

    for race in sample_races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0

        # 予測取得（既存予測を使用）
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
        top3 = [p['pit_number'] for p in preds[:3]]
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
        results = cursor.fetchall()

        if len(results) >= 3:
            actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

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

    hit_rate = stats['hit'] / stats['target'] * 100 if stats['target'] > 0 else 0
    roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
    profit = stats['payout'] - stats['bet']

    return {
        'target': stats['target'],
        'hit': stats['hit'],
        'hit_rate': hit_rate,
        'bet': stats['bet'],
        'payout': stats['payout'],
        'profit': profit,
        'roi': roi
    }


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 100)
    print("P-3, P-6-1, P-6-2 個別効果検証（ab_rank ON, P-1 OFF）")
    print("=" * 100)
    print(f"実行開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("注意: この検証は既存予測（race_predictions）を使用するため、")
    print("P-3/P-6-1/P-6-2の効果は間接的にしか測れません。")
    print("これらの機能は予測スコア自体を変更するため、")
    print("正確な測定にはRacePredictorでの再予測が必要です。")
    print()

    # 全レース取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-11-30'
          AND EXISTS (SELECT 1 FROM race_predictions WHERE race_id = r.id AND prediction_type = 'before')
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id AND is_invalid = 0)
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    all_races = cursor.fetchall()
    print(f"全レース数: {len(all_races)}")
    print()

    # 設定パターン
    patterns = {
        'ベースライン（全ON）': {
            'kimarite_flow_prediction': True,
            'third_place_specialized_scorer': True,
            'makuri_risk_adjustment': True
        },
        'P-3 OFF': {
            'kimarite_flow_prediction': False,
            'third_place_specialized_scorer': True,
            'makuri_risk_adjustment': True
        },
        'P-6-1 OFF': {
            'kimarite_flow_prediction': True,
            'third_place_specialized_scorer': False,
            'makuri_risk_adjustment': True
        },
        'P-6-2 OFF': {
            'kimarite_flow_prediction': True,
            'third_place_specialized_scorer': True,
            'makuri_risk_adjustment': False
        },
        '全OFF': {
            'kimarite_flow_prediction': False,
            'third_place_specialized_scorer': False,
            'makuri_risk_adjustment': False
        }
    }

    results = {}

    for name, flags in patterns.items():
        print(f"[検証中] {name}")
        result = run_backtest_with_flags(flags, all_races, cursor)
        results[name] = result
        print(f"  購入={result['target']}, 的中={result['hit']}, "
              f"ROI={result['roi']:.1f}%, 収支={result['profit']:+,.0f}円")

    conn.close()

    # 結果比較
    print()
    print("=" * 100)
    print("結果比較（ab_rank ON, P-1 OFF 状態）")
    print("=" * 100)

    baseline = results['ベースライン（全ON）']

    print(f"\n{'設定':<20} {'購入':>10} {'的中':>8} {'ROI':>10} {'収支':>15} {'ROI差分':>10}")
    print("-" * 85)

    for name, result in results.items():
        roi_diff = result['roi'] - baseline['roi']
        profit_diff = result['profit'] - baseline['profit']
        print(f"{name:<20} {result['target']:>10,} {result['hit']:>8} "
              f"{result['roi']:>9.1f}% {result['profit']:>+14,.0f}円 {roi_diff:>+9.1f}pt")

    # 個別効果の分析
    print()
    print("=" * 100)
    print("個別効果分析（OFF時の差分 = マイナスなら機能が有効）")
    print("=" * 100)

    print(f"\n{'機能':<25} {'OFF時ROI差':>12} {'OFF時収支差':>15} {'判定':>15}")
    print("-" * 75)

    for feature, off_key in [
        ('P-3 (kimarite_flow)', 'P-3 OFF'),
        ('P-6-1 (third_place)', 'P-6-1 OFF'),
        ('P-6-2 (makuri_risk)', 'P-6-2 OFF')
    ]:
        off_result = results[off_key]
        roi_diff = off_result['roi'] - baseline['roi']
        profit_diff = off_result['profit'] - baseline['profit']

        if roi_diff < -2:
            judgment = "有効（維持）"
        elif roi_diff > 2:
            judgment = "無効化推奨"
        else:
            judgment = "効果不明"

        print(f"{feature:<25} {roi_diff:>+11.1f}pt {profit_diff:>+14,.0f}円 {judgment:>15}")

    # 全OFF vs 全ONの比較
    print()
    all_off = results['全OFF']
    total_effect_roi = baseline['roi'] - all_off['roi']
    total_effect_profit = baseline['profit'] - all_off['profit']
    print(f"P-3/P-6-1/P-6-2 全体効果: ROI {total_effect_roi:+.1f}pt, 収支 {total_effect_profit:+,.0f}円")

    print()
    print("=" * 100)
    print("重要: この結果は既存予測を使用しているため参考値です。")
    print("P-3/P-6-1/P-6-2は予測スコアを変更するため、")
    print("正確な効果測定にはRacePredictorでの再予測が必要です。")
    print("=" * 100)
    print(f"実行完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
