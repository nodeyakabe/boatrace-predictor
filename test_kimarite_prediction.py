"""
決まり手ベース予測システムのテストスクリプト
"""

import sys
import logging
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from src.prediction.integrated_kimarite_predictor import IntegratedKimaritePredictor

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def main():
    predictor = IntegratedKimaritePredictor()

    # テスト用レースID
    test_race_id = 445  # 実際のデータがあるレースID

    print("=" * 80)
    print("決まり手ベース予測システム - テスト実行")
    print("=" * 80)

    try:
        # 予測実行
        print(f"\nレースID {test_race_id} の予測を実行中...\n")
        result = predictor.predict_race(test_race_id, min_bets=3, max_bets=6)

        print(f"\n【レースID {test_race_id} の予測結果】\n")

        # 買い目を表示
        print("=== 推奨買い目 ===\n")
        formatted = predictor.format_prediction_for_ui(result)

        for bet_info in formatted['bets']:
            print(f"{bet_info['順位']}. {bet_info['買い目']} - {bet_info['確率']} ({bet_info['信頼度']})")
            print(f"   シナリオ: {bet_info['シナリオ']}\n")

        print(f"本命: {formatted['main_favorite']}")
        print(f"的中率カバー: {formatted['total_coverage']}")
        print(f"推奨: {formatted['recommendation']}\n")

        # シナリオサマリー
        print(predictor.scenario_engine.get_scenario_summary(result['scenarios']))

        print("\n" + "=" * 80)
        print("テスト完了")
        print("=" * 80)

    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
