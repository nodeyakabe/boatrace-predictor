"""
潮位補正モジュール

潮位（満潮/干潮/上げ潮/下げ潮）に基づいて予測スコアを補正する
海水・汽水会場のみに適用
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
from pathlib import Path


class TideAdjuster:
    """潮位に基づくスコア補正クラス"""

    # 観測所名 → 対応会場コードのマッピング
    STATION_TO_VENUES = {
        'Hiroshima': ['16'],          # 宮島
        'Tokuyama': ['17', '18'],     # 徳山、下関
        'Hakata': ['21', '22', '23'], # 福岡、芦屋、若松
        'Sasebo': ['24'],             # 大村
    }

    # 会場別潮位補正係数（分析結果に基づく）
    # 上げ潮時の1号艇勝率差分を基に算出
    # positive = 上げ潮で1コース有利、negative = 下げ潮で1コース有利
    VENUE_TIDE_COEFFICIENTS = {
        '17': {  # 徳山: 上げ潮で+14.7%の差
            'rising_course1_bonus': 0.07,      # +7%（差分の半分を適用）
            'falling_course1_penalty': -0.07,  # -7%
            'rising_outer_penalty': -0.02,     # 外コースペナルティ
            'falling_outer_bonus': 0.02,       # 外コースボーナス
        },
        '16': {  # 宮島: 上げ潮で+9.8%の差
            'rising_course1_bonus': 0.05,      # +5%
            'falling_course1_penalty': -0.05,  # -5%
            'rising_outer_penalty': -0.015,
            'falling_outer_bonus': 0.015,
        },
        '23': {  # 若松: 下げ潮で+6.6%（逆パターン）
            'rising_course1_bonus': -0.03,     # -3%（上げ潮で不利）
            'falling_course1_penalty': 0.03,   # +3%（下げ潮で有利）
            'rising_outer_penalty': 0.01,
            'falling_outer_bonus': -0.01,
        },
        '21': {  # 福岡: 標準パターン
            'rising_course1_bonus': 0.02,
            'falling_course1_penalty': -0.02,
            'rising_outer_penalty': -0.01,
            'falling_outer_bonus': 0.01,
        },
        '22': {  # 芦屋: 標準パターン
            'rising_course1_bonus': 0.02,
            'falling_course1_penalty': -0.02,
            'rising_outer_penalty': -0.01,
            'falling_outer_bonus': 0.01,
        },
        '18': {  # 下関: 徳山に準ずる
            'rising_course1_bonus': 0.04,
            'falling_course1_penalty': -0.04,
            'rising_outer_penalty': -0.015,
            'falling_outer_bonus': 0.015,
        },
        '24': {  # 大村: 標準パターン
            'rising_course1_bonus': 0.02,
            'falling_course1_penalty': -0.02,
            'rising_outer_penalty': -0.01,
            'falling_outer_bonus': 0.01,
        },
    }

    # デフォルト補正係数（会場別データがない場合）
    DEFAULT_TIDE_COEFFICIENTS = {
        'rising_course1_bonus': 0.02,
        'falling_course1_penalty': -0.02,
        'rising_outer_penalty': -0.01,
        'falling_outer_bonus': 0.01,
    }

    # 会場コード → 観測所名の逆引き
    VENUE_TO_STATION = {}
    for station, venues in STATION_TO_VENUES.items():
        for venue in venues:
            VENUE_TO_STATION[venue] = station

    # 海水/汽水会場（潮位の影響を受ける会場）
    SEAWATER_VENUES = {
        '02': '戸田',      # 汽水
        '06': '浜名湖',    # 汽水
        '07': '蒲郡',      # 海水
        '08': '常滑',      # 海水
        '09': '津',        # 海水
        '12': '住之江',    # 海水
        '14': '鳴門',      # 海水
        '15': '丸亀',      # 海水
        '16': '宮島',      # 海水
        '17': '徳山',      # 海水
        '18': '下関',      # 海水
        '19': '若松',      # 海水（23と同じ）
        '20': '芦屋',      # 海水（22と同じ）
        '21': '福岡',      # 海水
        '22': '芦屋',      # 海水
        '23': '若松',      # 海水（唐津）
        '24': '大村',      # 海水
    }

    # 潮位データがある会場（観測所からの推定）
    TIDE_DATA_VENUES = set(VENUE_TO_STATION.keys())

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path

    def get_tide_level(
        self,
        venue_code: str,
        race_datetime: datetime
    ) -> Optional[Dict]:
        """
        指定会場・日時の潮位データを取得

        Args:
            venue_code: 会場コード
            race_datetime: レース日時

        Returns:
            {
                'sea_level_cm': 潮位(cm),
                'tide_phase': 潮位フェーズ('rising'/'falling'/'high'/'low'),
                'station': 観測所名
            }
            または None（データなし）
        """
        station = self.VENUE_TO_STATION.get(venue_code)
        if not station:
            return None

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # レース時刻の前後30分のデータを取得
            dt_str = race_datetime.strftime('%Y-%m-%d %H:%M:%S')
            dt_before = (race_datetime - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
            dt_after = (race_datetime + timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')

            cursor.execute("""
                SELECT observation_datetime, sea_level_cm
                FROM rdmdb_tide
                WHERE station_name = ?
                AND observation_datetime BETWEEN ? AND ?
                ORDER BY observation_datetime
            """, (station, dt_before, dt_after))

            rows = cursor.fetchall()
            if not rows:
                return None

            # 最も近い時刻のデータを取得
            closest_row = min(rows, key=lambda r: abs(
                datetime.strptime(r['observation_datetime'], '%Y-%m-%d %H:%M:%S') - race_datetime
            ))

            sea_level = closest_row['sea_level_cm']

            # 潮位フェーズを判定（前後のデータから傾向を見る）
            tide_phase = self._determine_tide_phase(rows, closest_row)

            return {
                'sea_level_cm': sea_level,
                'tide_phase': tide_phase,
                'station': station
            }

        finally:
            conn.close()

    def _determine_tide_phase(
        self,
        rows: List,
        current_row
    ) -> str:
        """
        潮位の変化傾向からフェーズを判定
        より広い時間幅（10分前後）で変化を判定

        Returns:
            'rising': 上げ潮
            'falling': 下げ潮
            'high': 満潮付近
            'low': 干潮付近
        """
        if len(rows) < 3:
            return 'unknown'

        levels = [r['sea_level_cm'] for r in rows]
        current_level = current_row['sea_level_cm']
        current_idx = next(
            (i for i, r in enumerate(rows) if r['observation_datetime'] == current_row['observation_datetime']),
            len(rows) // 2
        )

        # より広い範囲（10分前後）で変化を判定
        # 1分間隔データなので10レコード = 10分
        offset = min(10, current_idx, len(levels) - 1 - current_idx)

        if offset < 3:
            return 'unknown'

        before = levels[current_idx - offset]
        after = levels[current_idx + offset]

        # 変化量
        change_before = current_level - before
        change_after = after - current_level

        # 満潮・干潮の判定（変化方向が逆転）
        # しきい値を設定（1cm以上の変化を有意とする）
        threshold = 1.0

        if change_before > threshold and change_after < -threshold:
            return 'high'  # 満潮
        elif change_before < -threshold and change_after > threshold:
            return 'low'   # 干潮
        elif change_before > threshold or change_after > threshold:
            return 'rising'  # 上げ潮
        elif change_before < -threshold or change_after < -threshold:
            return 'falling'  # 下げ潮
        else:
            # 変化が小さい場合は満潮/干潮付近
            # 現在値と全体平均を比較
            avg_level = sum(levels) / len(levels)
            if current_level > avg_level + 10:
                return 'high'
            elif current_level < avg_level - 10:
                return 'low'

        return 'unknown'

    def get_tide_category(self, sea_level_cm: float, station: str) -> str:
        """
        潮位レベルをカテゴリ化

        Args:
            sea_level_cm: 潮位(cm)
            station: 観測所名

        Returns:
            'high' / 'mid' / 'low'
        """
        # 観測所ごとの平均潮位を基準に判定
        # （実際のデータ分析後に調整が必要）
        STATION_AVERAGES = {
            'Hiroshima': 200,
            'Tokuyama': 180,
            'Hakata': 190,
            'Sasebo': 170,
        }

        avg = STATION_AVERAGES.get(station, 180)
        deviation = sea_level_cm - avg

        if deviation > 50:
            return 'high'
        elif deviation < -50:
            return 'low'
        else:
            return 'mid'

    def calculate_adjustment(
        self,
        venue_code: str,
        course: int,
        race_datetime: Optional[datetime] = None,
        tide_data: Optional[Dict] = None
    ) -> Dict:
        """
        潮位に基づくスコア補正を計算

        Args:
            venue_code: 会場コード
            course: コース番号（1-6）
            race_datetime: レース日時（tide_dataがない場合に使用）
            tide_data: 事前に取得した潮位データ

        Returns:
            {
                'adjustment': 補正値（-0.05 ~ +0.05）,
                'reason': 補正理由,
                'tide_phase': 潮位フェーズ,
                'sea_level_cm': 潮位
            }
        """
        result = {
            'adjustment': 0.0,
            'reason': '',
            'tide_phase': 'unknown',
            'sea_level_cm': None,
            'tide_category': 'unknown'
        }

        # 海水会場でない場合は補正なし
        if venue_code not in self.SEAWATER_VENUES:
            result['reason'] = '淡水会場（潮位影響なし）'
            return result

        # 潮位データを取得
        if tide_data is None and race_datetime:
            tide_data = self.get_tide_level(venue_code, race_datetime)

        if tide_data is None:
            # 潮位データがない会場
            if venue_code not in self.TIDE_DATA_VENUES:
                result['reason'] = f'潮位データ未対応会場'
            else:
                result['reason'] = '潮位データなし'
            return result

        result['sea_level_cm'] = tide_data['sea_level_cm']
        result['tide_phase'] = tide_data['tide_phase']
        result['tide_category'] = self.get_tide_category(
            tide_data['sea_level_cm'],
            tide_data['station']
        )

        reasons = []
        adjustment = 0.0

        # 会場別補正係数を取得
        venue_coef = self.VENUE_TIDE_COEFFICIENTS.get(
            venue_code, self.DEFAULT_TIDE_COEFFICIENTS
        )

        # === 潮位フェーズによる補正（会場別係数を使用） ===
        phase = tide_data['tide_phase']

        if phase == 'rising':
            # 上げ潮: 会場別に1コースへの影響が異なる
            if course == 1:
                bonus = venue_coef.get('rising_course1_bonus', 0.02)
                if bonus != 0:
                    adjustment += bonus
                    if bonus > 0:
                        reasons.append(f'上げ潮1コースボーナス({bonus:+.0%})')
                    else:
                        reasons.append(f'上げ潮1コースペナルティ({bonus:+.0%})')
            elif course in [4, 5, 6]:
                penalty = venue_coef.get('rising_outer_penalty', -0.01)
                if penalty != 0:
                    adjustment += penalty
                    if penalty < 0:
                        reasons.append(f'上げ潮外コースペナルティ({penalty:+.0%})')
                    else:
                        reasons.append(f'上げ潮外コースボーナス({penalty:+.0%})')

        elif phase == 'falling':
            # 下げ潮: 会場別にパターンが異なる
            if course == 1:
                penalty = venue_coef.get('falling_course1_penalty', -0.02)
                if penalty != 0:
                    adjustment += penalty
                    if penalty < 0:
                        reasons.append(f'下げ潮1コースペナルティ({penalty:+.0%})')
                    else:
                        reasons.append(f'下げ潮1コースボーナス({penalty:+.0%})')
            elif course in [3, 4, 5, 6]:
                bonus = venue_coef.get('falling_outer_bonus', 0.01)
                if bonus != 0:
                    adjustment += bonus
                    if bonus > 0:
                        reasons.append(f'下げ潮{course}コースボーナス({bonus:+.0%})')
                    else:
                        reasons.append(f'下げ潮{course}コースペナルティ({bonus:+.0%})')

        elif phase == 'high':
            # 満潮: 水面安定、一般的にインコース有利
            if course == 1:
                # 満潮は上げ潮の終端なので、rising係数の1.2倍を適用
                bonus = venue_coef.get('rising_course1_bonus', 0.02) * 1.2
                if bonus != 0:
                    adjustment += bonus
                    if bonus > 0:
                        reasons.append(f'満潮1コースボーナス({bonus:+.0%})')
                    else:
                        reasons.append(f'満潮1コースペナルティ({bonus:+.0%})')

        elif phase == 'low':
            # 干潮: 水面不安定、一般的にインコース不利
            if course == 1:
                # 干潮は下げ潮の終端なので、falling係数の1.2倍を適用
                penalty = venue_coef.get('falling_course1_penalty', -0.02) * 1.2
                if penalty != 0:
                    adjustment += penalty
                    if penalty < 0:
                        reasons.append(f'干潮1コースペナルティ({penalty:+.0%})')
                    else:
                        reasons.append(f'干潮1コースボーナス({penalty:+.0%})')
            elif course in [2, 3, 4]:
                bonus = venue_coef.get('falling_outer_bonus', 0.01) * 1.2
                if bonus != 0:
                    adjustment += bonus
                    if bonus > 0:
                        reasons.append(f'干潮{course}コースボーナス({bonus:+.0%})')
                    else:
                        reasons.append(f'干潮{course}コースペナルティ({bonus:+.0%})')

        result['adjustment'] = adjustment
        result['reason'] = ', '.join(reasons) if reasons else '補正なし'

        return result

    def get_venue_tide_stats(self, venue_code: str) -> Optional[Dict]:
        """
        会場の潮位統計を取得（分析用）

        Args:
            venue_code: 会場コード

        Returns:
            統計情報の辞書
        """
        station = self.VENUE_TO_STATION.get(venue_code)
        if not station:
            return None

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    MIN(sea_level_cm) as min_level,
                    MAX(sea_level_cm) as max_level,
                    AVG(sea_level_cm) as avg_level,
                    COUNT(*) as data_count,
                    MIN(observation_datetime) as min_date,
                    MAX(observation_datetime) as max_date
                FROM rdmdb_tide
                WHERE station_name = ?
            """, (station,))

            row = cursor.fetchone()
            if row and row[3] > 0:
                return {
                    'station': station,
                    'venue_code': venue_code,
                    'min_level': row[0],
                    'max_level': row[1],
                    'avg_level': row[2],
                    'data_count': row[3],
                    'date_range': f"{row[4][:10]} ~ {row[5][:10]}"
                }
            return None

        finally:
            conn.close()


