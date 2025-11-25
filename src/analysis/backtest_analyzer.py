"""
バックテスト結果の詳細分析ツール

バックテストの結果を多角的に分析し、可視化する
- ROI推移の時系列分析
- 的中率・回収率の詳細分析
- 閾値別パフォーマンス比較
- ドローダウン分析
- 会場別・時期別パフォーマンス
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path


class BacktestAnalyzer:
    """バックテスト結果分析クラス"""

    def __init__(self, results_df: Optional[pd.DataFrame] = None):
        """
        初期化

        Args:
            results_df: バックテスト結果のDataFrame
                必須カラム: race_id, race_date, predicted_prob, actual_result, odds, bet_amount
        """
        self.results_df = results_df
        self.metrics = {}

    def load_results(self, csv_path: str):
        """
        CSV形式のバックテスト結果を読み込み

        Args:
            csv_path: CSVファイルパス
        """
        self.results_df = pd.read_csv(csv_path, parse_dates=['race_date'])
        print(f"[OK] バックテスト結果を読み込み: {len(self.results_df)}件")

    def calculate_basic_metrics(self) -> Dict:
        """
        基本的な評価指標を計算

        Returns:
            Dict: 評価指標
        """
        if self.results_df is None or len(self.results_df) == 0:
            return {}

        df = self.results_df.copy()

        # 総投資額
        total_bet = df['bet_amount'].sum()

        # 総払戻額
        df['return'] = df.apply(
            lambda row: row['bet_amount'] * row['odds'] if row['actual_result'] == 1 else 0,
            axis=1
        )
        total_return = df['return'].sum()

        # ROI（回収率）
        roi = (total_return / total_bet * 100) if total_bet > 0 else 0

        # 的中率
        hit_count = (df['actual_result'] == 1).sum()
        hit_rate = (hit_count / len(df) * 100) if len(df) > 0 else 0

        # 利益
        profit = total_return - total_bet

        # 最大連勝・連敗
        df['win'] = (df['actual_result'] == 1).astype(int)
        win_streaks = df['win'].groupby((df['win'] != df['win'].shift()).cumsum()).cumsum()
        max_win_streak = win_streaks.max() if len(win_streaks) > 0 else 0

        loss_streaks = (1 - df['win']).groupby((df['win'] != df['win'].shift()).cumsum()).cumsum()
        max_loss_streak = loss_streaks.max() if len(loss_streaks) > 0 else 0

        # 平均オッズ
        avg_odds_hit = df.loc[df['actual_result'] == 1, 'odds'].mean() if hit_count > 0 else 0
        avg_odds_all = df['odds'].mean()

        metrics = {
            'total_races': len(df),
            'total_bet': total_bet,
            'total_return': total_return,
            'roi': roi,
            'hit_count': hit_count,
            'hit_rate': hit_rate,
            'profit': profit,
            'max_win_streak': int(max_win_streak),
            'max_loss_streak': int(max_loss_streak),
            'avg_odds_hit': avg_odds_hit,
            'avg_odds_all': avg_odds_all
        }

        self.metrics = metrics
        return metrics

    def calculate_threshold_metrics(self, thresholds: List[float] = None) -> pd.DataFrame:
        """
        閾値別の評価指標を計算

        Args:
            thresholds: 予測確率の閾値リスト

        Returns:
            pd.DataFrame: 閾値別メトリクス
        """
        if thresholds is None:
            thresholds = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]

        if self.results_df is None:
            return pd.DataFrame()

        df = self.results_df.copy()

        results = []

        for threshold in thresholds:
            df_filtered = df[df['predicted_prob'] >= threshold].copy()

            if len(df_filtered) == 0:
                results.append({
                    'threshold': threshold,
                    'race_count': 0,
                    'hit_rate': 0,
                    'roi': 0,
                    'profit': 0,
                    'avg_odds': 0
                })
                continue

            total_bet = df_filtered['bet_amount'].sum()
            df_filtered['return'] = df_filtered.apply(
                lambda row: row['bet_amount'] * row['odds'] if row['actual_result'] == 1 else 0,
                axis=1
            )
            total_return = df_filtered['return'].sum()

            hit_count = (df_filtered['actual_result'] == 1).sum()
            hit_rate = (hit_count / len(df_filtered) * 100)
            roi = (total_return / total_bet * 100) if total_bet > 0 else 0
            profit = total_return - total_bet

            results.append({
                'threshold': threshold,
                'race_count': len(df_filtered),
                'hit_rate': hit_rate,
                'roi': roi,
                'profit': profit,
                'avg_odds': df_filtered['odds'].mean()
            })

        return pd.DataFrame(results)

    def calculate_drawdown(self) -> pd.DataFrame:
        """
        ドローダウンを計算

        Returns:
            pd.DataFrame: 資金推移とドローダウン
        """
        if self.results_df is None:
            return pd.DataFrame()

        df = self.results_df.copy().sort_values('race_date')

        # 各レースの損益
        df['return'] = df.apply(
            lambda row: row['bet_amount'] * row['odds'] if row['actual_result'] == 1 else 0,
            axis=1
        )
        df['profit_loss'] = df['return'] - df['bet_amount']

        # 累積損益
        df['cumulative_profit'] = df['profit_loss'].cumsum()

        # 最大累積利益（それまでのピーク）
        df['peak_profit'] = df['cumulative_profit'].cumsum().expanding().max()

        # ドローダウン（ピークからの下落幅）
        df['drawdown'] = df['peak_profit'] - df['cumulative_profit']

        # ドローダウン率
        df['drawdown_pct'] = (df['drawdown'] / (df['peak_profit'] + 1)) * 100

        return df[['race_date', 'cumulative_profit', 'peak_profit', 'drawdown', 'drawdown_pct']]

    def analyze_by_venue(self) -> pd.DataFrame:
        """
        会場別パフォーマンスを分析

        Returns:
            pd.DataFrame: 会場別メトリクス
        """
        if self.results_df is None or 'venue_code' not in self.results_df.columns:
            return pd.DataFrame()

        df = self.results_df.copy()

        venue_stats = []

        for venue in df['venue_code'].unique():
            df_venue = df[df['venue_code'] == venue].copy()

            total_bet = df_venue['bet_amount'].sum()
            df_venue['return'] = df_venue.apply(
                lambda row: row['bet_amount'] * row['odds'] if row['actual_result'] == 1 else 0,
                axis=1
            )
            total_return = df_venue['return'].sum()

            hit_count = (df_venue['actual_result'] == 1).sum()
            hit_rate = (hit_count / len(df_venue) * 100) if len(df_venue) > 0 else 0
            roi = (total_return / total_bet * 100) if total_bet > 0 else 0

            venue_stats.append({
                'venue_code': venue,
                'race_count': len(df_venue),
                'hit_rate': hit_rate,
                'roi': roi,
                'profit': total_return - total_bet
            })

        return pd.DataFrame(venue_stats).sort_values('roi', ascending=False)

    def analyze_by_month(self) -> pd.DataFrame:
        """
        月別パフォーマンスを分析

        Returns:
            pd.DataFrame: 月別メトリクス
        """
        if self.results_df is None:
            return pd.DataFrame()

        df = self.results_df.copy()
        df['year_month'] = pd.to_datetime(df['race_date']).dt.to_period('M')

        month_stats = []

        for period in df['year_month'].unique():
            df_month = df[df['year_month'] == period].copy()

            total_bet = df_month['bet_amount'].sum()
            df_month['return'] = df_month.apply(
                lambda row: row['bet_amount'] * row['odds'] if row['actual_result'] == 1 else 0,
                axis=1
            )
            total_return = df_month['return'].sum()

            hit_count = (df_month['actual_result'] == 1).sum()
            hit_rate = (hit_count / len(df_month) * 100) if len(df_month) > 0 else 0
            roi = (total_return / total_bet * 100) if total_bet > 0 else 0

            month_stats.append({
                'year_month': str(period),
                'race_count': len(df_month),
                'hit_rate': hit_rate,
                'roi': roi,
                'profit': total_return - total_bet
            })

        return pd.DataFrame(month_stats).sort_values('year_month')

    def plot_cumulative_profit(self, output_path: Optional[str] = None):
        """
        累積利益の推移をプロット

        Args:
            output_path: 保存先パス（Noneの場合は表示のみ）
        """
        if self.results_df is None:
            print("[ERROR] バックテスト結果がありません")
            return

        df = self.results_df.copy().sort_values('race_date')

        df['return'] = df.apply(
            lambda row: row['bet_amount'] * row['odds'] if row['actual_result'] == 1 else 0,
            axis=1
        )
        df['profit_loss'] = df['return'] - df['bet_amount']
        df['cumulative_profit'] = df['profit_loss'].cumsum()

        plt.figure(figsize=(12, 6))
        plt.plot(df['race_date'], df['cumulative_profit'], linewidth=2)
        plt.axhline(y=0, color='r', linestyle='--', alpha=0.5)
        plt.title('累積利益の推移', fontsize=14)
        plt.xlabel('日付', fontsize=12)
        plt.ylabel('累積利益（円）', fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, dpi=300)
            print(f"[OK] グラフを保存: {output_path}")
        else:
            plt.show()

        plt.close()

    def plot_threshold_comparison(self, output_path: Optional[str] = None):
        """
        閾値別のROI比較をプロット

        Args:
            output_path: 保存先パス（Noneの場合は表示のみ）
        """
        threshold_metrics = self.calculate_threshold_metrics()

        if threshold_metrics.empty:
            print("[ERROR] 閾値別メトリクスがありません")
            return

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

        # ROI比較
        ax1.bar(threshold_metrics['threshold'], threshold_metrics['roi'])
        ax1.axhline(y=100, color='r', linestyle='--', alpha=0.5, label='損益分岐点')
        ax1.set_title('閾値別ROI', fontsize=14)
        ax1.set_xlabel('予測確率閾値', fontsize=12)
        ax1.set_ylabel('ROI (%)', fontsize=12)
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # 的中率比較
        ax2.bar(threshold_metrics['threshold'], threshold_metrics['hit_rate'])
        ax2.set_title('閾値別的中率', fontsize=14)
        ax2.set_xlabel('予測確率閾値', fontsize=12)
        ax2.set_ylabel('的中率 (%)', fontsize=12)
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, dpi=300)
            print(f"[OK] グラフを保存: {output_path}")
        else:
            plt.show()

        plt.close()

    def generate_report(self, output_path: str = "backtest_report.txt"):
        """
        詳細レポートをテキスト形式で生成

        Args:
            output_path: レポート保存先パス
        """
        if self.results_df is None:
            print("[ERROR] バックテスト結果がありません")
            return

        # 基本メトリクスを計算
        metrics = self.calculate_basic_metrics()

        # レポート作成
        report = []
        report.append("=" * 70)
        report.append("バックテスト詳細レポート")
        report.append("=" * 70)
        report.append(f"生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        report.append("【基本統計】")
        report.append(f"  総レース数: {metrics['total_races']:,}レース")
        report.append(f"  総投資額: {metrics['total_bet']:,.0f}円")
        report.append(f"  総払戻額: {metrics['total_return']:,.0f}円")
        report.append(f"  利益: {metrics['profit']:+,.0f}円")
        report.append("")

        report.append("【パフォーマンス】")
        report.append(f"  ROI: {metrics['roi']:.2f}%")
        report.append(f"  的中数: {metrics['hit_count']}レース")
        report.append(f"  的中率: {metrics['hit_rate']:.2f}%")
        report.append(f"  最大連勝: {metrics['max_win_streak']}連勝")
        report.append(f"  最大連敗: {metrics['max_loss_streak']}連敗")
        report.append("")

        report.append("【オッズ】")
        report.append(f"  平均オッズ（全体）: {metrics['avg_odds_all']:.2f}倍")
        report.append(f"  平均オッズ（的中）: {metrics['avg_odds_hit']:.2f}倍")
        report.append("")

        # 閾値別メトリクス
        threshold_metrics = self.calculate_threshold_metrics()
        if not threshold_metrics.empty:
            report.append("【閾値別パフォーマンス】")
            report.append(threshold_metrics.to_string(index=False))
            report.append("")

        # 会場別メトリクス
        venue_metrics = self.analyze_by_venue()
        if not venue_metrics.empty:
            report.append("【会場別パフォーマンス（上位10会場）】")
            report.append(venue_metrics.head(10).to_string(index=False))
            report.append("")

        # 月別メトリクス
        month_metrics = self.analyze_by_month()
        if not month_metrics.empty:
            report.append("【月別パフォーマンス】")
            report.append(month_metrics.to_string(index=False))
            report.append("")

        # ドローダウン
        drawdown_df = self.calculate_drawdown()
        if not drawdown_df.empty:
            max_drawdown = drawdown_df['drawdown'].max()
            max_drawdown_pct = drawdown_df['drawdown_pct'].max()
            report.append("【ドローダウン】")
            report.append(f"  最大ドローダウン: {max_drawdown:,.0f}円")
            report.append(f"  最大ドローダウン率: {max_drawdown_pct:.2f}%")
            report.append("")

        report.append("=" * 70)

        # ファイルに保存
        report_text = "\n".join(report)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_text)

        print(f"[OK] レポートを保存: {output_path}")
        print("\n" + report_text)

        return report_text


if __name__ == "__main__":
    # テスト実行
    print("=" * 70)
    print("BacktestAnalyzer テスト")
    print("=" * 70)

    # ダミーデータ作成
    np.random.seed(42)
    n_races = 100

    dummy_data = {
        'race_id': range(1, n_races + 1),
        'race_date': pd.date_range('2024-01-01', periods=n_races, freq='D'),
        'venue_code': np.random.choice(['01', '02', '03', '04', '05'], n_races),
        'predicted_prob': np.random.uniform(0.1, 0.9, n_races),
        'actual_result': np.random.choice([0, 1], n_races, p=[0.8, 0.2]),
        'odds': np.random.uniform(2.0, 10.0, n_races),
        'bet_amount': np.full(n_races, 100)
    }

    df = pd.DataFrame(dummy_data)

    # アナライザー初期化
    analyzer = BacktestAnalyzer(df)

    # 基本メトリクス計算
    print("\n【基本メトリクス】")
    metrics = analyzer.calculate_basic_metrics()
    for key, value in metrics.items():
        print(f"  {key}: {value}")

    # 閾値別メトリクス
    print("\n【閾値別メトリクス】")
    threshold_metrics = analyzer.calculate_threshold_metrics()
    print(threshold_metrics.to_string(index=False))

    # レポート生成
    print("\n【レポート生成】")
    analyzer.generate_report("test_backtest_report.txt")

    print("\n" + "=" * 70)
    print("テスト完了")
    print("=" * 70)
