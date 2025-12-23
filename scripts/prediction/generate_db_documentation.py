"""
データベース構造ドキュメント生成スクリプト

全テーブルのスキーマ、カラム情報、サンプルデータ、統計情報を
Markdown形式でドキュメント化します。
"""
import sqlite3
import sys
import io
from datetime import datetime
from typing import List, Dict, Tuple, Any

# UTF-8出力設定
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


class DatabaseDocumentGenerator:
    """データベースドキュメント生成クラス"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()

    def get_all_tables(self) -> List[str]:
        """全テーブル名を取得"""
        self.cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table'
            ORDER BY name
        """)
        return [row[0] for row in self.cursor.fetchall()]

    def get_table_schema(self, table_name: str) -> List[Tuple]:
        """テーブルのスキーマ情報を取得"""
        self.cursor.execute(f"PRAGMA table_info({table_name})")
        return self.cursor.fetchall()

    def get_table_row_count(self, table_name: str) -> int:
        """テーブルの行数を取得"""
        try:
            self.cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            return self.cursor.fetchone()[0]
        except:
            return 0

    def get_sample_data(self, table_name: str, limit: int = 3) -> List[Tuple]:
        """サンプルデータを取得"""
        try:
            self.cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
            return self.cursor.fetchall()
        except:
            return []

    def get_indexes(self, table_name: str) -> List[str]:
        """テーブルのインデックス情報を取得"""
        self.cursor.execute(f"PRAGMA index_list({table_name})")
        indexes = self.cursor.fetchall()
        result = []
        for idx in indexes:
            idx_name = idx[1]
            self.cursor.execute(f"PRAGMA index_info({idx_name})")
            cols = [col[2] for col in self.cursor.fetchall()]
            result.append(f"{idx_name} ({', '.join(cols)})")
        return result

    def get_foreign_keys(self, table_name: str) -> List[Tuple]:
        """外部キー制約を取得"""
        self.cursor.execute(f"PRAGMA foreign_key_list({table_name})")
        return self.cursor.fetchall()

    def generate_table_documentation(self, table_name: str) -> str:
        """テーブルのドキュメントを生成"""
        doc = []

        # テーブルヘッダー
        doc.append(f"### {table_name}")
        doc.append("")

        # 行数
        row_count = self.get_table_row_count(table_name)
        doc.append(f"**レコード数**: {row_count:,} 件")
        doc.append("")

        # カラム情報
        schema = self.get_table_schema(table_name)
        doc.append("#### カラム一覧")
        doc.append("")
        doc.append("| カラム名 | 型 | NULL許可 | デフォルト値 | PK | 説明 |")
        doc.append("|----------|-----|----------|--------------|-----|------|")

        for col in schema:
            col_id, name, type_, not_null, default_val, pk = col
            null_ok = "×" if not_null else "○"
            pk_mark = "★" if pk else ""
            default_str = str(default_val) if default_val is not None else ""

            # 型情報から説明を推測
            description = self._infer_column_description(table_name, name, type_)

            doc.append(f"| {name} | {type_} | {null_ok} | {default_str} | {pk_mark} | {description} |")

        doc.append("")

        # インデックス情報
        indexes = self.get_indexes(table_name)
        if indexes:
            doc.append("#### インデックス")
            doc.append("")
            for idx in indexes:
                doc.append(f"- {idx}")
            doc.append("")

        # 外部キー
        foreign_keys = self.get_foreign_keys(table_name)
        if foreign_keys:
            doc.append("#### 外部キー")
            doc.append("")
            for fk in foreign_keys:
                doc.append(f"- {fk[3]} → {fk[2]}.{fk[4]}")
            doc.append("")

        # サンプルデータ
        samples = self.get_sample_data(table_name, limit=2)
        if samples and row_count > 0:
            doc.append("#### サンプルデータ")
            doc.append("")
            doc.append("```")
            col_names = [col[1] for col in schema]
            for i, sample in enumerate(samples, 1):
                doc.append(f"サンプル {i}:")
                for col_name, value in zip(col_names, sample):
                    doc.append(f"  {col_name}: {value}")
                doc.append("")
            doc.append("```")
            doc.append("")

        doc.append("---")
        doc.append("")

        return "\n".join(doc)

    def _infer_column_description(self, table_name: str, col_name: str, col_type: str) -> str:
        """カラム名と型から説明を推測"""
        # 共通カラム
        common_descriptions = {
            'id': 'プライマリキー（自動採番）',
            'created_at': '作成日時',
            'updated_at': '更新日時',
            'race_id': 'レースID（racesテーブルへの参照）',
            'racer_id': '選手ID（racersテーブルへの参照）',
            'venue_code': '競艇場コード（01-24）',
            'race_date': 'レース開催日（YYYY-MM-DD形式）',
            'race_number': 'レース番号（1-12R）',
        }

        if col_name in common_descriptions:
            return common_descriptions[col_name]

        # テーブル固有の推測
        if 'odds' in table_name.lower():
            if 'first' in col_name or '1st' in col_name:
                return '1着艇番'
            elif 'second' in col_name or '2nd' in col_name:
                return '2着艇番'
            elif 'third' in col_name or '3rd' in col_name:
                return '3着艇番'
            elif 'odds' in col_name:
                return 'オッズ倍率'

        if 'prediction' in table_name.lower():
            if 'score' in col_name:
                return '予想スコア'
            elif 'rank' in col_name:
                return '予想順位'
            elif 'type' in col_name:
                return '予想タイプ（advance/before）'

        if 'result' in table_name.lower():
            if 'time' in col_name:
                return '走行タイム'
            elif 'position' in col_name or 'place' in col_name:
                return '着順'

        # デフォルト
        return ''

    def generate_full_documentation(self) -> str:
        """完全なデータベースドキュメントを生成"""
        doc = []

        # ヘッダー
        doc.append("# ボートレース予想システム データベース仕様書")
        doc.append("")
        doc.append(f"**生成日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        doc.append(f"**データベース**: {self.db_path}")
        doc.append("")

        # 目次
        tables = self.get_all_tables()
        doc.append("## 目次")
        doc.append("")
        doc.append("### テーブル一覧")
        doc.append("")

        # テーブルをカテゴリ分け
        categories = {
            'マスタデータ': [],
            'レース基本情報': [],
            'オッズデータ': [],
            '予想データ': [],
            '結果データ': [],
            '選手・モーター情報': [],
            'その他': []
        }

        for table in tables:
            table_lower = table.lower()
            if 'venue' in table_lower or 'racer' in table_lower and 'master' in table_lower:
                categories['マスタデータ'].append(table)
            elif 'race' in table_lower and 'prediction' not in table_lower and 'result' not in table_lower:
                categories['レース基本情報'].append(table)
            elif 'odds' in table_lower:
                categories['オッズデータ'].append(table)
            elif 'prediction' in table_lower:
                categories['予想データ'].append(table)
            elif 'result' in table_lower or 'payout' in table_lower:
                categories['結果データ'].append(table)
            elif 'racer' in table_lower or 'motor' in table_lower or 'boat' in table_lower or 'entry' in table_lower or 'entries' in table_lower:
                categories['選手・モーター情報'].append(table)
            else:
                categories['その他'].append(table)

        for category, table_list in categories.items():
            if table_list:
                doc.append(f"#### {category} ({len(table_list)}テーブル)")
                for table in sorted(table_list):
                    row_count = self.get_table_row_count(table)
                    doc.append(f"- [{table}](#{table}) ({row_count:,} 件)")
                doc.append("")

        doc.append("")
        doc.append("---")
        doc.append("")

        # 概要統計
        doc.append("## データベース概要")
        doc.append("")
        doc.append(f"- **総テーブル数**: {len(tables)}")

        total_rows = sum(self.get_table_row_count(t) for t in tables)
        doc.append(f"- **総レコード数**: {total_rows:,}")
        doc.append("")

        # 主要テーブルのサマリー
        doc.append("### 主要データ統計")
        doc.append("")

        # レース数
        try:
            self.cursor.execute("SELECT COUNT(*) FROM races")
            race_count = self.cursor.fetchone()[0]
            doc.append(f"- **総レース数**: {race_count:,}")
        except:
            pass

        # 2025年レース数
        try:
            self.cursor.execute("SELECT COUNT(*) FROM races WHERE race_date LIKE '2025%'")
            race_2025 = self.cursor.fetchone()[0]
            doc.append(f"- **2025年レース数**: {race_2025:,}")
        except:
            pass

        # 予想データ数
        try:
            self.cursor.execute("SELECT COUNT(*) FROM race_predictions")
            pred_count = self.cursor.fetchone()[0]
            doc.append(f"- **予想データ数**: {pred_count:,}")
        except:
            pass

        # オッズデータ数
        try:
            self.cursor.execute("SELECT COUNT(DISTINCT race_id) FROM trifecta_odds")
            odds_count = self.cursor.fetchone()[0]
            doc.append(f"- **オッズ取得済レース数**: {odds_count:,}")
        except:
            pass

        doc.append("")
        doc.append("---")
        doc.append("")

        # 各テーブルの詳細
        doc.append("## テーブル詳細")
        doc.append("")

        for category, table_list in categories.items():
            if table_list:
                doc.append(f"## {category}")
                doc.append("")

                for table in sorted(table_list):
                    doc.append(self.generate_table_documentation(table))

        # よくある検索パターン
        doc.append("## よくある検索パターン")
        doc.append("")
        doc.append("### データ名の対応表")
        doc.append("")
        doc.append("| 探しているデータ | 実際のテーブル名 | カラム名 |")
        doc.append("|-----------------|------------------|----------|")
        doc.append("| 3連単オッズ | `trifecta_odds` | `odds` |")
        doc.append("| 2連単オッズ | `exacta_odds` | `odds` |")
        doc.append("| 単勝オッズ | `win_odds` | `odds` |")
        doc.append("| レース結果（着順） | `results` | `position`, `racer_id` |")
        doc.append("| 払戻金 | `payouts` | `payout_amount` |")
        doc.append("| 予想データ | `race_predictions` | `predicted_position`, `score` |")
        doc.append("| 出走表 | `entries` | `racer_id`, `motor_id` 等 |")
        doc.append("| 選手マスタ | `racers` | `name`, `class` 等 |")
        doc.append("| ST時間 | `entries` | `start_timing` |")
        doc.append("| 展示タイム | `entries` | `exhibition_time` |")
        doc.append("")

        doc.append("### クエリ例")
        doc.append("")
        doc.append("```sql")
        doc.append("-- 2025年のレース一覧")
        doc.append("SELECT * FROM races WHERE race_date LIKE '2025%';")
        doc.append("")
        doc.append("-- 特定レースの3連単オッズ")
        doc.append("SELECT * FROM trifecta_odds WHERE race_id = 12345;")
        doc.append("")
        doc.append("-- 特定レースの予想データ")
        doc.append("SELECT * FROM race_predictions WHERE race_id = 12345;")
        doc.append("")
        doc.append("-- オッズが取得済みのレース")
        doc.append("SELECT DISTINCT r.* FROM races r")
        doc.append("INNER JOIN trifecta_odds o ON r.id = o.race_id")
        doc.append("WHERE r.race_date LIKE '2025%';")
        doc.append("```")
        doc.append("")

        return "\n".join(doc)

    def save_documentation(self, output_path: str):
        """ドキュメントをファイルに保存"""
        doc_content = self.generate_full_documentation()

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(doc_content)

        print(f"ドキュメントを生成しました: {output_path}")
        print(f"ファイルサイズ: {len(doc_content):,} bytes")

    def close(self):
        """データベース接続を閉じる"""
        self.conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='データベース構造ドキュメント生成')
    parser.add_argument('--db', default='data/boatrace.db', help='データベースパス')
    parser.add_argument('--output', default='docs/DATABASE_SCHEMA.md', help='出力ファイルパス')

    args = parser.parse_args()

    print("=" * 80)
    print("データベース構造ドキュメント生成")
    print("=" * 80)
    print(f"データベース: {args.db}")
    print(f"出力先: {args.output}")
    print("")

    generator = DatabaseDocumentGenerator(args.db)

    try:
        generator.save_documentation(args.output)
        print("")
        print("✓ ドキュメント生成完了")
    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
    finally:
        generator.close()
