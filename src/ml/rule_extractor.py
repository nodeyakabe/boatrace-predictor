"""
ルール抽出システム（加算方式）

機能:
- パターンから自動でルールを抽出
- 加算値（+10%など）として出力
- バックテストで有効性検証
- DB保存
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import sqlite3
from itertools import product
import json


class RuleExtractor:
    """ルール抽出クラス（加算方式）"""

    # 会場コードと名前のマッピング
    VENUE_NAMES = {
        '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
        '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
        '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
        '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
        '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
        '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
    }

    def __init__(self, db_path: str = "boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path
        self._create_rules_table()

    def _create_rules_table(self):
        """ルールテーブルを作成"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS extracted_rules (
                    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_name TEXT NOT NULL,
                    condition_json TEXT NOT NULL,
                    adjustment REAL NOT NULL,
                    sample_size INTEGER NOT NULL,
                    baseline_rate REAL NOT NULL,
                    actual_rate REAL NOT NULL,
                    confidence REAL NOT NULL,
                    is_valid INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(rule_name)
                )
            """)
            conn.commit()

    def load_analysis_data(self) -> pd.DataFrame:
        """分析用データを読み込み"""
        with sqlite3.connect(self.db_path) as conn:
            query = """
                SELECT
                    r.id AS race_id,
                    r.race_date,
                    r.venue_code,
                    r.race_number,
                    e.pit_number,
                    e.racer_number,
                    e.racer_rank,
                    e.win_rate AS nation_win_rate,
                    e.local_win_rate,
                    e.motor_second_rate AS motor_2ren_rate,
                    CAST(res.rank AS INTEGER) AS result_place,
                    w.wind_direction,
                    w.wind_speed,
                    w.wave_height,
                    t.tide_type AS tide_status
                FROM races r
                JOIN entries e ON r.id = e.race_id
                LEFT JOIN results res ON r.id = res.race_id
                    AND e.pit_number = res.pit_number
                LEFT JOIN weather w ON r.venue_code = w.venue_code
                    AND r.race_date = w.weather_date
                LEFT JOIN tide t ON r.venue_code = t.venue_code
                    AND r.race_date = t.tide_date
                WHERE res.rank IS NOT NULL
                    AND res.rank != ''
                    AND res.is_invalid = 0
            """
            df = pd.read_sql_query(query, conn)

        # 勝者フラグ
        df['is_winner'] = (df['result_place'] == 1).astype(int)

        return df

    def calculate_baseline_win_rate(self, df: pd.DataFrame) -> Dict[int, float]:
        """
        コース別ベースライン勝率を計算

        Args:
            df: 分析データ

        Returns:
            コース番号 -> 勝率 の辞書
        """
        baseline = {}
        for pit in range(1, 7):
            pit_data = df[df['pit_number'] == pit]
            if len(pit_data) > 0:
                baseline[pit] = pit_data['is_winner'].mean()
            else:
                baseline[pit] = 1 / 6  # デフォルト

        return baseline

    def extract_venue_course_rules(
        self,
        df: pd.DataFrame,
        min_samples: int = 100
    ) -> List[Dict[str, Any]]:
        """
        会場×コース別ルールを抽出

        Args:
            df: 分析データ
            min_samples: 最小サンプル数

        Returns:
            ルールリスト
        """
        baseline = self.calculate_baseline_win_rate(df)
        rules = []

        for venue_code in df['venue_code'].unique():
            venue_data = df[df['venue_code'] == venue_code]
            venue_name = self.VENUE_NAMES.get(venue_code, venue_code)

            for pit in range(1, 7):
                pit_data = venue_data[venue_data['pit_number'] == pit]

                if len(pit_data) < min_samples:
                    continue

                actual_rate = pit_data['is_winner'].mean()
                base_rate = baseline[pit]
                adjustment = actual_rate - base_rate

                # 有意な差がある場合のみ（±2%以上）
                if abs(adjustment) >= 0.02:
                    rule = {
                        'rule_name': f'{venue_name}_{pit}号艇',
                        'condition': {
                            'venue_code': venue_code,
                            'pit_number': pit
                        },
                        'adjustment': round(adjustment, 4),
                        'sample_size': len(pit_data),
                        'baseline_rate': round(base_rate, 4),
                        'actual_rate': round(actual_rate, 4),
                        'confidence': self._calculate_confidence(
                            len(pit_data), actual_rate, base_rate
                        )
                    }
                    rules.append(rule)

        return rules

    def extract_wind_rules(
        self,
        df: pd.DataFrame,
        min_samples: int = 50
    ) -> List[Dict[str, Any]]:
        """
        風向き×コース別ルールを抽出

        Args:
            df: 分析データ
            min_samples: 最小サンプル数

        Returns:
            ルールリスト
        """
        baseline = self.calculate_baseline_win_rate(df)
        rules = []

        # 風向きがある場合のみ
        if 'wind_direction' not in df.columns:
            return rules

        wind_df = df[df['wind_direction'].notna()]

        for wind in wind_df['wind_direction'].unique():
            if not wind or wind == '':
                continue

            wind_data = wind_df[wind_df['wind_direction'] == wind]

            for pit in range(1, 7):
                pit_data = wind_data[wind_data['pit_number'] == pit]

                if len(pit_data) < min_samples:
                    continue

                actual_rate = pit_data['is_winner'].mean()
                base_rate = baseline[pit]
                adjustment = actual_rate - base_rate

                if abs(adjustment) >= 0.02:
                    rule = {
                        'rule_name': f'{wind}風_{pit}号艇',
                        'condition': {
                            'wind_direction': wind,
                            'pit_number': pit
                        },
                        'adjustment': round(adjustment, 4),
                        'sample_size': len(pit_data),
                        'baseline_rate': round(base_rate, 4),
                        'actual_rate': round(actual_rate, 4),
                        'confidence': self._calculate_confidence(
                            len(pit_data), actual_rate, base_rate
                        )
                    }
                    rules.append(rule)

        return rules

    def extract_tide_rules(
        self,
        df: pd.DataFrame,
        min_samples: int = 50
    ) -> List[Dict[str, Any]]:
        """
        潮×コース別ルールを抽出

        Args:
            df: 分析データ
            min_samples: 最小サンプル数

        Returns:
            ルールリスト
        """
        baseline = self.calculate_baseline_win_rate(df)
        rules = []

        if 'tide_status' not in df.columns:
            return rules

        tide_df = df[df['tide_status'].notna()]

        for tide in tide_df['tide_status'].unique():
            if not tide or tide == '':
                continue

            tide_data = tide_df[tide_df['tide_status'] == tide]

            for pit in range(1, 7):
                pit_data = tide_data[tide_data['pit_number'] == pit]

                if len(pit_data) < min_samples:
                    continue

                actual_rate = pit_data['is_winner'].mean()
                base_rate = baseline[pit]
                adjustment = actual_rate - base_rate

                if abs(adjustment) >= 0.02:
                    rule = {
                        'rule_name': f'{tide}_{pit}号艇',
                        'condition': {
                            'tide_status': tide,
                            'pit_number': pit
                        },
                        'adjustment': round(adjustment, 4),
                        'sample_size': len(pit_data),
                        'baseline_rate': round(base_rate, 4),
                        'actual_rate': round(actual_rate, 4),
                        'confidence': self._calculate_confidence(
                            len(pit_data), actual_rate, base_rate
                        )
                    }
                    rules.append(rule)

        return rules

    def extract_rank_rules(
        self,
        df: pd.DataFrame,
        min_samples: int = 50
    ) -> List[Dict[str, Any]]:
        """
        選手ランク×コース別ルールを抽出

        Args:
            df: 分析データ
            min_samples: 最小サンプル数

        Returns:
            ルールリスト
        """
        baseline = self.calculate_baseline_win_rate(df)
        rules = []

        if 'racer_rank' not in df.columns:
            return rules

        rank_df = df[df['racer_rank'].notna()]

        # ランクを簡略化（A1, A2, B1, B2）
        def simplify_rank(rank):
            if pd.isna(rank):
                return None
            rank_str = str(rank).upper()
            if 'A1' in rank_str:
                return 'A1'
            elif 'A2' in rank_str:
                return 'A2'
            elif 'B1' in rank_str:
                return 'B1'
            elif 'B2' in rank_str:
                return 'B2'
            return None

        rank_df = rank_df.copy()
        rank_df['rank_simple'] = rank_df['racer_rank'].apply(simplify_rank)
        rank_df = rank_df[rank_df['rank_simple'].notna()]

        for rank in ['A1', 'A2', 'B1', 'B2']:
            rank_data = rank_df[rank_df['rank_simple'] == rank]

            for pit in range(1, 7):
                pit_data = rank_data[rank_data['pit_number'] == pit]

                if len(pit_data) < min_samples:
                    continue

                actual_rate = pit_data['is_winner'].mean()
                base_rate = baseline[pit]
                adjustment = actual_rate - base_rate

                if abs(adjustment) >= 0.02:
                    rule = {
                        'rule_name': f'{rank}選手_{pit}号艇',
                        'condition': {
                            'racer_rank': rank,
                            'pit_number': pit
                        },
                        'adjustment': round(adjustment, 4),
                        'sample_size': len(pit_data),
                        'baseline_rate': round(base_rate, 4),
                        'actual_rate': round(actual_rate, 4),
                        'confidence': self._calculate_confidence(
                            len(pit_data), actual_rate, base_rate
                        )
                    }
                    rules.append(rule)

        return rules

    def extract_combined_rules(
        self,
        df: pd.DataFrame,
        min_samples: int = 30
    ) -> List[Dict[str, Any]]:
        """
        会場×風向き×コースの複合ルールを抽出

        Args:
            df: 分析データ
            min_samples: 最小サンプル数

        Returns:
            ルールリスト
        """
        baseline = self.calculate_baseline_win_rate(df)
        rules = []

        if 'wind_direction' not in df.columns:
            return rules

        for venue_code in df['venue_code'].unique():
            venue_data = df[df['venue_code'] == venue_code]
            venue_name = self.VENUE_NAMES.get(venue_code, venue_code)

            for wind in venue_data['wind_direction'].dropna().unique():
                if not wind:
                    continue

                wind_data = venue_data[venue_data['wind_direction'] == wind]

                for pit in range(1, 7):
                    pit_data = wind_data[wind_data['pit_number'] == pit]

                    if len(pit_data) < min_samples:
                        continue

                    actual_rate = pit_data['is_winner'].mean()
                    base_rate = baseline[pit]
                    adjustment = actual_rate - base_rate

                    # より大きな差がある場合のみ（±3%以上）
                    if abs(adjustment) >= 0.03:
                        rule = {
                            'rule_name': f'{venue_name}_{wind}風_{pit}号艇',
                            'condition': {
                                'venue_code': venue_code,
                                'wind_direction': wind,
                                'pit_number': pit
                            },
                            'adjustment': round(adjustment, 4),
                            'sample_size': len(pit_data),
                            'baseline_rate': round(base_rate, 4),
                            'actual_rate': round(actual_rate, 4),
                            'confidence': self._calculate_confidence(
                                len(pit_data), actual_rate, base_rate
                            )
                        }
                        rules.append(rule)

        return rules

    def _calculate_confidence(
        self,
        n: int,
        actual: float,
        expected: float
    ) -> float:
        """
        信頼度を計算（サンプル数と乖離に基づく）

        Args:
            n: サンプル数
            actual: 実績値
            expected: 期待値

        Returns:
            信頼度（0-1）
        """
        # サンプル数による信頼度
        sample_confidence = min(1.0, n / 500)

        # 統計的有意性（簡易版）
        if n > 0:
            se = np.sqrt(expected * (1 - expected) / n)
            if se > 0:
                z = abs(actual - expected) / se
                significance = min(1.0, z / 3)  # z=3で信頼度1
            else:
                significance = 1.0
        else:
            significance = 0

        return round(sample_confidence * significance, 4)

    def extract_all_rules(
        self,
        min_confidence: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        全ルールを抽出

        Args:
            min_confidence: 最小信頼度

        Returns:
            全ルールリスト
        """
        print("ルール抽出を開始...")
        df = self.load_analysis_data()
        print(f"分析データ: {len(df):,}行")

        all_rules = []

        # 各種ルールを抽出
        print("  会場×コース...")
        all_rules.extend(self.extract_venue_course_rules(df))

        print("  風向き×コース...")
        all_rules.extend(self.extract_wind_rules(df))

        print("  潮×コース...")
        all_rules.extend(self.extract_tide_rules(df))

        print("  ランク×コース...")
        all_rules.extend(self.extract_rank_rules(df))

        print("  会場×風向き×コース...")
        all_rules.extend(self.extract_combined_rules(df))

        # 信頼度でフィルタ
        valid_rules = [r for r in all_rules if r['confidence'] >= min_confidence]

        # 有効性判定
        for rule in valid_rules:
            rule['is_valid'] = abs(rule['adjustment']) >= 0.02 and rule['confidence'] >= min_confidence

        print(f"\n抽出完了: {len(valid_rules)}ルール（全{len(all_rules)}から）")

        return valid_rules

    def save_rules_to_db(self, rules: List[Dict[str, Any]]):
        """
        ルールをDBに保存

        Args:
            rules: ルールリスト
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            for rule in rules:
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO extracted_rules
                        (rule_name, condition_json, adjustment, sample_size,
                         baseline_rate, actual_rate, confidence, is_valid, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        rule['rule_name'],
                        json.dumps(rule['condition']),
                        rule['adjustment'],
                        rule['sample_size'],
                        rule['baseline_rate'],
                        rule['actual_rate'],
                        rule['confidence'],
                        1 if rule.get('is_valid', False) else 0,
                        datetime.now().isoformat()
                    ))
                except Exception as e:
                    print(f"保存エラー ({rule['rule_name']}): {e}")

            conn.commit()
            print(f"{len(rules)}ルールを保存しました")

    def get_applicable_rules(
        self,
        venue_code: str,
        pit_number: int,
        wind_direction: Optional[str] = None,
        tide_status: Optional[str] = None,
        racer_rank: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        条件に適用可能なルールを取得

        Args:
            venue_code: 会場コード
            pit_number: ピット番号
            wind_direction: 風向き
            tide_status: 潮
            racer_rank: 選手ランク

        Returns:
            適用可能なルールリスト
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT rule_name, condition_json, adjustment, confidence
                FROM extracted_rules
                WHERE is_valid = 1
            """)

            applicable = []

            for row in cursor.fetchall():
                rule_name, condition_json, adjustment, confidence = row
                condition = json.loads(condition_json)

                # 条件チェック
                matches = True

                if 'venue_code' in condition and condition['venue_code'] != venue_code:
                    matches = False
                if 'pit_number' in condition and condition['pit_number'] != pit_number:
                    matches = False
                if 'wind_direction' in condition:
                    if not wind_direction or condition['wind_direction'] != wind_direction:
                        matches = False
                if 'tide_status' in condition:
                    if not tide_status or condition['tide_status'] != tide_status:
                        matches = False
                if 'racer_rank' in condition:
                    if not racer_rank or condition['racer_rank'] not in racer_rank:
                        matches = False

                if matches:
                    applicable.append({
                        'rule_name': rule_name,
                        'adjustment': adjustment,
                        'confidence': confidence
                    })

            return applicable

    def calculate_total_adjustment(
        self,
        applicable_rules: List[Dict[str, Any]]
    ) -> Tuple[float, List[str]]:
        """
        適用ルールから合計加算値を計算

        Args:
            applicable_rules: 適用可能なルールリスト

        Returns:
            (合計加算値, 適用ルール名リスト)
        """
        # 信頼度で重み付け加算
        total = 0
        rule_names = []

        for rule in applicable_rules:
            weighted_adj = rule['adjustment'] * rule['confidence']
            total += weighted_adj
            rule_names.append(rule['rule_name'])

        return total, rule_names

    def generate_report(self, rules: List[Dict[str, Any]]) -> str:
        """
        ルールレポートを生成

        Args:
            rules: ルールリスト

        Returns:
            フォーマットされたレポート
        """
        lines = [
            "=" * 60,
            "抽出ルールレポート（加算方式）",
            "=" * 60,
            f"生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"総ルール数: {len(rules)}",
            ""
        ]

        # 有効なルールのみ
        valid_rules = [r for r in rules if r.get('is_valid', False)]

        # 加算値でソート
        sorted_rules = sorted(valid_rules, key=lambda x: x['adjustment'], reverse=True)

        # プラス効果TOP10
        lines.extend([
            "【プラス効果 TOP10】"
        ])
        for i, rule in enumerate(sorted_rules[:10], 1):
            adj_pct = rule['adjustment'] * 100
            lines.append(
                f"  {i:2d}. {rule['rule_name']}: +{adj_pct:.1f}% "
                f"(n={rule['sample_size']}, conf={rule['confidence']:.2f})"
            )

        lines.append("")

        # マイナス効果TOP10
        lines.extend([
            "【マイナス効果 TOP10】"
        ])
        for i, rule in enumerate(sorted_rules[-10:], 1):
            adj_pct = rule['adjustment'] * 100
            lines.append(
                f"  {i:2d}. {rule['rule_name']}: {adj_pct:.1f}% "
                f"(n={rule['sample_size']}, conf={rule['confidence']:.2f})"
            )

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)


if __name__ == "__main__":
    # テスト
    print("ルール抽出システム テスト")
    print("-" * 40)

    extractor = RuleExtractor()

    try:
        # 全ルール抽出
        rules = extractor.extract_all_rules(min_confidence=0.3)

        # レポート表示
        print(extractor.generate_report(rules))

        # DBに保存
        extractor.save_rules_to_db(rules)

        # 適用テスト
        print("\n【適用テスト】")
        print("条件: 桐生, 1号艇, 追風")
        applicable = extractor.get_applicable_rules(
            venue_code='01',
            pit_number=1,
            wind_direction='追'
        )

        total_adj, names = extractor.calculate_total_adjustment(applicable)
        print(f"適用ルール: {names}")
        print(f"合計加算値: {total_adj * 100:.1f}%")

    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
