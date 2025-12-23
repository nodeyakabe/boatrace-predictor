# -*- coding: utf-8 -*-
"""
P-1代替案: 信頼度を下げた場合のシミュレーション

前付け常習者がいるレースで:
- A → C
- B → D

購入フィルターで切られて機会損失になるか検証
"""
import sys
import sqlite3
import io
import json
from pathlib import Path
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import config.feature_flags as ff
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def load_forward_movers():
    path = ROOT_DIR / "config" / "forward_movers.json"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return set(str(rn) for rn in data.get('racer_numbers', []))
    except:
        return set()


def downgrade_confidence(conf, has_forward):
    """前付けあり時に信頼度を2段階下げる"""
    if not has_forward:
        return conf

    mapping = {
        'A': 'C',
        'B': 'D',
        'C': 'E',  # C→Eはほぼ購入対象外
        'D': 'E',
        'E': 'E'
    }
    return mapping.get(conf, conf)


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    forward_movers = load_forward_movers()

    # ab_rank ON設定
    ff.FEATURE_FLAGS['ab_rank_special_betting'] = True
    evaluator = BetTargetEvaluator()

    print("=" * 100)
    print("P-1代替案シミュレーション: 信頼度ダウングレード")
    print("前付けあり時: A→C, B→D, C→E, D→E")
    print("=" * 100)
    print()

    # 2024-2025年データ
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code
        FROM races r
        WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2025-11-30'
          AND EXISTS (SELECT 1 FROM race_predictions WHERE race_id = r.id AND prediction_type = 'before')
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id AND is_invalid = 0)
    ''')
    races = cursor.fetchall()

    # 3パターンで比較
    # 1. 現状（信頼度そのまま）
    # 2. 信頼度ダウングレード
    # 3. P-1フィルター（完全除外）

    patterns = {
        '現状（信頼度維持）': {'downgrade': False, 'exclude': False},
        '信頼度ダウングレード': {'downgrade': True, 'exclude': False},
        'P-1フィルター（完全除外）': {'downgrade': False, 'exclude': True},
    }

    results = {}

    for pattern_name, settings in patterns.items():
        stats = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}
        lost_opportunities = 0  # 信頼度低下で購入対象外になったレース

        for race in races:
            race_id = race['race_id']
            venue_code = int(race['venue_code']) if race['venue_code'] else 0

            # 前付け常習者チェック
            cursor.execute('SELECT racer_number FROM entries WHERE race_id = ?', (race_id,))
            racer_numbers = [str(row['racer_number']) for row in cursor.fetchall()]
            has_forward = bool(set(racer_numbers) & forward_movers)

            # P-1フィルターで除外
            if settings['exclude'] and has_forward:
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

            original_confidence = preds[0]['confidence']

            # 信頼度ダウングレード
            if settings['downgrade']:
                confidence = downgrade_confidence(original_confidence, has_forward)
            else:
                confidence = original_confidence

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

            # 購入対象判定
            is_target = result.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]

            # 機会損失チェック（ダウングレードで購入対象外になったケース）
            if settings['downgrade'] and has_forward and not is_target:
                # 元の信頼度で判定
                original_result = evaluator.evaluate(
                    confidence=original_confidence,
                    c1_rank=c1_rank,
                    old_combo=combo,
                    new_combo=combo,
                    old_odds=odds,
                    new_odds=odds,
                    has_beforeinfo=True,
                    venue_code=venue_code
                )
                if original_result.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
                    lost_opportunities += 1

            if not is_target:
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

        results[pattern_name] = {
            'stats': stats,
            'lost': lost_opportunities
        }

    conn.close()

    # 結果表示
    print("=" * 100)
    print("シミュレーション結果")
    print("=" * 100)

    baseline = results['現状（信頼度維持）']['stats']
    baseline_roi = baseline['payout'] / baseline['bet'] * 100 if baseline['bet'] > 0 else 0
    baseline_profit = baseline['payout'] - baseline['bet']

    print(f"\n{'パターン':<30} {'購入数':>8} {'的中':>6} {'的中率':>8} {'ROI':>10} {'収支':>15} {'ROI差':>10}")
    print("-" * 100)

    for pattern_name, data in results.items():
        s = data['stats']
        roi = s['payout'] / s['bet'] * 100 if s['bet'] > 0 else 0
        hit_rate = s['hit'] / s['target'] * 100 if s['target'] > 0 else 0
        profit = s['payout'] - s['bet']
        roi_diff = roi - baseline_roi

        lost_info = f" (機会損失: {data['lost']}件)" if data['lost'] > 0 else ""
        print(f"{pattern_name:<30} {s['target']:>8,} {s['hit']:>6} {hit_rate:>7.2f}% {roi:>9.1f}% {profit:>+14,.0f}円 {roi_diff:>+9.1f}pt{lost_info}")

    # 詳細分析
    print()
    print("=" * 100)
    print("信頼度ダウングレードの影響詳細")
    print("=" * 100)

    downgrade_stats = results['信頼度ダウングレード']
    exclude_stats = results['P-1フィルター（完全除外）']

    downgrade_lost = downgrade_stats['lost']
    downgrade_s = downgrade_stats['stats']
    exclude_s = exclude_stats['stats']

    print(f"\n機会損失（ダウングレードで購入対象外になったレース）: {downgrade_lost}件")

    if downgrade_lost > 0:
        print("\n前付けありレースの取り扱い:")
        print(f"  - 信頼度ダウングレード: {downgrade_lost}件が購入対象外に（フィルターで切られた）")
        print(f"  - P-1フィルター: 完全除外（全レース購入対象外）")

    # 結論
    print()
    print("=" * 100)
    print("結論")
    print("=" * 100)

    downgrade_roi = downgrade_s['payout'] / downgrade_s['bet'] * 100 if downgrade_s['bet'] > 0 else 0
    downgrade_profit = downgrade_s['payout'] - downgrade_s['bet']

    if downgrade_roi > baseline_roi:
        print(f"\n信頼度ダウングレードでROI改善: +{downgrade_roi - baseline_roi:.1f}pt")
    elif downgrade_roi < baseline_roi:
        print(f"\n信頼度ダウングレードでROI悪化: {downgrade_roi - baseline_roi:.1f}pt")
    else:
        print("\n信頼度ダウングレードでROI変化なし")

    print(f"\n収支比較:")
    print(f"  現状維持: {baseline_profit:+,.0f}円")
    print(f"  ダウングレード: {downgrade_profit:+,.0f}円 ({downgrade_profit - baseline_profit:+,.0f}円)")

    if downgrade_profit >= baseline_profit:
        print("\n【推奨】信頼度ダウングレードも有効な選択肢")
    else:
        print("\n【推奨】現状維持（信頼度変更なし）が最適")


if __name__ == "__main__":
    main()
