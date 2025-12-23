"""
ST/展示タイム相関検証スクリプト

目的:
- STと実際の着順の点双列相関（point-biserial correlation）を計算
- 展示タイムと着順の相関を計算
- 会場別の相関係数を分析
- スコアリングの符号が正しいかを統計的に検証

使用方法:
    python scripts/verify_st_correlation.py
    python scripts/verify_st_correlation.py --min-races 100  # 最低レース数指定
"""

import sqlite3
import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import sys
from datetime import datetime
import math

# プロジェクトルートをパスに追加
sys.path.append(str(Path(__file__).parent.parent))


class STCorrelationVerifier:
    """ST/展示タイム相関検証クラス"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path

    def point_biserial_correlation(
        self,
        continuous_values: List[float],
        binary_values: List[int]
    ) -> Tuple[float, float, int]:
        """
        点双列相関係数を計算

        Args:
            continuous_values: 連続値（ST、展示タイムなど）
            binary_values: 二値（1=勝利、0=敗北）

        Returns:
            (相関係数, p値, サンプル数)
        """
        if len(continuous_values) != len(binary_values):
            raise ValueError("データ長が一致しません")

        n = len(continuous_values)
        if n < 2:
            return 0.0, 1.0, n

        # グループ分け
        group1_values = [continuous_values[i] for i in range(n) if binary_values[i] == 1]
        group0_values = [continuous_values[i] for i in range(n) if binary_values[i] == 0]

        n1 = len(group1_values)
        n0 = len(group0_values)

        if n1 == 0 or n0 == 0:
            return 0.0, 1.0, n

        # 平均
        mean1 = sum(group1_values) / n1
        mean0 = sum(group0_values) / n0

        # 全体の標準偏差
        overall_mean = sum(continuous_values) / n
        variance = sum((x - overall_mean) ** 2 for x in continuous_values) / n
        std = math.sqrt(variance)

        if std == 0:
            return 0.0, 1.0, n

        # 点双列相関係数
        r_pb = ((mean1 - mean0) / std) * math.sqrt((n1 * n0) / (n * n))

        # 簡易p値計算（t検定による近似）
        if n > 2:
            t_stat = r_pb * math.sqrt((n - 2) / (1 - r_pb ** 2 + 1e-10))
            # 簡易的な有意性判定（|t| > 2 でおおよそp < 0.05）
            p_value = 0.05 if abs(t_stat) < 2 else 0.01
        else:
            p_value = 1.0

        return r_pb, p_value, n

    def collect_st_data(
        self,
        venue_code: Optional[str] = None,
        min_races: int = 50
    ) -> Dict[str, List[Tuple[float, int]]]:
        """
        STデータを収集

        Args:
            venue_code: 会場コード（Noneの場合は全会場）
            min_races: 最低レース数

        Returns:
            {venue_code: [(st_value, is_winner), ...]}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT
                r.venue_code,
                rd.st_time,
                res.rank
            FROM races r
            INNER JOIN race_details rd ON r.id = rd.race_id
            INNER JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
            WHERE rd.st_time IS NOT NULL
              AND rd.st_time > 0
              AND res.rank IS NOT NULL
              AND res.rank != ''
              AND CAST(res.rank AS INTEGER) > 0
        """

        if venue_code:
            query += " AND r.venue_code = ?"
            cursor.execute(query, (venue_code,))
        else:
            cursor.execute(query)

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # 会場別にデータを集約
        venue_data = {}
        for venue, st, rank in rows:
            venue_str = str(venue).zfill(2)
            if venue_str not in venue_data:
                venue_data[venue_str] = []
            # is_winner: 1着=1, それ以外=0
            # rankはTEXT型なので変換
            rank_int = int(rank) if isinstance(rank, str) else rank
            is_winner = 1 if rank_int == 1 else 0
            venue_data[venue_str].append((st, is_winner))

        # 最低レース数のフィルタリング
        venue_data = {
            v: data for v, data in venue_data.items()
            if len(data) >= min_races
        }

        return venue_data

    def collect_exhibition_data(
        self,
        venue_code: Optional[str] = None,
        min_races: int = 50
    ) -> Dict[str, List[Tuple[float, int]]]:
        """
        展示タイムデータを収集

        Args:
            venue_code: 会場コード（Noneの場合は全会場）
            min_races: 最低レース数

        Returns:
            {venue_code: [(exhibition_time, is_winner), ...]}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT
                r.venue_code,
                rd.exhibition_time,
                res.rank
            FROM races r
            INNER JOIN race_details rd ON r.id = rd.race_id
            INNER JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
            WHERE rd.exhibition_time IS NOT NULL
              AND rd.exhibition_time > 0
              AND res.rank IS NOT NULL
              AND res.rank != ''
              AND CAST(res.rank AS INTEGER) > 0
        """

        if venue_code:
            query += " AND r.venue_code = ?"
            cursor.execute(query, (venue_code,))
        else:
            cursor.execute(query)

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # 会場別にデータを集約
        venue_data = {}
        for venue, ex_time, rank in rows:
            venue_str = str(venue).zfill(2)
            if venue_str not in venue_data:
                venue_data[venue_str] = []
            # is_winner: 1着=1, それ以外=0
            # rankはTEXT型なので変換
            rank_int = int(rank) if isinstance(rank, str) else rank
            is_winner = 1 if rank_int == 1 else 0
            venue_data[venue_str].append((ex_time, is_winner))

        # 最低レース数のフィルタリング
        venue_data = {
            v: data for v, data in venue_data.items()
            if len(data) >= min_races
        }

        return venue_data

    def analyze_st_correlation(
        self,
        min_races: int = 100
    ) -> Dict[str, Dict]:
        """
        ST相関を分析

        Args:
            min_races: 最低レース数

        Returns:
            会場別の相関統計
        """
        st_data = self.collect_st_data(min_races=min_races)

        results = {}
        for venue_code, data in st_data.items():
            st_values = [d[0] for d in data]
            is_winner = [d[1] for d in data]

            r_pb, p_value, n = self.point_biserial_correlation(st_values, is_winner)

            # 平均ST（勝者 vs 敗者）
            winner_st = [st_values[i] for i in range(len(st_values)) if is_winner[i] == 1]
            loser_st = [st_values[i] for i in range(len(st_values)) if is_winner[i] == 0]

            results[venue_code] = {
                'correlation': r_pb,
                'p_value': p_value,
                'sample_size': n,
                'winner_mean_st': sum(winner_st) / len(winner_st) if winner_st else 0,
                'loser_mean_st': sum(loser_st) / len(loser_st) if loser_st else 0,
                'sign_interpretation': '負（速いSTが有利）' if r_pb < 0 else '正（遅いSTが有利）'
            }

        return results

    def analyze_exhibition_correlation(
        self,
        min_races: int = 100
    ) -> Dict[str, Dict]:
        """
        展示タイム相関を分析

        Args:
            min_races: 最低レース数

        Returns:
            会場別の相関統計
        """
        ex_data = self.collect_exhibition_data(min_races=min_races)

        results = {}
        for venue_code, data in ex_data.items():
            ex_values = [d[0] for d in data]
            is_winner = [d[1] for d in data]

            r_pb, p_value, n = self.point_biserial_correlation(ex_values, is_winner)

            # 平均展示タイム（勝者 vs 敗者）
            winner_ex = [ex_values[i] for i in range(len(ex_values)) if is_winner[i] == 1]
            loser_ex = [ex_values[i] for i in range(len(ex_values)) if is_winner[i] == 0]

            results[venue_code] = {
                'correlation': r_pb,
                'p_value': p_value,
                'sample_size': n,
                'winner_mean_time': sum(winner_ex) / len(winner_ex) if winner_ex else 0,
                'loser_mean_time': sum(loser_ex) / len(loser_ex) if loser_ex else 0,
                'sign_interpretation': '負（速い展示が有利）' if r_pb < 0 else '正（遅い展示が有利）'
            }

        return results

    def generate_report(
        self,
        st_results: Dict[str, Dict],
        ex_results: Dict[str, Dict]
    ) -> str:
        """
        検証レポートを生成

        Args:
            st_results: ST相関結果
            ex_results: 展示タイム相関結果

        Returns:
            レポート文字列
        """
        # ST相関の全体統計
        st_correlations = [r['correlation'] for r in st_results.values()]
        st_mean_corr = sum(st_correlations) / len(st_correlations) if st_correlations else 0
        st_negative_count = sum(1 for r in st_correlations if r < 0)

        # 展示相関の全体統計
        ex_correlations = [r['correlation'] for r in ex_results.values()]
        ex_mean_corr = sum(ex_correlations) / len(ex_correlations) if ex_correlations else 0
        ex_negative_count = sum(1 for r in ex_correlations if r < 0)

        report = f"""
{'=' * 80}
ST/展示タイム相関検証レポート
{'=' * 80}

