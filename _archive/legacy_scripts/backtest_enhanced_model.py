"""
強化版モデルのバックテスト
Phase 7: 高精度モデルの評価

評価指標:
- 三連単TOP1的中率
- 三連単TOP10的中率
- リフト値（市場との差）
- 平均オッズ
- ROI（回収率）
- カバレッジ
"""
import os
import sys
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import json

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.tricast_engine.tricast_generator import EnhancedTrifectaGenerator
from src.tricast_engine.top_n_selector import TopNSelector


class EnhancedBacktester:
    """
    強化版バックテスタークラス

    高精度モデルの性能を評価
    """

    def __init__(self, db_path: str, model_dir: str = 'models'):
        self.db_path = db_path
        self.model_dir = model_dir
        self.generator = None
        self.selector = TopNSelector()

        self.results = []
        self.metrics = {}

    def initialize(self) -> None:
        """初期化"""
        print("バックテスター初期化中...")
        self.generator = EnhancedTrifectaGenerator(self.model_dir, self.db_path)
        self.generator.initialize()
        print("初期化完了")

    def load_test_races(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        テスト用レースデータを読み込み

        Args:
            start_date: 開始日
            end_date: 終了日

        Returns:
            レースデータ
        """
        conn = sqlite3.connect(self.db_path)

        query = """
            SELECT
                r.id as race_id,
                r.venue_code,
                r.race_date,
                r.race_number,
                e.pit_number,
                e.racer_number,
                e.racer_rank,
                e.motor_number,
                e.win_rate,
                e.second_rate,
                e.third_rate,
                rd.exhibition_time,
                rd.st_time,
                rd.actual_course,
                res.rank as result_rank,
                res.trifecta_odds
            FROM races r
            JOIN entries e ON r.id = e.race_id
            LEFT JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
            LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
            WHERE r.race_date BETWEEN ? AND ?
              AND res.rank IS NOT NULL
            ORDER BY r.race_date, r.race_number, e.pit_number
        """

        df = pd.read_sql_query(query, conn, params=(start_date, end_date))
        conn.close()

        print(f"テストデータ読み込み: {len(df):,}件, {df['race_id'].nunique():,}レース")

        return df

    def run_backtest(self, df: pd.DataFrame,
                     top_n_list: List[int] = [1, 3, 5, 10]) -> Dict:
        """
        バックテストを実行

        Args:
            df: テストデータ
            top_n_list: 評価するTOP N

        Returns:
            評価結果
        """
        if self.generator is None:
            self.initialize()

        race_groups = df.groupby('race_id')
        total_races = len(race_groups)

        print(f"\n=== バックテスト開始 ({total_races:,}レース) ===")

        # 結果集計用
        hits = {n: 0 for n in top_n_list}
        total_bets = {n: 0 for n in top_n_list}
        returns = {n: 0.0 for n in top_n_list}
        processed = 0

        for race_id, group in race_groups:
            if len(group) != 6:
                continue

            # レース情報
            venue_code = group['venue_code'].iloc[0]
            race_date = group['race_date'].iloc[0]

            # 実際の着順を取得
            actual_result = self._get_actual_trifecta(group)
            if actual_result is None:
                continue

            actual_combo, actual_odds = actual_result

            # 予測を生成
            try:
                prediction = self.generator.generate(
                    race_features=group.reset_index(drop=True),
                    venue_code=venue_code,
                    race_date=race_date,
                )

                if 'error' in prediction:
                    continue

                trifecta_probs = prediction.get('trifecta_probs', {})

                # TOP N 評価
                for n in top_n_list:
                    top_combos = [combo for combo, _ in self.selector.select_top_n(trifecta_probs, n)]

                    if actual_combo in top_combos:
                        hits[n] += 1
                        if actual_odds:
                            returns[n] += actual_odds

                    total_bets[n] += 1

            except Exception as e:
                print(f"予測エラー (race_id={race_id}): {e}")
                continue

            processed += 1
            if processed % 500 == 0:
                print(f"進捗: {processed}/{total_races} ({100*processed/total_races:.1f}%)")

        # 結果を集計
        results = {}
        for n in top_n_list:
            if total_bets[n] > 0:
                hit_rate = hits[n] / total_bets[n]
                roi = returns[n] / total_bets[n] if total_bets[n] > 0 else 0

                results[f'top{n}'] = {
                    'hits': hits[n],
                    'total': total_bets[n],
                    'hit_rate': hit_rate,
                    'total_return': returns[n],
                    'roi': roi,
                }

                print(f"\nTOP{n}:")
                print(f"  的中率: {100*hit_rate:.2f}% ({hits[n]}/{total_bets[n]})")
                print(f"  回収率: {100*roi:.2f}%")

        self.metrics = results
        return results

    def _get_actual_trifecta(self, group: pd.DataFrame) -> Optional[Tuple[str, float]]:
        """実際の三連単結果を取得"""
        try:
            first = group[group['result_rank'] == '1']['pit_number'].iloc[0]
            second = group[group['result_rank'] == '2']['pit_number'].iloc[0]
            third = group[group['result_rank'] == '3']['pit_number'].iloc[0]

            combo = f"{first}-{second}-{third}"

            # オッズ（1着艇のtrifecta_oddsを使用）
            odds_row = group[group['result_rank'] == '1']
            odds = odds_row['trifecta_odds'].iloc[0] if len(odds_row) > 0 else None

            return combo, odds

        except (IndexError, KeyError, ValueError):
            return None

    def compare_with_baseline(self, df: pd.DataFrame) -> Dict:
        """
        ベースラインモデルと比較

        Args:
            df: テストデータ

        Returns:
            比較結果
        """
        print("\n=== ベースライン比較 ===")

        # 強化モデルの結果（既に計算済みの場合）
        enhanced_results = self.metrics

        # ベースライン: 勝率ベースの単純予測
        baseline_hits = {'top1': 0, 'top10': 0}
        baseline_total = 0

        race_groups = df.groupby('race_id')

        for race_id, group in race_groups:
            if len(group) != 6:
                continue

            actual_result = self._get_actual_trifecta(group)
            if actual_result is None:
                continue

            actual_combo, _ = actual_result

            # ベースライン予測: 勝率順
            group_sorted = group.sort_values('win_rate', ascending=False)
            pits = group_sorted['pit_number'].values

            baseline_top1 = f"{pits[0]}-{pits[1]}-{pits[2]}"

            # TOP10は勝率上位3艇の全組み合わせ
            from itertools import permutations
            top3_perms = list(permutations(pits[:3], 3))
            baseline_top10 = [f"{p[0]}-{p[1]}-{p[2]}" for p in top3_perms]

            if actual_combo == baseline_top1:
                baseline_hits['top1'] += 1

            if actual_combo in baseline_top10:
                baseline_hits['top10'] += 1

            baseline_total += 1

        # 比較結果
        comparison = {
            'baseline': {
                'top1_rate': baseline_hits['top1'] / baseline_total if baseline_total > 0 else 0,
                'top10_rate': baseline_hits['top10'] / baseline_total if baseline_total > 0 else 0,
            },
            'enhanced': {
                'top1_rate': enhanced_results.get('top1', {}).get('hit_rate', 0),
                'top10_rate': enhanced_results.get('top10', {}).get('hit_rate', 0),
            },
        }

        # 改善率
        if comparison['baseline']['top1_rate'] > 0:
            comparison['improvement_top1'] = (
                comparison['enhanced']['top1_rate'] - comparison['baseline']['top1_rate']
            ) / comparison['baseline']['top1_rate']
        else:
            comparison['improvement_top1'] = 0

        if comparison['baseline']['top10_rate'] > 0:
            comparison['improvement_top10'] = (
                comparison['enhanced']['top10_rate'] - comparison['baseline']['top10_rate']
            ) / comparison['baseline']['top10_rate']
        else:
            comparison['improvement_top10'] = 0

        print(f"\nベースライン (勝率順):")
        print(f"  TOP1的中率: {100*comparison['baseline']['top1_rate']:.2f}%")
        print(f"  TOP10的中率: {100*comparison['baseline']['top10_rate']:.2f}%")

        print(f"\n強化モデル:")
        print(f"  TOP1的中率: {100*comparison['enhanced']['top1_rate']:.2f}%")
        print(f"  TOP10的中率: {100*comparison['enhanced']['top10_rate']:.2f}%")

        print(f"\n改善率:")
        print(f"  TOP1: {100*comparison['improvement_top1']:+.1f}%")
        print(f"  TOP10: {100*comparison['improvement_top10']:+.1f}%")

        return comparison

    def analyze_by_venue(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        会場別の性能分析

        Args:
            df: テストデータ

        Returns:
            会場別結果DataFrame
        """
        print("\n=== 会場別分析 ===")

        venue_results = {}

        for venue_code in df['venue_code'].unique():
            venue_df = df[df['venue_code'] == venue_code]

            # この会場のバックテスト
            hits = 0
            total = 0

            race_groups = venue_df.groupby('race_id')

            for race_id, group in race_groups:
                if len(group) != 6:
                    continue

                actual_result = self._get_actual_trifecta(group)
                if actual_result is None:
                    continue

                actual_combo, _ = actual_result

                try:
                    prediction = self.generator.generate(
                        race_features=group.reset_index(drop=True),
                        venue_code=venue_code,
                        race_date=group['race_date'].iloc[0],
                    )

                    if 'error' in prediction:
                        continue

                    trifecta_probs = prediction.get('trifecta_probs', {})
                    top1 = list(self.selector.select_top_n(trifecta_probs, 1))

                    if top1 and actual_combo == top1[0][0]:
                        hits += 1

                    total += 1

                except Exception:
                    continue

            if total > 0:
                venue_results[venue_code] = {
                    'total': total,
                    'hits': hits,
                    'hit_rate': hits / total,
                }

        # DataFrameに変換
        result_df = pd.DataFrame.from_dict(venue_results, orient='index')
        result_df = result_df.sort_values('hit_rate', ascending=False)

        print(result_df.to_string())

        return result_df

    def save_results(self, output_path: str = None) -> None:
        """結果を保存"""
        if output_path is None:
            output_path = os.path.join(PROJECT_ROOT, 'temp', 'backtest_results.json')

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        results = {
            'timestamp': datetime.now().isoformat(),
            'metrics': self.metrics,
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"\n結果保存: {output_path}")


def main():
    """メイン実行"""
    import argparse

    parser = argparse.ArgumentParser(description='強化版モデルのバックテスト')
    parser.add_argument('--db', default='data/boatrace.db', help='DBパス')
    parser.add_argument('--start-date', default='2024-10-01', help='開始日')
    parser.add_argument('--end-date', default='2024-11-30', help='終了日')
    parser.add_argument('--model-dir', default='models', help='モデルディレクトリ')

    args = parser.parse_args()

    backtester = EnhancedBacktester(args.db, args.model_dir)

    # テストデータ読み込み
    df = backtester.load_test_races(args.start_date, args.end_date)

    if len(df) == 0:
        print("テストデータがありません")
        return

    # バックテスト実行
    results = backtester.run_backtest(df)

    # ベースライン比較
    comparison = backtester.compare_with_baseline(df)

    # 結果保存
    backtester.save_results()

    print("\n=== バックテスト完了 ===")


if __name__ == '__main__':
    main()
