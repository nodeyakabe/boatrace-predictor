"""
確率校正の効果検証スクリプト

実際のモデルとデータを使用して、
Platt ScalingとIsotonic Regressionの効果を検証
"""

import sys
sys.path.append('.')

import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score
import matplotlib.pyplot as plt

from src.ml.probability_calibration import ProbabilityCalibrator


def load_sample_data(sample_size=10000):
    """
    サンプルデータを読み込み

    実データが利用できない場合は、シミュレーションデータを生成

    Returns:
        (y_prob_raw, y_true): 予測確率と実際のラベル
    """
    # データファイルパス
    data_dir = Path('data')

    # 実データを探索
    db_path = data_dir / 'boatrace.db'

    if db_path.exists():
        print("[INFO] 実データから確率・ラベルを読み込み中...")
        try:
            import sqlite3

            conn = sqlite3.connect(db_path)

            # 予測確率と実結果がある履歴データを取得
            query = """
            SELECT
                predicted_prob,
                CASE WHEN result_1st = predicted_racer THEN 1 ELSE 0 END as is_correct
            FROM race_results
            WHERE predicted_prob IS NOT NULL
              AND result_1st IS NOT NULL
            LIMIT ?
            """

            df = pd.read_sql_query(query, conn, params=(sample_size,))
            conn.close()

            if len(df) > 100:
                print(f"[OK] 実データ {len(df)}件を読み込みました")
                return df['predicted_prob'].values, df['is_correct'].values
            else:
                print(f"[WARNING] 実データ不足（{len(df)}件）、シミュレーションデータを使用")

        except Exception as e:
            print(f"[WARNING] 実データ読み込みエラー: {e}")
            print("[INFO] シミュレーションデータを使用します")

    # シミュレーションデータ生成
    print(f"[INFO] シミュレーションデータを生成中（{sample_size}件）...")

    np.random.seed(42)

    # バイアスのあるモデルをシミュレート
    # 過信傾向: 低確率を過小評価、高確率を過大評価
    y_prob_true = np.random.beta(2, 5, sample_size)  # 真の確率分布

    # バイアスを加える
    y_prob_raw = np.clip(y_prob_true ** 0.7, 0.01, 0.99)  # 過信

    # 真の確率に基づいて結果を生成
    y_true = np.random.binomial(1, y_prob_true)

    print(f"[OK] シミュレーションデータ生成完了")

    return y_prob_raw, y_true


def compute_calibration_metrics(y_prob, y_true):
    """
    校正関連の評価指標を計算

    Args:
        y_prob: 予測確率
        y_true: 実際のラベル

    Returns:
        dict: 評価指標
    """
    metrics = {
        'log_loss': log_loss(y_true, y_prob),
        'brier_score': brier_score_loss(y_true, y_prob),
        'roc_auc': roc_auc_score(y_true, y_prob)
    }

    # Expected Calibration Error (ECE)
    n_bins = 10
    bins = np.linspace(0, 1, n_bins + 1)
    bin_indices = np.digitize(y_prob, bins[:-1]) - 1
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)

    ece = 0.0
    for i in range(n_bins):
        mask = bin_indices == i
        if mask.sum() > 0:
            mean_prob = y_prob[mask].mean()
            mean_true = y_true[mask].mean()
            ece += mask.sum() / len(y_prob) * abs(mean_prob - mean_true)

    metrics['ece'] = ece

    return metrics


