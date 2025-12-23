"""
予測コース強制化の効果測定スクリプト

DBの予測結果に対してコース強制化ロジックを適用し、
改善効果をシミュレーションで検証する
"""
import os
import sys
import sqlite3
from datetime import datetime

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

import yaml


def load_prediction_strategy():
    """予測戦略設定をロード"""
    config_path = os.path.join(PROJECT_ROOT, 'config', 'prediction_strategy.yaml')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"設定ファイルロードエラー: {e}")
        return None


def simulate_course_enforcement(db_path: str, year: int = 2025):
    """コース強制化のシミュレーション"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    strategy = load_prediction_strategy()
    if strategy is None:
        print("ERROR: 予測戦略設定を読み込めませんでした")
        return

    enforcement_config = strategy.get('course_enforcement', {})
    mode = enforcement_config.get('mode', 'score_threshold')

    print("=" * 100)
    print(f"{year}年 予測コース強制化 効果測定")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)
    print(f"\n設定モード: {mode}")

    if mode == 'score_threshold':
        score_settings = enforcement_config.get('score_threshold_settings', {})
        min_score_diff = score_settings.get('min_score_difference', 8.0)
        print(f"スコア差閾値: {min_score_diff}pt")
    elif mode == 'confidence_threshold':
        conf_settings = enforcement_config.get('confidence_threshold_settings', {})
        min_confidence = conf_settings.get('min_confidence', 'C')
        print(f"信頼度閾値: {min_confidence}")

    # 1. 現在の予測結果を取得
    cursor.execute("""
        SELECT
            rp.race_id,
            rp.pit_number as predicted_pit,
            rp.total_score,
            rp.confidence,
            res.pit_number as actual_winner
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN results res ON rp.race_id = res.race_id AND res.rank = '1'
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rp.prediction_type = 'advance'
        AND rp.rank_prediction = 1
    """, (f'{year}-01-01', f'{year}-12-31'))

    current_predictions = cursor.fetchall()
    total_races = len(current_predictions)

    print(f"\n総予測数: {total_races:,}")

    # 2. 各レースの1コースのスコアも取得
    cursor.execute("""
        SELECT
            rp1.race_id,
            rp1.pit_number as top_pit,
            rp1.total_score as top_score,
            rp1.confidence,
            rp2.total_score as course1_score
        FROM race_predictions rp1
        JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id AND rp2.pit_number = 1 AND rp2.prediction_type = 'advance'
        JOIN races r ON rp1.race_id = r.id
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rp1.prediction_type = 'advance'
        AND rp1.rank_prediction = 1
    """, (f'{year}-01-01', f'{year}-12-31'))

    predictions_with_course1 = cursor.fetchall()

    # 3. シミュレーション
    current_correct = 0
    enforced_correct = 0
    enforcement_count = 0

    confidence_order = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'E': 1}

    for race_id, top_pit, top_score, confidence, course1_score in predictions_with_course1:
        # 実際の勝者を取得
        cursor.execute("""
            SELECT pit_number FROM results
            WHERE race_id = ? AND rank = '1'
        """, (race_id,))
        result = cursor.fetchone()
        if result is None:
            continue

        actual_winner = result[0]

        # 現在の予測が的中したか
        if top_pit == actual_winner:
            current_correct += 1

        # 強制化判定
        should_enforce = False
        if top_pit != 1:
            score_diff = top_score - course1_score if course1_score else 0

            if mode == 'all':
                should_enforce = True
            elif mode == 'score_threshold':
                min_score_diff = enforcement_config.get('score_threshold_settings', {}).get('min_score_difference', 8.0)
                if score_diff < min_score_diff:
                    should_enforce = True
            elif mode == 'confidence_threshold':
                min_confidence = enforcement_config.get('confidence_threshold_settings', {}).get('min_confidence', 'C')
                min_conf_level = confidence_order.get(min_confidence, 3)
                top_conf_level = confidence_order.get(confidence, 3)
                if top_conf_level <= min_conf_level:
                    should_enforce = True
            elif mode == 'combined':
                min_confidence = enforcement_config.get('confidence_threshold_settings', {}).get('min_confidence', 'C')
                min_score_diff = enforcement_config.get('score_threshold_settings', {}).get('min_score_difference', 8.0)
                min_conf_level = confidence_order.get(min_confidence, 3)
                top_conf_level = confidence_order.get(confidence, 3)
                if top_conf_level <= min_conf_level or score_diff < min_score_diff:
                    should_enforce = True

        # 強制化後の予測結果
        if should_enforce:
            enforcement_count += 1
            if actual_winner == 1:
                enforced_correct += 1
        else:
            if top_pit == actual_winner:
                enforced_correct += 1

    # 4. 結果出力
    current_accuracy = (current_correct / total_races * 100) if total_races > 0 else 0
    enforced_accuracy = (enforced_correct / total_races * 100) if total_races > 0 else 0
    improvement = enforced_accuracy - current_accuracy

    # ベースライン（常に1コース予測）
    cursor.execute("""
        SELECT COUNT(*)
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        JOIN results res ON rp.race_id = res.race_id AND res.rank = '1'
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rp.prediction_type = 'advance'
        AND rp.rank_prediction = 1
        AND res.pit_number = 1
    """, (f'{year}-01-01', f'{year}-12-31'))

    baseline_correct = cursor.fetchone()[0]
    baseline_accuracy = (baseline_correct / total_races * 100) if total_races > 0 else 0

    print("\n" + "=" * 100)
    print("[結果]")
    print("=" * 100)

    print(f"\n修正前（現システム）:")
    print(f"  的中率: {current_accuracy:.1f}%")
    print(f"  的中数: {current_correct:,} / {total_races:,}")

    print(f"\n修正後（コース強制化適用）:")
    print(f"  的中率: {enforced_accuracy:.1f}%")
    print(f"  強制化適用数: {enforcement_count:,}件")

    print(f"\nベースライン（常に1コース予測）:")
    print(f"  的中率: {baseline_accuracy:.1f}%")

    print("\n" + "=" * 100)
    print("[改善効果]")
    print("=" * 100)
    print(f"\n現システム比: {improvement:+.1f}pt")
    print(f"ベースライン比: {enforced_accuracy - baseline_accuracy:+.1f}pt")

    if enforced_accuracy > baseline_accuracy:
        print("\n[OK] ベースラインを上回る付加価値を達成")
    elif enforced_accuracy >= baseline_accuracy - 1:
        print("\n[CLOSE] ベースラインとほぼ同等")
    else:
        print("\n[NG] ベースラインを下回る")

    conn.close()

    print("\n" + "=" * 100)
    print("効果測定完了")
    print("=" * 100)

    return {
        'current_accuracy': current_accuracy,
        'enforced_accuracy': enforced_accuracy,
        'baseline_accuracy': baseline_accuracy,
        'improvement': improvement,
        'enforcement_count': enforcement_count
    }


def test_different_thresholds(db_path: str, year: int = 2025):
    """異なる閾値での効果を比較"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("\n" + "=" * 100)
    print("閾値別効果比較")
    print("=" * 100)

    # 予測データを取得
    cursor.execute("""
        SELECT
            rp1.race_id,
            rp1.pit_number as top_pit,
            rp1.total_score as top_score,
            rp1.confidence,
            rp2.total_score as course1_score,
            res.pit_number as actual_winner
        FROM race_predictions rp1
        JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id AND rp2.pit_number = 1 AND rp2.prediction_type = 'advance'
        JOIN races r ON rp1.race_id = r.id
        LEFT JOIN results res ON rp1.race_id = res.race_id AND res.rank = '1'
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rp1.prediction_type = 'advance'
        AND rp1.rank_prediction = 1
    """, (f'{year}-01-01', f'{year}-12-31'))

    predictions = cursor.fetchall()
    total_races = len(predictions)

    # ベースラインと現システム
    current_correct = 0
    baseline_correct = 0

    for race_id, top_pit, top_score, confidence, course1_score, actual_winner in predictions:
        if actual_winner is None:
            continue
        if top_pit == actual_winner:
            current_correct += 1
        if actual_winner == 1:
            baseline_correct += 1

    current_accuracy = (current_correct / total_races * 100) if total_races > 0 else 0
    baseline_accuracy = (baseline_correct / total_races * 100) if total_races > 0 else 0

    print(f"\n基準:")
    print(f"  現システム精度: {current_accuracy:.1f}%")
    print(f"  ベースライン: {baseline_accuracy:.1f}%")

    # 異なるスコア差閾値でテスト
    print(f"\n[スコア差閾値による強制化]")
    print(f"閾値   | 強制化数 | 修正後精度 | 現システム比 | ベースライン比")
    print("-" * 80)

    for threshold in [3, 5, 8, 10, 12, 15, 20]:
        enforced_correct = 0
        enforcement_count = 0

        for race_id, top_pit, top_score, confidence, course1_score, actual_winner in predictions:
            if actual_winner is None:
                continue

            score_diff = top_score - course1_score if course1_score else 0

            if top_pit != 1 and score_diff < threshold:
                enforcement_count += 1
                if actual_winner == 1:
                    enforced_correct += 1
            else:
                if top_pit == actual_winner:
                    enforced_correct += 1

        enforced_accuracy = (enforced_correct / total_races * 100) if total_races > 0 else 0
        improvement = enforced_accuracy - current_accuracy
        vs_baseline = enforced_accuracy - baseline_accuracy

        mark = " *" if vs_baseline >= 0 else ""
        print(f" {threshold:>4}pt | {enforcement_count:>8} | {enforced_accuracy:>10.1f}% | {improvement:>+11.1f}pt | {vs_baseline:>+13.1f}pt{mark}")

    conn.close()


if __name__ == '__main__':
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')
    simulate_course_enforcement(db_path)
    test_different_thresholds(db_path)
