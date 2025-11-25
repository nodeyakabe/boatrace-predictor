"""
潮位データを本番DBにマージするためのエクスポートスクリプト

生成したrace_tide_dataテーブルのデータをSQLファイルとして出力
本番環境での適用方法も含めて提供
"""

import sqlite3
from datetime import datetime
import os


class TideDataExporter:
    """潮位データのエクスポート"""

    def __init__(self, db_path="data/boatrace.db", export_dir="tide_export"):
        """
        初期化

        Args:
            db_path: エクスポート元データベースパス
            export_dir: エクスポート先ディレクトリ
        """
        self.db_path = db_path
        self.export_dir = export_dir

        os.makedirs(export_dir, exist_ok=True)

    def export_to_sql(self, output_file=None):
        """
        race_tide_dataテーブルをSQLファイルにエクスポート

        Args:
            output_file: 出力ファイル名（Noneの場合は自動生成）

        Returns:
            str: 出力ファイルパス
        """
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"race_tide_data_{timestamp}.sql"

        output_path = os.path.join(self.export_dir, output_file)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # データ統計取得
        cursor.execute("SELECT COUNT(*) FROM race_tide_data")
        total_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT data_source, COUNT(*) as count
            FROM race_tide_data
            GROUP BY data_source
            ORDER BY count DESC
        """)
        source_stats = cursor.fetchall()

        print("="*80)
        print("潮位データエクスポート")
        print("="*80)
        print(f"出力先: {output_path}")
        print(f"総レコード数: {total_count:,}")
        print("\nデータソース別:")
        for source, count in source_stats:
            print(f"  {source:30s}: {count:8,} ({count/total_count*100:5.1f}%)")
        print("="*80)

        # SQLファイル作成
        with open(output_path, 'w', encoding='utf-8') as f:
            # ヘッダー
            f.write("-- ================================================================\n")
            f.write("-- 潮位データインポート用SQLファイル\n")
            f.write(f"-- 生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"-- 総レコード数: {total_count:,}\n")
            f.write("-- ================================================================\n\n")

            # データソース統計
            f.write("-- データソース別統計:\n")
            for source, count in source_stats:
                f.write(f"--   {source:30s}: {count:8,} ({count/total_count*100:5.1f}%)\n")
            f.write("\n")

            # トランザクション開始
            f.write("BEGIN TRANSACTION;\n\n")

            # データエクスポート（バッチ単位）
            batch_size = 1000
            cursor.execute("""
                SELECT
                    race_id,
                    sea_level_cm,
                    data_source,
                    created_at,
                    updated_at
                FROM race_tide_data
                ORDER BY race_id
            """)

            exported = 0
            batch = []

            for row in cursor:
                race_id, sea_level_cm, data_source, created_at, updated_at = row

                # INSERT文を生成（INSERT OR REPLACE形式）
                insert_sql = (
                    f"INSERT OR REPLACE INTO race_tide_data "
                    f"(race_id, sea_level_cm, data_source, created_at, updated_at) "
                    f"VALUES ({race_id}, {sea_level_cm}, '{data_source}', "
                    f"'{created_at}', '{updated_at}');"
                )

                batch.append(insert_sql)

                if len(batch) >= batch_size:
                    # バッチ書き込み
                    f.write('\n'.join(batch) + '\n\n')
                    exported += len(batch)
                    batch = []

                    # 進捗表示
                    if exported % 10000 == 0:
                        print(f"  エクスポート中... {exported:,}/{total_count:,} ({exported/total_count*100:.1f}%)")

            # 残りのバッチを書き込み
            if batch:
                f.write('\n'.join(batch) + '\n\n')
                exported += len(batch)

            # トランザクション完了
            f.write("COMMIT;\n")

        conn.close()

        print(f"\n[完了] {exported:,} レコードをエクスポートしました")
        print(f"出力ファイル: {os.path.abspath(output_path)}")

        # 適用方法を別ファイルに出力
        self._generate_import_instructions(output_file)

        return output_path

    def export_to_csv(self, output_file=None):
        """
        race_tide_dataテーブルをCSVファイルにエクスポート

        Args:
            output_file: 出力ファイル名（Noneの場合は自動生成）

        Returns:
            str: 出力ファイルパス
        """
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"race_tide_data_{timestamp}.csv"

        output_path = os.path.join(self.export_dir, output_file)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # データ取得
        cursor.execute("SELECT COUNT(*) FROM race_tide_data")
        total_count = cursor.fetchone()[0]

        print("="*80)
        print("潮位データエクスポート（CSV形式）")
        print("="*80)
        print(f"出力先: {output_path}")
        print(f"総レコード数: {total_count:,}")
        print("="*80)

        # CSVファイル作成
        with open(output_path, 'w', encoding='utf-8') as f:
            # ヘッダー
            f.write("race_id,sea_level_cm,data_source,created_at,updated_at\n")

            # データエクスポート
            cursor.execute("""
                SELECT
                    race_id,
                    sea_level_cm,
                    data_source,
                    created_at,
                    updated_at
                FROM race_tide_data
                ORDER BY race_id
            """)

            exported = 0
            for row in cursor:
                race_id, sea_level_cm, data_source, created_at, updated_at = row
                f.write(f"{race_id},{sea_level_cm},{data_source},{created_at},{updated_at}\n")
                exported += 1

                if exported % 10000 == 0:
                    print(f"  エクスポート中... {exported:,}/{total_count:,} ({exported/total_count*100:.1f}%)")

        conn.close()

        print(f"\n[完了] {exported:,} レコードをエクスポートしました")
        print(f"出力ファイル: {os.path.abspath(output_path)}")

        return output_path

    def _generate_import_instructions(self, sql_file):
        """
        インポート手順書を生成

        Args:
            sql_file: SQLファイル名
        """
        instructions_file = os.path.join(self.export_dir, "IMPORT_INSTRUCTIONS.md")

        with open(instructions_file, 'w', encoding='utf-8') as f:
            f.write("# 潮位データ 本番DBインポート手順\n\n")
            f.write("## 概要\n\n")
            f.write("このSQLファイルには、以下のデータが含まれています：\n\n")
            f.write("- 2015-2021年: PyTides推定値\n")
            f.write("- 2022-2025年: RDMDB実測値\n\n")
            f.write("---\n\n")

            f.write("## インポート前の準備\n\n")
            f.write("### 1. バックアップ作成\n\n")
            f.write("```bash\n")
            f.write("# 本番DBのバックアップを作成\n")
            f.write("sqlite3 本番DB.db \".backup 本番DB_backup_$(date +%Y%m%d_%H%M%S).db\"\n")
            f.write("```\n\n")

            f.write("### 2. テーブル確認\n\n")
            f.write("```bash\n")
            f.write("sqlite3 本番DB.db \"SELECT COUNT(*) FROM race_tide_data\"\n")
            f.write("```\n\n")

            f.write("---\n\n")

            f.write("## インポート方法\n\n")
            f.write("### 方法1: SQLファイルを直接適用（推奨）\n\n")
            f.write("```bash\n")
            f.write(f"sqlite3 本番DB.db < {sql_file}\n")
            f.write("```\n\n")

            f.write("### 方法2: SQLiteコマンドラインから適用\n\n")
            f.write("```bash\n")
            f.write("sqlite3 本番DB.db\n")
            f.write(f"sqlite> .read {sql_file}\n")
            f.write("sqlite> .exit\n")
            f.write("```\n\n")

            f.write("### 方法3: Pythonスクリプトから適用\n\n")
            f.write("```python\n")
            f.write("import sqlite3\n\n")
            f.write("conn = sqlite3.connect('本番DB.db')\n")
            f.write(f"with open('{sql_file}', 'r', encoding='utf-8') as f:\n")
            f.write("    sql = f.read()\n")
            f.write("    conn.executescript(sql)\n")
            f.write("conn.close()\n")
            f.write("print('インポート完了')\n")
            f.write("```\n\n")

            f.write("---\n\n")

            f.write("## インポート後の確認\n\n")
            f.write("### 1. レコード数確認\n\n")
            f.write("```sql\n")
            f.write("SELECT COUNT(*) FROM race_tide_data;\n")
            f.write("```\n\n")

            f.write("### 2. データソース別確認\n\n")
            f.write("```sql\n")
            f.write("SELECT \n")
            f.write("    data_source,\n")
            f.write("    COUNT(*) as count\n")
            f.write("FROM race_tide_data\n")
            f.write("GROUP BY data_source\n")
            f.write("ORDER BY count DESC;\n")
            f.write("```\n\n")

            f.write("### 3. 期間別カバー率確認\n\n")
            f.write("```sql\n")
            f.write("SELECT \n")
            f.write("    CASE \n")
            f.write("        WHEN r.race_date < '2022-11-01' THEN '2015-2021'\n")
            f.write("        ELSE '2022-2025'\n")
            f.write("    END as period,\n")
            f.write("    COUNT(*) as total_races,\n")
            f.write("    SUM(CASE WHEN rtd.race_id IS NOT NULL THEN 1 ELSE 0 END) as with_tide\n")
            f.write("FROM races r\n")
            f.write("LEFT JOIN race_tide_data rtd ON r.id = rtd.race_id\n")
            f.write("WHERE r.venue_code IN ('15', '16', '17', '18', '20', '22', '24')\n")
            f.write("GROUP BY period;\n")
            f.write("```\n\n")

            f.write("---\n\n")

            f.write("## トラブルシューティング\n\n")
            f.write("### エラー: table race_tide_data has no column named ...\n\n")
            f.write("→ 本番DBのrace_tide_dataテーブル構造を確認してください\n\n")
            f.write("```sql\n")
            f.write("PRAGMA table_info(race_tide_data);\n")
            f.write("```\n\n")

            f.write("### エラー: UNIQUE constraint failed\n\n")
            f.write("→ INSERT OR REPLACE を使用しているため、通常は発生しません\n\n")

            f.write("### インポートが遅い\n\n")
            f.write("→ プラグマ設定でパフォーマンス改善\n\n")
            f.write("```sql\n")
            f.write("PRAGMA synchronous = OFF;\n")
            f.write("PRAGMA journal_mode = MEMORY;\n")
            f.write("-- SQLファイルを読み込み\n")
            f.write("PRAGMA synchronous = FULL;\n")
            f.write("PRAGMA journal_mode = DELETE;\n")
            f.write("```\n\n")

            f.write("---\n\n")

            f.write("## 注意事項\n\n")
            f.write("1. **必ずバックアップを取得してから実行してください**\n")
            f.write("2. INSERT OR REPLACE形式なので、既存データは上書きされます\n")
            f.write("3. インポート時間の目安: 約1-5分（レコード数による）\n")
            f.write("4. ディスク容量に余裕があることを確認してください\n\n")

        print(f"\nインポート手順書を作成しました: {os.path.abspath(instructions_file)}")

    def generate_summary_report(self):
        """データサマリーレポートを生成"""

        summary_file = os.path.join(self.export_dir, "DATA_SUMMARY.md")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("# 潮位データ サマリーレポート\n\n")
            f.write(f"生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")

            # 全体統計
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    MIN(race_id) as min_id,
                    MAX(race_id) as max_id
                FROM race_tide_data
            """)
            total, min_id, max_id = cursor.fetchone()

            f.write("## 全体統計\n\n")
            f.write(f"- 総レコード数: {total:,}\n")
            f.write(f"- レースID範囲: {min_id:,} ～ {max_id:,}\n\n")

            # データソース別
            cursor.execute("""
                SELECT
                    data_source,
                    COUNT(*) as count
                FROM race_tide_data
                GROUP BY data_source
                ORDER BY count DESC
            """)
            sources = cursor.fetchall()

            f.write("## データソース別統計\n\n")
            f.write("| データソース | レコード数 | 割合 |\n")
            f.write("|------------|-----------|------|\n")
            for source, count in sources:
                percentage = count / total * 100 if total > 0 else 0
                f.write(f"| {source} | {count:,} | {percentage:.1f}% |\n")
            f.write("\n")

            # 期間別カバー率
            cursor.execute("""
                SELECT
                    CASE
                        WHEN r.race_date < '2022-11-01' THEN '2015-2021'
                        ELSE '2022-2025'
                    END as period,
                    COUNT(*) as total_races,
                    SUM(CASE WHEN rtd.race_id IS NOT NULL THEN 1 ELSE 0 END) as with_tide
                FROM races r
                LEFT JOIN race_tide_data rtd ON r.id = rtd.race_id
                WHERE r.venue_code IN ('15', '16', '17', '18', '20', '22', '24')
                GROUP BY period
            """)
            periods = cursor.fetchall()

            f.write("## 期間別カバー率\n\n")
            f.write("| 期間 | 総レース数 | 潮位データあり | カバー率 |\n")
            f.write("|------|-----------|--------------|--------|\n")
            for period, total_races, with_tide in periods:
                coverage = with_tide / total_races * 100 if total_races > 0 else 0
                f.write(f"| {period} | {total_races:,} | {with_tide:,} | {coverage:.1f}% |\n")
            f.write("\n")

            # 会場別統計
            cursor.execute("""
                SELECT
                    r.venue_code,
                    COUNT(*) as total_races,
                    SUM(CASE WHEN rtd.race_id IS NOT NULL THEN 1 ELSE 0 END) as with_tide
                FROM races r
                LEFT JOIN race_tide_data rtd ON r.id = rtd.race_id
                WHERE r.venue_code IN ('15', '16', '17', '18', '20', '22', '24')
                GROUP BY r.venue_code
                ORDER BY r.venue_code
            """)
            venues = cursor.fetchall()

            venue_names = {
                '15': '丸亀', '16': '児島', '17': '宮島',
                '18': '徳山', '20': '若松', '22': '福岡', '24': '大村'
            }

            f.write("## 会場別統計\n\n")
            f.write("| 会場 | 総レース数 | 潮位データあり | カバー率 |\n")
            f.write("|------|-----------|--------------|--------|\n")
            for venue_code, total_races, with_tide in venues:
                venue_name = venue_names.get(venue_code, venue_code)
                coverage = with_tide / total_races * 100 if total_races > 0 else 0
                f.write(f"| {venue_name} | {total_races:,} | {with_tide:,} | {coverage:.1f}% |\n")
            f.write("\n")

        conn.close()

        print(f"サマリーレポートを作成しました: {os.path.abspath(summary_file)}")


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(
        description='潮位データを本番DBにマージするためのエクスポート'
    )
    parser.add_argument('--db', default='data/boatrace.db', help='データベースパス')
    parser.add_argument('--format', choices=['sql', 'csv', 'both'], default='both',
                       help='エクスポート形式')
    parser.add_argument('--export-dir', default='tide_export', help='エクスポート先ディレクトリ')

    args = parser.parse_args()

    exporter = TideDataExporter(
        db_path=args.db,
        export_dir=args.export_dir
    )

    # エクスポート実行
    if args.format in ['sql', 'both']:
        exporter.export_to_sql()

    if args.format in ['csv', 'both']:
        exporter.export_to_csv()

    # サマリーレポート生成
    exporter.generate_summary_report()

    print("\n" + "="*80)
    print("エクスポート完了")
    print("="*80)
    print(f"エクスポート先: {os.path.abspath(args.export_dir)}")
    print("\n次のステップ:")
    print(f"  1. {args.export_dir}/IMPORT_INSTRUCTIONS.md を確認")
    print(f"  2. 本番DBのバックアップを作成")
    print(f"  3. SQLファイルを本番DBに適用")
    print("="*80)


if __name__ == '__main__':
    main()
