"""
不足データ取得ワーカー（バックグラウンド実行用）

このスクリプトはジョブマネージャーから呼び出され、
進捗をファイルに書き込みながら処理を行う
"""
import os
import sys
import argparse
import json
from datetime import datetime, timedelta
import subprocess

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.utils.job_manager import update_job_progress, complete_job

JOB_NAME = 'missing_data_fetch'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, required=True,
                        help='設定ファイルパス（JSON）')
    args = parser.parse_args()

    try:
        # 設定ファイルを読み込み
        with open(args.config, 'r', encoding='utf-8') as f:
            config = json.load(f)

        missing_dates = config.get('missing_dates', [])
        check_types = config.get('check_types', [])

        if not missing_dates:
            complete_job(JOB_NAME, success=True, message='取得対象データがありません')
            return

        total = len(missing_dates)
        processed = 0
        errors = 0

        for item in missing_dates:
            date_str = item['日付']
            issues = item.get('問題', '')

            update_job_progress(JOB_NAME, {
                'status': 'running',
                'progress': int((processed / total) * 100),
                'message': f'{date_str} を処理中... ({processed+1}/{total})',
                'current_date': date_str,
                'processed': processed,
                'total': total,
                'errors': errors
            })

            try:
                # レース基本情報取得
                if "レース情報なし" in issues:
                    from src.scraper.bulk_scraper import BulkScraper
                    scraper = BulkScraper()

                    venue_codes = [f"{i:02d}" for i in range(1, 25)]
                    date_formatted = date_str.replace('-', '')

                    scraper.fetch_multiple_venues(
                        venue_codes=venue_codes,
                        race_date=date_formatted,
                        race_count=12
                    )

                # 補完スクリプトの実行
                scripts_to_run = []

                if "結果不足" in issues or "詳細不足" in issues:
                    scripts_to_run.append("補完_レース詳細データ_改善版v4.py")

                if "決まり手不足" in issues:
                    scripts_to_run.append("補完_決まり手データ_改善版.py")

                if "天候不足" in issues:
                    scripts_to_run.append("補完_天候データ_改善版.py")

                if "風向不足" in issues:
                    scripts_to_run.append("補完_風向データ_改善版.py")

                for script_name in scripts_to_run:
                    script_path = os.path.join(PROJECT_ROOT, script_name)
                    if os.path.exists(script_path):
                        # 出力をDEVNULLにリダイレクト（バッファブロック防止）
                        subprocess.run(
                            [sys.executable, script_path],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            cwd=PROJECT_ROOT,
                            timeout=300
                        )

            except Exception as e:
                errors += 1

            processed += 1

        # 完了
        message = f'{total}件の処理完了'
        if errors > 0:
            message += f'（エラー: {errors}件）'

        complete_job(JOB_NAME, success=True, message=message)

        # 設定ファイルを削除
        try:
            os.remove(args.config)
        except:
            pass

    except Exception as e:
        complete_job(JOB_NAME, success=False, message=f'エラー: {str(e)[:200]}')


if __name__ == '__main__':
    main()