# テスト用
if __name__ == "__main__":
    adjuster = TideAdjuster()

    print("=== 潮位補正モジュール テスト ===")
    print()

    # 対応会場の確認
    print("【潮位データ対応会場】")
    for venue, name in sorted(adjuster.SEAWATER_VENUES.items()):
        station = adjuster.VENUE_TO_STATION.get(venue, '-')
        status = '○' if station != '-' else '×'
        print(f"  {venue}: {name} → {station} [{status}]")
    print()

    # 統計確認
    print("【会場別潮位統計】")
    for venue in adjuster.TIDE_DATA_VENUES:
        stats = adjuster.get_venue_tide_stats(venue)
        if stats:
            print(f"  {venue}({stats['station']}): "
                  f"平均{stats['avg_level']:.1f}cm "
                  f"(範囲: {stats['min_level']:.0f}~{stats['max_level']:.0f}cm) "
                  f"[{stats['data_count']:,}件]")
        else:
            print(f"  {venue}: データなし")
    print()

    # 補正テスト
    print("【補正計算テスト】")
    test_cases = [
        ('16', 1, {'sea_level_cm': 250, 'tide_phase': 'high', 'station': 'Hiroshima'}),
        ('16', 1, {'sea_level_cm': 150, 'tide_phase': 'low', 'station': 'Hiroshima'}),
        ('17', 3, {'sea_level_cm': 200, 'tide_phase': 'falling', 'station': 'Tokuyama'}),
        ('01', 1, None),  # 淡水会場
    ]

    for venue, course, tide_data in test_cases:
        result = adjuster.calculate_adjustment(venue, course, tide_data=tide_data)
        print(f"  会場{venue} {course}コース: {result['adjustment']:+.1%} ({result['reason']})")
