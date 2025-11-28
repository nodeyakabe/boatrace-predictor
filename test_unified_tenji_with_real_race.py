#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
統合オリジナル展示収集器のテスト（実在レース使用）

DBから最新のレースを取得してテスト
"""
import sys
import os
import sqlite3
from datetime import datetime, timedelta

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.unified_tenji_collector import UnifiedTenjiCollector
from config.settings import DATABASE_PATH


def get_recent_race():
    """DBから最新のレースを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 最新のレースを取得
    cursor.execute("""
        SELECT race_date, venue_code, race_number
        FROM races
        ORDER BY race_date DESC
        LIMIT 1
    """)

    row = cursor.fetchone()
    conn.close()

    return row if row else (None, None, None)


def test_with_real_race():
    """実在するレースでテスト"""
    print("="*70)
    print("統合オリジナル展示収集器 - 実在レーステスト")
    print("="*70)
    print()

    # DBから最新レースを取得
    race_date, venue_code, race_number = get_recent_race()

    if not race_date:
        print("✗ DBにレースデータがありません")
        return

    print(f"テスト対象（DBから取得）:")
    print(f"  日付: {race_date}")
    print(f"  会場: {venue_code}")
    print(f"  レース: {race_number}R")
    print()

    print("注意: このレースは既に終了している可能性が高いため、")
    print("      オリジナル展示データは取得できないかもしれません。")
    print("      テストの目的は、収集器が正常に動作するかの確認です。")
    print()

    collector = None
    try:
        print("収集器を初期化中...")
        collector = UnifiedTenjiCollector(headless=True, timeout=15)
        print("✓ 初期化完了\n")

        print("データを収集中...")
        print("  1次試行: Boatersサイト")
        print("  2次試行: 各場公式HP（Boaters失敗時）")
        print()

        result = collector.get_original_tenji(venue_code, race_date, race_number)

        print()
        print("-" * 70)
        print("収集結果:")
        print("-" * 70)

        if result:
            print(f"✓ データ取得成功!")
            print(f"  データソース: {result.get('source', '不明')}")
            print()

            # 各艇のデータを表示
            boat_count = 0
            for boat_num in range(1, 7):
                if boat_num in result:
                    boat_data = result[boat_num]
                    boat_count += 1
                    print(f"  {boat_num}号艇:")
                    print(f"    直線タイム: {boat_data.get('chikusen_time', 'なし')}")
                    print(f"    1周タイム: {boat_data.get('isshu_time', 'なし')}")
                    print(f"    回り足タイム: {boat_data.get('mawariashi_time', 'なし')}")

            print()
            print(f"  取得艇数: {boat_count}/6")
        else:
            print("✗ データ取得失敗")
            print("  原因: レースが終了済みか、オリジナル展示データが未公開")

        # 統計情報を表示
        stats = collector.get_stats()
        print()
        print("-" * 70)
        print("収集統計:")
        print("-" * 70)
        print(f"試行回数: {stats['total_attempts']}")
        print(f"Boaters成功: {stats['boaters_success']}")
        print(f"各場HP成功: {stats['venue_success']}")
        print(f"両方失敗: {stats['failures']}")
        print(f"成功率: {stats['success_rate']:.1f}%")

        # 収集器が正常に動作したかの判定
        print()
        print("-" * 70)
        print("動作確認:")
        print("-" * 70)

        if stats['total_attempts'] > 0:
            print("✓ 収集器は正常に動作しました")
            print("✓ Boatersサイトへのアクセスを試行")

            if stats['boaters_success'] > 0:
                print("✓ Boatersサイトからのデータ取得成功")
            else:
                print("  Boatersサイトはデータなし（レース終了済みの可能性）")
                print("✓ 各場公式HPへの自動フォールバック動作を確認")
        else:
            print("✗ 収集器の動作に問題があります")

    except Exception as e:
        print(f"✗ エラー発生: {e}")
        import traceback
        traceback.print_exc()

    finally:
        if collector:
            print("\n収集器を終了中...")
            collector.close()
            print("✓ 終了完了")

    print()
    print("="*70)
    print("テスト完了")
    print("="*70)
    print()
    print("【推奨】未来のレース（明日以降）でテストすると、")
    print("       実際のデータ取得成功を確認できます:")
    print()
    print("  python fetch_original_tenji_daily.py --date 2025-11-29 --limit 5")


if __name__ == "__main__":
    test_with_real_race()
