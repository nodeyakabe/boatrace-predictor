"""
レース監視モジュール

購入対象レースの締切時刻を監視し、適切なタイミングで通知・直前情報取得を実行
※ BetTargetEvaluatorと統合し、実際の購入判定ロジックを使用
"""

import os
import sys
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.automation.notify import (
    send_race_notification,
    send_error_notification
)
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus
from src.betting.multi_bet_generator import MultiBetPattern


class RaceMonitor:
    """レース監視クラス"""

    def __init__(self, db_path: str):
        """
        Args:
            db_path: データベースパス
        """
        self.db_path = db_path
        self.notified_races = set()  # 通知済みレースID
        self.fetched_direct_info = set()  # 直前情報取得済みレースID

        # BetTargetEvaluatorを初期化（実際の購入判定ロジックを使用）
        self.bet_evaluator = BetTargetEvaluator(
            use_multi_bet=True,
            multi_bet_pattern=MultiBetPattern.PATTERN_H,
            enable_venue_wind_filter=True,
            enable_venue_course_adjustment=True,
            db_path=db_path
        )

    def get_connection(self) -> sqlite3.Connection:
        """DB接続を取得"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_todays_target_races(self) -> List[Dict]:
        """
        本日の購入対象レースと候補レースを取得

        BetTargetEvaluatorを使用して実際の購入判定を行う

        Returns:
            List[Dict]: レース情報リスト（購入対象+候補レース）
        """
        today = datetime.now().strftime('%Y-%m-%d')

        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            # 本日の全レースを取得
            cursor.execute("""
                SELECT
                    r.id as race_id,
                    r.race_date,
                    r.venue_code,
                    r.race_number,
                    r.race_time
                FROM races r
                WHERE r.race_date = ?
                ORDER BY r.race_time
            """, (today,))

            races = []
            for row in cursor.fetchall():
                race_id = row['race_id']

                # レースデータを取得
                race_data = self._get_race_data(cursor, race_id)
                if not race_data:
                    continue

                # 予測データを取得
                predictions = self._get_predictions(cursor, race_id)
                if not predictions:
                    continue

                # オッズデータを取得
                odds_data = self._get_odds_data(cursor, race_id, predictions)

                # BetTargetEvaluatorで購入判定
                bet_target = self.bet_evaluator.evaluate_race(
                    race_data=race_data,
                    predictions=predictions,
                    odds_data=odds_data,
                    has_beforeinfo=False
                )

                # 購入対象と候補レースを追加
                if bet_target.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED, BetStatus.CANDIDATE]:
                    race_info = {
                        'race_id': race_id,
                        'date': row['race_date'],
                        'venue_code': f"{row['venue_code']:02d}" if isinstance(row['venue_code'], int) else str(row['venue_code']).zfill(2),
                        'race_number': row['race_number'],
                        'deadline': row['race_time'],
                        'bet_target': bet_target,  # BetTarget情報を保持
                        'race_data': race_data,
                        'predictions': predictions
                    }
                    races.append(race_info)

            return races

        finally:
            conn.close()

    def _get_race_data(self, cursor, race_id: int) -> Optional[Dict]:
        """レースデータを取得"""
        cursor.execute("""
            SELECT
                r.id,
                r.venue_code,
                r.race_number,
                r.race_date,
                r.race_time
            FROM races r
            WHERE r.id = ?
        """, (race_id,))

        race_row = cursor.fetchone()
        if not race_row:
            return None

        # 気象情報を取得
        cursor.execute("""
            SELECT wind_speed
            FROM race_conditions
            WHERE race_id = ?
        """, (race_id,))

        conditions_row = cursor.fetchone()
        wind_speed = conditions_row['wind_speed'] if conditions_row and conditions_row['wind_speed'] else 0.0

        # エントリー情報を取得
        cursor.execute("""
            SELECT
                pit_number,
                racer_number,
                racer_name,
                racer_rank,
                motor_second_rate,
                second_rate
            FROM entries
            WHERE race_id = ?
            ORDER BY pit_number
        """, (race_id,))

        entries = [dict(row) for row in cursor.fetchall()]

        return {
            'id': race_row['id'],
            'venue_code': race_row['venue_code'],
            'race_number': race_row['race_number'],
            'race_date': race_row['race_date'],
            'race_time': race_row['race_time'],
            'wind_speed': wind_speed,
            'entries': entries
        }

    def _get_predictions(self, cursor, race_id: int) -> Optional[Dict]:
        """予測データを取得"""
        cursor.execute("""
            SELECT
                pit_number,
                rank_prediction,
                confidence
            FROM race_predictions
            WHERE race_id = ?
              AND prediction_type = 'advance'
            ORDER BY rank_prediction
        """, (race_id,))

        predictions = [dict(row) for row in cursor.fetchall()]
        if len(predictions) < 3:
            return None

        # 1-2-3着予測を取得
        old_pred = [p['pit_number'] for p in predictions[:3]]

        return {
            'confidence': predictions[0]['confidence'],
            'old_prediction': old_pred,
            'new_prediction': old_pred  # 事前予測の段階では同じ
        }

    def _get_odds_data(self, cursor, race_id: int, predictions: Dict) -> Optional[Dict[str, float]]:
        """オッズデータを取得"""
        old_pred = predictions['old_prediction']
        combination = '-'.join(map(str, old_pred))

        cursor.execute("""
            SELECT odds
            FROM trifecta_odds
            WHERE race_id = ? AND combination = ?
        """, (race_id, combination))

        row = cursor.fetchone()
        if row and row['odds']:
            return {combination: row['odds']}

        return None

    def get_venue_name(self, venue_code: str) -> str:
        """
        会場コードから会場名を取得

        Args:
            venue_code: 会場コード

        Returns:
            str: 会場名
        """
        venue_map = {
            '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
            '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
            '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
            '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
            '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
            '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
        }
        return venue_map.get(venue_code, f"会場{venue_code}")

    def parse_deadline(self, date_str: str, deadline_str: str) -> datetime:
        """
        締切時刻をdatetimeに変換

        Args:
            date_str: 日付文字列 (YYYY-MM-DD)
            deadline_str: 締切時刻文字列 (HH:MM)

        Returns:
            datetime: 締切日時
        """
        deadline_datetime_str = f"{date_str} {deadline_str}"
        return datetime.strptime(deadline_datetime_str, '%Y-%m-%d %H:%M')

    def check_and_fetch_direct_info(self, race: Dict) -> bool:
        """
        直前情報取得が必要かチェックし、必要なら取得して再評価

        Args:
            race: レース情報

        Returns:
            bool: 直前情報を取得して再評価したらTrue
        """
        race_id = race['race_id']

        # 既に取得済みならスキップ
        if race_id in self.fetched_direct_info:
            return False

        deadline = self.parse_deadline(race['date'], race['deadline'])
        now = datetime.now()
        time_until_deadline = (deadline - now).total_seconds() / 60  # 分

        # 締切20分前に直前情報取得
        if 15 <= time_until_deadline <= 25:
            print(f"直前情報取得: {race_id} (締切まであと{time_until_deadline:.0f}分)")

            try:
                # 直前情報取得スクリプトを実行
                # TODO: 実際の直前情報取得スクリプトへのパス
                # result = subprocess.run(
                #     ["python", "scripts/data_collection/fetch_direct_info.py", race_id],
                #     capture_output=True,
                #     text=True,
                #     timeout=60
                # )

                self.fetched_direct_info.add(race_id)

                # 直前情報取得後、購入判定を再評価
                self._reevaluate_after_beforeinfo(race)

                return True

            except Exception as e:
                print(f"[ERROR] 直前情報取得エラー: {race_id} - {e}")
                send_error_notification("直前情報取得失敗", f"レースID: {race_id}\nエラー: {str(e)}")
                return False

        return False

    def _reevaluate_after_beforeinfo(self, race: Dict) -> None:
        """
        直前情報取得後に購入判定を再評価

        Args:
            race: レース情報
        """
        race_id = race['race_id']

        try:
            # 直前予測を取得
            conn = self.get_connection()
            try:
                cursor = conn.cursor()

                # 直前予測データを取得
                predictions = self._get_predictions_with_beforeinfo(cursor, race_id)
                if not predictions:
                    return

                # オッズデータを再取得
                odds_data = self._get_odds_data(cursor, race_id, predictions)

                # 購入判定を再評価（has_beforeinfo=True）
                bet_target = self.bet_evaluator.evaluate_race(
                    race_data=race['race_data'],
                    predictions=predictions,
                    odds_data=odds_data,
                    has_beforeinfo=True
                )

                # 元のステータスと比較
                old_status = race['bet_target'].status
                new_status = bet_target.status

                # ステータスが変化した場合
                if old_status != new_status:
                    print(f"  レース{race_id}: {old_status.value} → {new_status.value}")

                    # 候補から購入対象に昇格した場合
                    if old_status == BetStatus.CANDIDATE and new_status in [BetStatus.TARGET_CONFIRMED]:
                        print(f"  候補レースが購入対象に昇格: {race_id}")
                        # BetTarget情報を更新
                        race['bet_target'] = bet_target

            finally:
                conn.close()

        except Exception as e:
            print(f"[ERROR] 再評価エラー: {race_id} - {e}")

    def _get_predictions_with_beforeinfo(self, cursor, race_id: int) -> Optional[Dict]:
        """直前予測を含む予測データを取得"""
        # 事前予測
        cursor.execute("""
            SELECT pit_number, rank_prediction, confidence
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
        """, (race_id,))
        advance_preds = [dict(row) for row in cursor.fetchall()]

        # 直前予測
        cursor.execute("""
            SELECT pit_number, rank_prediction
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY rank_prediction
        """, (race_id,))
        before_preds = [dict(row) for row in cursor.fetchall()]

        if len(advance_preds) < 3:
            return None

        old_pred = [p['pit_number'] for p in advance_preds[:3]]
        new_pred = [p['pit_number'] for p in before_preds[:3]] if len(before_preds) >= 3 else old_pred

        return {
            'confidence': advance_preds[0]['confidence'],
            'old_prediction': old_pred,
            'new_prediction': new_pred
        }

    def check_and_notify(self, race: Dict) -> bool:
        """
        通知が必要かチェックし、必要なら通知

        Args:
            race: レース情報

        Returns:
            bool: 通知を送信したらTrue
        """
        race_id = race['race_id']

        # 既に通知済みならスキップ
        if race_id in self.notified_races:
            return False

        # 最新のBetTargetステータスを確認
        bet_target = race['bet_target']

        # 購入対象（TARGET_ADVANCE または TARGET_CONFIRMED）のみ通知
        if bet_target.status not in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            return False

        deadline = self.parse_deadline(race['date'], race['deadline'])
        now = datetime.now()
        time_until_deadline = (deadline - now).total_seconds() / 60  # 分

        # 締切10分前に通知
        if 8 <= time_until_deadline <= 12:
            print(f"通知送信: {race_id} (締切まであと{time_until_deadline:.0f}分)")

            # レース情報整形
            race_info = {
                'venue': self.get_venue_name(race['venue_code']),
                'race_number': race['race_number'],
                'deadline': race['deadline'],
                'race_id': race_id
            }

            # 予想情報整形（BetTargetから取得）
            # 複数点買いの場合はmulti_bet_resultから取得
            if bet_target.multi_bet_result and bet_target.multi_bet_result.combinations:
                # パターンH（3点買い）
                pit_numbers = bet_target.multi_bet_result.combinations
            else:
                # 1点買い
                pit_numbers = [int(x) for x in bet_target.combination.split('-')]

            prediction = {
                'pit_numbers': pit_numbers,
                'confidence': float(bet_target.confidence) if isinstance(bet_target.confidence, str) and bet_target.confidence in ['A', 'B', 'C', 'D'] else 0.7
            }

            # オッズ情報整形
            odds_info = {
                'trifecta_odds': bet_target.odds if bet_target.odds else 10.0,
            }

            # 直前情報があれば取得
            direct_info = None
            if race_id in self.fetched_direct_info:
                # TODO: DBから直前情報を取得
                pass

            # 通知送信
            try:
                success = send_race_notification(race_info, prediction, odds_info, direct_info)

                if success:
                    self.notified_races.add(race_id)
                    return True
                else:
                    print(f"[ERROR] 通知送信失敗: {race_id}")
                    return False

            except Exception as e:
                print(f"[ERROR] 通知送信エラー: {race_id} - {e}")
                send_error_notification("レース通知失敗", f"レースID: {race_id}\nエラー: {str(e)}")
                return False

        return False

    def monitor_once(self) -> Dict[str, int]:
        """
        1回の監視サイクルを実行

        Returns:
            Dict[str, int]: 実行結果統計
        """
        stats = {
            'total_races': 0,
            'direct_info_fetched': 0,
            'notifications_sent': 0,
            'errors': 0
        }

        try:
            # 本日の購入対象レース取得（BetTargetEvaluatorで判定済み）
            races = self.get_todays_target_races()
            stats['total_races'] = len(races)

            if not races:
                return stats

            # 各レースをチェック
            for race in races:
                try:
                    # 直前情報取得チェック（取得後に再評価も実行）
                    if self.check_and_fetch_direct_info(race):
                        stats['direct_info_fetched'] += 1

                    # 通知チェック（再評価後のステータスで判定）
                    if self.check_and_notify(race):
                        stats['notifications_sent'] += 1

                except Exception as e:
                    print(f"[ERROR] レース処理エラー: {race['race_id']} - {e}")
                    stats['errors'] += 1

        except Exception as e:
            print(f"[ERROR] 監視サイクルエラー: {e}")
            send_error_notification("監視サイクル失敗", str(e))
            stats['errors'] += 1

        return stats


def main():
    """メイン処理（テスト用）"""
    db_path = project_root / "data" / "boatrace.db"

    if not db_path.exists():
        print(f"[ERROR] データベースが見つかりません: {db_path}")
        return

    monitor = RaceMonitor(str(db_path))

    print("=" * 60)
    print("レース監視テスト")
    print("=" * 60)

    # 本日の購入対象レース表示
    races = monitor.get_todays_target_races()
    print(f"\n本日の購入対象レース: {len(races)}件")

    for race in races:
        deadline = monitor.parse_deadline(race['date'], race['deadline'])
        now = datetime.now()
        time_until = (deadline - now).total_seconds() / 60

        venue_name = monitor.get_venue_name(race['venue_code'])
        bet_target = race['bet_target']

        # 買い目情報
        if bet_target.multi_bet_result and bet_target.multi_bet_result.combinations:
            bet_info = f"{len(bet_target.multi_bet_result.combinations)}点買い"
        else:
            bet_info = "1点買い"

        print(f"  {venue_name} {race['race_number']}R - 締切: {race['deadline']} (あと{time_until:.0f}分) - {bet_info}")

    # 監視サイクル実行
    print("\n" + "=" * 60)
    print("監視サイクル実行")
    print("=" * 60)

    stats = monitor.monitor_once()

    print(f"\n実行結果:")
    print(f"  対象レース数: {stats['total_races']}")
    print(f"  直前情報取得: {stats['direct_info_fetched']}")
    print(f"  通知送信: {stats['notifications_sent']}")
    print(f"  エラー: {stats['errors']}")


if __name__ == "__main__":
    main()
