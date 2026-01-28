#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
データ整合性チェックスクリプト

指定月のデータの整合性を詳細にチェックします。
"""
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import argparse

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import DATABASE_PATH


def check_data_integrity(year: int, month: int) -> dict:
    """
    データ整合性チェック

    Args:
        year: 年
        month: 月

    Returns:
        dict: チェック結果
    """
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 対象期間
    start_date = f"{year:04d}-{month:02d}-01"
    if month == 12:
        end_date = f"{year+1:04d}-01-01"
    else:
        end_date = f"{year:04d}-{month+1:02d}-01"

    results = {
        'period': f"{year}年{month}月",
        'start_date': start_date,
        'end_date': end_date,
        'checks': {}
    }

    print("=" * 80)
    print(f"データ整合性チェック: {results['period']}")
    print("=" * 80)
    print()

    # 1. 基本統計
    print("[1] 基本統計")
    print("-" * 80)

    cursor.execute("""
        SELECT COUNT(*) FROM races
        WHERE race_date >= ? AND race_date < ?
    """, (start_date, end_date))
    total_races = cursor.fetchone()[0]
    print(f"総レース数: {total_races:,}件")
    results['checks']['total_races'] = total_races

    cursor.execute("""
        SELECT COUNT(DISTINCT race_id) FROM results r
        JOIN races ON r.race_id = races.id
        WHERE races.race_date >= ? AND races.race_date < ?
    """, (start_date, end_date))
    races_with_results = cursor.fetchone()[0]
    result_coverage = races_with_results / total_races * 100 if total_races > 0 else 0
    print(f"結果データ: {races_with_results:,}件 ({result_coverage:.1f}%)")
    results['checks']['results'] = {
        'count': races_with_results,
        'coverage': result_coverage
    }

    cursor.execute("""
        SELECT COUNT(DISTINCT race_id) FROM trifecta_odds t
        JOIN races ON t.race_id = races.id
        WHERE races.race_date >= ? AND races.race_date < ?
    """, (start_date, end_date))
    races_with_odds = cursor.fetchone()[0]
    odds_coverage = races_with_odds / total_races * 100 if total_races > 0 else 0
    print(f"オッズデータ: {races_with_odds:,}件 ({odds_coverage:.1f}%)")
    results['checks']['odds'] = {
        'count': races_with_odds,
        'coverage': odds_coverage
    }

    cursor.execute("""
        SELECT COUNT(DISTINCT race_id) FROM race_predictions rp
        JOIN races ON rp.race_id = races.id
        WHERE races.race_date >= ? AND races.race_date < ?
            AND (rp.prediction_type IS NULL OR rp.prediction_type = 'advance')
    """, (start_date, end_date))
    races_with_predictions = cursor.fetchone()[0]
    pred_coverage = races_with_predictions / total_races * 100 if total_races > 0 else 0
    print(f"事前予想: {races_with_predictions:,}件 ({pred_coverage:.1f}%)")
    results['checks']['predictions'] = {
        'count': races_with_predictions,
        'coverage': pred_coverage
    }
    print()

    # 2. 日別データ完全性
    print("[2] 日別データ完全性")
    print("-" * 80)

    cursor.execute("""
        SELECT
            r.race_date,
            COUNT(r.id) as total,
            COUNT(DISTINCT res.race_id) as has_result,
            COUNT(DISTINCT t.race_id) as has_odds,
            COUNT(DISTINCT rp.race_id) as has_pred
        FROM races r
        LEFT JOIN results res ON r.id = res.race_id
        LEFT JOIN trifecta_odds t ON r.id = t.race_id
        LEFT JOIN race_predictions rp ON r.id = rp.race_id
            AND (rp.prediction_type IS NULL OR rp.prediction_type = 'advance')
        WHERE r.race_date >= ? AND r.race_date < ?
        GROUP BY r.race_date
        ORDER BY r.race_date
    """, (start_date, end_date))

    daily_stats = []
    print("日付       | レース | 結果 | オッズ | 予想")
    print("-" * 60)
    for row in cursor.fetchall():
        date = row['race_date']
        total = row['total']
        result = row['has_result']
        odds = row['has_odds']
        pred = row['has_pred']
        daily_stats.append({
            'date': date,
            'total': total,
            'result': result,
            'odds': odds,
            'pred': pred
        })
        print(f"{date} | {total:4d} | {result:4d} | {odds:4d} | {pred:4d}")

    results['checks']['daily_stats'] = daily_stats
    print()

    # 3. 予測データの信頼度分布
    print("[3] 予測データの信頼度分布")
    print("-" * 80)

    cursor.execute("""
        SELECT
            rp.confidence,
            COUNT(DISTINCT rp.race_id) as race_count
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date >= ? AND r.race_date < ?
            AND (rp.prediction_type IS NULL OR rp.prediction_type = 'advance')
            AND rp.confidence IS NOT NULL
        GROUP BY rp.confidence
        ORDER BY rp.confidence
    """, (start_date, end_date))

    confidence_dist = {}
    total_pred_races = 0
    for row in cursor.fetchall():
        conf = row['confidence']
        count = row['race_count']
        confidence_dist[conf] = count
        total_pred_races += count

    for conf in ['A', 'B', 'C', 'D']:
        count = confidence_dist.get(conf, 0)
        pct = count / total_pred_races * 100 if total_pred_races > 0 else 0
        print(f"信頼度{conf}: {count:4d}件 ({pct:5.1f}%)")

    results['checks']['confidence_distribution'] = confidence_dist
    print()

    # 4. オッズデータの取得タイミング
    print("[4] オッズデータの取得タイミング")
    print("-" * 80)

    cursor.execute("""
        SELECT
            DATE(t.fetched_at) as fetch_date,
            COUNT(DISTINCT t.race_id) as race_count,
            MIN(t.fetched_at) as first_fetch,
            MAX(t.fetched_at) as last_fetch
        FROM trifecta_odds t
        JOIN races r ON t.race_id = r.id
        WHERE r.race_date >= ? AND r.race_date < ?
        GROUP BY DATE(t.fetched_at)
        ORDER BY fetch_date
    """, (start_date, end_date))

    print("取得日     | レース数 | 最初       | 最後")
    print("-" * 60)
    odds_timing = []
    for row in cursor.fetchall():
        fetch_date = row['fetch_date']
        count = row['race_count']
        first = row['first_fetch']
        last = row['last_fetch']
        odds_timing.append({
            'fetch_date': fetch_date,
            'count': count,
            'first': first,
            'last': last
        })
        first_time = first[11:16] if len(first) > 11 else first
        last_time = last[11:16] if len(last) > 11 else last
        print(f"{fetch_date} | {count:6d} | {first_time} | {last_time}")

    results['checks']['odds_timing'] = odds_timing
    print()

    # 5. データの矛盾チェック
    print("[5] データの矛盾チェック")
    print("-" * 80)

    issues = []

    # 5.1 結果があるのにオッズがない
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        JOIN results res ON r.id = res.race_id
        LEFT JOIN trifecta_odds t ON r.id = t.race_id
        WHERE r.race_date >= ? AND r.race_date < ?
            AND t.race_id IS NULL
    """, (start_date, end_date))
    result_no_odds = cursor.fetchone()[0]
    if result_no_odds > 0:
        issues.append(f"結果ありだがオッズなし: {result_no_odds}件")
        print(f"[WARNING] 結果ありだがオッズなし: {result_no_odds}件")

    # 5.2 予測があるのにオッズがない
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id
        LEFT JOIN trifecta_odds t ON r.id = t.race_id
        WHERE r.race_date >= ? AND r.race_date < ?
            AND (rp.prediction_type IS NULL OR rp.prediction_type = 'advance')
            AND t.race_id IS NULL
    """, (start_date, end_date))
    pred_no_odds = cursor.fetchone()[0]
    if pred_no_odds > 0:
        issues.append(f"予測ありだがオッズなし: {pred_no_odds}件")
        print(f"[WARNING] 予測ありだがオッズなし: {pred_no_odds}件")

    # 5.3 予測の整合性（3艇の予測があるか）
    cursor.execute("""
        SELECT r.id, r.race_date, r.venue_code, r.race_number,
               COUNT(DISTINCT rp.pit_number) as pred_count
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id
        WHERE r.race_date >= ? AND r.race_date < ?
            AND (rp.prediction_type IS NULL OR rp.prediction_type = 'advance')
        GROUP BY r.id
        HAVING pred_count < 6
        LIMIT 10
    """, (start_date, end_date))

    incomplete_preds = cursor.fetchall()
    if incomplete_preds:
        count = len(incomplete_preds)
        issues.append(f"不完全な予測（6艇未満）: {count}件以上")
        print(f"[WARNING] 不完全な予測（6艇未満）: {count}件以上")

    if not issues:
        print("[OK] 矛盾なし")

    results['checks']['issues'] = issues
    print()

    # 6. 購入候補レースの分析
    print("[6] 購入候補レースの分析")
    print("-" * 80)

    # 購入候補レース（予測が6艇ある）のカウント
    cursor.execute("""
        SELECT COUNT(*) FROM (
            SELECT r.id
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id
            WHERE r.race_date >= ? AND r.race_date < ?
                AND (rp.prediction_type IS NULL OR rp.prediction_type = 'advance')
            GROUP BY r.id
            HAVING COUNT(DISTINCT rp.pit_number) = 6
        )
    """, (start_date, end_date))
    purchase_candidates = cursor.fetchone()
    purchase_count = purchase_candidates[0] if purchase_candidates else 0

    print(f"購入候補レース: {purchase_count:,}件")

    # 購入候補レースのデータカバー率
    cursor.execute("""
        SELECT
            COUNT(DISTINCT r.id) as total,
            SUM(CASE WHEN res.race_id IS NOT NULL THEN 1 ELSE 0 END) as with_result,
            SUM(CASE WHEN t.race_id IS NOT NULL THEN 1 ELSE 0 END) as with_odds
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id
        LEFT JOIN results res ON r.id = res.race_id
        LEFT JOIN trifecta_odds t ON r.id = t.race_id
        WHERE r.race_date >= ? AND r.race_date < ?
            AND (rp.prediction_type IS NULL OR rp.prediction_type = 'advance')
        GROUP BY r.id
        HAVING COUNT(DISTINCT rp.pit_number) = 6
    """, (start_date, end_date))

    purchase_stats = cursor.fetchall()
    if purchase_stats:
        total = len(purchase_stats)
        with_result = sum(1 for s in purchase_stats if s['with_result'] > 0)
        with_odds = sum(1 for s in purchase_stats if s['with_odds'] > 0)

        result_pct = with_result / total * 100 if total > 0 else 0
        odds_pct = with_odds / total * 100 if total > 0 else 0

        print(f"  結果データあり: {with_result:,}件 ({result_pct:.1f}%)")
        print(f"  オッズデータあり: {with_odds:,}件 ({odds_pct:.1f}%)")

        results['checks']['purchase_candidates'] = {
            'total': total,
            'with_result': with_result,
            'with_odds': with_odds,
            'result_coverage': result_pct,
            'odds_coverage': odds_pct
        }
    else:
        print("  購入候補レースなし")

    print()
    print("=" * 80)

    conn.close()
    return results


def main():
    parser = argparse.ArgumentParser(description='データ整合性チェック')
    parser.add_argument('--month', type=str, help='対象月 (YYYY-MM形式)')
    parser.add_argument('--year', type=int, help='年')
    parser.add_argument('--month-num', type=int, help='月（1-12）')

    args = parser.parse_args()

    if args.month:
        # YYYY-MM形式
        year, month = map(int, args.month.split('-'))
    elif args.year and args.month_num:
        year = args.year
        month = args.month_num
    else:
        # デフォルト: 今月
        now = datetime.now()
        year = now.year
        month = now.month

    results = check_data_integrity(year, month)

    # 簡易的な判定
    print("\n[総合判定]")
    print("-" * 80)

    issues_found = False

    # オッズカバー率チェック
    if results['checks']['odds']['coverage'] < 90:
        print(f"[WARNING] オッズカバー率が低い: {results['checks']['odds']['coverage']:.1f}%（90%未満）")
        issues_found = True

    # 購入候補レースのオッズカバー率
    if 'purchase_candidates' in results['checks']:
        pc = results['checks']['purchase_candidates']
        if pc['odds_coverage'] < 95:
            print(f"[WARNING] 購入候補レースのオッズカバー率が低い: {pc['odds_coverage']:.1f}%（95%未満）")
            issues_found = True

    # 矛盾チェック
    if results['checks']['issues']:
        print(f"[WARNING] データの矛盾が検出されました:")
        for issue in results['checks']['issues']:
            print(f"  - {issue}")
        issues_found = True

    if not issues_found:
        print("[OK] データは正常です")

    return 0 if not issues_found else 1


if __name__ == '__main__':
    sys.exit(main())
