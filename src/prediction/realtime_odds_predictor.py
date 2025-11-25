"""
リアルタイムオッズ統合予測システム
実際のオッズデータを使用して期待値計算を行う
"""

import sys
import os
from typing import Dict, Optional, List, Tuple
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.scraper.playwright_odds_scraper import PlaywrightOddsScraper
from src.scraper.odds_scraper import OddsScraper
from src.ml.conditional_rank_model import ConditionalRankModel
from src.ml.probability_adjuster import ProbabilityAdjuster


class RealtimeOddsPredictor:
    """
    リアルタイムオッズ統合予測クラス

    機能:
    - 3連単オッズのリアルタイム取得（Playwright）
    - 条件付き確率モデルによる3連単確率計算
    - 期待値計算と推奨ベット選定
    """

    def __init__(self, model_dir: str = 'models', use_playwright: bool = True, use_probability_adjustment: bool = True):
        """
        初期化

        Args:
            model_dir: モデルディレクトリ
            use_playwright: Playwrightを使用するか（Falseの場合はHTTPスクレイパー）
            use_probability_adjustment: 確率補正を使用するか（推奨: True）
        """
        self.model_dir = model_dir
        self.use_playwright = use_playwright
        self.use_probability_adjustment = use_probability_adjustment

        # オッズスクレイパー初期化
        if use_playwright:
            self.odds_scraper = PlaywrightOddsScraper(headless=True, timeout=30000)
        else:
            self.odds_scraper = OddsScraper()

        # 予測モデル（遅延ロード）
        self._model = None
        self._model_loaded = False

        # 確率補正器
        self.probability_adjuster = ProbabilityAdjuster(adjustment_strength=0.7) if use_probability_adjustment else None

    def _load_model(self):
        """モデルを遅延ロード"""
        if not self._model_loaded:
            self._model = ConditionalRankModel(model_dir=self.model_dir)
            try:
                self._model.load('conditional_rank_v1')
                self._model_loaded = True
                print(f"[INFO] モデル読み込み完了: {len(self._model.feature_names)}特徴量")
            except Exception as e:
                print(f"[ERROR] モデル読み込み失敗: {e}")
                self._model = None

    def get_real_odds(self, venue_code: str, race_date: str, race_number: int) -> Optional[Dict[str, float]]:
        """
        リアルタイム3連単オッズを取得

        Args:
            venue_code: 競艇場コード（2桁）
            race_date: レース日付（YYYYMMDD）
            race_number: レース番号

        Returns:
            {'1-2-3': 10.5, '1-2-4': 25.3, ...} 全120通り
        """
        if self.use_playwright:
            odds = self.odds_scraper.get_trifecta_odds(venue_code, race_date, race_number)
        else:
            # HTTPスクレイパーは3連単オッズを取得できないので警告
            print("[WARNING] HTTPスクレイパーは3連単オッズを取得できません")
            odds = None

        return odds

    def predict_trifecta_probabilities(self, race_features) -> Optional[Dict[str, float]]:
        """
        3連単確率を予測

        Args:
            race_features: レースの特徴量（DataFrame、6行）

        Returns:
            {'1-2-3': 0.08, '1-3-2': 0.06, ...} 全120通りの確率
        """
        self._load_model()

        if self._model is None:
            return None

        try:
            probs = self._model.predict_trifecta_probabilities(race_features)

            # 確率補正を適用
            if self.probability_adjuster and probs:
                probs_before = sum(probs.values())
                probs = self.probability_adjuster.adjust_trifecta_probabilities(probs)
                probs_after = sum(probs.values())

                print(f"[INFO] 確率補正適用: 補正前合計={probs_before:.3f}, 補正後合計={probs_after:.3f}")

            return probs
        except Exception as e:
            print(f"[ERROR] 確率予測失敗: {e}")
            return None

    def calculate_expected_values(self,
                                   probabilities: Dict[str, float],
                                   odds: Dict[str, float]) -> Dict[str, Dict]:
        """
        期待値を計算

        Args:
            probabilities: 予測確率 {'1-2-3': 0.08, ...}
            odds: 実際のオッズ {'1-2-3': 10.5, ...}

        Returns:
            {
                '1-2-3': {
                    'probability': 0.08,
                    'odds': 10.5,
                    'expected_value': 0.84,
                    'kelly_fraction': 0.0 (負なので0)
                },
                ...
            }
        """
        results = {}

        for combo in probabilities:
            prob = probabilities[combo]
            actual_odds = odds.get(combo, 0)

            if actual_odds > 0:
                # 期待値 = 確率 × オッズ
                ev = prob * actual_odds

                # ケリー基準: f* = (bp - q) / b = (p*odds - (1-p)) / odds
                # b = odds - 1 (純利益倍率)
                # p = prob, q = 1 - prob
                b = actual_odds - 1
                kelly = (prob * actual_odds - (1 - prob)) / actual_odds if actual_odds > 0 else 0
                kelly = max(0, kelly)  # 負の値は0にする

                results[combo] = {
                    'probability': prob,
                    'odds': actual_odds,
                    'expected_value': ev,
                    'kelly_fraction': kelly
                }

        return results

    def get_recommended_bets(self,
                              expected_values: Dict[str, Dict],
                              min_ev: float = 1.0,
                              min_prob: float = 0.01,
                              max_bets: int = 10) -> List[Dict]:
        """
        推奨ベットを選定

        Args:
            expected_values: 期待値データ
            min_ev: 最小期待値（デフォルト1.0=100%）
            min_prob: 最小確率
            max_bets: 最大推奨数

        Returns:
            [
                {
                    'combination': '1-2-3',
                    'probability': 0.08,
                    'odds': 15.0,
                    'expected_value': 1.2,
                    'kelly_fraction': 0.013,
                    'rank': 1
                },
                ...
            ]
        """
        # フィルタリング
        candidates = []
        for combo, data in expected_values.items():
            if data['expected_value'] >= min_ev and data['probability'] >= min_prob:
                candidates.append({
                    'combination': combo,
                    **data
                })

        # 期待値でソート
        candidates.sort(key=lambda x: x['expected_value'], reverse=True)

        # 上位を選定
        recommended = candidates[:max_bets]

        # ランク付け
        for i, bet in enumerate(recommended, 1):
            bet['rank'] = i

        return recommended

    def analyze_race(self,
                     venue_code: str,
                     race_date: str,
                     race_number: int,
                     race_features) -> Optional[Dict]:
        """
        レースを総合分析

        Args:
            venue_code: 競艇場コード
            race_date: レース日付
            race_number: レース番号
            race_features: レース特徴量

        Returns:
            {
                'venue_code': '02',
                'race_date': '20251117',
                'race_number': 1,
                'odds_retrieved': 120,
                'probabilities_calculated': 120,
                'recommended_bets': [...],
                'top_10_by_probability': [...],
                'top_10_by_expected_value': [...],
                'timestamp': '2025-11-17T12:00:00'
            }
        """
        print(f"\n{'='*60}")
        print(f"レース分析: {venue_code}場 {race_number}R ({race_date})")
        print(f"{'='*60}")

        # オッズ取得
        print("\n1. リアルタイムオッズ取得中...")
        odds = self.get_real_odds(venue_code, race_date, race_number)

        if not odds:
            print("[ERROR] オッズ取得失敗")
            return None

        print(f"   取得成功: {len(odds)}通り")

        # 確率予測
        print("\n2. 3連単確率計算中...")
        probs = self.predict_trifecta_probabilities(race_features)

        if not probs:
            print("[ERROR] 確率計算失敗")
            return None

        print(f"   計算完了: {len(probs)}通り")

        # 期待値計算
        print("\n3. 期待値計算中...")
        ev_data = self.calculate_expected_values(probs, odds)
        print(f"   計算完了: {len(ev_data)}通り")

        # 推奨ベット選定
        print("\n4. 推奨ベット選定...")
        recommended = self.get_recommended_bets(ev_data, min_ev=1.0, min_prob=0.005, max_bets=10)
        print(f"   期待値1.0以上: {len(recommended)}通り")

        # Top10（確率順）
        top10_prob = sorted(ev_data.items(), key=lambda x: x[1]['probability'], reverse=True)[:10]
        top10_prob_list = [
            {
                'combination': combo,
                **data
            }
            for combo, data in top10_prob
        ]

        # Top10（期待値順）
        top10_ev = sorted(ev_data.items(), key=lambda x: x[1]['expected_value'], reverse=True)[:10]
        top10_ev_list = [
            {
                'combination': combo,
                **data
            }
            for combo, data in top10_ev
        ]

        # 結果をまとめる
        result = {
            'venue_code': venue_code,
            'race_date': race_date,
            'race_number': race_number,
            'odds_retrieved': len(odds),
            'probabilities_calculated': len(probs),
            'recommended_bets': recommended,
            'top_10_by_probability': top10_prob_list,
            'top_10_by_expected_value': top10_ev_list,
            'timestamp': datetime.now().isoformat()
        }

        # サマリー表示
        print(f"\n{'='*60}")
        print("分析結果サマリー")
        print(f"{'='*60}")

        print("\n【確率Top5】")
        for i, item in enumerate(top10_prob_list[:5], 1):
            print(f"  {i}. {item['combination']}: "
                  f"確率{item['probability']*100:.2f}% × "
                  f"オッズ{item['odds']:.1f}倍 = "
                  f"期待値{item['expected_value']:.2f}")

        print("\n【期待値Top5】")
        for i, item in enumerate(top10_ev_list[:5], 1):
            print(f"  {i}. {item['combination']}: "
                  f"確率{item['probability']*100:.2f}% × "
                  f"オッズ{item['odds']:.1f}倍 = "
                  f"期待値{item['expected_value']:.2f}")

        if recommended:
            print(f"\n【推奨ベット（期待値1.0以上）】")
            for bet in recommended[:5]:
                print(f"  {bet['rank']}. {bet['combination']}: "
                      f"EV={bet['expected_value']:.2f}, "
                      f"Kelly={bet['kelly_fraction']*100:.1f}%")
        else:
            print("\n[WARNING] 期待値1.0以上の組み合わせがありません")

        return result

    def close(self):
        """リソースを解放"""
        if hasattr(self, 'odds_scraper') and hasattr(self.odds_scraper, 'close'):
            self.odds_scraper.close()


