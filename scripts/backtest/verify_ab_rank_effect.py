# -*- coding: utf-8 -*-
"""
A・Bランク特別条件の効果検証

ab_rank_special_betting フラグの効果を測定
"""
import sys
import sqlite3
import io
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

# フラグを操作する前にインポート
import config.feature_flags as ff


def run_backtest(ab_rank_enabled):
    """指定設定でバックテスト実行"""
    # フラグ設定
    ff.FEATURE_FLAGS['ab_rank_special_betting'] = ab_rank_enabled

    # 他の新機能はOFFにして純粋にab_rankの効果を見る
    ff.FEATURE_FLAGS['forward_mover_filter'] = False
    ff.FEATURE_FLAGS['kimarite_flow_prediction'] = False
    ff.FEATURE_FLAGS['third_place_specialized_scorer'] = False
    ff.FEATURE_FLAGS['makuri_risk_adjustment'] = False

    from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus

    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    evaluator = BetTargetEvaluator()

    stats = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}
    confidence_stats = {'A': 0, 'B': 0, 'C': 0, 'D': 0}

    # 2025年1-11月
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
        confidence_stats[confidence] = confidence_stats.get(confidence, 0) + 1

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
        'confidence_stats': confidence_stats
    }


def main():
    print("=" * 100)
    print("A・Bランク特別条件（ab_rank_special_betting）効果検証")
    print("=" * 100)
    print()
    print("※ P-1, P-3, P-6-1, P-6-2 は全てOFFで検証")
    print()

    # ab_rank OFF（ベースライン）
    print("[検証中] ab_rank_special_betting = OFF")
    result_off = run_backtest(ab_rank_enabled=False)
    print(f"  購入={result_off['target']}, 的中={result_off['hit']}, "
          f"ROI={result_off['roi']:.1f}%, 収支={result_off['profit']:+,.0f}円")
    print(f"  信頼度別: {result_off['confidence_stats']}")

    print()

    # ab_rank ON
    print("[検証中] ab_rank_special_betting = ON")
    result_on = run_backtest(ab_rank_enabled=True)
    print(f"  購入={result_on['target']}, 的中={result_on['hit']}, "
          f"ROI={result_on['roi']:.1f}%, 収支={result_on['profit']:+,.0f}円")
    print(f"  信頼度別: {result_on['confidence_stats']}")

    # 差分
    print()
    print("=" * 100)
    print("結果比較")
    print("=" * 100)
    print(f"\n{'指標':<15} {'OFF':>15} {'ON':>15} {'差分':>15}")
    print("-" * 65)
    print(f"{'購入件数':<15} {result_off['target']:>15,} {result_on['target']:>15,} {result_on['target'] - result_off['target']:>+15,}")
    print(f"{'的中数':<15} {result_off['hit']:>15,} {result_on['hit']:>15,} {result_on['hit'] - result_off['hit']:>+15,}")
    print(f"{'的中率':<15} {result_off['hit_rate']:>14.2f}% {result_on['hit_rate']:>14.2f}% {result_on['hit_rate'] - result_off['hit_rate']:>+14.2f}%")
    print(f"{'ROI':<15} {result_off['roi']:>14.1f}% {result_on['roi']:>14.1f}% {result_on['roi'] - result_off['roi']:>+14.1f}%")
    print(f"{'収支':<15} {result_off['profit']:>+14,.0f}円 {result_on['profit']:>+14,.0f}円 {result_on['profit'] - result_off['profit']:>+14,.0f}円")

    # 判定
    print()
    print("=" * 100)
    print("判定")
    print("=" * 100)
    diff_profit = result_on['profit'] - result_off['profit']
    diff_roi = result_on['roi'] - result_off['roi']

    if diff_profit > 5000:
        print(f"[プラス効果] ab_rank_special_betting により収支 {diff_profit:+,.0f}円、ROI {diff_roi:+.1f}%")
    elif diff_profit > -5000:
        print(f"[ほぼ変化なし] ab_rank_special_betting の影響は軽微（収支 {diff_profit:+,.0f}円、ROI {diff_roi:+.1f}%）")
    else:
        print(f"[マイナス効果] ab_rank_special_betting により収支 {diff_profit:+,.0f}円、ROI {diff_roi:+.1f}%")

    print()
    print("=" * 100)


if __name__ == "__main__":
    main()
