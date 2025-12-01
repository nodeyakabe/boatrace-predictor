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

        # カテゴリ別の補完スクリプトマッピング
        CATEGORY_SCRIPTS = {
            "レース基本情報": [],
            "選手データ": [],
            "モーター・ボート": [],
            "天候・気象": [("補完_天候データ_改善版.py", "天候データ"), ("補完_風向データ_改善版.py", "風向データ")],
            "水面・潮汐": [],
            "レース展開": [("補完_展示タイム_全件_高速化.py", "展示タイム")],
            "オッズ・人気": [],
            "結果データ": [("補完_レース詳細データ_改善版v4.py", "レース詳細"), ("補完_決まり手データ_改善版.py", "決まり手")],
            "直前情報": [("補完_展示タイム_全件_高速化.py", "直前情報")],
            "払戻データ": [("補完_払戻金データ.py", "払戻金")]
        }

        errors = 0
        total_steps = 0
        current_step = 0

        # フェーズ1: レース基本情報の取得が必要な日付を抽出
        missing_race_dates = []
        for item in missing_dates:
            if item.get('レース', 0) == 0:
                missing_race_dates.append(item['日付'])

        # フェーズ2: 補完スクリプトを収集（重複排除）
        scripts_to_run = []
        for category in check_types:
            if category in CATEGORY_SCRIPTS:
                for script_name, label in CATEGORY_SCRIPTS[category]:
                    if script_name and (script_name, label, category) not in [(s[0], s[1], s[2]) for s in scripts_to_run]:
                        scripts_to_run.append((script_name, label, category))

        # 総ステップ数を計算
        total_steps = len(missing_race_dates) + len(scripts_to_run)

        if total_steps == 0:
            complete_job(JOB_NAME, success=True, message='処理対象がありません')
            return

        # === フェーズ1: レース基本情報の取得 ===
        if missing_race_dates:
            update_job_progress(JOB_NAME, {
                'status': 'running',
                'progress': 0,
                'message': f'フェーズ1: {len(missing_race_dates)}日分のレース情報を取得中...',
                'phase': 1,
                'total_steps': total_steps
            })

            from src.scraper.bulk_scraper import BulkScraper
            scraper = BulkScraper()

            for idx, date_str in enumerate(missing_race_dates, 1):
                try:
                    progress = int((current_step / total_steps) * 100)
                    update_job_progress(JOB_NAME, {
                        'status': 'running',
                        'progress': progress,
                        'message': f'{date_str} のレース情報を取得中... ({idx}/{len(missing_race_dates)})',
                        'phase': 1,
                        'current_date': date_str
                    })

                    venue_codes = [f"{i:02d}" for i in range(1, 25)]
                    scraper.fetch_multiple_venues(
                        venue_codes=venue_codes,
                        race_date=date_str,
                        race_count=12
                    )

                    current_step += 1

                except Exception as e:
                    errors += 1
                    current_step += 1

        # === フェーズ2: 補完スクリプトの実行 ===
        if scripts_to_run:
            update_job_progress(JOB_NAME, {
                'status': 'running',
                'progress': int((current_step / total_steps) * 100),
                'message': f'フェーズ2: {len(scripts_to_run)}種類の補完スクリプトを実行中...',
                'phase': 2,
                'total_steps': total_steps
            })

            for idx, (script_name, label, category) in enumerate(scripts_to_run, 1):
                try:
                    progress = int((current_step / total_steps) * 100)
                    update_job_progress(JOB_NAME, {
                        'status': 'running',
                        'progress': progress,
                        'message': f'[{category}] {label}を補完中... ({idx}/{len(scripts_to_run)})',
                        'phase': 2,
                        'current_script': label
                    })

                    script_path = os.path.join(PROJECT_ROOT, script_name)

                    if not os.path.exists(script_path):
                        errors += 1
                        current_step += 1
                        continue

                    # スクリプトを実行（タイムアウト600秒）
                    result = subprocess.run(
                        [sys.executable, script_path],
                        capture_output=True,
                        text=True,
                        cwd=PROJECT_ROOT,
                        timeout=600,
                        encoding='utf-8',
                        errors='ignore'
                    )

                    if result.returncode != 0:
                        errors += 1

                    current_step += 1

                except subprocess.TimeoutExpired:
                    errors += 1
                    current_step += 1
                except Exception as e:
                    errors += 1
                    current_step += 1

        # 完了
        message = f'{total_steps}ステップ完了'
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
