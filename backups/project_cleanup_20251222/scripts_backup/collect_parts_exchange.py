"""
部品交換データ収集スクリプト

目的:
- レース詳細から部品交換情報を収集
- CSVファイルに保存（data/parts_exchange.csv）
- 収集状況をレポート出力

使用方法:
    python scripts/collect_parts_exchange.py
    python scripts/collect_parts_exchange.py --limit 1000  # 収集件数指定
    python scripts/collect_parts_exchange.py --start-date 2024-12-01  # 開始日指定
"""

import sqlite3
import csv
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import sys

# プロジェクトルートをパスに追加
sys.path.append(str(Path(__file__).parent.parent))


class PartsExchangeCollector:
    """部品交換データ収集クラス"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path
        self.output_csv = "data/parts_exchange.csv"

    def collect_parts_data(
        self,
        limit: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict]:
        """
        部品交換データを収集

        Args:
            limit: 収集件数上限（Noneの場合は全件）
            start_date: 開始日（YYYY-MM-DD形式）
            end_date: 終了日（YYYY-MM-DD形式）

        Returns:
            収集データのリスト
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # クエリ構築
        query = """
            SELECT
                r.id as race_id,
                r.race_date,
                r.venue_code,
                r.race_number,
                rd.pit_number,
                rd.parts_replacement,
                rd.adjusted_weight
            FROM races r
            INNER JOIN race_details rd ON r.id = rd.race_id
            WHERE 1=1
        """
        params = []

        if start_date:
            query += " AND r.race_date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND r.race_date <= ?"
            params.append(end_date)

        query += " ORDER BY r.race_date DESC, r.id DESC, rd.pit_number"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # データを辞書リストに変換
        collected_data = []
        for row in rows:
            parts = row['parts_replacement'] or ''
            # parts_replacementフィールドをパース（例: "プロペラ", "ボート", "プロペラ,ボート"）
            has_parts = 1 if parts and parts.strip() else 0

            collected_data.append({
                'race_id': row['race_id'],
                'race_date': row['race_date'],
                'venue_code': row['venue_code'],
                'race_number': row['race_number'],
                'pit_number': row['pit_number'],
                'parts_replacement': parts,
                'adjusted_weight': row['adjusted_weight'] if row['adjusted_weight'] else 0.0,
                'has_parts_exchange': has_parts
            })

        cursor.close()
        conn.close()

        return collected_data

    def save_to_csv(self, data: List[Dict]) -> str:
        """
        収集データをCSVに保存

        Args:
            data: 収集データのリスト

        Returns:
            保存したファイルパス
        """
        # 出力ディレクトリ作成
        output_path = Path(self.output_csv)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # CSV書き込み
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            if not data:
                # データがない場合はヘッダーのみ
                writer = csv.DictWriter(f, fieldnames=[
                    'race_id', 'race_date', 'venue_code', 'race_number', 'pit_number',
                    'propeller_parts_exchange', 'boat_parts_exchange', 'other_parts_exchange'
                ])
                writer.writeheader()
            else:
                writer = csv.DictWriter(f, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)

        return str(output_path)

    def analyze_coverage(self, data: List[Dict]) -> Dict:
        """
        データカバレッジを分析

        Args:
            data: 収集データのリスト

        Returns:
            統計情報の辞書
        """
        if not data:
            return {
                'total_records': 0,
                'parts_exchange_count': 0,
                'adjusted_weight_count': 0,
                'any_exchange_count': 0,
                'coverage_rate': 0.0,
                'weight_coverage_rate': 0.0,
                'date_range': None,
                'parts_types': {}
            }

        total_records = len(data)
        parts_count = sum(1 for d in data if d['has_parts_exchange'] == 1)
        weight_count = sum(1 for d in data if d['adjusted_weight'] != 0.0)
        any_data = sum(
            1 for d in data
            if d['has_parts_exchange'] == 1 or d['adjusted_weight'] != 0.0
        )

        coverage_rate = (parts_count / total_records * 100) if total_records > 0 else 0.0
        weight_coverage_rate = (weight_count / total_records * 100) if total_records > 0 else 0.0

        # 部品交換の種類を集計
        parts_types = {}
        for d in data:
            parts = d.get('parts_replacement', '')
            if parts and parts.strip():
                parts_types[parts] = parts_types.get(parts, 0) + 1

        dates = [d['race_date'] for d in data if d['race_date']]
        date_range = f"{min(dates)} 〜 {max(dates)}" if dates else None

        return {
            'total_records': total_records,
            'parts_exchange_count': parts_count,
            'adjusted_weight_count': weight_count,
            'any_exchange_count': any_data,
            'coverage_rate': coverage_rate,
            'weight_coverage_rate': weight_coverage_rate,
            'date_range': date_range,
            'parts_types': parts_types
        }

    def generate_report(self, data: List[Dict], output_path: str) -> str:
        """
        収集レポートを生成

        Args:
            data: 収集データのリスト
            output_path: CSV保存パス

        Returns:
            レポート文字列
        """
        stats = self.analyze_coverage(data)

        # 部品交換種類のトップ5
        parts_top5 = sorted(stats['parts_types'].items(), key=lambda x: x[1], reverse=True)[:5]
        parts_detail = "\n".join([f"  - {k}: {v}件" for k, v in parts_top5]) if parts_top5 else "  （データなし）"

        report = f"""
{'=' * 80}
部品交換データ収集レポート
{'=' * 80}

【収集結果】
- 収集日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- 保存先: {output_path}
- 総レコード数: {stats['total_records']:,}件
- 期間: {stats['date_range'] or 'データなし'}

【データカバレッジ】
- 部品交換データあり: {stats['parts_exchange_count']:,}件 ({stats['coverage_rate']:.1f}%)
- 体重調整データあり: {stats['adjusted_weight_count']:,}件 ({stats['weight_coverage_rate']:.1f}%)
- いずれかデータあり: {stats['any_exchange_count']:,}件 ({stats['any_exchange_count']/stats['total_records']*100 if stats['total_records'] > 0 else 0:.1f}%)

【部品交換種類（上位5種類）】
{parts_detail}

【Phase 1目標達成度】
- 現在の部品交換カバレッジ: {stats['coverage_rate']:.1f}%
- Phase 1目標: 50%以上
- 達成状況: {'[OK] 達成' if stats['coverage_rate'] >= 50 else f'未達成（あと{50 - stats['coverage_rate']:.1f}%必要）'}

{'=' * 80}
"""
        return report


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description='部品交換データ収集スクリプト',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 全件収集
  python scripts/collect_parts_exchange.py

  # 最新1000件のみ収集
  python scripts/collect_parts_exchange.py --limit 1000

  # 期間指定収集
  python scripts/collect_parts_exchange.py --start-date 2024-12-01

  # 期間+件数指定
  python scripts/collect_parts_exchange.py --start-date 2024-11-01 --end-date 2024-12-31 --limit 5000
        """
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='収集件数上限（デフォルト: 制限なし）'
    )
    parser.add_argument(
        '--start-date',
        type=str,
        default=None,
        help='開始日（YYYY-MM-DD形式）'
    )
    parser.add_argument(
        '--end-date',
        type=str,
        default=None,
        help='終了日（YYYY-MM-DD形式）'
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default='data/boatrace.db',
        help='データベースパス（デフォルト: data/boatrace.db）'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("部品交換データ収集を開始します...")
    print("=" * 80)

    # 収集実行
    collector = PartsExchangeCollector(db_path=args.db_path)

    print("\n[1/3] データベースから部品交換情報を読み込み中...")
    data = collector.collect_parts_data(
        limit=args.limit,
        start_date=args.start_date,
        end_date=args.end_date
    )

    print(f"      → {len(data):,}件のレコードを取得")

    print("\n[2/3] CSVファイルに保存中...")
    output_path = collector.save_to_csv(data)
    print(f"      → {output_path} に保存完了")

    print("\n[3/3] レポート生成中...")
    report = collector.generate_report(data, output_path)
    print(report)

    # レポートファイルも保存
    report_path = Path("temp/reports/parts_exchange_collection_report.txt")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"レポートを {report_path} に保存しました。")

    print("\n収集完了！")


if __name__ == '__main__':
    main()
