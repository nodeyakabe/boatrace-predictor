# -*- coding: utf-8 -*-
"""
信頼度Bフィルター効果検証スクリプト

過去データに対してフィルターを適用し、的中率の改善効果を検証
資金配分は考慮せず、純粋な的中率のみを比較
"""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime
import argparse

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.confidence_filter import ConfidenceBFilter
from config.settings import DATABASE_PATH


def get_prediction_and_result(cursor, race_id):
    """予測と実際の結果を取得"""
    # 予測（上位3艇）
    cursor.execute('''
        SELECT pit_number
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'advance'
        ORDER BY rank_prediction
        LIMIT 3
    ''', (race_id,))

    pred_rows = cursor.fetchall()
    if len(pred_rows) < 3:
        return None, None

    prediction = tuple(row[0] for row in pred_rows)

    # 実際の結果
    cursor.execute('''
        SELECT pit_number
        FROM results
        WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
        ORDER BY rank
        LIMIT 3
    ''', (race_id,))

    result_rows = cursor.fetchall()
    if len(result_rows) < 3:
        return prediction, None

    result = tuple(row[0] for row in result_rows)

    return prediction, result


def validate_filter_effectiveness(start_date: str, end_date: str, prediction_type: str = 'advance'):
    """
    フィルター効果を検証

    Args:
        start_date: 検証開始日（YYYY-MM-DD）
        end_date: 検証終了日（YYYY-MM-DD）
        prediction_type: 予測タイプ（'advance' or 'before'）
    """
    print("=" * 80)
    print("信頼度Bフィルター効果検証（資金配分なし）")
    print("=" * 80)
    print(f"検証期間: {start_date} ～ {end_date}")
    print(f"予測タイプ: {prediction_type}")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 信頼度Bの予測を抽出
    query = """
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            rp.total_score as confidence_score
        FROM races r
        INNER JOIN race_predictions rp ON r.id = rp.race_id
        WHERE r.race_date >= ? AND r.race_date <= ?
            AND rp.prediction_type = ?
            AND rp.rank_prediction = 1
            AND rp.confidence = 'B'
        ORDER BY r.race_date, r.venue_code, r.race_number
    """

    cursor.execute(query, (start_date, end_date, prediction_type))
    races = [dict(row) for row in cursor.fetchall()]

    if not races:
        print(f"\n[!] {start_date} ～ {end_date} に信頼度Bの予測が見つかりませんでした")
        conn.close()
        return

    print(f"\n総レース数: {len(races)}")

    # フィルター初期化
    b_filter = ConfidenceBFilter(
        exclude_low_venues=True,
        venue_threshold=5.0,
        seasonal_adjustment=True,
        low_season_score_boost=2.0
    )

    print("\n" + "=" * 80)
    print("フィルター設定")
    print("=" * 80)
    print(b_filter.get_venue_summary())

    # フィルタリング実行
    print("\n" + "=" * 80)
    print("フィルタリング実行中...")
    print("=" * 80)

    accepted_races = []
    rejected_races = []

    for race in races:
        filter_result = b_filter.should_accept_bet(
            venue_code=race['venue_code'],
            race_date=race['race_date'],
            confidence_score=race['confidence_score']
        )

        race_info = {
            **race,
            'filter_result': filter_result
        }

        if filter_result['accept']:
            accepted_races.append(race_info)
        else:
            rejected_races.append(race_info)

    print(f"\n受け入れ: {len(accepted_races)} ({len(accepted_races)/len(races)*100:.1f}%)")
    print(f"除外: {len(rejected_races)} ({len(rejected_races)/len(races)*100:.1f}%)")

    # 的中率計算（フィルター前）
    print("\n" + "=" * 80)
    print("【フィルター適用前】全レースの的中率")
    print("=" * 80)

    total_hits = 0
    total_with_results = 0

    for race in races:
        pred, result = get_prediction_and_result(cursor, race['race_id'])
        if pred and result:
            total_with_results += 1
            if pred == result:
                total_hits += 1

    before_hit_rate = (total_hits / total_with_results * 100) if total_with_results > 0 else 0

    print(f"\n総レース数: {len(races)}")
    print(f"結果あり: {total_with_results}")
    print(f"的中数: {total_hits}")
    print(f"的中率: {before_hit_rate:.2f}%")

    # 的中率計算（フィルター後 - 受け入れレース）
    print("\n" + "=" * 80)
    print("【フィルター適用後】受け入れレースの的中率")
    print("=" * 80)

    accepted_hits = 0
    accepted_with_results = 0

    for race in accepted_races:
        pred, result = get_prediction_and_result(cursor, race['race_id'])
        if pred and result:
            accepted_with_results += 1
            if pred == result:
                accepted_hits += 1

    after_hit_rate = (accepted_hits / accepted_with_results * 100) if accepted_with_results > 0 else 0

    print(f"\n受け入れレース数: {len(accepted_races)}")
    print(f"結果あり: {accepted_with_results}")
    print(f"的中数: {accepted_hits}")
    print(f"的中率: {after_hit_rate:.2f}%")

    # 除外レースの的中率（参考）
    print("\n" + "=" * 80)
    print("【参考】除外レースの的中率")
    print("=" * 80)

    rejected_hits = 0
    rejected_with_results = 0

    for race in rejected_races:
        pred, result = get_prediction_and_result(cursor, race['race_id'])
        if pred and result:
            rejected_with_results += 1
            if pred == result:
                rejected_hits += 1

    rejected_hit_rate = (rejected_hits / rejected_with_results * 100) if rejected_with_results > 0 else 0

    print(f"\n除外レース数: {len(rejected_races)}")
    print(f"結果あり: {rejected_with_results}")
    print(f"的中数: {rejected_hits}")
    print(f"的中率: {rejected_hit_rate:.2f}%")

    # 改善効果のサマリー
    print("\n" + "=" * 80)
    print("フィルター効果サマリー")
    print("=" * 80)

    improvement = after_hit_rate - before_hit_rate
    improvement_pct = (improvement / before_hit_rate * 100) if before_hit_rate > 0 else 0

    print(f"\nフィルター前の的中率: {before_hit_rate:.2f}%")
    print(f"フィルター後の的中率: {after_hit_rate:.2f}%")
    print(f"改善幅: {improvement:+.2f}ポイント ({improvement_pct:+.1f}%)")

    if improvement > 0:
        print(f"\n[OK] フィルターにより的中率が改善しました")
    elif improvement < 0:
        print(f"\n[WARNING] フィルターにより的中率が低下しました")
    else:
        print(f"\n[NEUTRAL] フィルターの効果は中立的です")

    # 除外理由の内訳
    print("\n" + "=" * 80)
    print("除外理由の内訳")
    print("=" * 80)

    rejection_reasons = {}
    for race in rejected_races:
        adjustment = race['filter_result']['adjustment']
        rejection_reasons[adjustment] = rejection_reasons.get(adjustment, 0) + 1

    for reason, count in sorted(rejection_reasons.items(), key=lambda x: x[1], reverse=True):
        percentage = count / len(rejected_races) * 100 if rejected_races else 0
        print(f"  {reason}: {count}件 ({percentage:.1f}%)")

    # 月別の効果
    print("\n" + "=" * 80)
    print("月別フィルター効果")
    print("=" * 80)

    monthly_stats = {}
    for race in races:
        try:
            month = datetime.strptime(race['race_date'], '%Y-%m-%d').month
        except:
            month = 0

        if month not in monthly_stats:
            monthly_stats[month] = {
                'total': 0, 'total_hits': 0,
                'accepted': 0, 'accepted_hits': 0,
                'rejected': 0, 'rejected_hits': 0
            }

        pred, result = get_prediction_and_result(cursor, race['race_id'])
        if pred and result:
            monthly_stats[month]['total'] += 1
            if pred == result:
                monthly_stats[month]['total_hits'] += 1

    # 受け入れ/除外の分類
    for race in accepted_races:
        try:
            month = datetime.strptime(race['race_date'], '%Y-%m-%d').month
        except:
            month = 0

        pred, result = get_prediction_and_result(cursor, race['race_id'])
        if pred and result:
            monthly_stats[month]['accepted'] += 1
            if pred == result:
                monthly_stats[month]['accepted_hits'] += 1

    for race in rejected_races:
        try:
            month = datetime.strptime(race['race_date'], '%Y-%m-%d').month
        except:
            month = 0

        pred, result = get_prediction_and_result(cursor, race['race_id'])
        if pred and result:
            monthly_stats[month]['rejected'] += 1
            if pred == result:
                monthly_stats[month]['rejected_hits'] += 1

    print(f"\n{'月':>4} | {'全体的中率':>12} | {'受入的中率':>12} | {'除外的中率':>12} | {'改善':>8}")
    print("-" * 70)

    for month in sorted(monthly_stats.keys()):
        if month == 0:
            continue

        stats = monthly_stats[month]

        total_rate = (stats['total_hits'] / stats['total'] * 100) if stats['total'] > 0 else 0
        accepted_rate = (stats['accepted_hits'] / stats['accepted'] * 100) if stats['accepted'] > 0 else 0
        rejected_rate = (stats['rejected_hits'] / stats['rejected'] * 100) if stats['rejected'] > 0 else 0
        improvement_month = accepted_rate - total_rate

        print(f"{month:4d} | {total_rate:11.2f}% | {accepted_rate:11.2f}% | {rejected_rate:11.2f}% | {improvement_month:+7.2f}pt")

    conn.close()

    print("\n" + "=" * 80)
    print("検証完了")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description='信頼度Bフィルター効果検証')
    parser.add_argument('--start', type=str, default='2024-01-01', help='検証開始日（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, default='2024-12-31', help='検証終了日（YYYY-MM-DD）')
    parser.add_argument('--type', type=str, default='advance', choices=['advance', 'before'], help='予測タイプ')

    args = parser.parse_args()

    try:
        validate_filter_effectiveness(args.start, args.end, args.type)
    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