def test_realtime_predictor():
    """テスト実行"""
    import pandas as pd
    import sqlite3

    print("="*60)
    print("リアルタイムオッズ統合予測 テスト")
    print("="*60)

    # 予測器初期化
    predictor = RealtimeOddsPredictor(use_playwright=True)

    # 今日の日付
    today = datetime.now().strftime('%Y%m%d')

    # テスト用のダミー特徴量を作成（実際のDBから取得する必要がある）
    # ここでは戸田競艇場の最近のレースデータを使用
    db_path = 'data/boatrace.db'

    if os.path.exists(db_path):
        print("\nデータベースからレース特徴量を取得...")

        with sqlite3.connect(db_path) as conn:
            # 最新のレースデータを取得
            query = """
                SELECT
                    e.pit_number,
                    COALESCE(e.win_rate, 5.0) as win_rate,
                    COALESCE(e.second_rate, 10.0) as second_rate,
                    COALESCE(e.third_rate, 15.0) as third_rate,
                    COALESCE(e.motor_second_rate, 30.0) as motor_2nd_rate,
                    COALESCE(e.motor_third_rate, 40.0) as motor_3rd_rate,
                    COALESCE(e.boat_second_rate, 30.0) as boat_2nd_rate,
                    COALESCE(e.boat_third_rate, 40.0) as boat_3rd_rate,
                    COALESCE(e.racer_weight, 52.0) as weight,
                    COALESCE(e.avg_st, 0.15) as avg_st,
                    COALESCE(e.local_win_rate, 20.0) as local_win_rate,
                    CASE e.racer_rank
                        WHEN 'A1' THEN 4
                        WHEN 'A2' THEN 3
                        WHEN 'B1' THEN 2
                        ELSE 1
                    END as racer_rank_score
                FROM entries e
                JOIN races r ON e.race_id = r.id
                WHERE r.venue_code = '02'
                ORDER BY r.race_date DESC, r.id DESC, e.pit_number
                LIMIT 6
            """
            race_features = pd.read_sql_query(query, conn)
    else:
        print("\nダミーデータを使用...")
        # ダミーデータ
        race_features = pd.DataFrame({
            'pit_number': [1, 2, 3, 4, 5, 6],
            'win_rate': [35.0, 15.0, 12.0, 10.0, 8.0, 5.0],
            'second_rate': [25.0, 20.0, 18.0, 15.0, 12.0, 10.0],
            'third_rate': [20.0, 22.0, 20.0, 18.0, 15.0, 12.0],
            'motor_2nd_rate': [35.0, 32.0, 30.0, 28.0, 25.0, 22.0],
            'motor_3rd_rate': [45.0, 42.0, 40.0, 38.0, 35.0, 32.0],
            'boat_2nd_rate': [33.0, 31.0, 29.0, 27.0, 25.0, 23.0],
            'boat_3rd_rate': [43.0, 41.0, 39.0, 37.0, 35.0, 33.0],
            'weight': [52.0, 51.5, 53.0, 52.5, 51.0, 54.0],
            'avg_st': [0.14, 0.15, 0.16, 0.15, 0.17, 0.18],
            'local_win_rate': [40.0, 25.0, 20.0, 15.0, 10.0, 5.0],
            'racer_rank_score': [4, 3, 3, 2, 2, 1]
        })

    print(f"特徴量形状: {race_features.shape}")

    # レース分析
    result = predictor.analyze_race('02', today, 1, race_features)

    if result:
        print(f"\n\n分析完了")
        print(f"オッズ取得: {result['odds_retrieved']}通り")
        print(f"確率計算: {result['probabilities_calculated']}通り")
        print(f"推奨ベット: {len(result['recommended_bets'])}通り")
    else:
        print("\n分析失敗")

    predictor.close()

    print("\n" + "="*60)
    print("テスト完了")
    print("="*60)


if __name__ == "__main__":
    test_realtime_predictor()
