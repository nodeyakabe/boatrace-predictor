"""
ハイブリッド実装前後の性能比較

race_predictions_before_hybrid（実装前）と
race_predictions（実装後）を比較し、改善効果を測定。
"""

import sys
import warnings
from pathlib import Path
import sqlite3
from collections import defaultdict

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def evaluate_predictions(cursor, table_name, description):
    """予想データの評価"""

    print(f"\n{'=' * 80}")
    print(f"{description}")
    print('=' * 80)
    print()

    # 全体統計
    overall_stats = {
        'total': 0,
        'hit': 0,
        'rank1_correct': 0,
        'rank2_correct': 0,
        'rank3_correct': 0,
        'total_invested': 0,
        'total_return': 0
    }

    # 信頼度別統計
    confidence_stats = defaultdict(lambda: {
        'total': 0,
        'hit': 0,
        'rank1_correct': 0,
        'rank2_correct': 0,
        'rank3_correct': 0,
        'total_invested': 0,
        'total_return': 0
    })

    # レース一覧を取得
    cursor.execute(f'''
        SELECT DISTINCT r.id, r.race_date
        FROM races r
        JOIN {table_name} rp ON r.id = rp.race_id
        WHERE r.race_date >= '2025-01-01'
          AND r.race_date < '2026-01-01'
        ORDER BY r.race_date
    ''')
    races = cursor.fetchall()

    print(f"評価レース数: {len(races):,}レース")

    for idx, (race_id, race_date) in enumerate(races):
        if (idx + 1) % 1000 == 0:
            print(f"処理中: {idx+1:,}/{len(races):,}レース...", flush=True)

        try:
            # 予想上位3艇を取得
            cursor.execute(f'''
                SELECT pit_number, confidence
                FROM {table_name}
                WHERE race_id = ?
                ORDER BY rank_prediction
                LIMIT 3
            ''', (race_id,))
            preds = cursor.fetchall()

            if len(preds) < 3:
                continue

            pred_pits = [p[0] for p in preds]
            confidence = preds[0][1]

            # 信頼度A/Eは除外
            if confidence in ['A', 'E'] or confidence is None:
                continue

            # 実際の結果取得
            cursor.execute('''
                SELECT pit_number, CAST(rank AS INTEGER) as rank_int
                FROM results
                WHERE race_id = ? AND is_invalid = 0 AND CAST(rank AS INTEGER) <= 3
                ORDER BY rank_int
            ''', (race_id,))
            actual_results = cursor.fetchall()

            if len(actual_results) < 3:
                continue

            actual_top3 = [row[0] for row in actual_results]
            actual_combo = f"{actual_top3[0]}-{actual_top3[1]}-{actual_top3[2]}"
            predicted_combo = f"{pred_pits[0]}-{pred_pits[1]}-{pred_pits[2]}"

            # オッズ取得
            cursor.execute('''
                SELECT odds FROM trifecta_odds
                WHERE race_id = ? AND combination = ?
            ''', (race_id, actual_combo))
            odds_row = cursor.fetchone()
            actual_odds = odds_row[0] if odds_row else 0

            # 的中判定
            is_hit = (predicted_combo == actual_combo)
            rank1_correct = (pred_pits[0] == actual_top3[0])
            rank2_correct = (pred_pits[1] == actual_top3[1])
            rank3_correct = (pred_pits[2] == actual_top3[2])

            investment = 100
            return_amount = actual_odds * investment if is_hit else 0

            # 統計更新
            overall_stats['total'] += 1
            if is_hit:
                overall_stats['hit'] += 1
            if rank1_correct:
                overall_stats['rank1_correct'] += 1
            if rank2_correct:
                overall_stats['rank2_correct'] += 1
            if rank3_correct:
                overall_stats['rank3_correct'] += 1
            overall_stats['total_invested'] += investment
            overall_stats['total_return'] += return_amount

            confidence_stats[confidence]['total'] += 1
            if is_hit:
                confidence_stats[confidence]['hit'] += 1
            if rank1_correct:
                confidence_stats[confidence]['rank1_correct'] += 1
            if rank2_correct:
                confidence_stats[confidence]['rank2_correct'] += 1
            if rank3_correct:
                confidence_stats[confidence]['rank3_correct'] += 1
            confidence_stats[confidence]['total_invested'] += investment
            confidence_stats[confidence]['total_return'] += return_amount

        except Exception:
            continue

    # 結果表示
    print()
    print("【全体結果】")
    if overall_stats['total'] > 0:
        hit_rate = overall_stats['hit'] / overall_stats['total'] * 100
        rank1_rate = overall_stats['rank1_correct'] / overall_stats['total'] * 100
        rank2_rate = overall_stats['rank2_correct'] / overall_stats['total'] * 100
        rank3_rate = overall_stats['rank3_correct'] / overall_stats['total'] * 100
        roi = (overall_stats['total_return'] / overall_stats['total_invested']) * 100 if overall_stats['total_invested'] > 0 else 0
        profit = overall_stats['total_return'] - overall_stats['total_invested']

        print(f"分析レース数: {overall_stats['total']:,}レース")
        print(f"三連単的中率: {hit_rate:.2f}% ({overall_stats['hit']}/{overall_stats['total']})")
        print(f"1位的中率: {rank1_rate:.2f}%")
        print(f"2位的中率: {rank2_rate:.2f}%")
        print(f"3位的中率: {rank3_rate:.2f}%")
        print(f"ROI: {roi:.2f}%")
        print(f"収支: {profit:+,.0f}円")

    # 信頼度別
    print()
    print("【信頼度別結果】")
    for confidence in sorted(confidence_stats.keys()):
        stats = confidence_stats[confidence]
        if stats['total'] == 0:
            continue

        hit_rate = stats['hit'] / stats['total'] * 100
        roi = (stats['total_return'] / stats['total_invested']) * 100 if stats['total_invested'] > 0 else 0
        profit = stats['total_return'] - stats['total_invested']

        print(f"信頼度{confidence}: {stats['total']:,}R | 的中率 {hit_rate:.2f}% | ROI {roi:.2f}% | 収支 {profit:+,.0f}円")

    return overall_stats, confidence_stats