検証日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

【ST相関分析】
- 分析会場数: {len(st_results)}会場
- 平均相関係数: {st_mean_corr:.4f}
- 負の相関（速いSTが有利）: {st_negative_count}/{len(st_results)}会場 ({st_negative_count/len(st_results)*100 if st_results else 0:.1f}%)
- 正の相関（遅いSTが有利）: {len(st_results) - st_negative_count}/{len(st_results)}会場

【展示タイム相関分析】
- 分析会場数: {len(ex_results)}会場
- 平均相関係数: {ex_mean_corr:.4f}
- 負の相関（速い展示が有利）: {ex_negative_count}/{len(ex_results)}会場 ({ex_negative_count/len(ex_results)*100 if ex_results else 0:.1f}%)
- 正の相関（遅い展示が有利）: {len(ex_results) - ex_negative_count}/{len(ex_results)}会場

{'=' * 80}

【会場別ST相関係数】

会場 | 相関係数 | サンプル数 | 勝者平均ST | 敗者平均ST | 解釈
-----|---------|-----------|-----------|-----------|-----
"""
        # ST会場別詳細
        for venue, data in sorted(st_results.items()):
            report += f"{venue}   | {data['correlation']:7.4f} | {data['sample_size']:9d} | {data['winner_mean_st']:9.4f} | {data['loser_mean_st']:9.4f} | {data['sign_interpretation']}\n"

        report += f"\n{'=' * 80}\n\n【会場別展示タイム相関係数】\n\n"
        report += "会場 | 相関係数 | サンプル数 | 勝者平均時間 | 敗者平均時間 | 解釈\n"
        report += "-----|---------|-----------|------------|------------|-----\n"

        # 展示会場別詳細
        for venue, data in sorted(ex_results.items()):
            report += f"{venue}   | {data['correlation']:7.4f} | {data['sample_size']:9d} | {data['winner_mean_time']:10.4f} | {data['loser_mean_time']:10.4f} | {data['sign_interpretation']}\n"

        # 結論
        report += f"\n{'=' * 80}\n\n【結論】\n\n"

        # ST符号判定
        if st_mean_corr < 0:
            report += "ST: 負の相関（速いSTが有利） → 現在のスコアリング符号は**正しい**\n"
            report += "     （速いST = 正のスコア、遅いST = 負のスコア）\n"
        else:
            report += "ST: 正の相関（遅いSTが有利） → 現在のスコアリング符号は**逆転している可能性**\n"
            report += "     （速いST = 負のスコア、遅いST = 正のスコアに修正が必要）\n"

        # 展示符号判定
        if ex_mean_corr < 0:
            report += "\n展示: 負の相関（速い展示が有利） → 現在のスコアリング符号は**正しい**\n"
            report += "     （速い展示 = 正のスコア、遅い展示 = 負のスコア）\n"
        else:
            report += "\n展示: 正の相関（遅い展示が有利） → 現在のスコアリング符号は**逆転している可能性**\n"
            report += "     （速い展示 = 負のスコア、遅い展示 = 正のスコアに修正が必要）\n"

        report += f"\n{'=' * 80}\n"

        return report


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description='ST/展示タイム相関検証スクリプト',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--min-races',
        type=int,
        default=100,
        help='会場別の最低レース数（デフォルト: 100）'
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default='data/boatrace.db',
        help='データベースパス（デフォルト: data/boatrace.db）'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("ST/展示タイム相関検証を開始します...")
    print("=" * 80)

    verifier = STCorrelationVerifier(db_path=args.db_path)

    print("\n[1/3] STデータを収集・分析中...")
    st_results = verifier.analyze_st_correlation(min_races=args.min_races)
    print(f"      → {len(st_results)}会場のデータを分析完了")

    print("\n[2/3] 展示タイムデータを収集・分析中...")
    ex_results = verifier.analyze_exhibition_correlation(min_races=args.min_races)
    print(f"      → {len(ex_results)}会場のデータを分析完了")

    print("\n[3/3] レポート生成中...")
    report = verifier.generate_report(st_results, ex_results)
    print(report)

    # JSON形式でも保存
    output_json = {
        'timestamp': datetime.now().isoformat(),
        'min_races': args.min_races,
        'st_correlation': st_results,
        'exhibition_correlation': ex_results
    }

    json_path = Path("temp/diagnosis/st_correlation_report.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output_json, f, ensure_ascii=False, indent=2)

    # テキストレポートも保存
    report_path = Path("temp/diagnosis/st_correlation_report.txt")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\nJSON結果: {json_path}")
    print(f"レポート: {report_path}")
    print("\n検証完了！")


if __name__ == '__main__':
    main()
