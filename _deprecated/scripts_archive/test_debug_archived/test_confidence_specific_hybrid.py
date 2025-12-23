"""
信頼度別ハイブリッドスコアリング適用の検証
信頼度Bのみハイブリッド適用、C/Dは従来スコアを確認
"""

import sys
import warnings
from pathlib import Path
import sqlite3

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.race_predictor import RacePredictor


def main():
    print("=" * 80)
    print("信頼度別ハイブリッドスコアリング適用の検証")
    print("=" * 80)
    print()

    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    predictor = RacePredictor(str(db_path))

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 信頼度Bレース3件、信頼度Cレース3件を取得
    confidence_tests = {
        'B': [],
        'C': []
    }

    for conf in ['B', 'C']:
        cursor.execute('''
            SELECT DISTINCT r.id, r.race_date, r.venue_code
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id
            WHERE rp.confidence = ?
              AND rp.prediction_type = 'advance'
              AND r.race_date >= '2024-01-01'
              AND r.race_date < '2025-01-01'
            ORDER BY r.race_date DESC
            LIMIT 3
        ''', (conf,))
        confidence_tests[conf] = cursor.fetchall()

    conn.close()

    # 各信頼度のレースをテスト
    for conf, races in confidence_tests.items():
        print(f"\n【信頼度{conf}のテスト】")
        print("-" * 80)

        for race_id, race_date, venue_code in races:
            print(f"\nレースID: {race_id} ({race_date} {venue_code}場)")

            try:
                predictions = predictor.predict_race(race_id)

                if not predictions or len(predictions) < 3:
                    print("  予測データ不足")
                    continue

                # トップ3艇の情報を表示
                print(f"  信頼度: {predictions[0]['confidence']}")
                print(f"  Top3艇:")
                for i, pred in enumerate(predictions[:3], 1):
                    # ハイブリッドスコアが適用されているか確認
                    has_hybrid = 'hybrid_score' in pred
                    hybrid_indicator = " [ハイブリッド適用]" if has_hybrid else ""
                    print(f"    {i}位: {pred['pit_number']}号 - スコア{pred['total_score']:.1f}{hybrid_indicator}")

            except Exception as e:
                print(f"  エラー: {e}")

    print("\n" + "=" * 80)
    print("検証完了")
    print("=" * 80)
    print()
    print("期待結果:")
    print("  - 信頼度Bレース: [ハイブリッド適用] が表示される")
    print("  - 信頼度Cレース: [ハイブリッド適用] が表示されない")


if __name__ == "__main__":
    main()