def plot_calibration_comparison(
    y_prob_raw,
    y_prob_platt,
    y_prob_isotonic,
    y_true,
    save_path='data/calibration_comparison.png'
):
    """
    3つの校正曲線を比較プロット

    Args:
        y_prob_raw: 校正前の確率
        y_prob_platt: Platt Scaling校正後
        y_prob_isotonic: Isotonic Regression校正後
        y_true: 実際のラベル
        save_path: 保存パス
    """
    fig, ax = plt.subplots(figsize=(10, 8))

    n_bins = 10

    def compute_curve(y_prob, y_true):
        bins = np.linspace(0, 1, n_bins + 1)
        bin_indices = np.digitize(y_prob, bins[:-1]) - 1
        bin_indices = np.clip(bin_indices, 0, n_bins - 1)

        prob_bins = []
        true_bins = []

        for i in range(n_bins):
            mask = bin_indices == i
            if mask.sum() > 0:
                prob_bins.append(y_prob[mask].mean())
                true_bins.append(y_true[mask].mean())

        return np.array(prob_bins), np.array(true_bins)

    # 校正前
    prob_raw, true_raw = compute_curve(y_prob_raw, y_true)
    ax.plot(prob_raw, true_raw, 'o-', label='Before Calibration',
            color='red', markersize=8, linewidth=2, alpha=0.7)

    # Platt Scaling
    prob_platt, true_platt = compute_curve(y_prob_platt, y_true)
    ax.plot(prob_platt, true_platt, 's-', label='Platt Scaling',
            color='blue', markersize=8, linewidth=2, alpha=0.7)

    # Isotonic Regression
    prob_iso, true_iso = compute_curve(y_prob_isotonic, y_true)
    ax.plot(prob_iso, true_iso, '^-', label='Isotonic Regression',
            color='green', markersize=8, linewidth=2, alpha=0.7)

    # 理想線
    ax.plot([0, 1], [0, 1], '--', label='Perfectly Calibrated',
            color='gray', linewidth=2)

    ax.set_xlabel('Mean Predicted Probability', fontsize=12, fontweight='bold')
    ax.set_ylabel('Fraction of Positives', fontsize=12, fontweight='bold')
    ax.set_title('Probability Calibration Comparison', fontsize=14, fontweight='bold')
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1])

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"[OK] 校正曲線を保存: {save_path}")
    plt.close()


