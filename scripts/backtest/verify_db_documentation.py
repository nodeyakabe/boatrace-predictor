"""
データベースドキュメントの正確性検証スクリプト

ソースコードで実際に使用されているテーブル名・カラム名を抽出し、
生成されたドキュメントと照合して矛盾を検出します。
"""
import os
import re
import sqlite3
from collections import defaultdict
from typing import Dict, Set, List, Tuple


class DBDocumentationVerifier:
    """ドキュメント検証クラス"""

    def __init__(self, db_path: str, src_dirs: List[str]):
        self.db_path = db_path
        self.src_dirs = src_dirs
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()

        # 実際のDB構造
        self.actual_tables: Dict[str, Set[str]] = {}  # table_name -> {columns}
        self.load_actual_schema()

        # ソースコードで使用されているテーブル・カラム
        self.used_tables: Set[str] = set()
        self.used_columns: Dict[str, Set[str]] = defaultdict(set)  # table -> {columns}

    def load_actual_schema(self):
        """実際のDBスキーマを読み込み"""
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in self.cursor.fetchall()]

        for table in tables:
            self.cursor.execute(f"PRAGMA table_info({table})")
            columns = {row[1] for row in self.cursor.fetchall()}
            self.actual_tables[table] = columns

    def extract_table_usage_from_file(self, filepath: str) -> Tuple[Set[str], Dict[str, Set[str]]]:
        """ファイルからテーブル・カラムの使用状況を抽出"""
        used_tables = set()
        used_columns = defaultdict(set)

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

                # SQLクエリパターン
                # FROM table_name, JOIN table_name
                from_pattern = r'\b(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)\b'
                for match in re.finditer(from_pattern, content, re.IGNORECASE):
                    table_name = match.group(1).lower()
                    if table_name in self.actual_tables:
                        used_tables.add(table_name)

                # INSERT INTO table_name
                insert_pattern = r'\bINSERT\s+INTO\s+([a-z_][a-z0-9_]*)\b'
                for match in re.finditer(insert_pattern, content, re.IGNORECASE):
                    table_name = match.group(1).lower()
                    if table_name in self.actual_tables:
                        used_tables.add(table_name)

                # UPDATE table_name
                update_pattern = r'\bUPDATE\s+([a-z_][a-z0-9_]*)\b'
                for match in re.finditer(update_pattern, content, re.IGNORECASE):
                    table_name = match.group(1).lower()
                    if table_name in self.actual_tables:
                        used_tables.add(table_name)

                # DELETE FROM table_name
                delete_pattern = r'\bDELETE\s+FROM\s+([a-z_][a-z0-9_]*)\b'
                for match in re.finditer(delete_pattern, content, re.IGNORECASE):
                    table_name = match.group(1).lower()
                    if table_name in self.actual_tables:
                        used_tables.add(table_name)

                # カラム参照: table.column または 'column'
                for table_name in used_tables:
                    # table.column パターン
                    col_pattern = rf'\b{table_name}\.([a-z_][a-z0-9_]*)\b'
                    for match in re.finditer(col_pattern, content, re.IGNORECASE):
                        col_name = match.group(1).lower()
                        if col_name in self.actual_tables[table_name]:
                            used_columns[table_name].add(col_name)

                    # SELECT ... FROM table の中のカラム
                    # 簡易パターン（完全な解析ではない）
                    select_pattern = rf'SELECT\s+(.+?)\s+FROM\s+{table_name}\b'
                    for match in re.finditer(select_pattern, content, re.IGNORECASE | re.DOTALL):
                        select_clause = match.group(1)
                        # カンマ区切りのカラム名を抽出
                        for col_match in re.finditer(r'\b([a-z_][a-z0-9_]*)\b', select_clause):
                            col_name = col_match.group(1).lower()
                            if col_name in self.actual_tables[table_name]:
                                used_columns[table_name].add(col_name)

        except Exception as e:
            print(f"Warning: {filepath} の解析エラー: {e}")

        return used_tables, dict(used_columns)

    def scan_source_code(self):
        """ソースコードをスキャンしてテーブル・カラム使用状況を収集"""
        for src_dir in self.src_dirs:
            for root, dirs, files in os.walk(src_dir):
                for file in files:
                    if file.endswith('.py'):
                        filepath = os.path.join(root, file)
                        tables, columns = self.extract_table_usage_from_file(filepath)
                        self.used_tables.update(tables)
                        for table, cols in columns.items():
                            self.used_columns[table].update(cols)

    def verify_documentation(self) -> Dict[str, any]:
        """ドキュメントを検証"""
        results = {
            'total_tables': len(self.actual_tables),
            'used_tables': len(self.used_tables),
            'unused_tables': [],
            'table_details': {},
            'critical_tables': {
                'races': self.verify_table('races'),
                'trifecta_odds': self.verify_table('trifecta_odds'),
                'race_predictions': self.verify_table('race_predictions'),
                'results': self.verify_table('results'),
                'entries': self.verify_table('entries'),
            }
        }

        # 未使用テーブルを検出
        for table in self.actual_tables.keys():
            if table not in self.used_tables and table not in ['sqlite_sequence', 'sqlite_stat1']:
                results['unused_tables'].append(table)

        return results

    def verify_table(self, table_name: str) -> Dict:
        """特定テーブルの詳細検証"""
        if table_name not in self.actual_tables:
            return {'exists': False, 'error': 'テーブルが存在しません'}

        actual_cols = self.actual_tables[table_name]
        used_cols = self.used_columns.get(table_name, set())

        return {
            'exists': True,
            'total_columns': len(actual_cols),
            'used_columns': len(used_cols),
            'unused_columns': sorted(actual_cols - used_cols),
            'all_columns': sorted(actual_cols),
            'frequently_used': sorted(used_cols),
        }

    def generate_report(self) -> str:
        """検証レポートを生成"""
        self.scan_source_code()
        results = self.verify_documentation()

        report = []
        report.append("=" * 80)
        report.append("データベースドキュメント検証レポート")
        report.append("=" * 80)
        report.append("")

        # サマリー
        report.append("## 検証サマリー")
        report.append("")
        report.append(f"- 総テーブル数: {results['total_tables']}")
        report.append(f"- ソースコードで使用中: {results['used_tables']}")
        report.append(f"- 未使用テーブル数: {len(results['unused_tables'])}")
        report.append("")

        # 未使用テーブル
        if results['unused_tables']:
            report.append("## 未使用テーブル（要確認）")
            report.append("")
            for table in sorted(results['unused_tables']):
                row_count = self.get_row_count(table)
                report.append(f"- {table} ({row_count:,} 件)")
            report.append("")

        # 主要テーブルの詳細検証
        report.append("## 主要テーブル検証")
        report.append("")

        critical_tables = [
            ('races', 'レース基本情報'),
            ('trifecta_odds', '3連単オッズ'),
            ('race_predictions', '予想データ'),
            ('results', 'レース結果'),
            ('entries', '出走表'),
        ]

        for table_name, description in critical_tables:
            report.append(f"### {table_name} ({description})")
            report.append("")

            detail = results['critical_tables'][table_name]

            if not detail['exists']:
                report.append(f"❌ **エラー**: {detail['error']}")
                report.append("")
                continue

            report.append(f"- 総カラム数: {detail['total_columns']}")
            report.append(f"- ソースコードで使用中: {detail['used_columns']}")
            report.append("")

            report.append("**実際のカラム一覧:**")
            report.append("```")
            for col in detail['all_columns']:
                usage = "✓ 使用中" if col in detail['frequently_used'] else "  未使用"
                report.append(f"{usage}  {col}")
            report.append("```")
            report.append("")

            if detail['unused_columns']:
                report.append(f"**未使用カラム ({len(detail['unused_columns'])}個):**")
                report.append("")
                for col in detail['unused_columns']:
                    report.append(f"- {col}")
                report.append("")

        # ドキュメント vs 実際の整合性チェック
        report.append("## ドキュメント整合性チェック")
        report.append("")
        report.append("### よくある検索パターンの検証")
        report.append("")

        # ドキュメントに記載されている対応表を検証
        mappings = [
            ('3連単オッズ', 'trifecta_odds', 'odds'),
            ('2連単オッズ', 'exacta_odds', 'odds'),
            ('単勝オッズ', 'win_odds', 'odds'),
            ('レース結果（着順）', 'results', 'position'),
            ('払戻金', 'payouts', 'payout_amount'),
            ('予想データ', 'race_predictions', 'predicted_position'),
            ('出走表', 'entries', 'racer_id'),
            ('ST時間', 'entries', 'start_timing'),
            ('展示タイム', 'entries', 'exhibition_time'),
        ]

        for data_name, table_name, column_name in mappings:
            status = self.verify_mapping(table_name, column_name)
            symbol = "✅" if status['valid'] else "❌"
            report.append(f"{symbol} **{data_name}**")
            report.append(f"   - テーブル: `{table_name}` {status['table_status']}")
            report.append(f"   - カラム: `{column_name}` {status['column_status']}")
            report.append("")

        report.append("=" * 80)
        report.append("検証完了")
        report.append("=" * 80)

        return "\n".join(report)

    def verify_mapping(self, table_name: str, column_name: str) -> Dict:
        """マッピングの妥当性を検証"""
        result = {'valid': True, 'table_status': '', 'column_status': ''}

        if table_name not in self.actual_tables:
            result['valid'] = False
            result['table_status'] = '❌ 存在しません'
        else:
            result['table_status'] = '✓ 存在'

            if column_name not in self.actual_tables[table_name]:
                result['valid'] = False
                result['column_status'] = '❌ 存在しません'
            else:
                result['column_status'] = '✓ 存在'

        return result

    def get_row_count(self, table_name: str) -> int:
        """テーブルの行数を取得"""
        try:
            self.cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            return self.cursor.fetchone()[0]
        except:
            return 0

    def close(self):
        """DB接続を閉じる"""
        self.conn.close()


if __name__ == "__main__":
    import sys
    import io

    # UTF-8出力設定
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    db_path = 'data/boatrace.db'
    src_dirs = ['src', 'scripts']

    print("=" * 80)
    print("データベースドキュメント検証")
    print("=" * 80)
    print(f"データベース: {db_path}")
    print(f"ソースディレクトリ: {', '.join(src_dirs)}")
    print("")

    verifier = DBDocumentationVerifier(db_path, src_dirs)

    try:
        print("ソースコードをスキャン中...")
        report = verifier.generate_report()

        print("")
        print(report)

        # レポートをファイルに保存
        output_path = 'docs/DB_VERIFICATION_REPORT.md'
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)

        print("")
        print(f"検証レポートを保存しました: {output_path}")

    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
    finally:
        verifier.close()
