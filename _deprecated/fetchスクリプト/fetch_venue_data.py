"""
BOAT RACE公式サイトから全24会場のデータを取得してDBに保存

実行方法:
    python fetch_venue_data.py

取得データ:
    - 会場名、水質、干満差、モーター種別
    - コース別1着率（1〜6コース）
    - レコードタイム・記録保持者
"""

import sys
import os

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.scraper.official_venue_scraper import OfficialVenueScraper
from src.database.venue_data import VenueDataManager
from config.settings import DATABASE_PATH


def main():
    """メイン処理"""
    print("="*80)
    print("BOAT RACE公式サイトから会場データを取得")
    print("="*80)

    # スクレイパー初期化
    scraper = OfficialVenueScraper(timeout=30)

    # データベースマネージャー初期化
    manager = VenueDataManager(DATABASE_PATH)

    print(f"\nデータベース: {DATABASE_PATH}")
    print(f"現在の会場数: {manager.count_venues()}件\n")

    print("="*80)
    print("実行内容:")
    print("  1. 全24会場のデータを取得（各会場2秒間隔）")
    print("  2. データベースに保存（UPSERT）")
    print("  3. 取得結果のサマリー表示")
    print("="*80)

    # 確認プロンプト
    print("\n実行しますか？ (y/n): ", end='')
    response = input().lower()

    if response != 'y':
        print("\nキャンセルしました")
        scraper.close()
        return

    # 全会場データ取得
    print("\n" + "="*80)
    print("データ取得開始...")
    print("="*80 + "\n")

    all_data = scraper.fetch_all_venues(delay=2.0)

    # データベースに保存
    if all_data:
        print("\n" + "="*80)
        print("データベースに保存中...")
        print("="*80 + "\n")

        success_count = manager.save_all_venues(all_data)

        # サマリー表示
        print("\n" + "="*80)
        print("取得結果サマリー")
        print("="*80)
        print(f"\n取得成功: {len(all_data)}/24 会場")
        print(f"保存成功: {success_count}/{len(all_data)} 会場")

        # 1コース勝率TOP5を表示
        print("\n【1コース勝率 TOP5】")
        sorted_venues = sorted(
            all_data.values(),
            key=lambda x: x.get('course_1_win_rate', 0),
            reverse=True
        )

        for i, venue in enumerate(sorted_venues[:5], 1):
            print(f"  {i}. {venue['venue_name']:8s} - {venue['course_1_win_rate']:.1f}%")

        # 1コース勝率BOTTOM5を表示
        print("\n【1コース勝率 BOTTOM5】")
        for i, venue in enumerate(sorted_venues[-5:], 1):
            print(f"  {i}. {venue['venue_name']:8s} - {venue['course_1_win_rate']:.1f}%")

        print("\n" + "="*80)
        print("完了")
        print("="*80)
    else:
        print("\n✗ データ取得に失敗しました")

    # クリーンアップ
    scraper.close()


if __name__ == "__main__":
    main()
