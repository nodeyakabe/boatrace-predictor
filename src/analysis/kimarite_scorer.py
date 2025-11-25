"""
決まり手適性スコア計算モジュール
選手の決まり手傾向と会場のコース別決まり手傾向の相性を評価
"""

import sqlite3
from typing import Dict, Optional
from datetime import datetime, timedelta


class KimariteScorer:
    """決まり手適性スコア計算クラス"""

    # 決まり手の定義
    KIMARITE_NAMES = {
        1: '逃げ',
        2: '差し',
        3: 'まくり',
        4: 'まくり差し',
        5: '抜き',
        6: '恵まれ'
    }

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path

    def _connect(self):
        """データベース接続"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def calculate_kimarite_affinity_score(
        self,
        racer_number: int,
        venue_code: str,
        course: int,
        days: int = 180,
        max_score: float = 15.0
    ) -> Dict:
        """
        決まり手適性スコアを計算

        Args:
            racer_number: 選手登録番号
            venue_code: 会場コード
            course: コース番号（1-6）
            days: 過去何日間のデータを使用するか
            max_score: 最大スコア（デフォルト15点）

        Returns:
            {
                'score': 12.5,
                'racer_primary_kimarite': '逃げ',
                'venue_primary_kimarite': '逃げ',
                'match': True,
                'racer_kimarite_rate': 65.0,
                'venue_kimarite_rate': 58.0,
                'confidence': 'High'
            }
        """
        conn = self._connect()
        cursor = conn.cursor()

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        # 選手のコース別決まり手傾向を取得
        query_racer = """
            SELECT r.winning_technique, COUNT(*) as count
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND e.pit_number = ?
              AND r.rank = 1
              AND r.winning_technique IS NOT NULL
              AND ra.race_date BETWEEN ? AND ?
            GROUP BY r.winning_technique
            ORDER BY count DESC
        """

        cursor.execute(query_racer, (racer_number, course, start_date.isoformat(), end_date.isoformat()))
        racer_kimarite = cursor.fetchall()

        # 会場のコース別決まり手傾向を取得
        query_venue = """
            SELECT r.winning_technique, COUNT(*) as count
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            WHERE ra.venue_code = ?
              AND r.pit_number = ?
              AND r.rank = 1
              AND r.winning_technique IS NOT NULL
              AND ra.race_date BETWEEN ? AND ?
            GROUP BY r.winning_technique
            ORDER BY count DESC
        """

        cursor.execute(query_venue, (venue_code, course, start_date.isoformat(), end_date.isoformat()))
        venue_kimarite = cursor.fetchall()

        conn.close()

        # データがない場合は中間スコアを返す
        if not racer_kimarite or not venue_kimarite:
            return {
                'score': max_score * 0.5,  # 中間スコア
                'racer_primary_kimarite': None,
                'venue_primary_kimarite': None,
                'match': False,
                'racer_kimarite_rate': 0.0,
                'venue_kimarite_rate': 0.0,
                'confidence': 'Low',
                'reason': 'insufficient_data'
            }

        # 選手の最頻決まり手
        racer_total = sum(row['count'] for row in racer_kimarite)
        racer_primary = racer_kimarite[0]
        racer_primary_technique = racer_primary['winning_technique']
        racer_primary_rate = racer_primary['count'] / racer_total * 100

        # 会場の最頻決まり手
        venue_total = sum(row['count'] for row in venue_kimarite)
        venue_primary = venue_kimarite[0]
        venue_primary_technique = venue_primary['winning_technique']
        venue_primary_rate = venue_primary['count'] / venue_total * 100

        # 選手の決まり手分布を辞書化
        racer_distribution = {row['winning_technique']: row['count'] / racer_total for row in racer_kimarite}

        # 会場の決まり手分布を辞書化
        venue_distribution = {row['winning_technique']: row['count'] / venue_total for row in venue_kimarite}

        # スコア計算ロジック
        score = 0.0
        match = False

        # 1. 最頻決まり手が一致する場合: 高得点
        if racer_primary_technique == venue_primary_technique:
            match = True
            # 両方の出現率が高いほど高得点
            combined_rate = (racer_primary_rate + venue_primary_rate) / 2
            score = max_score * (combined_rate / 100)
        else:
            # 2. 一致しない場合: 選手の決まり手が会場でも出現するかを評価
            if venue_primary_technique in racer_distribution:
                # 選手も会場の最頻決まり手を使える
                racer_rate_for_venue_primary = racer_distribution[venue_primary_technique] * 100
                score = max_score * (racer_rate_for_venue_primary / 100) * 0.7
            else:
                # 全く合わない場合: 低スコア
                score = max_score * 0.3

        # 信頼度の判定
        if racer_total >= 10 and venue_total >= 30:
            if match and racer_primary_rate >= 50 and venue_primary_rate >= 40:
                confidence = 'High'
            elif match:
                confidence = 'Medium'
            else:
                confidence = 'Low'
        else:
            confidence = 'Low'

        return {
            'score': round(score, 2),
            'racer_primary_kimarite': self.KIMARITE_NAMES.get(racer_primary_technique, '不明'),
            'venue_primary_kimarite': self.KIMARITE_NAMES.get(venue_primary_technique, '不明'),
            'match': match,
            'racer_kimarite_rate': round(racer_primary_rate, 1),
            'venue_kimarite_rate': round(venue_primary_rate, 1),
            'confidence': confidence,
            'racer_sample_size': racer_total,
            'venue_sample_size': venue_total
        }

    def calculate_batch_scores(
        self,
        entries: list,
        venue_code: str,
        days: int = 180,
        max_score: float = 15.0
    ) -> Dict[int, Dict]:
        """
        複数の出走艇の決まり手適性スコアを一括計算

        Args:
            entries: [(racer_number, pit_number), ...]
            venue_code: 会場コード
            days: 過去何日間のデータを使用するか
            max_score: 最大スコア

        Returns:
            {
                1: {'score': 12.5, ...},
                2: {'score': 8.3, ...},
                ...
            }
        """
        results = {}

        for racer_number, pit_number in entries:
            score_data = self.calculate_kimarite_affinity_score(
                racer_number, venue_code, pit_number, days, max_score
            )
            results[pit_number] = score_data

        return results


if __name__ == "__main__":
    # テスト
    scorer = KimariteScorer()

    print("=" * 80)
    print("決まり手適性スコア計算テスト")
    print("=" * 80)

    # テストケース
    racer_number = 4320
    venue_code = "03"  # 江戸川
    course = 1

    print(f"\n選手番号: {racer_number}")
    print(f"会場: {venue_code}")
    print(f"コース: {course}")

    result = scorer.calculate_kimarite_affinity_score(racer_number, venue_code, course)

    print("\n【結果】")
    print(f"スコア: {result['score']:.2f}/15.0")
    print(f"選手の得意決まり手: {result['racer_primary_kimarite']} ({result['racer_kimarite_rate']}%)")
    print(f"会場の主要決まり手: {result['venue_primary_kimarite']} ({result['venue_kimarite_rate']}%)")
    print(f"相性: {'◎ 一致' if result['match'] else '△ 不一致'}")
    print(f"信頼度: {result['confidence']}")

    if 'reason' in result:
        print(f"理由: {result['reason']}")
    else:
        print(f"サンプル数: 選手={result['racer_sample_size']}回, 会場={result['venue_sample_size']}回")

    print("\n" + "=" * 80)
