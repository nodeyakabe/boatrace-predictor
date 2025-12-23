#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2020-2023年の直前予想（before）一括生成スクリプト

目的:
- 2020-2023年の4年分（約63,647レース）のbefore予測を生成
- B-1会場フィルター、A-2特徴量A/Bテストの長期検証に使用
- 過学習リスクの複数年検証

処理内容:
- 各年度ごとに予測を生成
- 既存のadvance予測は保持
- before予測のみを追加生成
"""
import sys
import os
import io
import sqlite3
from datetime import datetime

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
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')

    races = cursor.fetchall()
    conn.close()
    return races


def check_existing_before_predictions(year: int):
    """既存のbefore予測数を確認"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute(f'''
        SELECT COUNT(DISTINCT race_id)
        FROM race_predictions
        WHERE prediction_type = 'before'
          AND race_id IN (
            SELECT id FROM races
            WHERE race_date >= '{year}-01-01' AND race_date <= '{year}-12-31'
        )
    ''')

    count = cursor.fetchone()[0]
    conn.close()
    return count


def generate_year_predictions(year: int, predictor: RacePredictor, data_manager: DataManager):
    """指定年の予測を生成"""

    print(f"\n{'='*70}")
    print(f"{year}年 before予測生成")
    print(f"{'='*70}")

    # 既存予測の確認
    existing_count = check_existing_before_predictions(year)
    if existing_count > 0:
        print(f"[INFO] 既存のbefore予測: {existing_count:,}件")
        response = input(f"既存のbefore予測を削除して再生成しますか？ (y/n): ")
        if response.lower() != 'y':
            print(f"[SKIP] {year}年をスキップします")
            return 0, 0

        # 既存予測の削除
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute(f'''
            DELETE FROM race_predictions
            WHERE prediction_type = 'before'
              AND race_id IN (
                  SELECT id FROM races
                  WHERE race_date >= '{year}-01-01' AND race_date <= '{year}-12-31'
              )
        ''')
        conn.commit()
        conn.close()
        print(f"[INFO] {existing_count:,}件の既存予測を削除しました")

    # 対象レース取得
    races = get_races_for_year(year)
    print(f"\n対象レース数: {len(races):,}件")

    if len(races) == 0:
        print(f"[WARNING] {year}年の予測可能レースがありません")
        return 0, 0

    # 予測実行
    success_count = 0
    fail_count = 0
    last_date = None

    for idx, (race_id, race_date, venue_code, race_number) in enumerate(races, 1):
        # 日付が変わったら進捗表示
        if race_date != last_date:
            if last_date is not None:
                print()  # 改行
            print(f"\n[{race_date}] ", end='', flush=True)
            last_date = race_date

        try:
            # before予測（直前情報あり）
            predictor.predict_and_save_race(
                race_id=race_id,
                use_beforeinfo=True,
                prediction_type='before'
            )
            print('.', end='', flush=True)
            success_count += 1

        except Exception as e:
            print('x', end='', flush=True)
            fail_count += 1
            if fail_count <= 5:  # 最初の5件のみエラー表示
                print(f"\n[ERROR] {race_date} {venue_code}場 {race_number}R: {e}")

        # 進捗表示（1000件ごと）
        if idx % 1000 == 0:
            print(f"\n  進捗: {idx:,}/{len(races):,} ({idx/len(races)*100:.1f}%)")

    print()  # 最終改行
    print(f"\n完了: 成功 {success_count:,}件 / 失敗 {fail_count:,}件")

    return success_count, fail_count


def main():
    print("=" * 70)
    print("2020-2023年 before予測一括生成")
    print("=" * 70)
    print()
    print("対象年度: 2020, 2021, 2022, 2023")
    print("予測タイプ: before（直前情報あり）")
    print("推定時間: 2-4時間")
    print()

    # 各年の予測可能レース数を表示
    print("予測対象:")
    total_races = 0
    for year in range(2020, 2024):
        races = get_races_for_year(year)
        existing = check_existing_before_predictions(year)
        print(f"  {year}年: {len(races):,}件（既存: {existing:,}件）")
        total_races += len(races)

    print(f"\n合計: {total_races:,}件")
    print()

    # 実行確認
    response = input("実行しますか？ (y/n): ")
    if response.lower() != 'y':
        print("キャンセルしました")
        return

    # 初期化
    print("\n初期化中...")
    predictor = RacePredictor()
    data_manager = DataManager()
    print("[OK] 初期化完了")

    # 年度ごとに処理
    start_time = datetime.now()
    total_success = 0
    total_fail = 0

    for year in range(2020, 2024):
        year_start = datetime.now()
        success, fail = generate_year_predictions(year, predictor, data_manager)
        year_elapsed = (datetime.now() - year_start).total_seconds()

        total_success += success
        total_fail += fail

        print(f"\n{year}年完了: {success:,}件生成（{year_elapsed:.1f}秒）")

    # 最終結果
    total_elapsed = (datetime.now() - start_time).total_seconds()

    print(f"\n{'='*70}")
    print("全体完了")
    print(f"{'='*70}")
    print(f"\n総生成数: {total_success:,}件")
    print(f"失敗数: {total_fail:,}件")
    print(f"所要時間: {total_elapsed/60:.1f}分（{total_elapsed/3600:.2f}時間）")

    # 最終確認
    print(f"\n{'='*70}")
    print("生成後の状況確認")
    print(f"{'='*70}")

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    for year in range(2020, 2024):
        cursor.execute(f'''
            SELECT COUNT(DISTINCT race_id)
            FROM race_predictions
            WHERE prediction_type = 'before'
              AND race_id IN (
                SELECT id FROM races
                WHERE race_date >= '{year}-01-01' AND race_date <= '{year}-12-31'
            )
        ''')
        count = cursor.fetchone()[0]
        print(f"{year}年 before予測: {count:,}件")

    conn.close()

    print(f"\n[次のステップ]")
    print("1. Phase 2-1: B-1会場フィルターの複数年検証")
    print("2. Phase 2-2: A-2特徴量A/Bテストの長期検証")
    print("3. Phase 2-3: 局所的効果検証（4年分データ）")


if __name__ == '__main__':
    main()
