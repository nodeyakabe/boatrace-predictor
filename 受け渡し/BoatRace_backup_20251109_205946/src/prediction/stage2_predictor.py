"""
Stage2予測器

Stage2Trainerを使用して、レース結果の着順確率を予測するクラス。
リアルタイム予想で使用される。
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import sqlite3
from datetime import datetime

from src.training.stage2_trainer import Stage2Trainer


class Stage2Predictor:
    """
    Stage2モデルを使用した予測器

    特徴:
    - Stage2Trainerで学習したモデルを読み込み
    - レースの特徴量を生成
    - 各艇の着順確率を予測
    - 三連単の組み合わせ確率を計算
    """

    def __init__(self, model_path: Optional[str] = None, db_path: str = "data/boatrace.db"):
        """
        初期化

        Args:
            model_path: モデルファイルのパス（Noneの場合は最新モデルを使用）
            db_path: データベースのパス
        """
        self.db_path = db_path
        self.trainer = Stage2Trainer()
        self.model_loaded = False

        # モデル読み込み
        if model_path:
            self.load_model(model_path)
        else:
            # 最新モデルを自動検索
            self.load_latest_model()

    def load_model(self, model_path: str) -> bool:
        """
        指定されたモデルを読み込む

        Args:
            model_path: モデルディレクトリのパス

        Returns:
            読み込み成功: True, 失敗: False
        """
        try:
            self.trainer.load_models(model_path)
            self.model_loaded = True
            print(f"✅ モデル読み込み成功: {model_path}")
            return True
        except Exception as e:
            print(f"❌ モデル読み込み失敗: {e}")
            self.model_loaded = False
            return False

    def load_latest_model(self) -> bool:
        """
        最新のStage2モデルを自動検索して読み込む

        Returns:
            読み込み成功: True, 失敗: False
        """
        models_dir = Path("models/stage2")

        if not models_dir.exists():
            print("❌ models/stage2 ディレクトリが存在しません")
            return False

        # stage2_model_* のディレクトリを検索
        model_dirs = list(models_dir.glob("stage2_model_*"))

        if not model_dirs:
            print("❌ Stage2モデルが見つかりません。まず学習してください。")
            return False

        # 最新のモデルを選択（ディレクトリ名のタイムスタンプでソート）
        latest_model = sorted(model_dirs, reverse=True)[0]

        return self.load_model(str(latest_model))

    def generate_features_from_db(self, race_date: str, venue_code: str, race_number: int) -> Optional[pd.DataFrame]:
        """
        データベースからレースデータを取得し、特徴量を生成

        Args:
            race_date: レース日（YYYY-MM-DD）
            venue_code: 会場コード（2桁）
            race_number: レース番号

        Returns:
            特徴量DataFrame（6艇分）、データがない場合はNone
        """
        conn = sqlite3.connect(self.db_path)

        try:
            # レースIDを構築
            race_id_pattern = f"{race_date}_{venue_code}_{race_number:02d}"

            # レース詳細データ取得
            query = """
                SELECT
                    rd.pit_number,
                    rd.racer_number,
                    rd.racer_name,
                    rd.actual_course,
                    r.venue_name,
                    r.grade,
                    r.race_date
                FROM race_details rd
                JOIN races r ON rd.race_id = r.id
                WHERE r.id LIKE ?
                ORDER BY rd.pit_number
            """

            df_race = pd.read_sql_query(query, conn, params=(f"{race_id_pattern}%",))

            if df_race.empty:
                print(f"⚠️ レースデータが見つかりません: {race_id_pattern}")
                return None

            # 選手の過去成績を取得（簡易版）
            features_list = []

            for idx, row in df_race.iterrows():
                racer_number = row['racer_number']

                # 選手の過去90日間の成績を取得
                stats_query = """
                    SELECT
                        AVG(CASE WHEN res.rank = 1 THEN 1.0 ELSE 0.0 END) as win_rate,
                        AVG(CASE WHEN res.rank <= 2 THEN 1.0 ELSE 0.0 END) as place_rate_2,
                        AVG(CASE WHEN res.rank <= 3 THEN 1.0 ELSE 0.0 END) as place_rate_3,
                        AVG(res.rank) as avg_rank,
                        COUNT(*) as total_races
                    FROM results res
                    JOIN races r ON res.race_id = r.id
                    WHERE res.racer_number = ?
                      AND r.race_date >= date(?, '-90 days')
                      AND r.race_date < ?
                """

                df_stats = pd.read_sql_query(
                    stats_query,
                    conn,
                    params=(racer_number, race_date, race_date)
                )

                # Stage1の簡易スコアを計算（Stage1モデルがない場合のフォールバック）
                if df_stats.iloc[0]['total_races'] > 0:
                    prob_1st_stage1 = df_stats.iloc[0]['win_rate']
                    prob_2nd_stage1 = df_stats.iloc[0]['place_rate_2'] - prob_1st_stage1
                    prob_3rd_stage1 = df_stats.iloc[0]['place_rate_3'] - df_stats.iloc[0]['place_rate_2']
                else:
                    # データがない場合はコース別の期待値を使用
                    course = row['actual_course'] if pd.notna(row['actual_course']) else row['pit_number']
                    course_rates = [0.50, 0.20, 0.12, 0.08, 0.06, 0.04]  # 1-6コースの平均勝率
                    prob_1st_stage1 = course_rates[course - 1] if 1 <= course <= 6 else 0.15
                    prob_2nd_stage1 = 0.15
                    prob_3rd_stage1 = 0.15

                # 特徴量を作成
                features = {
                    'pit_number': row['pit_number'],
                    'racer_number': racer_number,
                    'racer_name': row['racer_name'],
                    'actual_course': row['actual_course'] if pd.notna(row['actual_course']) else row['pit_number'],
                    'prob_1st_stage1': prob_1st_stage1,
                    'prob_2nd_stage1': prob_2nd_stage1,
                    'prob_3rd_stage1': prob_3rd_stage1,
                    'win_rate': df_stats.iloc[0]['win_rate'] if df_stats.iloc[0]['total_races'] > 0 else prob_1st_stage1,
                    'place_rate_2': df_stats.iloc[0]['place_rate_2'] if df_stats.iloc[0]['total_races'] > 0 else prob_1st_stage1 + prob_2nd_stage1,
                    'place_rate_3': df_stats.iloc[0]['place_rate_3'] if df_stats.iloc[0]['total_races'] > 0 else prob_1st_stage1 + prob_2nd_stage1 + prob_3rd_stage1,
                    'avg_rank': df_stats.iloc[0]['avg_rank'] if df_stats.iloc[0]['total_races'] > 0 else 3.5,
                    'total_races': df_stats.iloc[0]['total_races']
                }

                features_list.append(features)

            df_features = pd.DataFrame(features_list)

            return df_features

        except Exception as e:
            print(f"❌ 特徴量生成エラー: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            conn.close()

    def predict_race_probabilities(self, race_date: str, venue_code: str, race_number: int) -> Optional[pd.DataFrame]:
        """
        レースの各艇の着順確率を予測

        Args:
            race_date: レース日（YYYY-MM-DD）
            venue_code: 会場コード
            race_number: レース番号

        Returns:
            予測結果DataFrame（columns: pit_number, racer_name, prob_1, prob_2, ..., prob_6）
        """
        if not self.model_loaded:
            print("❌ モデルが読み込まれていません")
            return None

        # 特徴量生成
        df_features = self.generate_features_from_db(race_date, venue_code, race_number)

        if df_features is None or df_features.empty:
            return None

        # Stage2予測用の特徴量を抽出
        feature_columns = ['prob_1st_stage1', 'prob_2nd_stage1', 'prob_3rd_stage1',
                          'win_rate', 'place_rate_2', 'place_rate_3', 'avg_rank']

        X = df_features[feature_columns]

        # Stage2モデルで予測
        try:
            prob_df = self.trainer.predict_probabilities(X)

            # 結果を整形
            result = pd.DataFrame({
                'pit_number': df_features['pit_number'],
                'racer_number': df_features['racer_number'],
                'racer_name': df_features['racer_name'],
                'prob_1': prob_df['prob_1'],
                'prob_2': prob_df['prob_2'],
                'prob_3': prob_df['prob_3'],
                'prob_4': prob_df['prob_4'],
                'prob_5': prob_df['prob_5'],
                'prob_6': prob_df['prob_6']
            })

            return result

        except Exception as e:
            print(f"❌ 予測エラー: {e}")
            import traceback
            traceback.print_exc()
            return None

    def predict_top3(self, race_date: str, venue_code: str, race_number: int) -> List[Dict]:
        """
        レースのトップ3を予測（1着〜3着の最有力艇）

        Args:
            race_date: レース日
            venue_code: 会場コード
            race_number: レース番号

        Returns:
            上位3艇の情報リスト [{'pit_number': 1, 'racer_name': '...', 'prob': 0.45}, ...]
        """
        prob_df = self.predict_race_probabilities(race_date, venue_code, race_number)

        if prob_df is None:
            return []

        # 1着確率でソート
        prob_df_sorted = prob_df.sort_values('prob_1', ascending=False)

        top3 = []
        for idx in range(min(3, len(prob_df_sorted))):
            row = prob_df_sorted.iloc[idx]
            top3.append({
                'pit_number': int(row['pit_number']),
                'racer_number': int(row['racer_number']),
                'racer_name': row['racer_name'],
                'prob_1st': float(row['prob_1']),
                'prob_2nd': float(row['prob_2']),
                'prob_3rd': float(row['prob_3'])
            })

        return top3

    def calculate_sanrentan_probabilities(self, race_date: str, venue_code: str, race_number: int,
                                         top_n: int = 10) -> List[Dict]:
        """
        三連単の組み合わせ確率を計算

        Args:
            race_date: レース日
            venue_code: 会場コード
            race_number: レース番号
            top_n: 上位何組み合わせまで返すか

        Returns:
            組み合わせ確率のリスト [{'combination': '1-2-3', 'prob': 0.05}, ...]
        """
        prob_df = self.predict_race_probabilities(race_date, venue_code, race_number)

        if prob_df is None:
            return []

        combinations = []

        # 全組み合わせの確率を計算
        for i in range(len(prob_df)):
            pit_i = int(prob_df.iloc[i]['pit_number'])
            prob_i_1st = prob_df.iloc[i]['prob_1']

            for j in range(len(prob_df)):
                if j == i:
                    continue

                pit_j = int(prob_df.iloc[j]['pit_number'])
                prob_j_2nd = prob_df.iloc[j]['prob_2']

                for k in range(len(prob_df)):
                    if k == i or k == j:
                        continue

                    pit_k = int(prob_df.iloc[k]['pit_number'])
                    prob_k_3rd = prob_df.iloc[k]['prob_3']

                    # 組み合わせ確率を計算（独立と仮定）
                    combined_prob = prob_i_1st * prob_j_2nd * prob_k_3rd

                    combinations.append({
                        'combination': f"{pit_i}-{pit_j}-{pit_k}",
                        'prob': combined_prob,
                        'pit_1st': pit_i,
                        'pit_2nd': pit_j,
                        'pit_3rd': pit_k
                    })

        # 確率でソート
        combinations.sort(key=lambda x: x['prob'], reverse=True)

        # 正規化（上位top_nの合計を1.0に）
        top_combinations = combinations[:top_n]
        total_prob = sum(c['prob'] for c in top_combinations)

        if total_prob > 0:
            for c in top_combinations:
                c['prob'] = c['prob'] / total_prob

        return top_combinations


# テスト用コード
if __name__ == "__main__":
    print("=== Stage2Predictor テスト ===\n")

    predictor = Stage2Predictor()

    if not predictor.model_loaded:
        print("⚠️ モデルが読み込まれていません。")
        print("まず Stage2Trainer で学習を実行してください:")
        print("  1. Streamlit UI: 「モデル学習」タブ → 「データ準備 (Stage2)」→「モデル学習 (Stage2)」")
        print("  2. または python src/training/stage2_trainer.py でサンプル学習")
        exit(0)

    # テスト用のレースデータ（実際のデータが必要）
    test_date = "2024-11-01"
    test_venue = "01"
    test_race = 1

    print(f"テストレース: {test_date} {test_venue}会場 {test_race}R\n")

    # トップ3予測
    print("【トップ3予測】")
    top3 = predictor.predict_top3(test_date, test_venue, test_race)

    if top3:
        for i, boat in enumerate(top3, 1):
            print(f"{i}位: {boat['pit_number']}号艇 {boat['racer_name']} "
                  f"(1着確率: {boat['prob_1st']:.1%})")
    else:
        print("予測データがありません")

    print("\n【三連単 TOP5】")
    sanrentan = predictor.calculate_sanrentan_probabilities(test_date, test_venue, test_race, top_n=5)

    if sanrentan:
        for i, combo in enumerate(sanrentan, 1):
            print(f"{i}. {combo['combination']}: {combo['prob']:.2%}")
    else:
        print("組み合わせデータがありません")

    print("\nテスト完了")
