# -*- coding: utf-8 -*-
"""
イン強会場のデータを詳細調査

なぜ購入対象が少ないのかを調べる
"""

import sys
import sqlite3
from pathlib import Path

# パス設定
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 70)
    print("イン強会場データ調査")
    print("=" * 70)

    # 2025年1-7月のイン強会場レース
    cursor.execute('''
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-07-31'
          AND r.venue_code IN (24, 19, 18)
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')

    races = cursor.fetchall()
    print(f"総レース数: {len(races)}")
    print()

    evaluator = BetTargetEvaluator()

    stats = {
        'total': 0,
        'has_prediction': 0,
        'confidence_d': 0,
        'c1_a1_a2': 0,
        'has_odds': 0,
        'target': 0,
        'reasons': {},
    }

    for i, race in enumerate(races[:20]):  # 最初の20レースのみ詳細表示
        race_id = race['race_id']
        venue_code = race['venue_code']

        # 1コース級別を取得
        cursor.execute('''
            SELECT e.racer_rank
            FROM entries e
            WHERE e.race_id = ? AND e.pit_number = 1
        ''', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else None

        # 予測情報を取得
        cursor.execute('''
            SELECT pit_number, rank_prediction, confidence
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
        ''', (race_id,))
        preds = cursor.fetchall()

        confidence = preds[0]['confidence'] if preds else None

        # オッズ取得
        if len(preds) >= 3:
            combo = f"{preds[0]['pit_number']}-{preds[1]['pit_number']}-{preds[2]['pit_number']}"
            cursor.execute('''
                SELECT odds
                FROM trifecta_odds
                WHERE race_id = ? AND combination = ?
            ''', (race_id, combo))
            odds_row = cursor.fetchone()
            odds = odds_row['odds'] if odds_row else None
        else:
            combo = None
            odds = None

        print(f"[{i+1}] {race['race_date']} 会場{venue_code} R{race['race_number']}")
        print(f"    1コース: {c1_rank if c1_rank else 'なし'}")
        print(f"    予測数: {len(preds)}, 信頼度: {confidence if confidence else 'なし'}")
        print(f"    買い目: {combo if combo else 'なし'}, オッズ: {odds if odds else 'なし'}")

        # 条件チェック
        if len(preds) < 6:
            print(f"    -> 除外理由: 予測数不足（{len(preds)}件）")
            continue

        stats['has_prediction'] += 1

        if confidence != 'D':
            print(f"    -> 除外理由: 信頼度が{confidence}（Dでない）")
            continue

        stats['confidence_d'] += 1

        if c1_rank != 'B1':
            print(f"    -> 除外理由: 1コースが{c1_rank}（B1でない）")
            continue

        stats['c1_a1_a2'] += 1

        if not odds:
            print(f"    -> 除外理由: オッズデータなし")
            continue

        stats['has_odds'] += 1

        # BetTargetEvaluatorで判定
        result = evaluator.evaluate(
            confidence='D',
            c1_rank=c1_rank,
            old_combo=combo,
            new_combo=combo,
            old_odds=odds,
            new_odds=odds,
            has_beforeinfo=True,
            venue_code=venue_code
        )

        print(f"    判定: {result.status.value}")
        print(f"    理由: {result.reason}")

        if result.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            stats['target'] += 1
            print(f"    -> [OK] 購入対象（賭け金{result.bet_amount}円）")
        else:
            reason = result.reason
            stats['reasons'][reason] = stats['reasons'].get(reason, 0) + 1

        print()

    conn.close()

    print("=" * 70)
    print("集計結果（最初の20レース）")
    print("=" * 70)
    print(f"予測あり: {stats['has_prediction']}")
    print(f"信頼度D: {stats['confidence_d']}")
    print(f"1コースA1/A2: {stats['c1_a1_a2']}")
    print(f"オッズあり: {stats['has_odds']}")
    print(f"購入対象: {stats['target']}")
    print()

    print("除外理由:")
    for reason, count in stats['reasons'].items():
        print(f"  - {reason}: {count}件")


if __name__ == '__main__':
    main()
