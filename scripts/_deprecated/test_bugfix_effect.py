"""
バグ修正効果検証スクリプト

展示タイム重複加算バグの修正前後で的中率を比較する。

使用方法:
    python scripts/test_bugfix_effect.py
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import sqlite3
from datetime import datetime, timedelta
from config.settings import DATABASE_PATH
from config.feature_flags import FEATURE_FLAGS, enable_feature, disable_feature


def evaluate_accuracy(use_legacy_exhibition: bool, days: int = 30):
    """
    指定期間の1着的中率を評価

    Args:
        use_legacy_exhibition: 旧展示補正を使用するか
        days: 評価期間（日数）

    Returns:
        (的中数, 総レース数, 的中率)
    """
    # フラグ設定
    if use_legacy_exhibition:
        enable_feature('legacy_exhibition_adjustment')
    else:
        disable_feature('legacy_exhibition_adjustment')

    # RacePredictorを再インポート（フラグ反映のため）
    from importlib import reload
    import src.analysis.race_predictor as rp
    reload(rp)
    from src.analysis.race_predictor import RacePredictor

    predictor = RacePredictor(DATABASE_PATH)

    # 評価期間
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # レース取得
    cursor.execute("""
        SELECT r.id as race_id
        FROM races r
        JOIN results res ON r.id = res.race_id AND res.rank = '1'
        WHERE r.race_date BETWEEN ? AND ?
        ORDER BY r.race_date DESC
        LIMIT 500
    """, (start_date.isoformat(), end_date.isoformat()))

    races = cursor.fetchall()

    hit_count = 0
    total_count = 0

    for race in races:
        race_id = race['race_id']

        try:
            # 予測実行
            predictions = predictor.predict_race(race_id)

            if not predictions:
                continue

            # 1着予測
            predicted_winner = predictions[0]['pit_number']

            # 実際の1着
            cursor.execute("""
                SELECT pit_number FROM results
                WHERE race_id = ? AND rank = '1'
            """, (race_id,))
            result = cursor.fetchone()

            if result:
                actual_winner = result['pit_number']
                if predicted_winner == actual_winner:
                    hit_count += 1
                total_count += 1

        except Exception as e:
            continue

    cursor.close()
    conn.close()

    hit_rate = hit_count / total_count if total_count > 0 else 0

    return hit_count, total_count, hit_rate


def main():
    print("=" * 60)
    print("バグ修正効果検証")
    print("=" * 60)
    print()

    # 評価期間
    days = 30
    print(f"評価期間: 直近{days}日間")
    print()

    # 修正後（旧展示補正OFF）
    print("[1] 修正後（展示重複加算なし）")
    print("-" * 40)
    hit1, total1, rate1 = evaluate_accuracy(use_legacy_exhibition=False, days=days)
    print(f"  的中: {hit1}/{total1} ({rate1:.2%})")
    print()

    # 修正前（旧展示補正ON）
    print("[2] 修正前（展示重複加算あり）")
    print("-" * 40)
    hit2, total2, rate2 = evaluate_accuracy(use_legacy_exhibition=True, days=days)
    print(f"  的中: {hit2}/{total2} ({rate2:.2%})")
    print()

    # 比較
    print("=" * 60)
    print("比較結果")
    print("=" * 60)
    diff = rate1 - rate2
    print(f"  修正後: {rate1:.2%}")
    print(f"  修正前: {rate2:.2%}")
    print(f"  差分: {diff:+.2%}")

    if diff > 0:
        print(f"\n  → 修正により的中率が {diff:.2%} 向上")
    elif diff < 0:
        print(f"\n  → 修正により的中率が {abs(diff):.2%} 低下（要確認）")
    else:
        print(f"\n  → 的中率に変化なし")


if __name__ == '__main__':
    main()
