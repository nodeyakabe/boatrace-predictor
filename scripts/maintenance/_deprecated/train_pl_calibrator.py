#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Plackett-Luce確率のキャリブレーターを学習・保存するスクリプト

【問題】
  P-Lモデルは10%以上の確率帯で30-40%の過大評価をする。
  例: P-Lが15%と推定したレースの実際の的中率は約12.6%

【解法】
  2020-2024年データでIsotonic Regressionを学習し、
  P-L確率 -> 実際の確率に補正するモデルを作成する。

使用方法:
  python scripts/maintenance/train_pl_calibrator.py
  python scripts/maintenance/train_pl_calibrator.py --train-years 2020 2021 2022 2023
  python scripts/maintenance/train_pl_calibrator.py --eval-only
"""

import sqlite3
import math
import sys
import os
import argparse
import joblib
import numpy as np
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

PL_SCALE = 20.0
CALIBRATOR_PATH = Path(PROJECT_ROOT) / 'models' / 'pl_calibrator.pkl'


def compute_pl_prob(scores: dict, combo: tuple, scale: float = PL_SCALE) -> float:
    """Plackett-Luce確率を計算"""
    a, b, c = combo
    if not all(k in scores for k in [a, b, c]):
        return 0.0
    max_s = max(scores.values())
    exp_s = {k: math.exp((v - max_s) / scale) for k, v in scores.items()}
    total = sum(exp_s.values())
    if total == 0:
        return 0.0
    pa = exp_s[a] / total
    denom_b = total - exp_s[a]
    if denom_b <= 0:
        return 0.0
    pb = exp_s[b] / denom_b
    denom_c = denom_b - exp_s[b]
    if denom_c <= 0:
        return 0.0
    pc = exp_s[c] / denom_c
    return pa * pb * pc


def build_training_data(years: list, sample_per_year: int = 50000) -> tuple:
    """
    学習データ生成: (P-L確率, 実際の的中 0/1) のペア

    1-2-3の組み合わせのみ（最も重要な単一買い目）を対象。
    """
    print(f"学習データ生成中 {years} ...")
    all_probs = []
    all_hits = []

    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        for year in years:
            print(f"  {year}年 処理中...", end='', flush=True)

            # スコアマップ取得
            cursor.execute('''
                SELECT rp.race_id, rp.pit_number, rp.total_score
                FROM race_predictions rp
                JOIN races r ON rp.race_id = r.id
                WHERE r.race_date >= ? AND r.race_date < ?
                AND rp.prediction_type = 'before'
                AND rp.total_score IS NOT NULL
            ''', (f'{year}-01-01', f'{year+1}-01-01'))

            score_map = {}
            for rid, pit, sc in cursor.fetchall():
                if rid not in score_map:
                    score_map[rid] = {}
                score_map[rid][pit] = sc

            # 予測1-2-3を取得
            cursor.execute('''
                SELECT rp1.race_id, rp1.pit_number, rp2.pit_number, rp3.pit_number
                FROM race_predictions rp1
                JOIN race_predictions rp2 ON rp1.race_id=rp2.race_id
                    AND rp2.prediction_type='before' AND rp2.rank_prediction=2
                JOIN race_predictions rp3 ON rp1.race_id=rp3.race_id
                    AND rp3.prediction_type='before' AND rp3.rank_prediction=3
                JOIN races r ON rp1.race_id=r.id
                WHERE rp1.prediction_type='before' AND rp1.rank_prediction=1
                AND r.race_date >= ? AND r.race_date < ?
            ''', (f'{year}-01-01', f'{year+1}-01-01'))
            pred_map = {row[0]: (row[1], row[2], row[3]) for row in cursor.fetchall()}

            # 実際の結果取得
            race_ids = list(pred_map.keys())
            if not race_ids:
                print(" 0件")
                continue

            # バッチ処理
            batch_size = 5000
            result_map = {}
            for i in range(0, len(race_ids), batch_size):
                batch = race_ids[i:i+batch_size]
                placeholders = ','.join(['?'] * len(batch))
                cursor.execute(f'''
                    SELECT race_id, pit_number, rank
                    FROM results
                    WHERE race_id IN ({placeholders})
                    AND is_invalid=0 AND rank IN ('1','2','3')
                ''', batch)
                for rid, pit, rank in cursor.fetchall():
                    if rid not in result_map:
                        result_map[rid] = {}
                    result_map[rid][rank] = pit

            # P-L確率 + 的中フラグのペアを作成
            count = 0
            for rid, (p1, p2, p3) in pred_map.items():
                if rid not in score_map or rid not in result_map:
                    continue
                scores = score_map[rid]
                if len(scores) < 4:
                    continue

                pl = compute_pl_prob(scores, (p1, p2, p3))
                if pl <= 0:
                    continue

                res = result_map[rid]
                hit = 1 if (res.get('1') == p1 and res.get('2') == p2 and res.get('3') == p3) else 0

                all_probs.append(pl)
                all_hits.append(hit)
                count += 1

            print(f" {count:,}件")

    probs = np.array(all_probs)
    hits = np.array(all_hits)
    print(f"合計: {len(probs):,}件  実際の的中率: {hits.mean()*100:.2f}%  P-L平均: {probs.mean()*100:.2f}%")
    return probs, hits


def train_and_save(probs: np.ndarray, hits: np.ndarray) -> object:
    """Isotonic Regressionを学習して保存"""
    from sklearn.isotonic import IsotonicRegression

    print("\nIsotonic Regression 学習中...")
    calibrator = IsotonicRegression(out_of_bounds='clip')
    calibrator.fit(probs, hits)

    # 保存
    CALIBRATOR_PATH.parent.mkdir(exist_ok=True)
    joblib.dump(calibrator, CALIBRATOR_PATH)
    print(f"保存: {CALIBRATOR_PATH}")
    return calibrator


def evaluate(calibrator, probs: np.ndarray, hits: np.ndarray, label: str = ''):
    """キャリブレーション前後の精度比較"""
    from sklearn.metrics import brier_score_loss

    cal_probs = calibrator.transform(probs)

    print(f"\n=== 評価 {label} ===")
    print(f"Brier Score 補正前: {brier_score_loss(hits, probs):.6f}")
    print(f"Brier Score 補正後: {brier_score_loss(hits, cal_probs):.6f}")

    # バケット別比較
    print("\nバケット別 補正前/補正後/実績:")
    print(f"{'P-L範囲':>12} {'件数':>7} {'補正前':>8} {'補正後':>8} {'実績':>8} {'改善':>8}")
    bins = [0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.15, 0.20, 0.30, 1.0]
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (probs >= lo) & (probs < hi)
        if mask.sum() < 10:
            continue
        avg_before = probs[mask].mean()
        avg_after = cal_probs[mask].mean()
        actual = hits[mask].mean()
        improvement = abs(avg_after - actual) - abs(avg_before - actual)
        sign = "改善" if improvement < -0.001 else ("悪化" if improvement > 0.001 else "同等")
        print(f"  {lo*100:4.1f}-{hi*100:4.1f}%  {mask.sum():>7,}  "
              f"{avg_before*100:>7.2f}%  {avg_after*100:>7.2f}%  {actual*100:>7.2f}%  {sign}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--train-years', type=int, nargs='+',
                        default=[2020, 2021, 2022, 2023, 2024],
                        help='学習に使う年度（デフォルト: 2020-2024）')
    parser.add_argument('--eval-only', action='store_true',
                        help='既存モデルの評価のみ実行（2025年データで評価）')
    args = parser.parse_args()

    if args.eval_only:
        if not CALIBRATOR_PATH.exists():
            print(f"ERROR: {CALIBRATOR_PATH} が存在しません。先に学習を実行してください。")
            sys.exit(1)
        calibrator = joblib.load(CALIBRATOR_PATH)
        print(f"モデルを読み込み: {CALIBRATOR_PATH}")
        probs, hits = build_training_data([2025])
        evaluate(calibrator, probs, hits, "2025年（OOSテスト）")
        return

    # 学習
    probs, hits = build_training_data(args.train_years)
    if len(probs) == 0:
        print("ERROR: 学習データが0件です")
        sys.exit(1)

    calibrator = train_and_save(probs, hits)

    # 学習データでの評価
    evaluate(calibrator, probs, hits, f"学習データ {args.train_years}")

    # 2025年（OOS）での評価
    print("\n--- 2025年 OOS評価 ---")
    probs_oos, hits_oos = build_training_data([2025])
    if len(probs_oos) > 0:
        evaluate(calibrator, probs_oos, hits_oos, "2025年（OOSテスト）")


if __name__ == '__main__':
    main()
