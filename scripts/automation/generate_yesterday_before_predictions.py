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

from src.prediction.predictor_helpers import create_standard_predictor
from src.database.data_manager import DataManager
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
        predictor = create_standard_predictor(use_cache=True)
        data_manager = DataManager()

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

        race_ids = [r['id'] for r in races]
        placeholders = ','.join(['?'] * len(race_ids))

        # 直前情報（exhibition_time）の有無を一括チェック（N+1クエリを解消）
        cursor.execute(
            f"SELECT DISTINCT race_id FROM race_details"
            f" WHERE race_id IN ({placeholders}) AND exhibition_time IS NOT NULL",
            race_ids
        )
        has_beforeinfo_ids = {row[0] for row in cursor.fetchall()}

        # 既存のbefore予測の有無を一括チェック（forceでない場合のみ）
        existing_before_ids = set()
        if not force:
            cursor.execute(
                f"SELECT DISTINCT race_id FROM race_predictions"
                f" WHERE prediction_type = 'before' AND race_id IN ({placeholders})",
                race_ids
            )
            existing_before_ids = {row[0] for row in cursor.fetchall()}

        conn.close()

        success_count = 0
        skip_count = 0
        errors = []

        for race in races:
            race_id = race['id']

            try:
                # 直前情報がないレースはスキップ
                if race_id not in has_beforeinfo_ids:
                    skip_count += 1
                    continue

                # 既存のbefore予測があり、forceでない場合はスキップ
                if race_id in existing_before_ids:
                    skip_count += 1
                    continue

                # 直前予想を生成
                predictions = predictor.predict_race(race_id, use_beforeinfo=True)

                if predictions and len(predictions) > 0:
                    # DataManager経由で保存（環境要因減点も自動適用）
                    # save_race_predictions は先にDELETEしてからINSERTするため force に対応済み
                    if data_manager.save_race_predictions(race_id, predictions, prediction_type='before'):
                        success_count += 1
                        if success_count % 50 == 0:
                            print(f"  進捗: {success_count}/{len(races)}")

            except Exception as e:
                error_msg = f"直前予想生成エラー: race_id={race_id}, エラー={str(e)}"
                errors.append(error_msg)
                print(f"[WARNING] {error_msg}")
                continue

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
    from scripts.safety_check import safety_check

    # 安全チェック（hierarchical_predictorが有効かを確認）
    safety_check()

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
