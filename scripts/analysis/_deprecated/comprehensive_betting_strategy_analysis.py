"""
競艇3連単の買い目戦略を徹底的に分析するスクリプト

目的:
1. 現在の分析結果の妥当性チェック
2. 1点買い vs 複数点買いの詳細分析
3. 他の買い目パターンの可能性検証
4. 投資効率の最適化
5. 機会損失の定量化
"""

import sqlite3
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

DB_PATH = project_root / 'data' / 'boatrace.db'

class BettingStrategyAnalyzer:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)

    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()

    def get_basic_stats(self) -> pd.DataFrame:
        """基本統計を取得"""
        query = """
        SELECT
            COUNT(DISTINCT race_id) as total_races,
            COUNT(DISTINCT CASE WHEN prediction_type = 'before' THEN race_id END) as before_races,
            COUNT(DISTINCT CASE WHEN prediction_type = 'advance' THEN race_id END) as advance_races
        FROM race_predictions
        """
        return pd.read_sql(query, self.conn)

    def get_prediction_accuracy_by_rank(self) -> pd.DataFrame:
        """予測順位別の実際の着順分布"""
        query = """
        SELECT
            rp.rank_prediction,
            CAST(r.rank AS INTEGER) as actual_rank,
            COUNT(*) as count
        FROM race_predictions rp
        JOIN results r ON rp.race_id = r.race_id AND rp.pit_number = r.pit_number
        WHERE rp.prediction_type = 'before'
          AND r.is_invalid = 0
          AND r.rank != ''
        GROUP BY rp.rank_prediction, r.rank
        ORDER BY rp.rank_prediction, actual_rank
        """
        df = pd.read_sql(query, self.conn)
        pivot = df.pivot(index='rank_prediction', columns='actual_rank', values='count').fillna(0)
        pivot = pivot.astype(int)
        pivot['total'] = pivot.sum(axis=1)

        # 各着順の的中率を計算
        for col in range(1, 7):
            if col in pivot.columns:
                pivot[f'rank_{col}_rate'] = (pivot[col] / pivot['total'] * 100).round(2)

        return pivot

    def analyze_betting_pattern(self, pattern_name: str, bets: List[Tuple[int, int, int, int]]) -> Dict:
        """
        買い目パターンの分析

        Args:
            pattern_name: パターン名
            bets: [(予測1位, 予測2位, 予測3位, 賭け金), ...]

        Returns:
            分析結果の辞書
        """
        bet_conditions = []
        for i, (pred1, pred2, pred3, amount) in enumerate(bets):
            bet_conditions.append(f"""
            WHEN rp1.rank_prediction = {pred1}
                AND rp2.rank_prediction = {pred2}
                AND rp3.rank_prediction = {pred3}
            THEN {amount}
            """)

        bet_case = "CASE " + " ".join(bet_conditions) + " ELSE 0 END"

        query = f"""
        WITH race_predictions_wide AS (
            SELECT
                race_id,
                MAX(CASE WHEN rank_prediction = 1 THEN pit_number END) as pred_1st,
                MAX(CASE WHEN rank_prediction = 2 THEN pit_number END) as pred_2nd,
                MAX(CASE WHEN rank_prediction = 3 THEN pit_number END) as pred_3rd,
                MAX(CASE WHEN rank_prediction = 4 THEN pit_number END) as pred_4th,
                MAX(CASE WHEN rank_prediction = 5 THEN pit_number END) as pred_5th,
                MAX(CASE WHEN rank_prediction = 6 THEN pit_number END) as pred_6th,
                MAX(CASE WHEN rank_prediction = 1 THEN confidence END) as confidence_1st
            FROM race_predictions
            WHERE prediction_type = 'before'
            GROUP BY race_id
        ),
        race_results_wide AS (
            SELECT
                race_id,
                MAX(CASE WHEN rank = '1' THEN pit_number END) as actual_1st,
                MAX(CASE WHEN rank = '2' THEN pit_number END) as actual_2nd,
                MAX(CASE WHEN rank = '3' THEN pit_number END) as actual_3rd
            FROM results
            WHERE is_invalid = 0 AND rank != ''
            GROUP BY race_id
        ),
        trifecta_combinations AS (
            SELECT
                rp.race_id,
                rp.confidence_1st,
                rp1.rank_prediction as pred1,
                rp2.rank_prediction as pred2,
                rp3.rank_prediction as pred3,
                CAST(rp1.pit_number AS TEXT) || '-' ||
                CAST(rp2.pit_number AS TEXT) || '-' ||
                CAST(rp3.pit_number AS TEXT) as combination,
                {bet_case} as bet_amount
            FROM race_predictions_wide rp
            JOIN race_predictions rp1 ON rp.race_id = rp1.race_id
            JOIN race_predictions rp2 ON rp.race_id = rp2.race_id
            JOIN race_predictions rp3 ON rp.race_id = rp3.race_id
            WHERE rp1.prediction_type = 'before'
              AND rp2.prediction_type = 'before'
              AND rp3.prediction_type = 'before'
              AND rp1.pit_number != rp2.pit_number
              AND rp1.pit_number != rp3.pit_number
              AND rp2.pit_number != rp3.pit_number
        ),
        race_bets AS (
            SELECT
                tc.race_id,
                tc.confidence_1st,
                SUM(tc.bet_amount) as total_bet,
                tc.combination,
                tc.bet_amount
            FROM trifecta_combinations tc
            WHERE tc.bet_amount > 0
            GROUP BY tc.race_id, tc.confidence_1st, tc.combination, tc.bet_amount
        ),
        race_outcomes AS (
            SELECT
                rb.race_id,
                rb.confidence_1st,
                rb.total_bet,
                CAST(rr.actual_1st AS TEXT) || '-' ||
                CAST(rr.actual_2nd AS TEXT) || '-' ||
                CAST(rr.actual_3rd AS TEXT) as actual_combination,
                MAX(CASE WHEN rb.combination =
                    CAST(rr.actual_1st AS TEXT) || '-' ||
                    CAST(rr.actual_2nd AS TEXT) || '-' ||
                    CAST(rr.actual_3rd AS TEXT)
                    THEN rb.bet_amount ELSE 0 END) as winning_bet,
                to_.odds
            FROM race_bets rb
            JOIN race_results_wide rr ON rb.race_id = rr.race_id
            LEFT JOIN trifecta_odds to_ ON rb.race_id = to_.race_id
                AND CAST(rr.actual_1st AS TEXT) || '-' ||
                    CAST(rr.actual_2nd AS TEXT) || '-' ||
                    CAST(rr.actual_3rd AS TEXT) = to_.combination
            GROUP BY rb.race_id, rb.confidence_1st, rb.total_bet, rr.actual_1st, rr.actual_2nd, rr.actual_3rd, to_.odds
        )
        SELECT
            confidence_1st as confidence,
            COUNT(*) as race_count,
            SUM(CASE WHEN winning_bet > 0 THEN 1 ELSE 0 END) as hit_count,
            ROUND(100.0 * SUM(CASE WHEN winning_bet > 0 THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate,
            SUM(total_bet) as total_investment,
            SUM(CASE WHEN winning_bet > 0 THEN winning_bet * odds ELSE 0 END) as total_return,
            SUM(CASE WHEN winning_bet > 0 THEN winning_bet * odds ELSE 0 END) - SUM(total_bet) as net_profit,
            ROUND(100.0 * SUM(CASE WHEN winning_bet > 0 THEN winning_bet * odds ELSE 0 END) / SUM(total_bet), 2) as roi
        FROM race_outcomes
        WHERE confidence_1st IS NOT NULL
        GROUP BY confidence_1st
        ORDER BY confidence_1st
        """

        return pd.read_sql(query, self.conn)

    def analyze_all_patterns(self) -> pd.DataFrame:
        """すべての買い目パターンを分析"""
        patterns = {
            '1点買い (1-2-3)': [
                (1, 2, 3, 400)
            ],
            'パターンH (本命厚め)': [
                (1, 2, 3, 200),
                (1, 2, 4, 100),
                (1, 2, 5, 100)
            ],
            '均等3点買い': [
                (1, 2, 3, 133),
                (1, 2, 4, 133),
                (1, 2, 5, 134)
            ],
            '4点買い': [
                (1, 2, 3, 100),
                (1, 2, 4, 100),
                (1, 2, 5, 100),
                (1, 2, 6, 100)
            ],
            '2着3着入替 (1-2-3, 1-3-2, 1-2-4)': [
                (1, 2, 3, 133),
                (1, 3, 2, 133),
                (1, 2, 4, 134)
            ],
            '5点買い (1位軸、2-3着分散)': [
                (1, 2, 3, 80),
                (1, 2, 4, 80),
                (1, 3, 2, 80),
                (1, 3, 4, 80),
                (1, 4, 2, 80)
            ],
            '6点買い (1位軸、2着2-4、3着2-4)': [
                (1, 2, 3, 67),
                (1, 2, 4, 67),
                (1, 3, 2, 67),
                (1, 3, 4, 66),
                (1, 4, 2, 66),
                (1, 4, 3, 67)
            ],
            'フォーメーション (1-2軸、3着3-5)': [
                (1, 2, 3, 133),
                (1, 2, 4, 133),
                (1, 2, 5, 134)
            ]
        }

        all_results = []
        for pattern_name, bets in patterns.items():
            print(f"分析中: {pattern_name}")
            result = self.analyze_betting_pattern(pattern_name, bets)
            result['pattern'] = pattern_name
            all_results.append(result)

        return pd.concat(all_results, ignore_index=True)

    def calculate_opportunity_loss(self) -> pd.DataFrame:
        """機会損失の定量化"""
        query = """
        WITH race_predictions_wide AS (
            SELECT
                race_id,
                MAX(CASE WHEN rank_prediction = 1 THEN pit_number END) as pred_1st,
                MAX(CASE WHEN rank_prediction = 2 THEN pit_number END) as pred_2nd,
                MAX(CASE WHEN rank_prediction = 3 THEN pit_number END) as pred_3rd,
                MAX(CASE WHEN rank_prediction = 4 THEN pit_number END) as pred_4th,
                MAX(CASE WHEN rank_prediction = 5 THEN pit_number END) as pred_5th,
                MAX(CASE WHEN rank_prediction = 1 THEN confidence END) as confidence_1st
            FROM race_predictions
            WHERE prediction_type = 'before'
            GROUP BY race_id
        ),
        race_results_wide AS (
            SELECT
                race_id,
                MAX(CASE WHEN rank = '1' THEN pit_number END) as actual_1st,
                MAX(CASE WHEN rank = '2' THEN pit_number END) as actual_2nd,
                MAX(CASE WHEN rank = '3' THEN pit_number END) as actual_3rd
            FROM results
            WHERE is_invalid = 0 AND rank != ''
            GROUP BY race_id
        ),
        hit_analysis AS (
            SELECT
                rp.race_id,
                rp.confidence_1st,
                CASE WHEN rp.pred_1st = rr.actual_1st
                     AND rp.pred_2nd = rr.actual_2nd
                     AND rp.pred_3rd = rr.actual_3rd THEN '1-2-3的中'
                     WHEN rp.pred_1st = rr.actual_1st
                     AND rp.pred_2nd = rr.actual_2nd
                     AND rp.pred_4th = rr.actual_3rd THEN '1-2-4的中'
                     WHEN rp.pred_1st = rr.actual_1st
                     AND rp.pred_2nd = rr.actual_2nd
                     AND rp.pred_5th = rr.actual_3rd THEN '1-2-5的中'
                     WHEN rp.pred_1st = rr.actual_1st
                     AND rp.pred_2nd = rr.actual_2nd THEN '1-2的中（3着外し）'
                     WHEN rp.pred_1st = rr.actual_1st THEN '1着のみ的中'
                     ELSE '全外し' END as hit_category,
                to_.odds
            FROM race_predictions_wide rp
            JOIN race_results_wide rr ON rp.race_id = rr.race_id
            LEFT JOIN trifecta_odds to_ ON rp.race_id = to_.race_id
                AND CAST(rr.actual_1st AS TEXT) || '-' ||
                    CAST(rr.actual_2nd AS TEXT) || '-' ||
                    CAST(rr.actual_3rd AS TEXT) = to_.combination
        )
        SELECT
            confidence_1st,
            hit_category,
            COUNT(*) as race_count,
            AVG(odds) as avg_odds,
            MIN(odds) as min_odds,
            MAX(odds) as max_odds
        FROM hit_analysis
        WHERE confidence_1st IS NOT NULL
        GROUP BY confidence_1st, hit_category
        ORDER BY confidence_1st, hit_category
        """
        return pd.read_sql(query, self.conn)

    def analyze_odds_distribution(self) -> pd.DataFrame:
        """的中時のオッズ分布を分析"""
        query = """
        WITH race_predictions_wide AS (
            SELECT
                race_id,
                MAX(CASE WHEN rank_prediction = 1 THEN pit_number END) as pred_1st,
                MAX(CASE WHEN rank_prediction = 2 THEN pit_number END) as pred_2nd,
                MAX(CASE WHEN rank_prediction = 3 THEN pit_number END) as pred_3rd,
                MAX(CASE WHEN rank_prediction = 1 THEN confidence END) as confidence_1st
            FROM race_predictions
            WHERE prediction_type = 'before'
            GROUP BY race_id
        ),
        race_results_wide AS (
            SELECT
                race_id,
                MAX(CASE WHEN rank = '1' THEN pit_number END) as actual_1st,
                MAX(CASE WHEN rank = '2' THEN pit_number END) as actual_2nd,
                MAX(CASE WHEN rank = '3' THEN pit_number END) as actual_3rd
            FROM results
            WHERE is_invalid = 0 AND rank != ''
            GROUP BY race_id
        ),
        hit_odds AS (
            SELECT
                rp.confidence_1st,
                to_.odds,
                CASE
                    WHEN to_.odds < 5 THEN '1-5倍未満'
                    WHEN to_.odds < 10 THEN '5-10倍'
                    WHEN to_.odds < 20 THEN '10-20倍'
                    WHEN to_.odds < 50 THEN '20-50倍'
                    WHEN to_.odds < 100 THEN '50-100倍'
                    ELSE '100倍以上' END as odds_range
            FROM race_predictions_wide rp
            JOIN race_results_wide rr ON rp.race_id = rr.race_id
            JOIN trifecta_odds to_ ON rp.race_id = to_.race_id
                AND CAST(rr.actual_1st AS TEXT) || '-' ||
                    CAST(rr.actual_2nd AS TEXT) || '-' ||
                    CAST(rr.actual_3rd AS TEXT) = to_.combination
            WHERE rp.pred_1st = rr.actual_1st
              AND rp.pred_2nd = rr.actual_2nd
              AND rp.pred_3rd = rr.actual_3rd
        )
        SELECT
            confidence_1st,
            odds_range,
            COUNT(*) as hit_count,
            AVG(odds) as avg_odds
        FROM hit_odds
        WHERE confidence_1st IS NOT NULL
        GROUP BY confidence_1st, odds_range
        ORDER BY confidence_1st,
                 CASE odds_range
                     WHEN '1-5倍未満' THEN 1
                     WHEN '5-10倍' THEN 2
                     WHEN '10-20倍' THEN 3
                     WHEN '20-50倍' THEN 4
                     WHEN '50-100倍' THEN 5
                     ELSE 6 END
        """
        return pd.read_sql(query, self.conn)

