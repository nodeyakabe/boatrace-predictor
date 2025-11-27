"""
期待値ベース戦略のバックテストスクリプト

オッズデータと予測スコアを使って、期待値ベースの買い目戦略を検証する

使い方:
  python backtest_expected_value.py --start 2024-10-01 --end 2024-10-31 --min-ev 5
"""

import sys
import os
import argparse
from datetime import datetime
import sqlite3
from typing import List, Dict, Tuple
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import DATABASE_PATH, VENUES


class ExpectedValueBacktest:
    """期待値ベースのバックテストクラス"""

    def __init__(self, min_ev: float = 5.0, min_confidence: float = 50.0):
        """
        初期化

        Args:
            min_ev: 最小期待値(%)
            min_confidence: 最小信頼度(%)
        """
        self.min_ev = min_ev
        self.min_confidence = min_confidence
        self.confidence_map = {'A': 100, 'B': 80, 'C': 60, 'D': 40, 'E': 20}

    def calculate_expected_value(self, win_prob: float, odds: float) -> float:
        """
        期待値計算

        Args:
            win_prob: 的中確率
            odds: オッズ

        Returns:
            期待値(%)
        """
        ev = (win_prob * odds) - 1.0
        return ev * 100

    def get_races_with_odds(self, start_date: str, end_date: str) -> List[Tuple]:
        """オッズデータがあるレースを取得"""

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT
                r.id as race_id,
                r.race_date,
                r.venue_code,
                r.race_number
            FROM races r
            INNER JOIN trifecta_odds t ON r.id = t.race_id
            WHERE r.race_date BETWEEN ? AND ?
            ORDER BY r.race_date, r.venue_code, r.race_number
        """, (start_date, end_date))

        races = cursor.fetchall()
        conn.close()

        return races

    def get_race_prediction(self, race_id: int) -> List[Dict]:
        """レースの予測データを取得"""

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                pit_number,
                rank_prediction,
                total_score,
                confidence
            FROM race_predictions
            WHERE race_id = ?
            ORDER BY rank_prediction
        """, (race_id,))

        predictions = []
        for row in cursor.fetchall():
            predictions.append({
                'pit_number': row[0],
                'rank': row[1],
                'score': row[2],
                'confidence': row[3]
            })

        conn.close()
        return predictions

    def get_race_result(self, race_id: int) -> str:
        """レース結果を取得（3連単）"""

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT first_place, second_place, third_place
            FROM race_results
            WHERE race_id = ?
        """, (race_id,))

        result = cursor.fetchone()
        conn.close()

        if result and all(result):
            return f"{result[0]}-{result[1]}-{result[2]}"
        return None

    def get_odds(self, race_id: int, combination: str) -> float:
        """オッズを取得"""

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT odds
            FROM trifecta_odds
            WHERE race_id = ? AND combination = ?
        """, (race_id, combination))

        result = cursor.fetchone()
        conn.close()

        return result[0] if result else None

    def backtest(self, start_date: str, end_date: str) -> Dict:
        """バックテスト実行"""

        print("="*70)
        print("期待値ベース戦略バックテスト")
        print("="*70)
        print(f"\n期間: {start_date} 〜 {end_date}")
        print(f"最小期待値: {self.min_ev}%")
        print(f"最小信頼度: {self.min_confidence}%")
        print("="*70)

        # オッズデータがあるレースを取得
        races = self.get_races_with_odds(start_date, end_date)

        if not races:
            print("\n❌ オッズデータがあるレースが見つかりませんでした")
            return None

        print(f"\nオッズデータがあるレース: {len(races)}件")

        # バックテスト実行
        results = {
            'total_races': 0,
            'bet_races': 0,
            'hits': 0,
            'total_bet': 0,
            'total_return': 0,
            'roi': 0,
            'hit_rate': 0,
            'details': []
        }

        venue_names = {}
        for vid, vinfo in VENUES.items():
            venue_names[vinfo['code']] = vinfo['name']

        for idx, (race_id, race_date, venue_code, race_number) in enumerate(races, 1):
            venue_name = venue_names.get(venue_code, f'会場{venue_code}')

            # 予測データ取得
            predictions = self.get_race_prediction(race_id)

            if len(predictions) < 3:
                continue

            # 信頼度計算
            top3 = predictions[:3]
            top3_confidences = [self.confidence_map.get(p['confidence'], 50) for p in top3]
            weights = [0.5, 0.3, 0.2]
            confidence = sum(c * w for c, w in zip(top3_confidences, weights))

            # 信頼度フィルター
            if confidence < self.min_confidence:
                continue

            # 予測買い目
            first = top3[0]['pit_number']
            second = top3[1]['pit_number']
            third = top3[2]['pit_number']
            combination = f"{first}-{second}-{third}"

            # オッズ取得
            odds = self.get_odds(race_id, combination)

            if not odds:
                continue

            # 的中確率推定（スコアベース）
            total_score = sum(p['score'] for p in predictions)
            win_prob = (top3[0]['score'] / total_score) if total_score > 0 else 0.1

            # 期待値計算
            ev = self.calculate_expected_value(win_prob, odds)

            # 期待値フィルター
            if ev < self.min_ev:
                continue

            # レース結果取得
            actual_result = self.get_race_result(race_id)

            if not actual_result:
                continue

            # ベット実行
            bet_amount = 100  # 1レースあたり100円
            results['bet_races'] += 1
            results['total_bet'] += bet_amount

            # 的中判定
            hit = (combination == actual_result)

            if hit:
                results['hits'] += 1
                payout = bet_amount * odds
                results['total_return'] += payout
            else:
                payout = 0

            # 詳細記録
            results['details'].append({
                'race_date': race_date,
                'venue': venue_name,
                'race_number': race_number,
                'combination': combination,
                'odds': odds,
                'expected_value': ev,
                'confidence': confidence,
                'hit': hit,
                'bet': bet_amount,
                'return': payout,
                'actual_result': actual_result
            })

            # 進捗表示
            if idx % 100 == 0:
                print(f"  進捗: {idx}/{len(races)}件処理中...")

        results['total_races'] = len(races)

        # ROI計算
        if results['total_bet'] > 0:
            results['roi'] = (results['total_return'] / results['total_bet'] - 1) * 100
            results['hit_rate'] = (results['hits'] / results['bet_races']) * 100 if results['bet_races'] > 0 else 0

        return results

    def print_results(self, results: Dict):
        """結果を表示"""

        if not results:
            return

        print("\n" + "="*70)
        print("バックテスト結果")
        print("="*70)

        print(f"\n総レース数: {results['total_races']}件")
        print(f"購入レース数: {results['bet_races']}件 ({results['bet_races']/results['total_races']*100:.1f}%)")
        print(f"的中数: {results['hits']}件")
        print(f"的中率: {results['hit_rate']:.1f}%")
        print(f"\n総投資額: ¥{results['total_bet']:,}")
        print(f"総払戻額: ¥{results['total_return']:,}")
        print(f"収支: ¥{results['total_return'] - results['total_bet']:,}")
        print(f"ROI: {results['roi']:+.1f}%")

        # 統計
        if results['details']:
            evs = [d['expected_value'] for d in results['details']]
            odds_list = [d['odds'] for d in results['details']]
            confidences = [d['confidence'] for d in results['details']]

            print(f"\n平均期待値: {sum(evs)/len(evs):.1f}%")
            print(f"平均オッズ: {sum(odds_list)/len(odds_list):.1f}倍")
            print(f"平均信頼度: {sum(confidences)/len(confidences):.1f}%")

        # 的中詳細（最初の10件）
        if results['hits'] > 0:
            print("\n" + "-"*70)
            print("的中詳細（最初の10件）")
            print("-"*70)

            hit_details = [d for d in results['details'] if d['hit']][:10]

            for detail in hit_details:
                print(f"{detail['race_date']} {detail['venue']} {detail['race_number']}R")
                print(f"  買い目: {detail['combination']} ({detail['odds']:.1f}倍)")
                print(f"  期待値: {detail['expected_value']:+.1f}% | 信頼度: {detail['confidence']:.1f}%")
                print(f"  払戻: ¥{detail['return']:,}")

        print("\n" + "="*70)


def main():
    """メイン関数"""

    parser = argparse.ArgumentParser(
        description='期待値ベース戦略のバックテスト'
    )
    parser.add_argument(
        '--start',
        type=str,
        required=True,
        help='開始日（YYYY-MM-DD）'
    )
    parser.add_argument(
        '--end',
        type=str,
        required=True,
        help='終了日（YYYY-MM-DD）'
    )
    parser.add_argument(
        '--min-ev',
        type=float,
        default=5.0,
        help='最小期待値（%%）デフォルト: 5.0'
    )
    parser.add_argument(
        '--min-confidence',
        type=float,
        default=50.0,
        help='最小信頼度（%%）デフォルト: 50.0'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='結果をJSONファイルに保存'
    )

    args = parser.parse_args()

    # バックテスト実行
    backtest = ExpectedValueBacktest(
        min_ev=args.min_ev,
        min_confidence=args.min_confidence
    )

    results = backtest.backtest(args.start, args.end)

    if results:
        backtest.print_results(results)

        # JSON出力
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"\n結果を {args.output} に保存しました")


if __name__ == "__main__":
    main()