def main():
    """
    メイン検証プロセス
    """
    print("=" * 70)
    print("確率校正の効果検証")
    print("=" * 70)

    # 1. データ読み込み
    print("\n[1/5] データ読み込み")
    print("-" * 70)
    y_prob_raw, y_true = load_sample_data(sample_size=10000)

    print(f"  サンプル数: {len(y_prob_raw)}")
    print(f"  正例数: {y_true.sum()} ({y_true.mean():.2%})")
    print(f"  予測確率範囲: [{y_prob_raw.min():.4f}, {y_prob_raw.max():.4f}]")

    # 2. 訓練/検証分割
    print("\n[2/5] データ分割")
    print("-" * 70)
    y_prob_train, y_prob_test, y_true_train, y_true_test = train_test_split(
        y_prob_raw, y_true, test_size=0.3, random_state=42, stratify=y_true
    )

    print(f"  訓練データ: {len(y_prob_train)}件")
    print(f"  検証データ: {len(y_prob_test)}件")

    # 3. 校正前の評価
    print("\n[3/5] 校正前の評価")
    print("-" * 70)
    metrics_raw = compute_calibration_metrics(y_prob_test, y_true_test)

    print(f"  Log Loss:        {metrics_raw['log_loss']:.6f}")
    print(f"  Brier Score:     {metrics_raw['brier_score']:.6f}")
    print(f"  ROC AUC:         {metrics_raw['roc_auc']:.6f}")
    print(f"  ECE:             {metrics_raw['ece']:.6f}")

    # 4. 確率校正
    print("\n[4/5] 確率校正実行")
    print("-" * 70)

    # Platt Scaling
    print("\n  [Platt Scaling]")
    calibrator_platt = ProbabilityCalibrator(method='platt')
    calibrator_platt.fit(y_prob_train, y_true_train)
    y_prob_platt = calibrator_platt.transform(y_prob_test)

    metrics_platt = compute_calibration_metrics(y_prob_platt, y_true_test)

    print(f"    Log Loss:      {metrics_platt['log_loss']:.6f} "
          f"(改善: {(metrics_raw['log_loss'] - metrics_platt['log_loss']):.6f})")
    print(f"    Brier Score:   {metrics_platt['brier_score']:.6f} "
          f"(改善: {(metrics_raw['brier_score'] - metrics_platt['brier_score']):.6f})")
    print(f"    ECE:           {metrics_platt['ece']:.6f} "
          f"(改善: {(metrics_raw['ece'] - metrics_platt['ece']):.6f})")

    # Isotonic Regression
    print("\n  [Isotonic Regression]")
    calibrator_isotonic = ProbabilityCalibrator(method='isotonic')
    calibrator_isotonic.fit(y_prob_train, y_true_train)
    y_prob_isotonic = calibrator_isotonic.transform(y_prob_test)

    metrics_isotonic = compute_calibration_metrics(y_prob_isotonic, y_true_test)

    print(f"    Log Loss:      {metrics_isotonic['log_loss']:.6f} "
          f"(改善: {(metrics_raw['log_loss'] - metrics_isotonic['log_loss']):.6f})")
    print(f"    Brier Score:   {metrics_isotonic['brier_score']:.6f} "
          f"(改善: {(metrics_raw['brier_score'] - metrics_isotonic['brier_score']):.6f})")
    print(f"    ECE:           {metrics_isotonic['ece']:.6f} "
          f"(改善: {(metrics_raw['ece'] - metrics_isotonic['ece']):.6f})")

    # 5. 結果サマリー
    print("\n[5/5] 検証結果サマリー")
    print("=" * 70)

    print("\n【Log Loss比較】")
    print(f"  校正前:            {metrics_raw['log_loss']:.6f}")
    print(f"  Platt Scaling:     {metrics_platt['log_loss']:.6f} "
          f"({'改善' if metrics_platt['log_loss'] < metrics_raw['log_loss'] else '悪化'} "
          f"{abs((metrics_platt['log_loss'] - metrics_raw['log_loss']) / metrics_raw['log_loss'] * 100):.2f}%)")
    print(f"  Isotonic Reg:      {metrics_isotonic['log_loss']:.6f} "
          f"({'改善' if metrics_isotonic['log_loss'] < metrics_raw['log_loss'] else '悪化'} "
          f"{abs((metrics_isotonic['log_loss'] - metrics_raw['log_loss']) / metrics_raw['log_loss'] * 100):.2f}%)")

    print("\n【Brier Score比較】")
    print(f"  校正前:            {metrics_raw['brier_score']:.6f}")
    print(f"  Platt Scaling:     {metrics_platt['brier_score']:.6f} "
          f"({'改善' if metrics_platt['brier_score'] < metrics_raw['brier_score'] else '悪化'} "
          f"{abs((metrics_platt['brier_score'] - metrics_raw['brier_score']) / metrics_raw['brier_score'] * 100):.2f}%)")
    print(f"  Isotonic Reg:      {metrics_isotonic['brier_score']:.6f} "
          f"({'改善' if metrics_isotonic['brier_score'] < metrics_raw['brier_score'] else '悪化'} "
          f"{abs((metrics_isotonic['brier_score'] - metrics_raw['brier_score']) / metrics_raw['brier_score'] * 100):.2f}%)")

    print("\n【Expected Calibration Error (ECE)】")
    print(f"  校正前:            {metrics_raw['ece']:.6f}")
    print(f"  Platt Scaling:     {metrics_platt['ece']:.6f} "
          f"({'改善' if metrics_platt['ece'] < metrics_raw['ece'] else '悪化'} "
          f"{abs((metrics_platt['ece'] - metrics_raw['ece']) / metrics_raw['ece'] * 100):.2f}%)")
    print(f"  Isotonic Reg:      {metrics_isotonic['ece']:.6f} "
          f"({'改善' if metrics_isotonic['ece'] < metrics_raw['ece'] else '悪化'} "
          f"{abs((metrics_isotonic['ece'] - metrics_raw['ece']) / metrics_raw['ece'] * 100):.2f}%)")

    # 6. 校正曲線プロット
    print("\n" + "-" * 70)
    plot_calibration_comparison(
        y_prob_test,
        y_prob_platt,
        y_prob_isotonic,
        y_true_test
    )

    # 7. 推奨方法
    print("\n" + "=" * 70)
    print("【推奨方法】")

    # Log LossとECEの総合判定
    platt_score = (
        (metrics_platt['log_loss'] < metrics_raw['log_loss']) * 2 +
        (metrics_platt['ece'] < metrics_raw['ece']) * 1
    )

    isotonic_score = (
        (metrics_isotonic['log_loss'] < metrics_raw['log_loss']) * 2 +
        (metrics_isotonic['ece'] < metrics_raw['ece']) * 1
    )

    if isotonic_score > platt_score:
        print("  Isotonic Regression を推奨")
        print("  理由: Log LossとECEの改善度が最も高い")
    elif platt_score > isotonic_score:
        print("  Platt Scaling を推奨")
        print("  理由: シンプルで解釈性が高く、十分な改善効果")
    else:
        print("  どちらの方法も同等の効果")
        print("  推奨: Platt Scaling (シンプルさを優先)")

    print("\n" + "=" * 70)
    print("検証完了")
    print("=" * 70)

    return {
        'raw': metrics_raw,
        'platt': metrics_platt,
        'isotonic': metrics_isotonic
    }


if __name__ == '__main__':
    try:
        results = main()
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] 検証エラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
