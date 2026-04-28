# -*- coding: utf-8 -*-
"""
2日間放置用 データ収集・補完 オーバーナイトパイプライン

実行するステップ:
  Step 1: 2026年4月データ全補完（brute-force）
  Step 2: 2026年4月 CSV → DB インポート
  Step 3: SG欠損レース収集（2018-2025、303件）
  Step 4: SG CSV → DB インポート
  Step 5: race_grade バックフィル（2018-2026）
  Step 6: 決まり手補完（全年度）
  Step 7: レース詳細補完（全年度）
  Step 8: オッズ補完（2026年）
  Step 9: 統計指標再生成

再起動耐性: 各ステップの完了状態を progress_overnight.json に保存。
           再実行すると完了済みステップをスキップして途中から再開。

使い方:
    python scripts/automation/overnight_data_pipeline.py

    # 特定ステップから再開（強制）
    python scripts/automation/overnight_data_pipeline.py --from-step 3

    # 状態確認のみ
    python scripts/automation/overnight_data_pipeline.py --status
"""

import sys
import io
import os
import json
import subprocess
import argparse
from pathlib import Path
from datetime import datetime, date

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

ROOT_DIR = Path(__file__).parent.parent.parent
PROGRESS_FILE = ROOT_DIR / 'data' / 'progress_overnight.json'
LOG_FILE = ROOT_DIR / 'logs' / 'overnight_pipeline.log'

TODAY = date.today().strftime('%Y-%m-%d')
CURRENT_YEAR = date.today().year

# =========================================================
# ステップ定義
# =========================================================
def build_steps():
    return [
        {
            'id': 1,
            'name': '2026年4月データ全補完（brute-force CSV収集）',
            'cmd': [
                sys.executable,
                'scripts/data_collection/fetch_to_csv_parallel_improved.py',
                '--start', '2026-04-01',
                '--end', TODAY,
                '--brute-force',
                '--output', 'data/csv/2026_04_補完',
                '--workers', '8',
            ],
        },
        {
            'id': 2,
            'name': '2026年4月 CSV → DB インポート',
            'cmd': [
                sys.executable,
                'scripts/data_collection/import_races_csv.py',
                '--dir', 'data/csv/2026_04_補完',
            ],
        },
        {
            'id': 3,
            'name': 'SG欠損レース収集（2018-2025）',
            'cmd': [
                sys.executable,
                'scripts/data_collection/collect_sg_missing_data.py',
                '--start-year', '2018',
                '--end-year', '2025',
                '--workers', '4',
                '--delay', '0.5',
            ],
        },
        {
            'id': 4,
            'name': 'SG欠損 CSV → DB インポート',
            'cmd': [
                sys.executable,
                'scripts/data_collection/import_races_csv.py',
                '--dir', 'data/csv/sg_missing',
            ],
        },
        {
            'id': 5,
            'name': 'race_grade バックフィル（2018-2026、gradesch完全版）',
            'cmd': [
                sys.executable,
                'scripts/maintenance/backfill_race_grades_v2.py',
                '--start-year', '2018',
                '--end-year', str(CURRENT_YEAR),
                '--delay', '1.0',
            ],
        },
        {
            'id': 6,
            'name': '決まり手補完（全年度）',
            'cmd': [
                sys.executable,
                'scripts/data_collection/補完_決まり手データ_改善版.py',
            ],
        },
        {
            'id': 7,
            'name': 'レース詳細補完（全年度）',
            'cmd': [
                sys.executable,
                'scripts/data_collection/補完_レース詳細データ_改善版v4.py',
            ],
        },
        {
            'id': 8,
            'name': 'オッズ補完（2026年）',
            'cmd': [
                sys.executable,
                'scripts/data_collection/fetch_odds_parallel_safe.py',
                '--start-date', '2026-01-01',
                '--end-date', TODAY,
                '--workers', '8',
            ],
        },
        {
            'id': 9,
            'name': '統計指標再生成',
            'cmd': [
                sys.executable,
                'scripts/data_collection/build_indicator_stats.py',
                '--recreate',
            ],
        },
    ]


# =========================================================
# 進捗管理
# =========================================================
def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding='utf-8'))
    return {'completed': [], 'failed': [], 'started_at': None}


def save_progress(progress: dict):
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding='utf-8')


def log(msg: str):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


# =========================================================
# ステップ実行
# =========================================================
def run_step(step: dict) -> bool:
    log(f'▶ Step {step["id"]}: {step["name"]}')
    log(f'  コマンド: {" ".join(step["cmd"])}')

    start = datetime.now()
    try:
        result = subprocess.run(
            step['cmd'],
            cwd=str(ROOT_DIR),
            encoding='utf-8',
            errors='replace',
        )
        elapsed = (datetime.now() - start).seconds
        if result.returncode == 0:
            log(f'  ✅ 完了 ({elapsed}秒)')
            return True
        else:
            log(f'  ❌ 失敗 (returncode={result.returncode}, {elapsed}秒)')
            return False
    except Exception as e:
        log(f'  ❌ 例外発生: {e}')
        return False


# =========================================================
# メイン
# =========================================================
def main():
    parser = argparse.ArgumentParser(description='オーバーナイトデータパイプライン')
    parser.add_argument('--from-step', type=int, default=None,
                        help='このステップIDから強制再実行（完了済みを無視）')
    parser.add_argument('--status', action='store_true',
                        help='進捗状態を表示して終了')
    args = parser.parse_args()

    steps = build_steps()
    progress = load_progress()

    if args.status:
        print('=== overnight_pipeline 進捗状態 ===')
        print(f'開始時刻: {progress.get("started_at", "未実行")}')
        for s in steps:
            sid = s['id']
            if sid in progress['completed']:
                mark = '✅ 完了'
            elif sid in progress['failed']:
                mark = '❌ 失敗'
            else:
                mark = '⏳ 未実行'
            print(f'  Step {sid}: {mark}  {s["name"]}')
        return

    # --from-step 指定時: それ以降の完了済みフラグをクリア
    if args.from_step is not None:
        progress['completed'] = [s for s in progress['completed'] if s < args.from_step]
        progress['failed']    = [s for s in progress['failed']    if s < args.from_step]
        save_progress(progress)

    if not progress.get('started_at'):
        progress['started_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        save_progress(progress)

    log('=' * 60)
    log('オーバーナイトパイプライン 開始')
    log(f'対象日: {TODAY}')
    log('=' * 60)

    total = len(steps)
    for step in steps:
        sid = step['id']

        if sid in progress['completed']:
            log(f'⏭  Step {sid}: スキップ（完了済み）— {step["name"]}')
            continue

        success = run_step(step)

        if success:
            progress['completed'].append(sid)
            if sid in progress['failed']:
                progress['failed'].remove(sid)
        else:
            if sid not in progress['failed']:
                progress['failed'].append(sid)
            log(f'  ⚠ Step {sid} 失敗。次のステップに進みます。')

        save_progress(progress)

    log('=' * 60)
    done  = len(progress['completed'])
    failed = len(progress['failed'])
    log(f'パイプライン終了: 完了 {done}/{total}  失敗 {failed}件')
    if progress['failed']:
        names = {s['id']: s['name'] for s in steps}
        for fid in progress['failed']:
            log(f'  失敗ステップ: Step {fid} — {names.get(fid, "?")}')
    log('=' * 60)


if __name__ == '__main__':
    main()
