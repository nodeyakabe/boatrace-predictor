#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
予想データ一括生成スクリプト

指定期間の全レースに対して事前予想と直前予想を生成してDBに保存します。

実行方法:
  python scripts/generate_predictions_batch.py --start 2025-01-01 --end 2025-09-30
  python scripts/generate_predictions_batch.py --start 2025-01-01 --end 2025-09-30 --force
"""
import sys
import os
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

# Force unbuffered output
os.environ['PYTHONUNBUFFERED'] = '1'

import time
import sqlite3
import argparse
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.analysis.race_predictor import RacePredictor
from config.settings import DATABASE_PATH


class BatchPredictionGenerator:
    """予測一括生成クラス"""

    def __init__(self, start_date: str, end_date: str):
        self.start_date = start_date
        self.end_date = end_date
        self.predictor = RacePredictor(use_cache=True)
        self.db_path = DATABASE_PATH

        # 統計
        self.stats = {
            'total_races': 0,
            'advance_generated': 0,
            'before_generated': 0,
            'skipped': 0,
            'errors': 0
        }

    def get_date_range(self) -> list:
        """日付範囲を取得"""
        dates = []
        start = datetime.strptime(self.start_date, '%Y-%m-%d')
        end = datetime.strptime(self.end_date, '%Y-%m-%d')

        current = start
        while current <= end:
            dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)

        return dates

    def get_races_for_date(self, race_date: str) -> list:
        """指定日のレース一覧を取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT r.id, r.venue_code, r.race_number, r.race_date
            FROM races r
            WHERE r.race_date = ?
            ORDER BY r.venue_code, r.race_number
        """, (race_date,))

        races = []
        for row in cursor.fetchall():
            races.append({
                'race_id': row[0],
                'venue_code': row[1],
                'race_number': row[2],
                'race_date': row[3]
            })

        conn.close()
        return races

    def has_before_data(self, race_id: int) -> bool:
        """直前データ（展示タイム等）が存在するか確認"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM race_details
            WHERE race_id = ? AND exhibition_time IS NOT NULL
        """, (race_id,))
        count = cursor.fetchone()[0]

        conn.close()
        return count > 0

    def prediction_exists(self, race_id: int, prediction_type: str) -> bool:
        """既存の予測があるか確認"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM race_predictions
            WHERE race_id = ? AND prediction_type = ?
        """, (race_id, prediction_type))
        count = cursor.fetchone()[0]

        conn.close()
        return count > 0

    def generate_prediction(self, race_id: int, prediction_type: str) -> bool:
        """予想を生成"""
        try:
            predictions = self.predictor.predict_race(race_id)

            if predictions and len(predictions) > 0:
                return self.save_predictions(race_id, predictions, prediction_type)
            return False
        except Exception as e:
            # エラー詳細は表示しない（大量に出るため）
            return False

    def save_predictions(self, race_id: int, predictions: list, prediction_type: str) -> bool:
        """予測結果をDBに保存"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            for pred in predictions:
                cursor.execute("""
                    INSERT OR REPLACE INTO race_predictions (
                        race_id, pit_number, rank_prediction, total_score,
                        confidence, racer_name, racer_number, applied_rules,
                        course_score, racer_score, motor_score, kimarite_score,
                        grade_score, prediction_type, generated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    race_id,
                    pred.get('pit_number'),
                    pred.get('predicted_rank', pred.get('rank_prediction')),
                    pred.get('total_score', 0),
                    pred.get('confidence', 'medium'),
                    pred.get('racer_name', ''),
                    pred.get('racer_number', ''),
                    str(pred.get('applied_rules', '')),
                    pred.get('course_score', 0),
                    pred.get('racer_score', 0),
                    pred.get('motor_score', 0),
                    pred.get('kimarite_score', 0),
                    pred.get('grade_score', 0),
                    prediction_type,
                    generated_at
                ))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            conn.rollback()
            conn.close()
            return False

    def run(self, force: bool = False):
        """指定期間の予測を生成"""
        print("=" * 70)
        print(f"予想データ一括生成")
        print("=" * 70)
        print(f"期間: {self.start_date} 〜 {self.end_date}")
        print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"強制上書き: {'有効' if force else '無効'}")
        print("=" * 70)

        start_time = time.time()
        dates = self.get_date_range()

        print(f"対象日数: {len(dates)}日間")
        print()

        for date_idx, race_date in enumerate(dates, 1):
            races = self.get_races_for_date(race_date)

            if not races:
                continue

            # BatchDataLoaderにデータをロード
            if self.predictor.batch_loader:
                self.predictor.batch_loader.load_daily_data(race_date)

            day_advance = 0
            day_before = 0
            day_skip = 0
            day_error = 0

            for race in races:
                race_id = race['race_id']
                self.stats['total_races'] += 1

                # 事前予想
                if force or not self.prediction_exists(race_id, 'advance'):
                    if self.generate_prediction(race_id, 'advance'):
                        self.stats['advance_generated'] += 1
                        day_advance += 1
                    else:
                        self.stats['errors'] += 1
                        day_error += 1
                else:
                    self.stats['skipped'] += 1
                    day_skip += 1

                # 直前予想（展示データがある場合のみ）
                if self.has_before_data(race_id):
                    if force or not self.prediction_exists(race_id, 'before'):
                        if self.generate_prediction(race_id, 'before'):
                            self.stats['before_generated'] += 1
                            day_before += 1

            # 日次サマリー
            elapsed = time.time() - start_time
            print(f"[{date_idx:3}/{len(dates)}] {race_date}: {len(races):3}R "
                  f"(事前:{day_advance:3} 直前:{day_before:3} Skip:{day_skip:3} Err:{day_error:2}) "
                  f"[{elapsed/60:.1f}分経過]", flush=True)

        elapsed = time.time() - start_time

        # 結果サマリー
        print()
        print("=" * 70)
        print("予想生成完了")
        print("=" * 70)
        print(f"総レース数: {self.stats['total_races']:,}件")
        print(f"事前予想生成: {self.stats['advance_generated']:,}件")
        print(f"直前予想生成: {self.stats['before_generated']:,}件")
        print(f"スキップ: {self.stats['skipped']:,}件")
        print(f"エラー: {self.stats['errors']:,}件")
        print(f"処理時間: {elapsed/60:.1f}分")
        print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)

        return self.stats


def main():
    parser = argparse.ArgumentParser(description='予想データ一括生成')
    parser.add_argument('--start', type=str, required=True, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, required=True, help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--force', action='store_true', help='既存の予想を上書き')

    args = parser.parse_args()

    try:
        generator = BatchPredictionGenerator(
            start_date=args.start,
            end_date=args.end
        )
        stats = generator.run(force=args.force)

        if stats['errors'] > stats['advance_generated'] * 0.1:
            sys.exit(1)
        sys.exit(0)

    except KeyboardInterrupt:
        print('\n処理を中断しました')
        sys.exit(1)
    except Exception as e:
        print(f'\nエラー: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
