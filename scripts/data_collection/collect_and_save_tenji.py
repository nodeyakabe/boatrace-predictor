"""
オリジナル展示データの収集とDB保存を一括で実行

使い方:
    # 本日の全場データを収集してDB保存
    python scripts/data_collection/collect_and_save_tenji.py

    # 特定日・特定場を収集
    python scripts/data_collection/collect_and_save_tenji.py --date 2026-01-15 --venue 01

    # 既存データを更新
    python scripts/data_collection/collect_and_save_tenji.py --date 2026-01-15 --update
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import argparse
import json

# Windows環境での文字化け対策
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.scraper.original_tenji_browser import OriginalTenjiBrowserScraper
from scripts.data_collection.save_tenji_to_db import save_tenji_data


def collect_and_save(venues, target_date, race_range, headless, update_existing, db_path):
    """
    オリジナル展示データを収集してDBに保存

    Args:
        venues: 場コードのリスト
        target_date: 対象日付
        race_range: レース範囲
        headless: ヘッドレスモード
        update_existing: 既存データ更新
        db_path: DBパス
    """
    print(f"{'='*80}")
    print(f"オリジナル展示データ収集 & DB保存")
    print(f"対象日付: {target_date}")
    print(f"対象場: {venues if len(venues) <= 5 else f'{len(venues)}場'}")
    print(f"対象レース: {race_range if len(race_range) <= 3 else f'{len(race_range)}レース'}")
    print(f"{'='*80}\n")

    all_results = []

    # 各場ごとにブラウザを再起動（セッション安定化のため）
    for venue in venues:
        scraper = None

        try:
            # 場ごとにスクレイパーを初期化
            scraper = OriginalTenjiBrowserScraper(headless=headless, timeout=30)
            print(f"\n場コード {venue} の収集開始")

            for race_no in race_range:
                print(f"  [{venue}] {target_date} {race_no}R - 取得中...")

                try:
                    result = scraper.get_original_tenji(venue, target_date, race_no)

                    if result:
                        print(f"    ✓ データ取得成功: {len(result)}名")
                        all_results.append({
                            'venue_code': int(venue),
                            'date': target_date,
                            'race_no': race_no,
                            'racers': result
                        })
                    else:
                        print(f"    - データなし（開催なし or データ未公開）")

                except Exception as e:
                    print(f"    ✗ エラー: {e}")

        except Exception as e:
            print(f"✗ {venue}場でエラー: {e}")

        finally:
            # 場ごとにブラウザをクローズ
            if scraper:
                try:
                    scraper.close()
                except Exception:
                    pass

    if not all_results:
        print("\n収集データがありません")
        return

    # 一時JSONファイルに保存
    temp_json = project_root / 'temp' / f'tenji_{target_date.replace("-", "")}_temp.json'
    temp_json.parent.mkdir(parents=True, exist_ok=True)

    with open(temp_json, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*80}")
    print(f"収集完了: {len(all_results)}レース")
    print(f"一時保存: {temp_json}")
    print(f"{'='*80}\n")

    # DBに保存
    print("DBへの保存を開始...")
    save_tenji_data(temp_json, db_path, update_existing=update_existing)

    # 永久保存用にコピー
    final_json = project_root / 'data' / 'tenji' / 'boaters' / f'tenji_{target_date.replace("-", "")}.json'
    final_json.parent.mkdir(parents=True, exist_ok=True)

    with open(final_json, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*80}")
    print(f"全て完了")
    print(f"JSONバックアップ: {final_json}")
    print(f"{'='*80}")


def main():
    """メイン処理"""

    parser = argparse.ArgumentParser(description='オリジナル展示データ収集 & DB保存')
    parser.add_argument('--date', type=str, help='対象日付 (YYYY-MM-DD)', default=None)
    parser.add_argument('--venue', type=str, help='場コード (01-24)', default=None)
    parser.add_argument('--race', type=int, help='レース番号 (1-12、指定時は単一レースのみ)', default=None)
    parser.add_argument('--headless', action='store_true', help='ヘッドレスモードで実行', default=True)
    parser.add_argument('--show-browser', action='store_true', help='ブラウザを表示（デバッグ用）')
    parser.add_argument('--update', action='store_true', help='既存データを更新')
    parser.add_argument('--db', type=str, default='data/boatrace.db', help='DBファイルパス')
    args = parser.parse_args()

    # デフォルトは本日
    target_date = args.date if args.date else datetime.now().strftime('%Y-%m-%d')

    # デフォルトは全場
    if args.venue:
        venues = [f"{int(args.venue):02d}"]
    else:
        venues = [f"{i:02d}" for i in range(1, 25)]

    # レース範囲
    if args.race:
        race_range = [args.race]
    else:
        race_range = list(range(1, 13))

    # ヘッドレスモード設定
    headless = args.headless and not args.show_browser

    # DB パス
    db_path = project_root / args.db

    collect_and_save(venues, target_date, race_range, headless, args.update, db_path)


if __name__ == '__main__':
    main()
