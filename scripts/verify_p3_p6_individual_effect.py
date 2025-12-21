# -*- coding: utf-8 -*-
"""
P-3, P-6-1, P-6-2 の個別効果検証

ab_rank_special_betting = ON の状態で、
各機能を個別にON/OFFして効果を測定

注意: P-3, P-6-1, P-6-2 は予測スコアに影響するため、
既存のrace_predictionsテーブルでは効果を測定できない。
→ RacePredictorを使用した検証が必要（時間がかかる）

このスクリプトでは、P-1（フィルターのみ）の効果を
ab_rank ON状態で再確認する。
"""
import sys
import sqlite3
import io
import json
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import config.feature_flags as ff
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def load_forward_movers():
    """前付け常習者リストを読み込む"""
    path = ROOT_DIR / "config" / "forward_movers.json"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return set(str(rn) for rn in data.get('racer_numbers', []))
    except:
        return set()


def run_backtest(apply_p1_filter=False):
    """バックテスト実行"""
    # ab_rank ON、その他の新機能はOFF（既存予測を使うため）
    ff.FEATURE_FLAGS['ab_rank_special_betting'] = True
    ff.FEATURE_FLAGS['forward_mover_filter'] = False  # フィルターはここで手動適用
    ff.FEATURE_FLAGS['kimarite_flow_prediction'] = False
    ff.FEATURE_FLAGS['third_place_specialized_scorer'] = False
    ff.FEATURE_FLAGS['makuri_risk_adjustment'] = False

    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    evaluator = BetTargetEvaluator()
    forward_movers = load_forward_movers() if apply_p1_filter else set()

    stats = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}
    excluded_by_p1 = 0

    cursor.execute('''
        SELECT r.id as race_id, r.venue_code
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-11-30'
          AND EXISTS (SELECT 1 FROM race_predictions WHERE race_id = r.id AND prediction_type = 'before')
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id AND is_invalid = 0)
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0

        # P-1フィルター適用
        if apply_p1_filter and forward_movers:
            cursor.execute('SELECT racer_number FROM entries WHERE race_id = ?', (race_id,))
            racer_numbers = [str(row['racer_number']) for row in cursor.fetchall()]
            if set(racer_numbers) & forward_movers:
                excluded_by_p1 += 1
                continue

        # 予測取得
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

        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

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

    conn.close()

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
        'roi': roi,
        'excluded_by_p1': excluded_by_p1
    }


def main():
    print("=" * 100)
    print("P-1効果検証（ab_rank_special_betting = ON 状態）")
    print("=" * 100)
    print()
    print("新ベースライン: ab_rank ON, P-1/P-3/P-6-1/P-6-2 全OFF")
    print()

    # ベースライン（ab_rank ON、P-1 OFF）
    print("[検証中] ベースライン（ab_rank ON、P-1〜P-6-2 全OFF）")
    baseline = run_backtest(apply_p1_filter=False)
    print(f"  購入={baseline['target']}, 的中={baseline['hit']}, "
          f"ROI={baseline['roi']:.1f}%, 収支={baseline['profit']:+,.0f}円")

    print()

    # P-1 ON
    print("[検証中] P-1フィルター ON")
    with_p1 = run_backtest(apply_p1_filter=True)
    print(f"  購入={with_p1['target']}, 的中={with_p1['hit']}, "
          f"ROI={with_p1['roi']:.1f}%, 収支={with_p1['profit']:+,.0f}円")
    print(f"  P-1で除外: {with_p1['excluded_by_p1']}レース")

    # 結果比較
    print()
    print("=" * 100)
    print("結果比較")
    print("=" * 100)
    print(f"\n{'指標':<15} {'ベースライン':>15} {'P-1適用':>15} {'差分':>15}")
    print("-" * 65)
    print(f"{'購入件数':<15} {baseline['target']:>15,} {with_p1['target']:>15,} {with_p1['target'] - baseline['target']:>+15,}")
    print(f"{'的中数':<15} {baseline['hit']:>15,} {with_p1['hit']:>15,} {with_p1['hit'] - baseline['hit']:>+15,}")
    print(f"{'的中率':<15} {baseline['hit_rate']:>14.2f}% {with_p1['hit_rate']:>14.2f}% {with_p1['hit_rate'] - baseline['hit_rate']:>+14.2f}%")
    print(f"{'ROI':<15} {baseline['roi']:>14.1f}% {with_p1['roi']:>14.1f}% {with_p1['roi'] - baseline['roi']:>+14.1f}%")
    print(f"{'収支':<15} {baseline['profit']:>+14,.0f}円 {with_p1['profit']:>+14,.0f}円 {with_p1['profit'] - baseline['profit']:>+14,.0f}円")

    print()
    print("=" * 100)
    print("重要: P-3, P-6-1, P-6-2 の効果測定には RacePredictor が必要")
    print("これらは予測スコアを変更するため、既存予測では測定不可")
    print("=" * 100)


if __name__ == "__main__":
    main()
