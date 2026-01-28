#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
前日の直前予想を生成するスクリプト

daily_schedulerから毎朝呼び出される。
前日の直前情報（beforeinfo）を使って直前予想を生成する。
"""
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.analysis.race_predictor import RacePredictor
from config.settings import DATABASE_PATH
import sqlite3


def generate_yesterday_before_predictions(force: bool = False, target_date: str = None) -> int:
    """
    直前予想を生成

    Args:
        force: 既存の予想を上書きするか
        target_date: 対象日付（YYYY-MM-DD形式）。Noneの場合は前日

    Returns:
        int: 生成したレース数
    """
    # 対象日付を取得
    if target_date:
        date_str = target_date
    else:
        yesterday = datetime.now() - timedelta(days=1)
        date_str = yesterday.strftime('%Y-%m-%d')

    print(f"直前予想生成開始: {date_str}")

    try:
        predictor = RacePredictor(use_cache=True)

        # BatchDataLoaderにデータをロード
        if predictor.batch_loader:
            predictor.batch_loader.load_daily_data(date_str)

        # 前日のレース一覧を取得
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, venue_code, race_number, race_date
            FROM races
            WHERE race_date = ?
            ORDER BY venue_code, race_number
        ''', (date_str,))
        races = [dict(row) for row in cursor.fetchall()]

        if not races:
            print(f"対象日({date_str})のレースデータが見つかりません")
            conn.close()
            return 0

        print(f"対象日のレース数: {len(races)}")

        # 直前予想を生成
        success_count = 0
        skip_count = 0
        errors = []

        for race in races:
            race_id = race['id']

            try:
                # 直前情報があるかチェック
                cursor.execute("""
                    SELECT COUNT(*) FROM race_details
                    WHERE race_id = ? AND exhibition_time IS NOT NULL
                """, (race_id,))
                has_beforeinfo = cursor.fetchone()[0] > 0

                if not has_beforeinfo:
                    skip_count += 1
                    continue

                # 既存の直前予想をチェック
                cursor.execute("""
                    SELECT COUNT(*) FROM race_predictions
                    WHERE race_id = ? AND prediction_type = 'before'
                """, (race_id,))
                before_exists = cursor.fetchone()[0] > 0

                if before_exists and not force:
                    skip_count += 1
                    continue

                # 直前予想を生成
                predictions = predictor.predict_race(race_id, use_beforeinfo=True)

                if predictions and len(predictions) > 0:
                    # DBに保存
                    for pred in predictions:
                        pred['race_id'] = race_id
                        pred['prediction_type'] = 'before'

                        # 既存の予想を削除（force=Trueの場合）
                        if force:
                            cursor.execute("""
                                DELETE FROM race_predictions
                                WHERE race_id = ? AND prediction_type = 'before'
                            """, (race_id,))

                        # 予想を挿入
                        cursor.execute("""
                            INSERT INTO race_predictions (
                                race_id, pit_number, rank_prediction,
                                total_score, confidence, racer_name, racer_number,
                                applied_rules, created_at, course_score,
                                racer_score, motor_score, kimarite_score,
                                grade_score, prediction_type, generated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            pred['race_id'],
                            pred.get('pit_number'),
                            pred.get('rank_prediction'),
                            pred.get('total_score'),
                            pred.get('confidence'),
                            pred.get('racer_name'),
                            pred.get('racer_number'),
                            pred.get('applied_rules'),
                            pred.get('created_at', datetime.now().isoformat()),
                            pred.get('course_score'),
                            pred.get('racer_score'),
                            pred.get('motor_score'),
                            pred.get('kimarite_score'),
                            pred.get('grade_score'),
                            pred.get('prediction_type', 'before'),
                            pred.get('generated_at', datetime.now().isoformat())
                        ))

                    conn.commit()
                    success_count += 1

                    if success_count % 50 == 0:
                        print(f"  進捗: {success_count}/{len(races)}")

            except Exception as e:
                error_msg = f"直前予想生成エラー: race_id={race_id}, エラー={str(e)}"
                errors.append(error_msg)
                print(f"[WARNING] {error_msg}")
                continue

        conn.close()

        print(f"\n直前予想生成完了:")
        print(f"  生成成功: {success_count}レース")
        print(f"  スキップ: {skip_count}レース")

        if errors:
            print(f"  エラー: {len(errors)}件")
            for error in errors[:5]:  # 最初の5件のみ表示
                print(f"    - {error}")

        return success_count

    except Exception as e:
        print(f"[ERROR] 直前予想生成でエラー: {str(e)}")
        raise


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='直前予想を生成（デフォルトは前日）')
    parser.add_argument('--force', action='store_true',
                       help='既存の予想を上書き')
    parser.add_argument('--date', type=str,
                       help='対象日付（YYYY-MM-DD形式）。未指定の場合は前日')
    args = parser.parse_args()

    try:
        count = generate_yesterday_before_predictions(force=args.force, target_date=args.date)
        print(f"\n生成完了: {count}レース")
        return 0
    except Exception as e:
        print(f"\n[ERROR] エラーが発生しました: {str(e)}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
