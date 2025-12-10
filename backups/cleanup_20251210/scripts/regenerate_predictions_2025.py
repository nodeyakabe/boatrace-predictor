"""
2025年全レースの予想再生成（ハイブリッドスコアリング適用）

ハイブリッドスコアリング実装後、2025年全データの予想を再生成する。
race_predictionsテーブルを更新し、正確な評価を可能にする。

実行時間: 約3-5時間（17,131レース）
"""

import sys
import warnings
from pathlib import Path
import sqlite3
from datetime import datetime

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.race_predictor import RacePredictor


def main():
    print("=" * 80)
    print("2025年全レース予想再生成（ハイブリッドスコアリング適用）")
    print("=" * 80)
    print()
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    predictor = RacePredictor(str(db_path))

    conn = sqlite3.connect(db_path, timeout=60.0)
    cursor = conn.cursor()

    # 2025年の全レースを取得
    cursor.execute('''
        SELECT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01'
          AND r.race_date < '2026-01-01'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    all_races = cursor.fetchall()

    print(f"2025年総レース数: {len(all_races):,}レース")
    print()

    # 既存の2025年予想を削除
    print("既存の予想データを削除中...")
    cursor.execute('''
        DELETE FROM race_predictions
        WHERE race_id IN (
            SELECT id FROM races
            WHERE race_date >= '2025-01-01' AND race_date < '2026-01-01'
        )
    ''')
    deleted_count = cursor.rowcount
    conn.commit()
    print(f"削除完了: {deleted_count:,}件")
    print()

    # 予想を再生成
    print("予想再生成開始...")
    print()

    processed = 0
    succeeded = 0
    failed = 0
    start_time = datetime.now()

    for idx, (race_id, race_date, venue_code, race_number) in enumerate(all_races):
        if (idx + 1) % 100 == 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = (idx + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(all_races) - idx - 1) / rate if rate > 0 else 0
            remaining_hours = remaining / 3600

            print(f"処理中: {idx+1:,}/{len(all_races):,}レース "
                  f"({succeeded:,}成功, {failed:,}失敗) "
                  f"[速度: {rate:.1f}レース/秒, 残り約{remaining_hours:.1f}時間]", flush=True)

        try:
            # 予想実行（ハイブリッドスコアリング適用）
            predictions = predictor.predict_race(race_id)

            if predictions and len(predictions) >= 6:
                # race_predictionsテーブルに保存
                cursor.execute('DELETE FROM race_predictions WHERE race_id = ?',
                             (race_id,))

                for pred in predictions:
                    cursor.execute('''
                        INSERT INTO race_predictions (
                            race_id, pit_number, rank_prediction, total_score,
                            confidence, racer_name, racer_number, applied_rules,
                            course_score, racer_score, motor_score, kimarite_score, grade_score,
                            prediction_type, generated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        race_id,
                        pred['pit_number'],
                        pred['rank_prediction'],
                        pred['total_score'],
                        pred['confidence'],
                        pred.get('racer_name', ''),
                        pred.get('racer_number', ''),
                        pred.get('applied_rules', ''),
                        pred.get('course_score', 0),
                        pred.get('racer_score', 0),
                        pred.get('motor_score', 0),
                        pred.get('kimarite_score', 0),
                        pred.get('grade_score', 0),
                        'after',
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    ))

                succeeded += 1

                # 100レースごとにコミット
                if (idx + 1) % 100 == 0:
                    conn.commit()
            else:
                failed += 1

            processed += 1

        except Exception as e:
            failed += 1
            if failed <= 10:  # 最初の10件のエラーのみ表示
                print(f"  エラー: レースID {race_id} - {e}")
            continue

    # 最終コミット
    conn.commit()

    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()

    print()
    print("=" * 80)
    print("再生成完了")
    print("=" * 80)
    print()
    print(f"終了時刻: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"所要時間: {elapsed/3600:.2f}時間 ({elapsed/60:.1f}分)")
    print()
    print(f"処理レース数: {processed:,}レース")
    print(f"成功: {succeeded:,}レース")
    print(f"失敗: {failed:,}レース")
    print(f"成功率: {succeeded/processed*100:.1f}%" if processed > 0 else "成功率: 0%")
    print()

    # 生成されたデータの確認
    cursor.execute('''
        SELECT COUNT(*)
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date >= '2025-01-01'
          AND r.race_date < '2026-01-01'
          AND rp.prediction_type = 'after'
    ''')
    new_count = cursor.fetchone()[0]

    print(f"生成された予想データ: {new_count:,}件")
    print(f"期待値（6艇×成功レース数）: {succeeded*6:,}件")

    if new_count >= succeeded * 6 * 0.95:  # 95%以上あればOK
        print("✓ データ生成成功")
    else:
        print("⚠ データ生成に問題がある可能性があります")

    print()

    # 信頼度別の統計
    cursor.execute('''
        SELECT
            rp.confidence,
            COUNT(DISTINCT rp.race_id) as race_count
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date >= '2025-01-01'
          AND r.race_date < '2026-01-01'
          AND rp.prediction_type = 'after'
        GROUP BY rp.confidence
        ORDER BY rp.confidence
    ''')

    print("信頼度別レース数:")
    for confidence, count in cursor.fetchall():
        print(f"  信頼度{confidence}: {count:,}レース")

    conn.close()

    print()
    print("=" * 80)
    print("次のステップ:")
    print("  1. 信頼度B単独評価: python scripts/analyze_confidence_b_only.py")
    print("  2. 全データ評価: python scripts/analyze_2025_fast.py")
    print("  3. 戦略Aとの統合評価: python scripts/integrated_strategy_evaluation.py")
    print("=" * 80)


if __name__ == "__main__":
    main()
