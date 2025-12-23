#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2020-2024年before予測自動連続生成スクリプト

機能:
- 2024年の生成完了を待機
- 完了後、自動的に2020-2023年を実行
- エラー時も継続実行（ログに記録）
- 進捗をファイルに記録
"""
import sys
import os
import io
import sqlite3
import time
from datetime import datetime
from pathlib import Path

# Windows環境でのstdout/stderrエンコーディングをUTF-8に設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.analysis.race_predictor import RacePredictor
from src.database.data_manager import DataManager
from config.settings import DATABASE_PATH

# ログファイル
LOG_FILE = Path(PROJECT_ROOT) / 'logs' / f'before_prediction_generation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
LOG_FILE.parent.mkdir(exist_ok=True)


def log(message: str):
    """ログ出力（画面とファイル）"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] {message}"
    print(log_msg)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_msg + '\n')


def check_year_completion(year: int) -> tuple[int, int]:
    """指定年のbefore予測の生成状況を確認

    Returns:
        (生成済み件数, 予測可能総数)
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # before予測済み
    cursor.execute(f'''
        SELECT COUNT(DISTINCT race_id)
        FROM race_predictions
        WHERE prediction_type = 'before'
          AND race_id IN (
            SELECT id FROM races
            WHERE race_date >= '{year}-01-01' AND race_date <= '{year}-12-31'
        )
    ''')
    completed = cursor.fetchone()[0]

    # 予測可能総数
    cursor.execute(f'''
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_date >= '{year}-01-01' AND r.race_date <= '{year}-12-31'
          AND EXISTS (SELECT 1 FROM race_details WHERE race_id = r.id)
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id)
          AND EXISTS (
              SELECT 1 FROM entries
              WHERE race_id = r.id
              GROUP BY race_id
              HAVING COUNT(DISTINCT pit_number) = 6
          )
    ''')
    total = cursor.fetchone()[0]

    conn.close()
    return completed, total


def wait_for_2024_completion(check_interval: int = 300):
    """2024年の生成完了を待機

    Args:
        check_interval: チェック間隔（秒）デフォルト5分
    """
    log("=" * 70)
    log("2024年before予測生成の完了待機中")
    log("=" * 70)

    while True:
        completed, total = check_year_completion(2024)

        if total == 0:
            log("[ERROR] 2024年の予測可能レースが0件です")
            return False

        completion_rate = completed / total * 100
        log(f"2024年進捗: {completed:,}/{total:,}件 ({completion_rate:.1f}%)")

        if completion_rate >= 95:  # 95%以上完了で次に進む
            log("[OK] 2024年の生成がほぼ完了しました")
            return True

        log(f"次回チェック: {check_interval}秒後")
        time.sleep(check_interval)


def get_races_for_year(year: int):
    """指定年の予測可能レースを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute(f'''
        SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        WHERE r.race_date >= '{year}-01-01' AND r.race_date <= '{year}-12-31'
          AND EXISTS (SELECT 1 FROM race_details WHERE race_id = r.id)
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id)
          AND EXISTS (
              SELECT 1 FROM entries
              WHERE race_id = r.id
              GROUP BY race_id
              HAVING COUNT(DISTINCT pit_number) = 6
          )
          AND NOT EXISTS (
              SELECT 1 FROM race_predictions
              WHERE race_id = r.id AND prediction_type = 'before'
          )
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')

    races = cursor.fetchall()
    conn.close()
    return races


def generate_year_predictions(year: int, predictor: RacePredictor, data_manager: DataManager):
    """指定年の予測を生成（エラー時も継続）"""

    log("")
    log("=" * 70)
    log(f"{year}年 before予測生成開始")
    log("=" * 70)

    # 対象レース取得（未生成のみ）
    races = get_races_for_year(year)
    log(f"対象レース数: {len(races):,}件")

    if len(races) == 0:
        log(f"[INFO] {year}年は生成済みまたは予測可能レースがありません")
        return 0, 0

    # 予測実行
    success_count = 0
    fail_count = 0
    last_date = None
    start_time = datetime.now()

    for idx, (race_id, race_date, venue_code, race_number) in enumerate(races, 1):
        # 日付が変わったら進捗表示
        if race_date != last_date:
            if last_date is not None:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = success_count / elapsed if elapsed > 0 else 0
                remaining = (len(races) - idx) / rate if rate > 0 else 0
                log(f"進捗: {idx:,}/{len(races):,} ({idx/len(races)*100:.1f}%) "
                    f"成功:{success_count:,} 失敗:{fail_count:,} "
                    f"残り約{remaining/60:.0f}分")
            last_date = race_date

        try:
            # before予測（直前情報あり）
            predictions = predictor.predict_race(race_id, use_beforeinfo=True)
            if predictions:
                data_manager.save_race_predictions(
                    race_id, predictions, prediction_type='before'
                )
                success_count += 1
            else:
                fail_count += 1
                if fail_count <= 10:
                    log(f"[WARN] {race_date} {venue_code}場 {race_number}R: 予測結果がNone")

        except Exception as e:
            fail_count += 1
            if fail_count <= 10:  # 最初の10件のみログ出力
                log(f"[ERROR] {race_date} {venue_code}場 {race_number}R: {str(e)[:100]}")

        # 100件ごとに進捗保存
        if idx % 100 == 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = success_count / elapsed if elapsed > 0 else 0
            remaining = (len(races) - idx) / rate if rate > 0 else 0
            log(f"進捗: {idx:,}/{len(races):,} ({idx/len(races)*100:.1f}%) "
                f"成功:{success_count:,} 失敗:{fail_count:,} "
                f"残り約{remaining/60:.0f}分")

    elapsed = (datetime.now() - start_time).total_seconds()
    log(f"\n{year}年完了: 成功 {success_count:,}件 / 失敗 {fail_count:,}件 "
        f"/ 所要時間 {elapsed/60:.1f}分")

    return success_count, fail_count


def main():
    log("=" * 70)
    log("2020-2024年 before予測自動連続生成")
    log("=" * 70)
    log(f"ログファイル: {LOG_FILE}")
    log("")

    # 1. 2024年の完了を待機
    if not wait_for_2024_completion(check_interval=300):  # 5分ごとにチェック
        log("[ERROR] 2024年の生成に問題があります")
        return

    log("")
    log("=" * 70)
    log("2020-2023年の生成を開始します")
    log("=" * 70)

    # 2. 初期化
    try:
        log("\n初期化中...")
        predictor = RacePredictor()
        data_manager = DataManager()
        log("[OK] 初期化完了")
    except Exception as e:
        log(f"[ERROR] 初期化失敗: {e}")
        return

    # 3. 年度ごとに処理
    overall_start = datetime.now()
    total_success = 0
    total_fail = 0
    results = {}

    for year in range(2020, 2024):
        try:
            success, fail = generate_year_predictions(year, predictor, data_manager)
            total_success += success
            total_fail += fail
            results[year] = {'success': success, 'fail': fail}
        except Exception as e:
            log(f"[ERROR] {year}年の処理中にエラー: {e}")
            results[year] = {'success': 0, 'fail': 0, 'error': str(e)}
            # エラーでも次の年に進む

    # 4. 最終結果
    overall_elapsed = (datetime.now() - overall_start).total_seconds()

    log("")
    log("=" * 70)
    log("全体完了")
    log("=" * 70)
    log(f"\n総生成数: {total_success:,}件")
    log(f"総失敗数: {total_fail:,}件")
    log(f"総所要時間: {overall_elapsed/60:.1f}分（{overall_elapsed/3600:.2f}時間）")

    # 年度別結果
    log("\n年度別結果:")
    for year in range(2020, 2025):
        completed, total = check_year_completion(year)
        log(f"{year}年: {completed:,}/{total:,}件 ({completed/total*100:.1f}%)")

    log(f"\n[完了] ログファイル: {LOG_FILE}")
    log("[次のステップ] Phase 2の詳細検証を実施してください")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log(f"[FATAL ERROR] {e}")
        import traceback
        log(traceback.format_exc())
