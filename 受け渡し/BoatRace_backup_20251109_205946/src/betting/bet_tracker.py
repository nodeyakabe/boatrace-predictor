"""
購入実績記録・分析モジュール

実際の購入結果を記録し、ROI、勝率、最大ドローダウンなどを分析する機能を提供。
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta


class BetTracker:
    """
    購入実績の記録・分析クラス

    機能:
    - 購入記録の保存（三連単の組み合わせ、賭け金、オッズなど）
    - 結果の更新（的中/不的中、払戻金額）
    - ROI（投資収益率）の計算
    - 勝率・回収率の集計
    - 最大ドローダウンの追跡
    - 資金推移のグラフデータ生成
    - CSV エクスポート機能
    """

    def __init__(self, db_path: str = "data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースファイルのパス
        """
        self.db_path = db_path
        self._initialize_database()

    def _initialize_database(self):
        """
        bet_history テーブルが存在しない場合は作成
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bet_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bet_date TEXT NOT NULL,
                venue_code TEXT NOT NULL,
                venue_name TEXT,
                race_number INTEGER NOT NULL,
                combination TEXT NOT NULL,
                bet_amount INTEGER NOT NULL,
                odds REAL NOT NULL,
                predicted_prob REAL,
                expected_value REAL,
                buy_score REAL,
                result INTEGER,
                payout INTEGER,
                profit INTEGER,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # インデックスの作成（検索高速化）
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_bet_date ON bet_history(bet_date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_venue_code ON bet_history(venue_code)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_result ON bet_history(result)
        """)

        conn.commit()
        conn.close()

        print("[OK] bet_history テーブル初期化完了")

    def add_bet(self,
                bet_date: str,
                venue_code: str,
                race_number: int,
                combination: str,
                bet_amount: int,
                odds: float,
                venue_name: Optional[str] = None,
                predicted_prob: Optional[float] = None,
                expected_value: Optional[float] = None,
                buy_score: Optional[float] = None,
                notes: Optional[str] = None) -> int:
        """
        購入記録を追加

        Args:
            bet_date: 購入日（YYYY-MM-DD形式）
            venue_code: 会場コード
            race_number: レース番号
            combination: 三連単の組み合わせ（例: "1-2-3"）
            bet_amount: 賭け金額
            odds: オッズ
            venue_name: 会場名（オプション）
            predicted_prob: 予測確率（オプション）
            expected_value: 期待値（オプション）
            buy_score: 購入スコア（オプション）
            notes: メモ（オプション）

        Returns:
            追加されたレコードのID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO bet_history (
                bet_date, venue_code, venue_name, race_number, combination,
                bet_amount, odds, predicted_prob, expected_value, buy_score,
                result, payout, profit, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?)
        """, (
            bet_date, venue_code, venue_name, race_number, combination,
            bet_amount, odds, predicted_prob, expected_value, buy_score, notes
        ))

        bet_id = cursor.lastrowid
        conn.commit()
        conn.close()

        print(f"[OK] 購入記録追加: ID={bet_id}, {bet_date} {venue_name or venue_code} {race_number}R {combination}")
        return bet_id

    def update_result(self, bet_id: int, is_hit: bool, payout: int = 0):
        """
        購入結果を更新

        Args:
            bet_id: 購入記録ID
            is_hit: 的中したかどうか (True=的中, False=不的中)
            payout: 払戻金額（的中時のみ）
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 元の賭け金を取得
        cursor.execute("SELECT bet_amount FROM bet_history WHERE id = ?", (bet_id,))
        row = cursor.fetchone()

        if row is None:
            print(f"[ERROR] ID={bet_id} の購入記録が見つかりません")
            conn.close()
            return

        bet_amount = row[0]
        result = 1 if is_hit else 0
        profit = payout - bet_amount if is_hit else -bet_amount

        cursor.execute("""
            UPDATE bet_history
            SET result = ?, payout = ?, profit = ?
            WHERE id = ?
        """, (result, payout, profit, bet_id))

        conn.commit()
        conn.close()

        status = "的中" if is_hit else "不的中"
        print(f"[OK] 購入結果更新: ID={bet_id}, {status}, 払戻={payout}円, 利益={profit}円")

    def bulk_update_results(self, results: List[Tuple[int, bool, int]]):
        """
        複数の購入結果を一括更新

        Args:
            results: [(bet_id, is_hit, payout), ...] のリスト
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for bet_id, is_hit, payout in results:
            cursor.execute("SELECT bet_amount FROM bet_history WHERE id = ?", (bet_id,))
            row = cursor.fetchone()

            if row is None:
                continue

            bet_amount = row[0]
            result = 1 if is_hit else 0
            profit = payout - bet_amount if is_hit else -bet_amount

            cursor.execute("""
                UPDATE bet_history
                SET result = ?, payout = ?, profit = ?
                WHERE id = ?
            """, (result, payout, profit, bet_id))

        conn.commit()
        conn.close()
        print(f"[OK] {len(results)}件の購入結果を一括更新しました")

    def get_bet_history(self,
                       start_date: Optional[str] = None,
                       end_date: Optional[str] = None,
                       venue_code: Optional[str] = None,
                       result_only: Optional[bool] = None) -> pd.DataFrame:
        """
        購入履歴を取得

        Args:
            start_date: 開始日（YYYY-MM-DD形式）
            end_date: 終了日（YYYY-MM-DD形式）
            venue_code: 会場コードでフィルタ
            result_only: True=結果確定済みのみ, False=未確定のみ, None=全て

        Returns:
            購入履歴のDataFrame
        """
        conn = sqlite3.connect(self.db_path)

        query = "SELECT * FROM bet_history WHERE 1=1"
        params = []

        if start_date:
            query += " AND bet_date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND bet_date <= ?"
            params.append(end_date)

        if venue_code:
            query += " AND venue_code = ?"
            params.append(venue_code)

        if result_only is not None:
            if result_only:
                query += " AND result IS NOT NULL"
            else:
                query += " AND result IS NULL"

        query += " ORDER BY bet_date DESC, race_number DESC"

        df = pd.read_sql_query(query, conn, params=params if params else None)
        conn.close()

        return df

    def calculate_statistics(self,
                            start_date: Optional[str] = None,
                            end_date: Optional[str] = None) -> Dict:
        """
        統計情報を計算

        Args:
            start_date: 開始日（YYYY-MM-DD形式）
            end_date: 終了日（YYYY-MM-DD形式）

        Returns:
            統計情報の辞書:
                - total_bets: 総購入数
                - total_investment: 総投資額
                - total_payout: 総払戻額
                - total_profit: 総利益
                - roi: ROI（投資収益率）%
                - win_rate: 勝率 %
                - recovery_rate: 回収率 %
                - avg_odds: 平均オッズ
                - avg_profit_per_bet: 1回あたり平均利益
                - max_profit: 最大利益
                - max_loss: 最大損失
                - max_drawdown: 最大ドローダウン
        """
        df = self.get_bet_history(start_date=start_date, end_date=end_date, result_only=True)

        if df.empty:
            return {
                'total_bets': 0,
                'total_investment': 0,
                'total_payout': 0,
                'total_profit': 0,
                'roi': 0.0,
                'win_rate': 0.0,
                'recovery_rate': 0.0,
                'avg_odds': 0.0,
                'avg_profit_per_bet': 0.0,
                'max_profit': 0,
                'max_loss': 0,
                'max_drawdown': 0.0
            }

        total_bets = len(df)
        total_investment = df['bet_amount'].sum()
        total_payout = df['payout'].sum()
        total_profit = df['profit'].sum()

        # ROI（投資収益率）
        roi = (total_profit / total_investment * 100) if total_investment > 0 else 0.0

        # 勝率
        win_count = df[df['result'] == 1].shape[0]
        win_rate = (win_count / total_bets * 100) if total_bets > 0 else 0.0

        # 回収率
        recovery_rate = (total_payout / total_investment * 100) if total_investment > 0 else 0.0

        # 平均オッズ
        avg_odds = df['odds'].mean()

        # 1回あたり平均利益
        avg_profit_per_bet = total_profit / total_bets if total_bets > 0 else 0.0

        # 最大利益・最大損失
        max_profit = df['profit'].max()
        max_loss = df['profit'].min()

        # 最大ドローダウンの計算
        df_sorted = df.sort_values('created_at')
        cumulative_profit = df_sorted['profit'].cumsum()
        running_max = cumulative_profit.cummax()
        drawdown = running_max - cumulative_profit
        max_drawdown = drawdown.max()

        return {
            'total_bets': total_bets,
            'total_investment': int(total_investment),
            'total_payout': int(total_payout),
            'total_profit': int(total_profit),
            'roi': float(roi),
            'win_rate': float(win_rate),
            'recovery_rate': float(recovery_rate),
            'avg_odds': float(avg_odds),
            'avg_profit_per_bet': float(avg_profit_per_bet),
            'max_profit': int(max_profit),
            'max_loss': int(max_loss),
            'max_drawdown': float(max_drawdown)
        }

    def get_fund_transition(self,
                           start_date: Optional[str] = None,
                           end_date: Optional[str] = None,
                           initial_fund: int = 100000) -> pd.DataFrame:
        """
        資金推移データを取得

        Args:
            start_date: 開始日
            end_date: 終了日
            initial_fund: 初期資金

        Returns:
            資金推移DataFrame (columns: date, cumulative_profit, fund_balance)
        """
        df = self.get_bet_history(start_date=start_date, end_date=end_date, result_only=True)

        if df.empty:
            return pd.DataFrame(columns=['date', 'cumulative_profit', 'fund_balance'])

        df_sorted = df.sort_values('created_at')
        df_sorted['cumulative_profit'] = df_sorted['profit'].cumsum()
        df_sorted['fund_balance'] = initial_fund + df_sorted['cumulative_profit']

        # 日付ごとに集計
        result = df_sorted.groupby('bet_date').agg({
            'cumulative_profit': 'last',
            'fund_balance': 'last'
        }).reset_index()
        result.columns = ['date', 'cumulative_profit', 'fund_balance']

        return result

    def get_venue_statistics(self,
                            start_date: Optional[str] = None,
                            end_date: Optional[str] = None) -> pd.DataFrame:
        """
        会場別統計を取得

        Args:
            start_date: 開始日
            end_date: 終了日

        Returns:
            会場別統計DataFrame
        """
        df = self.get_bet_history(start_date=start_date, end_date=end_date, result_only=True)

        if df.empty:
            return pd.DataFrame()

        venue_stats = df.groupby('venue_name').agg({
            'id': 'count',
            'bet_amount': 'sum',
            'payout': 'sum',
            'profit': 'sum',
            'result': 'sum',
            'odds': 'mean'
        }).reset_index()

        venue_stats.columns = ['venue_name', 'total_bets', 'total_investment',
                               'total_payout', 'total_profit', 'wins', 'avg_odds']

        venue_stats['win_rate'] = (venue_stats['wins'] / venue_stats['total_bets'] * 100).round(2)
        venue_stats['roi'] = (venue_stats['total_profit'] / venue_stats['total_investment'] * 100).round(2)
        venue_stats['recovery_rate'] = (venue_stats['total_payout'] / venue_stats['total_investment'] * 100).round(2)

        return venue_stats.sort_values('roi', ascending=False)

    def export_to_csv(self,
                     file_path: str,
                     start_date: Optional[str] = None,
                     end_date: Optional[str] = None):
        """
        購入履歴をCSVファイルにエクスポート

        Args:
            file_path: 出力ファイルパス
            start_date: 開始日
            end_date: 終了日
        """
        df = self.get_bet_history(start_date=start_date, end_date=end_date)

        if df.empty:
            print("[WARNING] エクスポートするデータがありません")
            return

        df.to_csv(file_path, index=False, encoding='utf-8-sig')
        print(f"[OK] {len(df)}件の購入履歴を {file_path} にエクスポートしました")

    def delete_bet(self, bet_id: int):
        """
        購入記録を削除

        Args:
            bet_id: 削除する購入記録のID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM bet_history WHERE id = ?", (bet_id,))

        if cursor.rowcount == 0:
            print(f"[ERROR] ID={bet_id} の購入記録が見つかりません")
        else:
            print(f"[OK] ID={bet_id} の購入記録を削除しました")

        conn.commit()
        conn.close()


# テスト用コード
if __name__ == "__main__":
    print("=== BetTracker テスト ===\n")

    # トラッカー初期化
    tracker = BetTracker()

    # サンプルデータ追加
    print("【サンプルデータ追加】")
    bet_id_1 = tracker.add_bet(
        bet_date="2025-11-01",
        venue_code="06",
        venue_name="浜名湖",
        race_number=1,
        combination="1-2-3",
        bet_amount=1000,
        odds=15.5,
        predicted_prob=0.10,
        expected_value=1.55,
        buy_score=0.75
    )

    bet_id_2 = tracker.add_bet(
        bet_date="2025-11-01",
        venue_code="06",
        venue_name="浜名湖",
        race_number=2,
        combination="3-1-4",
        bet_amount=1000,
        odds=25.0,
        predicted_prob=0.06,
        expected_value=1.50,
        buy_score=0.72
    )

    bet_id_3 = tracker.add_bet(
        bet_date="2025-11-02",
        venue_code="12",
        venue_name="住之江",
        race_number=5,
        combination="2-4-1",
        bet_amount=1500,
        odds=8.5,
        predicted_prob=0.15,
        expected_value=1.28,
        buy_score=0.68
    )

    print("\n【結果更新】")
    tracker.update_result(bet_id_1, is_hit=True, payout=15500)  # 的中
    tracker.update_result(bet_id_2, is_hit=False, payout=0)      # 不的中
    tracker.update_result(bet_id_3, is_hit=True, payout=12750)   # 的中

    print("\n【統計情報】")
    stats = tracker.calculate_statistics()
    print(f"総購入数: {stats['total_bets']}回")
    print(f"総投資額: {stats['total_investment']:,}円")
    print(f"総払戻額: {stats['total_payout']:,}円")
    print(f"総利益: {stats['total_profit']:,}円")
    print(f"ROI: {stats['roi']:.2f}%")
    print(f"勝率: {stats['win_rate']:.2f}%")
    print(f"回収率: {stats['recovery_rate']:.2f}%")
    print(f"最大ドローダウン: {stats['max_drawdown']:,.0f}円")

    print("\n【資金推移】")
    fund_df = tracker.get_fund_transition(initial_fund=100000)
    print(fund_df)

    print("\n【会場別統計】")
    venue_stats = tracker.get_venue_statistics()
    print(venue_stats[['venue_name', 'total_bets', 'win_rate', 'roi', 'recovery_rate']])

    print("\nテスト完了！")
