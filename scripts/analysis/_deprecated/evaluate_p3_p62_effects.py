# -*- coding: utf-8 -*-
"""
P-3（決まり手別展開予測）とP-6-2（まくりリスク調整）の効果検証

既存予測と新規予測を比較し、精度・ROIへの影響を測定
"""
import sys
import sqlite3
import io
from pathlib import Path
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import config.feature_flags as ff
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def get_existing_predictions(cursor, race_id):
    """既存の予測を取得"""
    cursor.execute('''
        SELECT pit_number, total_score, confidence
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'before'
        ORDER BY total_score DESC
    ''', (race_id,))
    return cursor.fetchall()


def generate_new_prediction(race_predictor, race_id, cursor):
    """新規予測を生成（P-3/P-6-2有効）"""
    cursor.execute('''
        SELECT race_date, venue_code, race_number
        FROM races WHERE id = ?
    ''', (race_id,))
    race_info = cursor.fetchone()
    if not race_info:
        return None

    race_date = race_info[0]
    venue_code = race_info[1]
    race_number = race_info[2]

    try:
        predictions = race_predictor.predict(
            race_date=race_date,
            venue_code=venue_code,
            race_number=race_number,
            before_info=True
        )
        return predictions
    except Exception as e:
        return None


def compare_predictions(old_preds, new_preds):
    """予測の差分を比較"""
    if not old_preds or not new_preds:
        return None

    old_ranking = [p[0] for p in old_preds]  # pit_number順
    new_ranking = [p['pit_number'] for p in sorted(new_preds, key=lambda x: x.get('total_score', 0), reverse=True)]

    return {
        'old_top3': old_ranking[:3],
        'new_top3': new_ranking[:3],
        'changed': old_ranking[:3] != new_ranking[:3]
    }


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # フィーチャーフラグ設定
    ff.FEATURE_FLAGS['ab_rank_special_betting'] = True
    ff.FEATURE_FLAGS['kimarite_flow_prediction'] = True
    ff.FEATURE_FLAGS['makuri_risk_adjustment'] = True

    print("=" * 100)
    print("P-3/P-6-2 効果検証")
    print("=" * 100)
    print()

    # まず既存予測でのベースラインを計算
    print("【ベースライン計算中...】")

    evaluator = BetTargetEvaluator()

    # 2025年の購入対象レースを取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-11-30'
          AND EXISTS (SELECT 1 FROM race_predictions WHERE race_id = r.id AND prediction_type = 'before')
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id AND is_invalid = 0)
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()
    print(f"対象レース数: {len(races):,}件")

    # ベースライン統計
    baseline_stats = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0

        # 既存予測取得
        preds = get_existing_predictions(cursor, race_id)
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
        baseline_stats['target'] += 1
        baseline_stats['bet'] += bet_amount

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
                    baseline_stats['hit'] += 1
                    baseline_stats['payout'] += payout

    conn.close()

    # ベースライン結果
    baseline_roi = baseline_stats['payout'] / baseline_stats['bet'] * 100 if baseline_stats['bet'] > 0 else 0
    baseline_hit_rate = baseline_stats['hit'] / baseline_stats['target'] * 100 if baseline_stats['target'] > 0 else 0
    baseline_profit = baseline_stats['payout'] - baseline_stats['bet']

    print()
    print("=" * 100)
    print("ベースライン結果（既存予測 = P-3/P-6-2なし）")
    print("=" * 100)
    print(f"購入対象: {baseline_stats['target']:,}件")
    print(f"的中数: {baseline_stats['hit']}件")
    print(f"的中率: {baseline_hit_rate:.2f}%")
    print(f"ROI: {baseline_roi:.1f}%")
    print(f"収支: {baseline_profit:+,.0f}円")

    print()
    print("=" * 100)
    print("P-3/P-6-2効果検証の方法")
    print("=" * 100)
    print()
    print("現在の予測データは2025-12-18以前に生成されたもので、")
    print("P-3（決まり手別展開予測）とP-6-2（まくりリスク調整）の効果は含まれていません。")
    print()
    print("正確な効果測定には予測の再生成が必要です。")
    print()
    print("【選択肢】")
    print("1. 予測を全件再生成する（時間がかかる）")
    print("2. サンプルレースで効果を確認する")
    print("3. P-3/P-6-2をOFFにして現状ROI 136.0%を維持（安全策）")
    print()
    print("現在のフィーチャーフラグ設定:")
    print(f"  kimarite_flow_prediction: {ff.FEATURE_FLAGS.get('kimarite_flow_prediction', False)}")
    print(f"  makuri_risk_adjustment: {ff.FEATURE_FLAGS.get('makuri_risk_adjustment', False)}")


if __name__ == "__main__":
    main()
