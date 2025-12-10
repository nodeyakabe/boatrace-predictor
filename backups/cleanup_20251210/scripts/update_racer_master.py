"""
ボートレーサー名鑑から選手マスタデータを更新

使用方法:
    python scripts/update_racer_master.py           # 全選手を更新
    python scripts/update_racer_master.py --test    # テスト（10人のみ）
    python scripts/update_racer_master.py --limit 50  # 件数指定
"""

import os
import sys
import argparse

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.scraper.racer_master_scraper import RacerMasterScraper


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(description='選手マスタデータ更新')
    parser.add_argument('--test', action='store_true', help='テストモード（10人のみ）')
    parser.add_argument('--limit', type=int, help='取得件数制限')
    parser.add_argument('--detail', action='store_true', help='詳細情報も取得（時間がかかります）')
    args = parser.parse_args()

    # データベースパス
    db_path = os.path.join(PROJECT_ROOT, 'data', 'boatrace.db')

    if not os.path.exists(db_path):
        print(f"エラー: データベースが見つかりません: {db_path}")
        print("先にマイグレーションを実行してください:")
        print("  python scripts/migrate_create_racers_table.py")
        return

    # 取得件数
    limit = None
    if args.test:
        limit = 10
        print("テストモード: 10人のみ取得します")
    elif args.limit:
        limit = args.limit
        print(f"制限モード: {limit}人のみ取得します")

    # スクレイパー実行
    scraper = RacerMasterScraper(db_path, headless=True)

    if args.detail:
        print("詳細情報取得モード")
        scraper.update_all_racers(limit=limit)
    else:
        print("簡易モード（登録番号と性別のみ）")
        scraper.update_racers_basic_only(limit=limit)


if __name__ == '__main__':
    main()
