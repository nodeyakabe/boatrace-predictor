"""
進入変更効果分析スクリプト

目的:
- 進入変更が実際に予測を改善したかを分析
- 会場別の進入変更率を確認
- changed_races.csvを生成

使用方法:
    python scripts/analyze_changed_races.py
    python scripts/analyze_changed_races.py --min-races 100  # 最低レース数指定
"""

import sqlite3
import csv
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import sys
from datetime import datetime

# プロジェクトルートをパスに追加
sys.path.append(str(Path(__file__).parent.parent))


class ChangedRacesAnalyzer:
    """進入変更分析クラス"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path

    def collect_entry_change_data(self) -> List[Dict]:
        """
        進入変更データを収集

        Returns:
            進入変更データのリスト
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT
                r.id as race_id,
                r.race_date,
                r.venue_code,
                r.race_number,
                rd.pit_number,
                rd.actual_course,
                res.rank
            FROM races r
            INNER JOIN race_details rd ON r.id = rd.race_id
            INNER JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
            WHERE rd.actual_course IS NOT NULL
              AND rd.actual_course > 0
              AND res.rank IS NOT NULL
              AND res.rank != ''
        """

        cursor.execute(query)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # データを辞書リストに変換
        data_list = []
        for row in rows:
            race_id, race_date, venue_code, race_number, pit_number, actual_course, rank = row

            # 進入変更判定（pit_number != actual_course）
            is_changed = 1 if pit_number != actual_course else 0

            # rankをint型に変換
            rank_int = int(rank) if isinstance(rank, str) else rank

            data_list.append({
                'race_id': race_id,
                'race_date': race_date,
                'venue_code': str(venue_code).zfill(2),
                'race_number': race_number,
                'pit_number': pit_number,
                'actual_course': actual_course,
                'rank': rank_int,
                'is_changed': is_changed
            })

        return data_list

    def analyze_entry_changes(self, data: List[Dict]) -> Dict:
        """
        進入変更を分析

        Args:
            data: 進入変更データのリスト

        Returns:
            分析結果の辞書
        """
        total_entries = len(data)
        changed_entries = sum(1 for d in data if d['is_changed'] == 1)
        unchanged_entries = total_entries - changed_entries

        # 進入変更ありの勝率
        changed_wins = sum(1 for d in data if d['is_changed'] == 1 and d['rank'] == 1)
        changed_win_rate = (changed_wins / changed_entries * 100) if changed_entries > 0 else 0

        # 進入変更なしの勝率
        unchanged_wins = sum(1 for d in data if d['is_changed'] == 0 and d['rank'] == 1)
        unchanged_win_rate = (unchanged_wins / unchanged_entries * 100) if unchanged_entries > 0 else 0

        # 会場別進入変更率
        venue_stats = {}
        for d in data:
            venue = d['venue_code']
            if venue not in venue_stats:
                venue_stats[venue] = {'total': 0, 'changed': 0, 'changed_wins': 0, 'unchanged_wins': 0}

            venue_stats[venue]['total'] += 1
            if d['is_changed'] == 1:
                venue_stats[venue]['changed'] += 1
                if d['rank'] == 1:
                    venue_stats[venue]['changed_wins'] += 1
            else:
                if d['rank'] == 1:
                    venue_stats[venue]['unchanged_wins'] += 1

        # 会場別の変更率を計算
        for venue in venue_stats:
            total = venue_stats[venue]['total']
            changed = venue_stats[venue]['changed']
            venue_stats[venue]['change_rate'] = (changed / total * 100) if total > 0 else 0

            # 変更あり勝率
            changed_win_rate_venue = (venue_stats[venue]['changed_wins'] / changed * 100) if changed > 0 else 0
            venue_stats[venue]['changed_win_rate'] = changed_win_rate_venue

            # 変更なし勝率
            unchanged = total - changed
            unchanged_win_rate_venue = (venue_stats[venue]['unchanged_wins'] / unchanged * 100) if unchanged > 0 else 0
            venue_stats[venue]['unchanged_win_rate'] = unchanged_win_rate_venue

        return {
            'total_entries': total_entries,
            'changed_entries': changed_entries,
            'unchanged_entries': unchanged_entries,
            'overall_change_rate': (changed_entries / total_entries * 100) if total_entries > 0 else 0,
            'changed_win_rate': changed_win_rate,
            'unchanged_win_rate': unchanged_win_rate,
            'venue_stats': venue_stats
        }

    def save_changed_races_csv(self, data: List[Dict]) -> str:
        """
        changed_races.csvを保存

        Args:
            data: 進入変更データのリスト

        Returns:
            保存したファイルパス
        """
        # 進入変更があったレースのみを抽出
        changed_data = [d for d in data if d['is_changed'] == 1]

        output_path = Path("data/changed_races.csv")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            if changed_data:
                writer = csv.DictWriter(f, fieldnames=changed_data[0].keys())
                writer.writeheader()
                writer.writerows(changed_data)
            else:
                # データがない場合はヘッダーのみ
                writer = csv.DictWriter(f, fieldnames=[
                    'race_id', 'race_date', 'venue_code', 'race_number',
                    'pit_number', 'actual_course', 'rank', 'is_changed'
                ])
                writer.writeheader()

        return str(output_path)

    def generate_report(self, analysis: Dict) -> str:
        """
        分析レポートを生成

        Args:
            analysis: 分析結果の辞書

        Returns:
            レポート文字列
        """
        venue_stats = analysis['venue_stats']

        report = f"""
{'=' * 80}
進入変更効果分析レポート
{'=' * 80}

