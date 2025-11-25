"""
リアルタイム予想機能
本日・これから開催されるレースの予想を自動生成
"""

import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
from src.scraper.schedule_scraper import ScheduleScraper
from src.analysis.race_predictor import RacePredictor
from config.settings import DATABASE_PATH


class RealtimePredictor:
    """リアルタイム予想マネージャー"""

    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self.schedule_scraper = ScheduleScraper()
        self.race_predictor = RacePredictor()

    def get_today_races(self) -> List[Dict]:
        """
        本日開催されるレース情報を取得

        Returns:
            [
                {
                    'venue_code': '01',
                    'venue_name': '桐生',
                    'date': '20251030',
                    'race_number': 1,
                    'status': 'upcoming' / 'finished'
                },
                ...
            ]
        """
        # スケジュールから本日の開催場を取得
        today_schedule = self.schedule_scraper.get_today_schedule()

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        races = []

        from config.settings import VENUES

        for venue_code, date in today_schedule.items():
            # データベースから本日のレース情報を取得
            cursor.execute("""
                SELECT
                    r.id as race_id,
                    r.venue_code,
                    r.race_date,
                    r.race_number,
                    r.race_time,
                    CASE
                        WHEN EXISTS (
                            SELECT 1 FROM results res
                            WHERE res.race_id = r.id
                            LIMIT 1
                        ) THEN 'finished'
                        ELSE 'upcoming'
                    END as status
                FROM races r
                WHERE r.venue_code = ? AND r.race_date = ?
                ORDER BY r.race_number
            """, (venue_code, date))

            race_rows = cursor.fetchall()

            for row in race_rows:
                # venue_codeからvenue_nameを取得
                venue_name = None
                for venue_id, venue_info in VENUES.items():
                    if venue_info['code'] == row['venue_code']:
                        venue_name = venue_info['name']
                        break

                races.append({
                    'race_id': row['race_id'],
                    'venue_code': row['venue_code'],
                    'venue_name': venue_name or f"会場{row['venue_code']}",
                    'date': row['race_date'],
                    'race_number': row['race_number'],
                    'race_time': row['race_time'] or '',
                    'status': row['status']
                })

        conn.close()

        return races

    def get_upcoming_races_only(self) -> List[Dict]:
        """
        本日のこれから開催されるレース（結果未確定）のみ取得

        Returns:
            レース情報のリスト（status='upcoming'のみ）
        """
        all_races = self.get_today_races()
        return [race for race in all_races if race['status'] == 'upcoming']

    def predict_race(self, race_id: int) -> Optional[List[Dict]]:
        """
        指定レースの予想を生成

        Args:
            race_id: レースID

        Returns:
            予想結果のリスト、またはNone
        """
        try:
            predictions = self.race_predictor.predict_race(race_id)
            return predictions
        except Exception as e:
            print(f"予想エラー (race_id={race_id}): {e}")
            return None

    def predict_all_upcoming_races(self) -> Dict[int, List[Dict]]:
        """
        本日のこれから開催されるすべてのレースの予想を生成

        Returns:
            {
                race_id: [予想結果リスト],
                ...
            }
        """
        upcoming_races = self.get_upcoming_races_only()
        predictions_dict = {}

        for race in upcoming_races:
            race_id = race['race_id']
            predictions = self.predict_race(race_id)

            if predictions:
                predictions_dict[race_id] = predictions

        return predictions_dict

    def get_race_with_prediction(self, race_id: int) -> Optional[Dict]:
        """
        レース情報と予想結果を統合して取得

        Args:
            race_id: レースID

        Returns:
            {
                'race_info': {...},
                'predictions': [...]
            }
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # レース基本情報を取得
        cursor.execute("""
            SELECT
                r.id as race_id,
                r.venue_code,
                r.venue_name,
                r.race_date,
                r.race_number,
                r.race_title,
                r.weather,
                r.wind_direction,
                r.wind_speed,
                r.wave_height,
                r.water_temp,
                r.air_temp
            FROM races r
            WHERE r.id = ?
        """, (race_id,))

        race_row = cursor.fetchone()
        conn.close()

        if not race_row:
            return None

        race_info = dict(race_row)

        # 予想を生成
        predictions = self.predict_race(race_id)

        return {
            'race_info': race_info,
            'predictions': predictions if predictions else []
        }

    def get_today_predictions_summary(self) -> Dict:
        """
        本日の予想サマリーを取得

        Returns:
            {
                'total_races': 24,
                'upcoming_races': 18,
                'finished_races': 6,
                'venues': [
                    {
                        'venue_code': '01',
                        'venue_name': '桐生',
                        'total': 12,
                        'upcoming': 8,
                        'finished': 4
                    },
                    ...
                ]
            }
        """
        races = self.get_today_races()

        total_races = len(races)
        upcoming_races = len([r for r in races if r['status'] == 'upcoming'])
        finished_races = len([r for r in races if r['status'] == 'finished'])

        # 会場ごとに集計
        venue_dict = {}
        for race in races:
            venue_code = race['venue_code']
            venue_name = race['venue_name']

            if venue_code not in venue_dict:
                venue_dict[venue_code] = {
                    'venue_code': venue_code,
                    'venue_name': venue_name,
                    'total': 0,
                    'upcoming': 0,
                    'finished': 0
                }

            venue_dict[venue_code]['total'] += 1
            if race['status'] == 'upcoming':
                venue_dict[venue_code]['upcoming'] += 1
            else:
                venue_dict[venue_code]['finished'] += 1

        venues = list(venue_dict.values())

        return {
            'total_races': total_races,
            'upcoming_races': upcoming_races,
            'finished_races': finished_races,
            'venues': venues
        }

    def close(self):
        """リソースを解放"""
        self.schedule_scraper.close()


if __name__ == "__main__":
    # テスト実行
    predictor = RealtimePredictor()

    print("="*70)
    print("リアルタイム予想テスト")
    print("="*70)

    # 本日のサマリーを表示
    summary = predictor.get_today_predictions_summary()

    print(f"\n【本日のレース状況】")
    print(f"総レース数: {summary['total_races']}")
    print(f"これから: {summary['upcoming_races']}")
    print(f"終了: {summary['finished_races']}")

    print(f"\n【会場別】")
    for venue in summary['venues']:
        print(f"  {venue['venue_name']}（{venue['venue_code']}）: "
              f"全{venue['total']}R（これから{venue['upcoming']}R、終了{venue['finished']}R）")

    # これからのレースを取得
    upcoming = predictor.get_upcoming_races_only()

    if upcoming:
        print(f"\n【これから開催されるレース】（{len(upcoming)}レース）")
        for race in upcoming[:5]:  # 最初の5レースのみ表示
            print(f"  {race['venue_name']} {race['race_number']}R")

        # 1つ目のレースの予想を表示
        first_race = upcoming[0]
        print(f"\n【予想例】{first_race['venue_name']} {first_race['race_number']}R")

        result = predictor.get_race_with_prediction(first_race['race_id'])

        if result and result['predictions']:
            print(f"  天候: {result['race_info'].get('weather', 'N/A')}")
            print(f"  風: {result['race_info'].get('wind_direction', 'N/A')} {result['race_info'].get('wind_speed', 'N/A')}m")

            print(f"\n  予想順位:")
            for pred in result['predictions'][:3]:
                print(f"    {pred['rank_prediction']}位: {pred['pit_number']}号艇 {pred['racer_name']} "
                      f"({pred['total_score']:.1f}点 / {pred['confidence']})")
    else:
        print("\n本日はこれ以上のレースがありません")

    predictor.close()

    print("\n" + "="*70)
    print("テスト完了")
    print("="*70)
