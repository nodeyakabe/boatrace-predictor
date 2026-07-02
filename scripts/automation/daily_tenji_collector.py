"""
オリジナル展示データの自動収集スケジューラー

毎日朝8時に前日のオリジナル展示データを収集してDBに保存します。
オリジナル展示データは前日分のみ取得可能なため、毎日実行が必須です。

使い方:
    # スケジューラーを起動（常駐）
    python scripts/automation/daily_tenji_collector.py

    # テスト実行（即座に1回実行）
    python scripts/automation/daily_tenji_collector.py --test

    # 手動で前日分を収集
    python scripts/automation/daily_tenji_collector.py --manual
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import time
import schedule
import argparse
import logging

# Windows環境での文字化け対策
# __main__のときのみ実行（importされた場合はスキップ）
# scheduler の _TeeStream が sys.stdout を管理しているため、
# モジュールインポート時に上書きすると scheduler log への出力が失われる
if __name__ == '__main__' and sys.platform == 'win32' and hasattr(sys.stdout, 'buffer'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'replace')

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.scraper.original_tenji_browser import OriginalTenjiBrowserScraper
from scripts.data_collection.save_tenji_to_db import save_tenji_data
import json

# ログ設定
log_dir = project_root / 'logs' / 'tenji_collection'
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / f'tenji_collector_{datetime.now().strftime("%Y%m")}.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def collect_previous_day_tenji(headless=True, update_existing=True):
    """
    前日のオリジナル展示データを収集してDBに保存

    Args:
        headless: ヘッドレスモード
        update_existing: 既存データを更新するか

    Returns:
        int: 収集したレース数
    """
    # 前日の日付を取得
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    logger.info(f"{'='*80}")
    logger.info(f"オリジナル展示データ自動収集開始")
    logger.info(f"対象日付: {yesterday} (前日)")
    logger.info(f"{'='*80}")

    # 全24場を対象
    venues = [f"{i:02d}" for i in range(1, 25)]

    all_results = []
    successful_venues = []
    failed_venues = []

    # 各場ごとにブラウザを再起動（セッション安定化のため）
    for venue in venues:
        venue_results = []
        scraper = None

        try:
            # 場ごとにスクレイパーを初期化
            scraper = OriginalTenjiBrowserScraper(headless=headless, timeout=60)
            venue_name = scraper.VENUE_CODE_TO_NAME.get(venue, '不明')

            logger.info(f"\n場コード {venue} ({venue_name}) の収集開始")

            for race_no in range(1, 13):
                result = None
                last_error = None
                for attempt in range(2):  # 最大2回試行（1回リトライ）
                    try:
                        result = scraper.get_original_tenji(venue, yesterday, race_no)
                        last_error = None
                        break  # 成功したらリトライ不要
                    except Exception as e:
                        last_error = e
                        if attempt == 0:
                            logger.warning(f"  [{venue}] {yesterday} {race_no}R - エラー(リトライ): {e}")
                            time.sleep(2)
                        else:
                            logger.warning(f"  [{venue}] {yesterday} {race_no}R - エラー(最終): {e}")

                if last_error is not None:
                    pass  # 全試行失敗、エラーはログ済み
                elif result:
                    logger.info(f"  [{venue}] {yesterday} {race_no}R - OK 取得成功: {len(result)}名")
                    venue_results.append({
                        'venue_code': venue,  # '01'形式の文字列のまま渡す（int変換するとDBの'01'と不一致になる）
                        'date': yesterday,
                        'race_no': race_no,
                        'racers': result
                    })
                else:
                    # データなしは正常（開催なし or 未公開）
                    logger.debug(f"  [{venue}] {yesterday} {race_no}R - データなし")

                # レート制限対策
                time.sleep(0.5)

            if venue_results:
                all_results.extend(venue_results)
                successful_venues.append(f"{venue}({venue_name})")
                logger.info(f"  {venue}場 完了: {len(venue_results)}レース")
            else:
                failed_venues.append(f"{venue}({venue_name})")
                logger.info(f"  {venue}場 - データなし（開催なし）")

        except Exception as e:
            logger.error(f"  {venue}場でエラー: {e}")
            failed_venues.append(f"{venue}(エラー)")

        finally:
            # 場ごとにブラウザをクローズ
            if scraper:
                try:
                    scraper.close()
                    logger.debug(f"  {venue}場 - ブラウザクローズ完了")
                except Exception:
                    pass

    if not all_results:
        logger.warning("収集データがありません（全会場でデータなし or スクレイピング失敗）")
        try:
            from scripts.automation.notify import send_error_notification
            send_error_notification(
                "展示データ収集0件",
                f"前日({yesterday})のオリジナル展示データが収集できませんでした。\n"
                f"エラー会場: {', '.join(failed_venues[:10])}"
            )
        except Exception:
            pass
        return 0

    # 一時JSONファイルに保存
    temp_json = project_root / 'temp' / f'tenji_{yesterday.replace("-", "")}_auto.json'
    temp_json.parent.mkdir(parents=True, exist_ok=True)

    with open(temp_json, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    logger.info(f"\n{'='*80}")
    logger.info(f"収集完了: {len(all_results)}レース")
    logger.info(f"成功: {len(successful_venues)}場 - {', '.join(successful_venues[:5])}{' ...' if len(successful_venues) > 5 else ''}")
    if failed_venues:
        logger.info(f"データなし: {len(failed_venues)}場")
    logger.info(f"一時保存: {temp_json}")
    logger.info(f"{'='*80}\n")

    # DBに保存
    logger.info("DBへの保存を開始...")
    db_path = project_root / 'data' / 'boatrace.db'

    try:
        saved = save_tenji_data(str(temp_json), str(db_path), update_existing=update_existing)
        if saved == 0:
            logger.warning(
                f"DB保存結果が0件（JSONには{len(all_results)}レースあり）"
                f" → 既存データのスキップか保存失敗の可能性"
            )
            print(
                f"[WARNING] 展示データDB保存0件 (JSON:{len(all_results)}レース)",
                flush=True
            )
    except Exception as e:
        logger.error(f"DB保存エラー: {e}")
        import traceback
        logger.error(traceback.format_exc())
        print(f"[ERROR] 展示データDB保存エラー: {e}", flush=True)
        return 0

    # 永久保存用にコピー
    final_json = project_root / 'data' / 'tenji' / 'boaters' / f'tenji_{yesterday.replace("-", "")}.json'
    final_json.parent.mkdir(parents=True, exist_ok=True)

    with open(final_json, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    logger.info(f"\n{'='*80}")
    logger.info(f"全て完了")
    logger.info(f"JSONバックアップ: {final_json}")
    logger.info(f"{'='*80}")

    return len(all_results)


def scheduled_job():
    """スケジュール実行されるジョブ"""
    logger.info("\n" + "="*80)
    logger.info("定期実行開始")
    logger.info("="*80)

    try:
        count = collect_previous_day_tenji(headless=True, update_existing=True)
        logger.info(f"定期実行完了: {count}レース収集")
    except Exception as e:
        logger.error(f"定期実行エラー: {e}", exc_info=True)


def run_scheduler():
    """スケジューラーを起動"""
    logger.info("オリジナル展示データ自動収集スケジューラー起動")
    logger.info("毎日朝8時に前日分のデータを収集します")
    logger.info(f"ログファイル: {log_dir}")

    # 毎日朝8時に実行
    schedule.every().day.at("08:00").do(scheduled_job)

    logger.info("\nスケジュール設定完了")
    logger.info("次回実行予定: 翌朝8:00")
    logger.info("(Ctrl+C で停止)\n")

    # スケジューラーループ
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # 1分ごとにチェック
        except KeyboardInterrupt:
            logger.info("\nスケジューラーを停止しました")
            break
        except Exception as e:
            logger.error(f"スケジューラーエラー: {e}", exc_info=True)
            time.sleep(300)  # エラー時は5分待機


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(description='オリジナル展示データ自動収集')
    parser.add_argument('--test', action='store_true', help='テスト実行（即座に1回実行）')
    parser.add_argument('--manual', action='store_true', help='手動実行（前日分を収集）')
    parser.add_argument('--show-browser', action='store_true', help='ブラウザを表示')
    args = parser.parse_args()

    if args.test or args.manual:
        # テスト/手動実行
        headless = not args.show_browser
        logger.info("手動実行モード" if args.manual else "テスト実行モード")
        count = collect_previous_day_tenji(headless=headless, update_existing=True)
        logger.info(f"実行完了: {count}レース収集")
    else:
        # スケジューラー起動
        run_scheduler()


if __name__ == '__main__':
    main()