def main():
    print("=" * 80)
    print("競艇3連単買い目戦略の徹底分析")
    print("=" * 80)

    analyzer = BettingStrategyAnalyzer(str(DB_PATH))

    # 1. 基本統計
    print("\n" + "=" * 80)
    print("1. 基本統計")
    print("=" * 80)
    basic_stats = analyzer.get_basic_stats()
    print(basic_stats.to_string(index=False))

    # 2. 予測順位別の精度
    print("\n" + "=" * 80)
    print("2. 予測順位別の実際の着順分布")
    print("=" * 80)
    accuracy = analyzer.get_prediction_accuracy_by_rank()
    print(accuracy.to_string())

    # サマリー
    print("\n【予測精度サマリー】")
    for pred_rank in range(1, 7):
        if pred_rank in accuracy.index:
            rank_1_rate = accuracy.loc[pred_rank, 'rank_1_rate']
            rank_2_rate = accuracy.loc[pred_rank, 'rank_2_rate']
            rank_3_rate = accuracy.loc[pred_rank, 'rank_3_rate']
            top3_rate = (accuracy.loc[pred_rank, 1] if 1 in accuracy.columns else 0) + \
                       (accuracy.loc[pred_rank, 2] if 2 in accuracy.columns else 0) + \
                       (accuracy.loc[pred_rank, 3] if 3 in accuracy.columns else 0)
            top3_rate = top3_rate / accuracy.loc[pred_rank, 'total'] * 100
            print(f"予測{pred_rank}位: 1着{rank_1_rate:.2f}%, 2着{rank_2_rate:.2f}%, 3着{rank_3_rate:.2f}%, 3着以内{top3_rate:.2f}%")

    # 3. 買い目パターン別の分析
    print("\n" + "=" * 80)
    print("3. 買い目パターン別の収支分析")
    print("=" * 80)
    all_patterns = analyzer.analyze_all_patterns()

    # 信頼度別にまとめて表示
    for conf in ['A', 'B', 'C', 'D', 'E']:
        conf_data = all_patterns[all_patterns['confidence'] == conf]
        if not conf_data.empty:
            print(f"\n【信頼度{conf}】")
            display_cols = ['pattern', 'race_count', 'hit_count', 'hit_rate',
                           'total_investment', 'total_return', 'net_profit', 'roi']
            print(conf_data[display_cols].to_string(index=False))

    # 全信頼度の集計
    print("\n【全信頼度合計】")
    total_by_pattern = all_patterns.groupby('pattern').agg({
        'race_count': 'sum',
        'hit_count': 'sum',
        'total_investment': 'sum',
        'total_return': 'sum',
        'net_profit': 'sum'
    }).reset_index()
    total_by_pattern['hit_rate'] = (total_by_pattern['hit_count'] / total_by_pattern['race_count'] * 100).round(2)
    total_by_pattern['roi'] = (total_by_pattern['total_return'] / total_by_pattern['total_investment'] * 100).round(2)
    print(total_by_pattern.to_string(index=False))

    # 4. 機会損失の分析
    print("\n" + "=" * 80)
    print("4. 機会損失の定量化")
    print("=" * 80)
    opportunity_loss = analyzer.calculate_opportunity_loss()
    print(opportunity_loss.to_string(index=False))

    # 5. オッズ分布
    print("\n" + "=" * 80)
    print("5. 的中時のオッズ分布（1-2-3的中時）")
    print("=" * 80)
    odds_dist = analyzer.analyze_odds_distribution()
    print(odds_dist.to_string(index=False))

    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)

if __name__ == "__main__":
    main()
