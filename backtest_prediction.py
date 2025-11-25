"""
過去データ予想テスト - バックテスト機能

収集済みの過去データを使って予想ロジックの精度を検証する
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
from datetime import datetime, timedelta
import pandas as pd
from collections import defaultdict

from config.settings import DATABASE_PATH


class PredictionBacktester:
    """予想バックテスター"""

    def __init__(self, db_path=DATABASE_PATH):
        self.db_path = db_path

    def get_test_races(self, start_date, end_date, venue_code=None):
        """
        テスト対象のレースを取得

        Args:
            start_date: 開始日
            end_date: 終了日
            venue_code: 会場コード（Noneの場合は全会場）

        Returns:
            list: レース情報のリスト
        """
        conn = sqlite3.connect(self.db_path)

        # SQLインジェクション対策: パラメータ化クエリを使用
        if venue_code:
            query = """
                SELECT
                    r.id,
                    r.venue_code,
                    r.race_date,
                    r.race_number,
                    r.race_time
                FROM races r
                WHERE r.race_date BETWEEN ? AND ?
                AND r.venue_code = ?
                ORDER BY r.race_date, r.venue_code, r.race_number
            """
            params = (start_date, end_date, venue_code)
        else:
            query = """
                SELECT
                    r.id,
                    r.venue_code,
                    r.race_date,
                    r.race_number,
                    r.race_time
                FROM races r
                WHERE r.race_date BETWEEN ? AND ?
                ORDER BY r.race_date, r.venue_code, r.race_number
            """
            params = (start_date, end_date)

        df = pd.read_sql_query(query, conn, params=params)
        conn.close()

        return df.to_dict('records')

    def get_race_features(self, race_id, hide_results=True):
        """
        レースの特徴量を取得（結果を隠す）

        Args:
            race_id: レースID
            hide_results: 結果を隠すかどうか

        Returns:
            dict: レース特徴量
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # レース基本情報
        cursor.execute("""
            SELECT
                r.venue_code,
                r.race_date,
                r.race_number,
                r.race_time,
                r.race_grade
            FROM races r
            WHERE r.id = ?
        """, (race_id,))

        race_info = cursor.fetchone()
        if not race_info:
            conn.close()
            return None

        features = {
            'race_id': race_id,
            'venue_code': race_info[0],
            'race_date': race_info[1],
            'race_number': race_info[2],
            'race_time': race_info[3],
            'race_grade': race_info[4],
            'boats': []
        }

        # 各艇の情報
        cursor.execute("""
            SELECT
                rd.pit_number,
                rd.racer_id,
                rd.actual_course,
                rd.start_timing,
                rd.chokushin_time,
                rd.isshu_time,
                rd.mawariashi_time,
                rd.motor_number,
                rd.boat_number,
                rd.motor_2rate,
                rd.motor_3rate,
                rd.boat_2rate,
                rd.boat_3rate,
                rd.racer_rank,
                rd.racer_win_rate,
                rd.racer_show_rate
            FROM race_details rd
            WHERE rd.race_id = ?
            ORDER BY rd.pit_number
        """, (race_id,))

        boats_data = cursor.fetchall()

        for boat in boats_data:
            boat_info = {
                'pit_number': boat[0],
                'racer_id': boat[1],
                'actual_course': boat[2],
                'start_timing': boat[3],
                'chokushin_time': boat[4],
                'isshu_time': boat[5],
                'mawariashi_time': boat[6],
                'motor_number': boat[7],
                'boat_number': boat[8],
                'motor_2rate': boat[9],
                'motor_3rate': boat[10],
                'boat_2rate': boat[11],
                'boat_3rate': boat[12],
                'racer_rank': boat[13],
                'racer_win_rate': boat[14],
                'racer_show_rate': boat[15]
            }

            # 結果を隠さない場合は追加
            if not hide_results:
                cursor.execute("""
                    SELECT rank, race_time, kimarite
                    FROM results
                    WHERE race_id = ? AND pit_number = ?
                """, (race_id, boat[0]))

                result = cursor.fetchone()
                if result:
                    boat_info['result_rank'] = result[0]
                    boat_info['result_time'] = result[1]
                    boat_info['result_kimarite'] = result[2]

            features['boats'].append(boat_info)

        # 天候情報
        cursor.execute("""
            SELECT temperature, water_temp, wave_height
            FROM weather
            WHERE venue_code = ? AND weather_date = ?
            LIMIT 1
        """, (features['venue_code'], features['race_date']))

        weather = cursor.fetchone()
        if weather:
            features['temperature'] = weather[0]
            features['water_temp'] = weather[1]
            features['wave_height'] = weather[2]

        conn.close()
        return features

    def predict_simple(self, race_features):
        """
        シンプルな予想ロジック

        Args:
            race_features: レース特徴量

        Returns:
            dict: 予想結果
        """
        boats = race_features['boats']

        if not boats or len(boats) < 6:
            return None

        # 各艇のスコアを計算
        scores = []

        for boat in boats:
            score = 0

            # 1. コース別基礎点
            course = boat.get('actual_course')
            if course == 1:
                score += 50
            elif course == 2:
                score += 20
            elif course == 3:
                score += 15
            elif course == 4:
                score += 10
            elif course == 5:
                score += 3
            elif course == 6:
                score += 2

            # 2. 選手級別
            rank = boat.get('racer_rank')
            if rank == 'A1':
                score += 30
            elif rank == 'A2':
                score += 20
            elif rank == 'B1':
                score += 10
            elif rank == 'B2':
                score += 5

            # 3. 選手勝率
            win_rate = boat.get('racer_win_rate')
            if win_rate:
                score += win_rate * 3

            # 4. モーター2連率
            motor_2rate = boat.get('motor_2rate')
            if motor_2rate:
                score += motor_2rate * 0.3

            # 5. 展示タイム
            chokushin = boat.get('chokushin_time')
            if chokushin:
                # 直進タイムが速いほど加点（6.5秒以下が優秀）
                if chokushin <= 6.5:
                    score += 10
                elif chokushin <= 6.7:
                    score += 5

            scores.append({
                'pit_number': boat['pit_number'],
                'score': score
            })

        # スコア順にソート
        scores.sort(key=lambda x: x['score'], reverse=True)

        return {
            'win_prediction': scores[0]['pit_number'],
            'place_predictions': [s['pit_number'] for s in scores[:3]],
            'scores': scores
        }

    def evaluate_prediction(self, prediction, actual_results):
        """
        予想を評価

        Args:
            prediction: 予想結果
            actual_results: 実際の結果

        Returns:
            dict: 評価結果
        """
        if not prediction or not actual_results:
            return None

        # 実際の1着
        actual_winner = None
        actual_top3 = []

        for boat in actual_results:
            rank = boat.get('result_rank')
            pit_number = boat.get('pit_number')

            if rank == 1:
                actual_winner = pit_number
            if rank in [1, 2, 3]:
                actual_top3.append(pit_number)

        if not actual_winner:
            return None

        # 評価
        win_hit = prediction['win_prediction'] == actual_winner
        place_hit = prediction['win_prediction'] in actual_top3

        # 複勝的中数
        place_predictions = prediction['place_predictions']
        place_hit_count = sum(1 for p in place_predictions if p in actual_top3)

        return {
            'win_hit': win_hit,
            'place_hit': place_hit,
            'place_hit_count': place_hit_count,
            'predicted_winner': prediction['win_prediction'],
            'actual_winner': actual_winner,
            'predicted_top3': place_predictions,
            'actual_top3': actual_top3
        }

    def run_backtest(self, start_date, end_date, venue_code=None):
        """
        バックテストを実行

        Args:
            start_date: 開始日
            end_date: 終了日
            venue_code: 会場コード（Noneの場合は全会場）

        Returns:
            dict: バックテスト結果
        """
        print("="*80)
        print("予想バックテスト")
        print("="*80)
        print(f"期間: {start_date} ～ {end_date}")
        if venue_code:
            print(f"会場: {venue_code}")
        else:
            print("会場: 全会場")
        print()

        # テスト対象レースを取得
        test_races = self.get_test_races(start_date, end_date, venue_code)

        if not test_races:
            print("対象レースが見つかりません")
            return None

        print(f"対象レース数: {len(test_races):,}レース")
        print()

        # 各レースで予想と評価
        results = []
        win_hits = 0
        place_hits = 0
        total_races = 0

        for i, race in enumerate(test_races, 1):
            race_id = race['id']

            # 特徴量取得（結果を隠す）
            features = self.get_race_features(race_id, hide_results=True)

            if not features or not features['boats']:
                continue

            # 予想実行
            prediction = self.predict_simple(features)

            if not prediction:
                continue

            # 実際の結果を取得
            actual_results = self.get_race_features(race_id, hide_results=False)

            # 評価
            evaluation = self.evaluate_prediction(prediction, actual_results['boats'])

            if evaluation:
                results.append({
                    'race': race,
                    'prediction': prediction,
                    'evaluation': evaluation
                })

                if evaluation['win_hit']:
                    win_hits += 1

                if evaluation['place_hit']:
                    place_hits += 1

                total_races += 1

            # 進捗表示
            if i % 100 == 0:
                print(f"処理中... {i}/{len(test_races)} レース")

        print()
        print("="*80)
        print("バックテスト結果")
        print("="*80)
        print(f"テスト実施レース数: {total_races:,}レース")
        print()
        print(f"単勝的中数: {win_hits:,}レース")
        print(f"単勝的中率: {win_hits/total_races*100:.2f}%" if total_races > 0 else "N/A")
        print()
        print(f"複勝的中数: {place_hits:,}レース")
        print(f"複勝的中率: {place_hits/total_races*100:.2f}%" if total_races > 0 else "N/A")
        print()

        # 会場別集計
        venue_stats = defaultdict(lambda: {'total': 0, 'win_hits': 0})
        for result in results:
            venue = result['race']['venue_code']
            venue_stats[venue]['total'] += 1
            if result['evaluation']['win_hit']:
                venue_stats[venue]['win_hits'] += 1

        if len(venue_stats) > 1:
            print("【会場別的中率】")
            for venue in sorted(venue_stats.keys()):
                stats = venue_stats[venue]
                rate = stats['win_hits'] / stats['total'] * 100 if stats['total'] > 0 else 0
                print(f"  {venue}: {stats['win_hits']}/{stats['total']} ({rate:.1f}%)")
            print()

        return {
            'total_races': total_races,
            'win_hits': win_hits,
            'win_rate': win_hits / total_races if total_races > 0 else 0,
            'place_hits': place_hits,
            'place_rate': place_hits / total_races if total_races > 0 else 0,
            'results': results,
            'venue_stats': dict(venue_stats)
        }


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='予想バックテスト')
    parser.add_argument('start_date', help='開始日 (YYYY-MM-DD)')
    parser.add_argument('end_date', help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--venue', help='会場コード（オプション）')

    args = parser.parse_args()

    # バックテスト実行
    backtester = PredictionBacktester()
    result = backtester.run_backtest(
        args.start_date,
        args.end_date,
        args.venue
    )

    if result:
        # 詳細結果をCSVに出力
        output_file = f"backtest_results_{args.start_date}_{args.end_date}.csv"

        data = []
        for r in result['results']:
            data.append({
                '日付': r['race']['race_date'],
                '会場': r['race']['venue_code'],
                'レース': r['race']['race_number'],
                '予想': r['evaluation']['predicted_winner'],
                '結果': r['evaluation']['actual_winner'],
                '単勝': '○' if r['evaluation']['win_hit'] else '×',
                '複勝': '○' if r['evaluation']['place_hit'] else '×'
            })

        df = pd.DataFrame(data)
        df.to_csv(output_file, index=False, encoding='utf-8-sig')

        print(f"詳細結果を保存しました: {output_file}")


if __name__ == "__main__":
    main()
