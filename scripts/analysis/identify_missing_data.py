#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
欠損データの詳細特定スクリプト

どの年・月・データ種別が欠けているかを月別に詳細特定します。
"""
import sys
import io
import sqlite3
from pathlib import Path
from datetime import datetime

# Windows文字コード対策
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DATABASE_PATH


def check_monthly_coverage(cursor: sqlite3.Cursor, year: int, month: int):
    """特定月のデータカバレッジを確認"""

    date_pattern = f'{year}-{month:02d}-%'

    # 総レース数
    cursor.execute("""
        SELECT COUNT(*) FROM races WHERE race_date LIKE ?
    """, (date_pattern,))
    total_races = cursor.fetchone()[0]

    if total_races == 0:
        return None

    # entries
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_date LIKE ?
        AND EXISTS (SELECT 1 FROM entries e WHERE e.race_id = r.id)
    """, (date_pattern,))
    with_entries = cursor.fetchone()[0]

    # results
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_date LIKE ?
        AND EXISTS (SELECT 1 FROM results res WHERE res.race_id = r.id)
    """, (date_pattern,))
    with_results = cursor.fetchone()[0]

    # trifecta_odds
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_date LIKE ?
        AND EXISTS (SELECT 1 FROM trifecta_odds t WHERE t.race_id = r.id)
    """, (date_pattern,))
    with_odds = cursor.fetchone()[0]

    # race_details
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_date LIKE ?
        AND EXISTS (SELECT 1 FROM race_details rd WHERE rd.race_id = r.id)
    """, (date_pattern,))
    with_details = cursor.fetchone()[0]

    # payouts
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_date LIKE ?
        AND EXISTS (SELECT 1 FROM payouts p WHERE p.race_id = r.id)
    """, (date_pattern,))
    with_payouts = cursor.fetchone()[0]

    return {
        'total': total_races,
        'entries': with_entries,
        'results': with_results,
        'odds': with_odds,
        'details': with_details,
        'payouts': with_payouts
    }


def main():
    print("=" * 80)
    print("欠損データの詳細特定")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    for year in [2021, 2023]:
        print(f"=== {year}年の月別欠損状況 ===")
        print()
        print("月  | レース数 | entries | results | odds    | details | payouts")
        print("----|----------|---------|---------|---------|---------|--------")

        critical_months = []

        for month in range(1, 13):
            coverage = check_monthly_coverage(cursor, year, month)

            if coverage is None:
                print(f"{month:2d}月 | データなし")
                continue

            total = coverage['total']
            entries_pct = coverage['entries'] / total * 100
            results_pct = coverage['results'] / total * 100
            odds_pct = coverage['odds'] / total * 100
            details_pct = coverage['details'] / total * 100
            payouts_pct = coverage['payouts'] / total * 100

            # 状態表示
            def status(pct):
                if pct >= 99.9:
                    return "✅"
                elif pct >= 80:
                    return "🟡"
                else:
                    return "❌"

            print(f"{month:2d}月 | {total:5d}件 | "
                  f"{status(entries_pct)} {entries_pct:5.1f}% | "
                  f"{status(results_pct)} {results_pct:5.1f}% | "
                  f"{status(odds_pct)} {odds_pct:5.1f}% | "
                  f"{status(details_pct)} {details_pct:5.1f}% | "
                  f"{status(payouts_pct)} {payouts_pct:5.1f}%")

            # 重大な欠損がある月を記録
            if odds_pct < 50 or details_pct < 50 or payouts_pct < 50:
                critical_months.append((month, coverage))

        print()

        # 重大な欠損がある月の詳細
        if critical_months:
            print(f"⚠️ {year}年の重大な欠損月:")
            for month, coverage in critical_months:
                print(f"  {year}年{month}月:")
                missing_odds = coverage['total'] - coverage['odds']
                missing_details = coverage['total'] - coverage['details']
                missing_payouts = coverage['total'] - coverage['payouts']

                if missing_odds > 0:
                    print(f"    - オッズ: {missing_odds}件欠損")
                if missing_details > 0:
                    print(f"    - レース詳細: {missing_details}件欠損")
                if missing_payouts > 0:
                    print(f"    - 払戻: {missing_payouts}件欠損")

        print()

    print("=" * 80)
    print("推奨アクション")
    print("=" * 80)
    print()
    print("全データ種別を一括で収集し直すのが最も確実です:")
    print()
    print("【方法1】月別に収集してDB投入（推奨）")
    print("  1. 欠損月のデータを収集（CSV生成）")
    print("  2. CSVをDBに投入")
    print("  3. 次の月へ（進捗保存可能）")
    print()
    print("【方法2】全期間を一括収集")
    print("  1. 2021年・2023年の全データを再収集")
    print("  2. 一括でDB投入")
    print("  3. 時間はかかるが確実")
    print()

    conn.close()


if __name__ == '__main__':
    main()