def main():
    print("=" * 80)
    print("ハイブリッド実装前後の性能比較")
    print("=" * 80)
    print()

    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # バックアップテーブルの存在確認
    cursor.execute('''
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='race_predictions_before_hybrid'
    ''')
    if not cursor.fetchone():
        print("エラー: race_predictions_before_hybridテーブルが見つかりません")
        print("先にバックアップを実行してください: python scripts/backup_old_predictions.py")
        conn.close()
        return

    # 実装前の評価
    before_overall, before_confidence = evaluate_predictions(
        cursor,
        'race_predictions_before_hybrid',
        '【実装前】ハイブリッドスコアリング導入前'
    )

    # 実装後の評価
    after_overall, after_confidence = evaluate_predictions(
        cursor,
        'race_predictions',
        '【実装後】ハイブリッドスコアリング導入後'
    )

    # 比較結果
    print()
    print("=" * 80)
    print("改善効果サマリー")
    print("=" * 80)
    print()

    if before_overall['total'] > 0 and after_overall['total'] > 0:
        print("【全体比較】")

        before_hit_rate = before_overall['hit'] / before_overall['total'] * 100
        after_hit_rate = after_overall['hit'] / after_overall['total'] * 100
        hit_rate_diff = after_hit_rate - before_hit_rate

        before_roi = (before_overall['total_return'] / before_overall['total_invested']) * 100
        after_roi = (after_overall['total_return'] / after_overall['total_invested']) * 100
        roi_diff = after_roi - before_roi

        before_profit = before_overall['total_return'] - before_overall['total_invested']
        after_profit = after_overall['total_return'] - after_overall['total_invested']
        profit_diff = after_profit - before_profit

        print(f"三連単的中率: {before_hit_rate:.2f}% → {after_hit_rate:.2f}% ({hit_rate_diff:+.2f}pt)")
        print(f"ROI: {before_roi:.2f}% → {after_roi:.2f}% ({roi_diff:+.2f}pt)")
        print(f"収支: {before_profit:+,.0f}円 → {after_profit:+,.0f}円 ({profit_diff:+,.0f}円)")
        print()

        # 各順位の的中率比較
        before_rank1 = before_overall['rank1_correct'] / before_overall['total'] * 100
        after_rank1 = after_overall['rank1_correct'] / after_overall['total'] * 100
        before_rank2 = before_overall['rank2_correct'] / before_overall['total'] * 100
        after_rank2 = after_overall['rank2_correct'] / after_overall['total'] * 100
        before_rank3 = before_overall['rank3_correct'] / before_overall['total'] * 100
        after_rank3 = after_overall['rank3_correct'] / after_overall['total'] * 100

        print("各順位的中率:")
        print(f"  1位: {before_rank1:.2f}% → {after_rank1:.2f}% ({after_rank1-before_rank1:+.2f}pt)")
        print(f"  2位: {before_rank2:.2f}% → {after_rank2:.2f}% ({after_rank2-before_rank2:+.2f}pt)")
        print(f"  3位: {before_rank3:.2f}% → {after_rank3:.2f}% ({after_rank3-before_rank3:+.2f}pt)")
        print()

    # 信頼度別比較
    print("【信頼度別比較】")
    for confidence in sorted(set(list(before_confidence.keys()) + list(after_confidence.keys()))):
        before_stats = before_confidence.get(confidence, {})
        after_stats = after_confidence.get(confidence, {})

        if before_stats.get('total', 0) == 0 or after_stats.get('total', 0) == 0:
            continue

        before_hit_rate = before_stats['hit'] / before_stats['total'] * 100
        after_hit_rate = after_stats['hit'] / after_stats['total'] * 100

        before_roi = (before_stats['total_return'] / before_stats['total_invested']) * 100
        after_roi = (after_stats['total_return'] / after_stats['total_invested']) * 100

        print(f"信頼度{confidence}:")
        print(f"  的中率: {before_hit_rate:.2f}% → {after_hit_rate:.2f}% ({after_hit_rate-before_hit_rate:+.2f}pt)")
        print(f"  ROI: {before_roi:.2f}% → {after_roi:.2f}% ({after_roi-before_roi:+.2f}pt)")

    conn.close()

    print()
    print("=" * 80)
    print("比較完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
