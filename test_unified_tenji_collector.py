#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
統合オリジナル展示収集器のテスト

簡易テスト: 1レースだけ収集して動作確認
"""
import sys
import os
from datetime import datetime, timedelta

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.unified_tenji_collector import UnifiedTenjiCollector


def test_single_race():
    """1レースだけテスト収集"""
    print("="*70)
    print("統合オリジナル展示収集器 - 動作テスト")
    print("="*70)
    print()

    # 今日の日付で若松（会場コード20）の1Rを試す
    venue_code = "20"  # 若松
    target_date = datetime.now().strftime('%Y-%m-%d')
    race_number = 1

    print(f"テスト対象:")
    print(f"  会場: {venue_code} (若松)")
    print(f"  日付: {target_date}")
    print(f"  レース: {race_number}R")
    print()

    collector = None
    try:
        print("収集器を初期化中...")
        collector = UnifiedTenjiCollector(headless=True, timeout=15)
        print("✓ 初期化完了\n")

        print("データを収集中...")
        result = collector.get_original_tenji(venue_code, target_date, race_number)

        print()
        print("-" * 70)
        print("収集結果:")
        print("-" * 70)

        if result:
            print(f"✓ データ取得成功!")
            print(f"  データソース: {result.get('source', '不明')}")
            print()

            # 各艇のデータを表示
            for boat_num in range(1, 7):
                if boat_num in result:
                    boat_data = result[boat_num]
                    print(f"  {boat_num}号艇:")
                    print(f"    直線タイム: {boat_data.get('chikusen_time', 'なし')}")
                    print(f"    1周タイム: {boat_data.get('isshu_time', 'なし')}")
                    print(f"    回り足タイム: {boat_data.get('mawariashi_time', 'なし')}")
        else:
            print("✗ データ取得失敗")
            print("  原因: レースが存在しないか、オリジナル展示データが未公開")

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


if __name__ == "__main__":
    test_single_race()
