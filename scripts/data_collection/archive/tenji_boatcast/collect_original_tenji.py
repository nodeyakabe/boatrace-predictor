"""
オリジナル展示データ収集スクリプト（既存スクレイパー利用版）

src/scraper/original_tenji_browser.py (Selenium版) を使用して
確実にデータを収集します。

使い方:
    # 本日の全場データを収集
    python scripts/data_collection/collect_original_tenji.py

    # 特定日のデータを収集
    python scripts/data_collection/collect_original_tenji.py --date 2026-01-15

    # 特定場のデータを収集
    python scripts/data_collection/collect_original_tenji.py --venue 01

    # 単一レースをテスト
    python scripts/data_collection/collect_original_tenji.py --venue 01 --date 2026-01-15 --race 1
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


def main():
    """メイン処理"""

    parser = argparse.ArgumentParser(description='オリジナル展示データ収集（Selenium版）')
    parser.add_argument('--date', type=str, help='対象日付 (YYYY-MM-DD)', default=None)
    parser.add_argument('--venue', type=str, help='場コード (01-24)', default=None)
    parser.add_argument('--race', type=int, help='レース番号 (1-12、指定時は単一レースのみ取得)', default=None)
    parser.add_argument('--headless', action='store_true', help='ヘッドレスモードで実行', default=True)
    parser.add_argument('--show-browser', action='store_true', help='ブラウザを表示（デバッグ用）')
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

    print(f"{'='*80}")
    print(f"オリジナル展示データ収集 (Selenium版)")
    print(f"対象日付: {target_date}")
    print(f"対象場: {venues if len(venues) <= 5 else f'{len(venues)}場'}")
    print(f"対象レース: {race_range if len(race_range) <= 3 else f'{len(race_range)}レース'}")
    print(f"ブラウザ表示: {'ON' if not headless else 'OFF'}")
    print(f"{'='*80}\n")

    all_results = []

    # 各場ごとにブラウザを再起動（セッション安定化のため）
    for venue in venues:
        scraper = None

        try:
            # 場ごとにスクレイパーを初期化
            scraper = OriginalTenjiBrowserScraper(headless=headless, timeout=30)
            print(f"\n場コード {venue} の処理開始")

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
            print("\n【解決方法】")
            print("1. ChromeDriverをインストール:")
            print("   pip install webdriver-manager")
            print("2. Chromeブラウザがインストールされているか確認")

        finally:
            # 場ごとにブラウザをクローズ
            if scraper:
                try:
                    scraper.close()
                except Exception:
                    pass

    # 結果を保存
    output_dir = project_root / 'data' / 'tenji' / 'boaters'
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f'tenji_{target_date.replace("-", "")}.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*80}")
    print(f"収集完了: {len(all_results)}レース")
    print(f"保存先: {output_file}")
    print(f"{'='*80}")


if __name__ == '__main__':
    main()
