# -*- coding: utf-8 -*-
"""
2024年のbefore予測データ生成

目的:
- 2024年レースデータでbefore予測（直前情報込み）を生成
- B-1会場フィルターの過学習検証に使用
- 2024年/2025年のデータ一貫性確認

処理内容:
1. 2024年の予測可能レース（詳細+6艇+結果あり）を抽出
2. 既存の学習済みモデルで予測を実行
3. prediction_type='before'でDBに保存
"""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime
import numpy as np

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.ml.conditional_rank_model import ConditionalRankModel
from src.features.feature_engineering import FeatureEngineering


def generate_2024_before_predictions(db_path: str, model_dir: str):
    """2024年before予測を生成"""

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 70)
    print("2024年before予測生成")
    print("=" * 70)

    # 1. 予測可能なレースを抽出
    print("\n[1] 予測対象レースの抽出中...")

    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2024-12-31'
          AND EXISTS (SELECT 1 FROM race_details WHERE race_id = r.id)
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id)
          AND EXISTS (
              SELECT 1 FROM entries
              WHERE race_id = r.id
              GROUP BY race_id
              HAVING COUNT(DISTINCT pit_number) = 6
          )
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')

    target_races = cursor.fetchall()
    print(f"対象レース数: {len(target_races):,}件")

    if len(target_races) == 0:
        print("[エラー] 予測対象レースがありません")
        conn.close()
        return

    # 2. モデルのロード
    print("\n[2] モデルのロード中...")

    model_path = Path(model_dir)
    if not model_path.exists():
        print(f"[エラー] モデルディレクトリが見つかりません: {model_path}")
        conn.close()
        return

    # v2モデル（baseline ROI 167%）を使用
    # v3は不採用のため除外
    v2_model = model_path / "conditional_rank_v2_20251215_first.json"

    if not v2_model.exists():
        print(f"[エラー] v2モデルが見つかりません: {v2_model}")
        print("\n利用可能なモデル:")
        for f in model_path.glob("conditional_rank_*_first.json"):
            print(f"  - {f.name}")
        conn.close()
        return

    model_prefix = str(v2_model).replace("_first.json", "")

    print(f"使用モデル: {Path(model_prefix).name}")

    try:
        model = ConditionalRankModel()
        model.load(model_prefix)
        print("[OK] モデルロード完了")
    except Exception as e:
        print(f"[エラー] モデルロードに失敗: {e}")
        conn.close()
        return

    # 3. 特徴量エンジニアリングの初期化
    print("\n[3] 特徴量エンジニアリングの初期化...")

    feature_eng = FeatureEngineering(db_path)
    print("[OK] 初期化完了")

    # 4. 予測実行
    print(f"\n[4] 予測実行中（{len(target_races):,}件）...")

    predictions_inserted = 0
    predictions_failed = 0

    # 既存のbefore予測を削除（再生成の場合）
    cursor.execute('''
        DELETE FROM race_predictions
        WHERE prediction_type = 'before'
          AND race_id IN (
              SELECT id FROM races
              WHERE race_date >= '2024-01-01' AND race_date <= '2024-12-31'
          )
    ''')
    deleted_count = cursor.rowcount
    if deleted_count > 0:
        print(f"[INFO] 既存のbefore予測を削除: {deleted_count}件")

    for idx, race in enumerate(target_races, 1):
        race_id = race['id']
        race_date = race['race_date']
        venue_code = race['venue_code']
        race_number = race['race_number']

        if idx % 1000 == 0:
            print(f"  進捗: {idx:,}/{len(target_races):,} ({idx/len(target_races)*100:.1f}%)")

        try:
            # レースデータ取得
            race_df = feature_eng.prepare_race_data(race_id)

            if race_df is None or len(race_df) == 0:
                predictions_failed += 1
                continue

            # 予測実行
            probabilities = model.predict_trifecta_probabilities(race_df)

            # スコア計算（確率→スコア変換）
            scores = {}
            for pit, probs in probabilities.items():
                # 1着確率 * 100 + 2着確率 * 50 + 3着確率 * 25
                score = (probs.get('first', 0) * 100 +
                        probs.get('second', 0) * 50 +
                        probs.get('third', 0) * 25)
                scores[pit] = score

            # スコア順にランク付け
            sorted_pits = sorted(scores.items(), key=lambda x: x[1], reverse=True)

            # DBに保存
            for rank, (pit_number, total_score) in enumerate(sorted_pits, 1):
                probs = probabilities[pit_number]

                cursor.execute('''
                    INSERT INTO race_predictions (
                        race_id, pit_number, prediction_type,
                        rank_prediction, total_score,
                        first_prob, second_prob, third_prob,
                        confidence, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    race_id, pit_number, 'before',
                    rank, total_score,
                    probs.get('first', 0),
                    probs.get('second', 0),
                    probs.get('third', 0),
                    'C',  # デフォルト信頼度
                    datetime.now().isoformat()
                ))

            predictions_inserted += 6  # 6艇分

        except Exception as e:
            predictions_failed += 1
            if predictions_failed <= 10:  # 最初の10件のみエラー表示
                print(f"[エラー] {race_date} {venue_code}場 {race_number}R: {e}")

    conn.commit()

    # 5. 結果サマリー
    print(f"\n" + "=" * 70)
    print("予測生成完了")
    print("=" * 70)
    print(f"\n対象レース数: {len(target_races):,}件")
    print(f"成功: {predictions_inserted//6:,}件")
    print(f"失敗: {predictions_failed:,}件")
    print(f"総予測数: {predictions_inserted:,}件（6艇×レース数）")

    # 確認クエリ
    cursor.execute('''
        SELECT COUNT(DISTINCT race_id)
        FROM race_predictions
        WHERE prediction_type = 'before'
          AND race_id IN (
              SELECT id FROM races
              WHERE race_date >= '2024-01-01' AND race_date <= '2024-12-31'
          )
    ''')
    inserted_races = cursor.fetchone()[0]
    print(f"\nDB確認: {inserted_races:,}レース分のbefore予測が保存されました")

    conn.close()

    print("\n[次のステップ]")
    print("1. B-1会場フィルターの2024年検証を実施")
    print("2. 2024年/2025年のROI比較分析")
    print("3. 過学習リスクの定量評価")


def main():
    db_path = str(ROOT_DIR / 'data' / 'boatrace.db')
    model_dir = str(ROOT_DIR / 'models')

    print("2024年before予測生成を開始します...")
    print(f"データベース: {db_path}")
    print(f"モデル: {model_dir}")
    print()

    confirm = input("実行しますか？ (y/n): ")
    if confirm.lower() != 'y':
        print("キャンセルしました")
        return

    generate_2024_before_predictions(db_path, model_dir)

    print("\n完了しました")


if __name__ == '__main__':
    main()
