# -*- coding: utf-8 -*-
"""
事前予想専用の再生成スクリプト（直前情報を完全に無視）

目的:
- 事前予想と直前予想の効果を正確に比較するため、
  直前情報（展示タイム・気象補正）を完全に無視した事前予想を再生成する

対象期間: 2024-01-01 〜 2025-12-31

実装方針:
1. beforeinfo_dataを強制的にNoneに設定
2. prediction_type='advance'として保存
3. 直前情報に依存する全てのスコアを0点にする
"""
import sys
import sqlite3
import warnings
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def process_single_day_advance_only(args):
    """
    1日分の事前予想を生成（直前情報完全無視）

    Args:
        args: (race_date, db_path)

    Returns:
        dict: 処理結果
    """
    race_date, db_path = args

    import sqlite3
    import warnings
    warnings.filterwarnings('ignore')

    sys.path.insert(0, str(PROJECT_ROOT))
    from src.analysis.race_predictor import RacePredictor

    result = {
        'date': race_date,
        'total_races': 0,
        'succeeded': 0,
        'failed': 0,
        'predictions': []
    }

    try:
        # Predictor初期化（直前情報無視モード）
        predictor = RacePredictor(use_cache=False)  # キャッシュを無効化

        # その日のレースを取得
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT r.id, r.venue_code, r.race_number
            FROM races r
            WHERE r.race_date = ?
            ORDER BY r.venue_code, r.race_number
        """, (race_date,))

        races = cursor.fetchall()
        conn.close()

        if not races:
            return result

        result['total_races'] = len(races)

        for race_id, venue_code, race_num in races:
            try:
                # ★重要: 直前情報を強制的に無視★
                # predict_race内部でbeforeinfo取得を無効化する
                # これはrace_predictor.pyのpredict_raceメソッドで
                # use_beforeinfo=Falseオプションを渡す必要がある

                # 現状のRacePredictorは直前情報を自動的に取得するため、
                # ここでは事前スコアのみを計算する

                predictions = predictor.predict_race_advance_only(race_id)

                if predictions and len(predictions) >= 6:
                    result['predictions'].append({
                        'race_id': race_id,
                        'data': predictions
                    })
                    result['succeeded'] += 1
                else:
                    result['failed'] += 1
            except Exception as e:
                result['failed'] += 1
                print(f"  [ERROR] race_id={race_id}: {e}")

    except Exception as e:
        result['failed'] = result['total_races']
        print(f"  [ERROR] date={race_date}: {e}")

    return result


def save_predictions_batch(predictions_list, db_path):
    """
    予測結果をバッチでDBに保存（prediction_type='advance'）
    """
    if not predictions_list:
        return 0

    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()
    saved = 0

    try:
        generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for item in predictions_list:
            race_id = item['race_id']
            predictions = item['data']

            # 既存の事前予想データを削除
            cursor.execute(
                'DELETE FROM race_predictions WHERE race_id = ? AND prediction_type = ?',
                (race_id, 'advance')
            )

            for pred in predictions:
                cursor.execute("""
                    INSERT INTO race_predictions (
                        race_id, pit_number, rank_prediction, total_score,
                        confidence, racer_name, racer_number, applied_rules,
                        course_score, racer_score, motor_score, kimarite_score,
                        grade_score, prediction_type, generated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    race_id,
                    pred.get('pit_number'),
                    pred.get('rank_prediction'),
                    pred.get('total_score', 0),
                    pred.get('confidence', 'E'),
                    pred.get('racer_name', ''),
                    pred.get('racer_number', ''),
                    str(pred.get('applied_rules', '')),
                    pred.get('course_score', 0),
                    pred.get('racer_score', 0),
                    pred.get('motor_score', 0),
                    pred.get('kimarite_score', 0),
                    pred.get('grade_score', 0),
                    'advance',  # ★重要: 事前予想として保存★
                    generated_at
                ))
                saved += 1

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] DB保存エラー: {e}")
        saved = 0
    finally:
        conn.close()

    return saved


def main():
    """メイン処理"""
    print("="*100)
    print("事前予想専用再生成スクリプト（直前情報完全無視）")
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*100)

    db_path = PROJECT_ROOT / "data" / "boatrace.db"

    # 対象期間: 2024-01-01 〜 2025-12-31
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2025, 12, 31)

    # 日付リストを生成
    date_list = []
    current_date = start_date
    while current_date <= end_date:
        date_list.append(current_date.strftime('%Y-%m-%d'))
        current_date += timedelta(days=1)

    total_days = len(date_list)
    print(f"\n対象期間: {start_date.date()} 〜 {end_date.date()}")
    print(f"対象日数: {total_days}日")

    # ★重要: まず、RacePredictorに事前予想専用メソッドがあるか確認★
    print(f"\n[警告] このスクリプトは現在、RacePredictor.predict_race_advance_only()メソッドを想定しています。")
    print(f"[警告] このメソッドが存在しない場合は、先にrace_predictor.pyを修正してください。")

    # 確認プロンプト
    proceed = input(f"\n{total_days}日分の事前予想を再生成します。よろしいですか？ (yes/no): ")
    if proceed.lower() != 'yes':
        print("処理を中止しました。")
        return

    # 並列処理設定
    max_workers = min(cpu_count() - 1, 8)
    print(f"\n並列ワーカー数: {max_workers}")

    # 並列処理実行
    print(f"\n処理開始...\n")
    start_time = datetime.now()

    total_races = 0
    total_succeeded = 0
    total_failed = 0
    all_predictions = []

    args_list = [(date, str(db_path)) for date in date_list]

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_date = {executor.submit(process_single_day_advance_only, args): args[0] for args in args_list}

        for i, future in enumerate(as_completed(future_to_date), 1):
            date = future_to_date[future]
            try:
                result = future.result()
                total_races += result['total_races']
                total_succeeded += result['succeeded']
                total_failed += result['failed']

                if result['predictions']:
                    all_predictions.extend(result['predictions'])

                if i % 100 == 0 or i == total_days:
                    print(f"  進捗: {i}/{total_days}日 "
                          f"({i/total_days*100:.1f}%) "
                          f"レース: {total_races}, 成功: {total_succeeded}, 失敗: {total_failed}")

            except Exception as e:
                print(f"  [ERROR] {date}: {e}")
                total_failed += 1

    # DB保存
    print(f"\n予測結果をDBに保存中...")
    saved_count = save_predictions_batch(all_predictions, str(db_path))

    # 結果表示
    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()

    print(f"\n{'='*100}")
    print(f"処理完了")
    print(f"{'='*100}\n")
    print(f"対象レース数: {total_races}レース")
    print(f"予想成功: {total_succeeded}レース")
    print(f"予想失敗: {total_failed}レース")
    print(f"DB保存数: {saved_count}件")
    print(f"処理時間: {elapsed:.1f}秒 ({elapsed/60:.1f}分)")
    print(f"平均速度: {total_races/elapsed:.1f}レース/秒")

    print(f"\n{'='*100}\n")


if __name__ == "__main__":
    main()