分析日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

【全体統計】
- 総エントリー数: {analysis['total_entries']:,}件
- 進入変更あり: {analysis['changed_entries']:,}件 ({analysis['overall_change_rate']:.2f}%)
- 進入変更なし（枠なり）: {analysis['unchanged_entries']:,}件 ({100 - analysis['overall_change_rate']:.2f}%)

【勝率比較】
- 進入変更あり勝率: {analysis['changed_win_rate']:.2f}%
- 進入変更なし勝率: {analysis['unchanged_win_rate']:.2f}%
- 差分: {analysis['changed_win_rate'] - analysis['unchanged_win_rate']:+.2f}ポイント

{'=' * 80}

【会場別進入変更率】

会場 | 総エントリー | 変更数 | 変更率 | 変更あり勝率 | 変更なし勝率 | 差分
-----|------------|--------|--------|------------|------------|------
"""
        for venue, stats in sorted(venue_stats.items()):
            diff = stats['changed_win_rate'] - stats['unchanged_win_rate']
            report += f"{venue}   | {stats['total']:10d} | {stats['changed']:6d} | {stats['change_rate']:5.1f}% | {stats['changed_win_rate']:10.2f}% | {stats['unchanged_win_rate']:10.2f}% | {diff:+6.2f}\n"

        # 変更率の高い会場トップ5
        top5_change = sorted(venue_stats.items(), key=lambda x: x[1]['change_rate'], reverse=True)[:5]
        report += f"\n{'=' * 80}\n\n【進入変更率が高い会場トップ5】\n\n"
        for i, (venue, stats) in enumerate(top5_change, 1):
            report += f"{i}. 会場{venue}: {stats['change_rate']:.2f}% ({stats['changed']}/{stats['total']}件)\n"

        # 変更による勝率向上が大きい会場トップ5
        top5_improvement = sorted(
            venue_stats.items(),
            key=lambda x: x[1]['changed_win_rate'] - x[1]['unchanged_win_rate'],
            reverse=True
        )[:5]
        report += f"\n【進入変更による勝率向上が大きい会場トップ5】\n\n"
        for i, (venue, stats) in enumerate(top5_improvement, 1):
            diff = stats['changed_win_rate'] - stats['unchanged_win_rate']
            report += f"{i}. 会場{venue}: {diff:+.2f}ポイント (変更あり{stats['changed_win_rate']:.2f}% vs 変更なし{stats['unchanged_win_rate']:.2f}%)\n"

        report += f"\n{'=' * 80}\n\n【結論】\n\n"

        if analysis['changed_win_rate'] > analysis['unchanged_win_rate']:
            report += f"進入変更は予測改善に**寄与している**（+{analysis['changed_win_rate'] - analysis['unchanged_win_rate']:.2f}ポイント）\n"
            report += "BEFORE_SAFEの進入スコアは有効と判断されます。\n"
        else:
            report += f"進入変更は予測改善に**寄与していない**（{analysis['changed_win_rate'] - analysis['unchanged_win_rate']:.2f}ポイント）\n"
            report += "BEFORE_SAFEの進入スコアの見直しが必要です。\n"

        report += f"\n全体の進入変更率{analysis['overall_change_rate']:.2f}%は"
        if analysis['overall_change_rate'] >= 10:
            report += "十分なサンプル数があり、統計的に意味があります。\n"
        else:
            report += f"かなり低く（目安10%）、データ不足の可能性があります。\n"

        report += f"\n{'=' * 80}\n"

        return report


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description='進入変更効果分析スクリプト',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--db-path',
        type=str,
        default='data/boatrace.db',
        help='データベースパス（デフォルト: data/boatrace.db）'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("進入変更効果分析を開始します...")
    print("=" * 80)

    analyzer = ChangedRacesAnalyzer(db_path=args.db_path)

    print("\n[1/4] 進入変更データを収集中...")
    data = analyzer.collect_entry_change_data()
    print(f"      → {len(data):,}件のエントリーデータを取得")

    print("\n[2/4] 進入変更を分析中...")
    analysis = analyzer.analyze_entry_changes(data)
    print(f"      → 進入変更率: {analysis['overall_change_rate']:.2f}%")

    print("\n[3/4] changed_races.csvを保存中...")
    csv_path = analyzer.save_changed_races_csv(data)
    print(f"      → {csv_path} に保存完了（{analysis['changed_entries']:,}件）")

    print("\n[4/4] レポート生成中...")
    report = analyzer.generate_report(analysis)
    print(report)

    # レポートファイルも保存
    report_path = Path("temp/diagnosis/changed_races_analysis.txt")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"レポートを {report_path} に保存しました。")
    print("\n分析完了！")


if __name__ == '__main__':
    main()
