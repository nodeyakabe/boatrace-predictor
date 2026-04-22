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
    send_error_notification,
    send_discord_notification,
    format_race_notification,
)
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus
from src.betting.multi_bet_generator import MultiBetPattern
from src.betting.evaluator_helpers import create_standard_evaluator
from src.scraper.beforeinfo_scraper import BeforeInfoScraper

# 信頼度グレード→float変換マップ（notify.py の {confidence:.1%} フォーマット用）
_CONFIDENCE_FLOAT_MAP = {'A': 0.85, 'B': 0.70, 'C': 0.60, 'D': 0.50}


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
        self.fetched_odds_races = set()   # オッズ再取得済みレースID
        self._bet_target_cache = {}       # {race_id: race_dict} - 購入判定キャッシュ
        self._cache_date = None           # キャッシュの日付

        # BetTargetEvaluatorを初期化（標準設定を使用 - generate_daily_predictions.py と同じ設定）
        self.bet_evaluator = create_standard_evaluator(db_path=db_path)

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

        # 日付が変わったらキャッシュをリセット
        if self._cache_date != today:
            self._bet_target_cache = {}
            self._cache_date = today

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

                # キャッシュがあれば再評価をスキップ
                # ただし TARGET_ADVANCE はオッズがDBに保存されており変化する可能性があるため除外
                if race_id in self._bet_target_cache:
                    cached = self._bet_target_cache[race_id]
                    if cached['bet_target'].status != BetStatus.TARGET_ADVANCE:
                        races.append(cached)
                        continue

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

                # 直前情報の有無を動的に判定
                has_beforeinfo = race_id in self.fetched_direct_info

                # advance予測の1-2-3位を取得（advance/beforeフィルタ用・before時のみ意味あり）
                advance_top3 = self._get_advance_top3(cursor, race_id) if has_beforeinfo else None

                # BetTargetEvaluatorで購入判定
                bet_target = self.bet_evaluator.evaluate_race(
                    race_data=race_data,
                    predictions=predictions,
                    odds_data=odds_data,
                    has_beforeinfo=has_beforeinfo,
                    advance_top3=advance_top3
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
                    self._bet_target_cache[race_id] = race_info

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
        """予測データを取得（before優先、なければadvanceにフォールバック）"""
        cursor.execute("""
            SELECT
                pit_number,
                rank_prediction,
                confidence,
                total_score
            FROM race_predictions
            WHERE race_id = ?
              AND prediction_type = 'before'
            ORDER BY rank_prediction
        """, (race_id,))

        predictions = [dict(row) for row in cursor.fetchall()]

        # before予測がなければadvance予測にフォールバック
        if len(predictions) < 3:
            cursor.execute("""
                SELECT
                    pit_number,
                    rank_prediction,
                    confidence,
                    total_score
                FROM race_predictions
                WHERE race_id = ?
                  AND prediction_type = 'advance'
                ORDER BY rank_prediction
            """, (race_id,))
            predictions = [dict(row) for row in cursor.fetchall()]

        if len(predictions) < 3:
            return None

        # 全予測を返す（パターンH用に5位以上必要）
        all_pred = [p['pit_number'] for p in predictions]

        # 1着予測選手の登録番号を取得（逃げ率・バイアス指数フィルター用）
        first_pred_pit = all_pred[0] if all_pred else None
        first_racer_number = None
        if first_pred_pit:
            cursor.execute("""
                SELECT racer_number FROM entries
                WHERE race_id = ? AND pit_number = ?
            """, (race_id, first_pred_pit))
            racer_row = cursor.fetchone()
            if racer_row:
                first_racer_number = racer_row['racer_number']

        return {
            'confidence': predictions[0]['confidence'],
            'total_score': predictions[0].get('total_score'),  # スコアフィルター用（2026-04-21追加）
            'old_prediction': all_pred,
            'new_prediction': all_pred,  # 事前予測の段階では同じ
            'first_racer_number': first_racer_number
        }

    def _get_odds_data(self, cursor, race_id: int, predictions: Dict) -> Optional[Dict[str, float]]:
        """オッズデータを取得（全組み合わせ）"""
        cursor.execute("""
            SELECT combination, odds
            FROM trifecta_odds
            WHERE race_id = ?
        """, (race_id,))

        rows = cursor.fetchall()
        if rows:
            result = {row['combination']: row['odds'] for row in rows if row['odds']}
            if result:
                return result

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

    def _notify_promotion(self, race: Dict, bet_target, label: str) -> None:
        """候補レースが購入対象に昇格した際の即時Discord通知"""
        race_id = race['race_id']
        try:
            venue_name = self.get_venue_name(race['venue_code'])
            race_info = {
                'venue': venue_name,
                'race_number': race['race_number'],
                'deadline': race['deadline'],
                'race_id': race_id
            }

            if bet_target.multi_bet_result and bet_target.multi_bet_result.bets:
                pit_numbers = [
                    [int(x) for x in bet.combination.split('-')]
                    for bet in bet_target.multi_bet_result.bets
                ]
                odds_info = {
                    'trifecta_odds': bet_target.odds if bet_target.odds else 10.0,
                    'multi_bets': [
                        {'combination': bet.combination, 'odds': bet.odds}
                        for bet in bet_target.multi_bet_result.bets
                    ]
                }
            else:
                if not bet_target.combination:
                    print(f"[WARNING] 昇格通知スキップ（組み合わせ未設定）: {race_id}")
                    return
                pit_numbers = [[int(x) for x in bet_target.combination.split('-')]]
                odds_info = {'trifecta_odds': bet_target.odds if bet_target.odds else 10.0}

            prediction = {
                'pit_numbers': pit_numbers,
                'confidence': (
                    _CONFIDENCE_FLOAT_MAP.get(bet_target.confidence, 0.70)
                    if isinstance(bet_target.confidence, str)
                    else (float(bet_target.confidence) if bet_target.confidence is not None else 0.70)
                )
            }

            base_msg = format_race_notification(race_info, prediction, odds_info)
            msg = f"🔔 **{label}** {base_msg}"
            send_discord_notification(msg)
            print(f"  昇格通知送信: {race_id}")

        except Exception as e:
            print(f"[ERROR] 昇格通知送信失敗: {race_id} - {e}")

    def _fetch_beforeinfo_for_race(self, race: Dict) -> bool:
        """
        特定レースの直前情報を取得してDBに保存

        Args:
            race: レース情報（venue_code, date, race_number, race_id を含む）

        Returns:
            bool: 取得成功ならTrue
        """
        try:
            venue_code = race['venue_code']
            race_date_yyyymmdd = race['date'].replace('-', '')  # YYYY-MM-DD -> YYYYMMDD
            race_number = race['race_number']
            race_id = race['race_id']

            # BeforeInfoScraperで直前情報を取得
            scraper = BeforeInfoScraper()
            result = scraper.get_race_beforeinfo(
                venue_code,
                race_date_yyyymmdd,
                race_number
            )

            if result and result.get('is_published'):
                # DBに保存
                success = scraper.save_to_db(race_id, result)
                scraper.close()

                if success:
                    print(f"  直前情報取得成功: 会場{venue_code} {race_number}R")
                    return True
                else:
                    print(f"  [WARNING] DB保存失敗: 会場{venue_code} {race_number}R")
                    return False
            else:
                print(f"  [WARNING] 直前情報未公開: 会場{venue_code} {race_number}R")
                scraper.close()
                return False

        except Exception as e:
            print(f"  [ERROR] 直前情報取得エラー: {e}")
            return False

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
                # 直前情報取得を実行
                success = self._fetch_beforeinfo_for_race(race)

                if success:
                    self.fetched_direct_info.add(race_id)

                    # 直前情報取得後、購入判定を再評価
                    self._reevaluate_after_beforeinfo(race)

                    return True
                else:
                    print(f"  [WARNING] 直前情報取得失敗: {race_id}")
                    return False

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

                # レースデータを再取得（気象条件更新のため、2026-01-28追加）
                race_data = self._get_race_data(cursor, race_id)
                if not race_data:
                    print(f"[WARNING] レースデータ取得失敗: {race_id}")
                    return

                # 直前予測データを取得
                predictions = self._get_predictions_with_beforeinfo(cursor, race_id)
                if not predictions:
                    return

                # オッズデータを再取得
                odds_data = self._get_odds_data(cursor, race_id, predictions)

                # advance予測の1-2-3位を取得（advance/beforeフィルタ用）
                advance_top3 = self._get_advance_top3(cursor, race_id)

                # 購入判定を再評価（has_beforeinfo=True、最新のrace_dataを使用）
                bet_target = self.bet_evaluator.evaluate_race(
                    race_data=race_data,
                    predictions=predictions,
                    odds_data=odds_data,
                    has_beforeinfo=True,
                    advance_top3=advance_top3
                )

                # 元のステータスと比較
                old_status = race['bet_target'].status
                new_status = bet_target.status

                # ステータス変化をログ出力
                if old_status != new_status:
                    print(f"  レース{race_id}: {old_status.value} → {new_status.value}")
                    if old_status == BetStatus.CANDIDATE and new_status == BetStatus.TARGET_CONFIRMED:
                        print(f"  候補レースが購入対象に昇格: {race_id}")
                        self._notify_promotion(race, bet_target, "候補→対象確定(直前情報)")

                # ステータス変化に関わらず常にキャッシュ更新（has_beforeinfo=True の評価結果を反映）
                race['bet_target'] = bet_target
                self._bet_target_cache[race_id] = race

            finally:
                conn.close()

        except Exception as e:
            print(f"[ERROR] 再評価エラー: {race_id} - {e}")

    def _get_predictions_with_beforeinfo(self, cursor, race_id: int) -> Optional[Dict]:
        """直前予測を含む予測データを取得"""
        # 事前予測
        cursor.execute("""
            SELECT pit_number, rank_prediction, confidence, total_score
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
        """, (race_id,))
        advance_preds = [dict(row) for row in cursor.fetchall()]

        # 直前予測（total_scoreはbefore予測から取得 - スコアフィルター用）
        cursor.execute("""
            SELECT pit_number, rank_prediction, total_score
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY rank_prediction
        """, (race_id,))
        before_preds = [dict(row) for row in cursor.fetchall()]

        if len(advance_preds) < 3:
            return None

        # 全件返却（パターンH用に5位以上必要）
        old_pred = [p['pit_number'] for p in advance_preds]
        new_pred = [p['pit_number'] for p in before_preds] if len(before_preds) >= 3 else old_pred

        # total_scoreはbefore予測優先、なければadvance予測から取得（スコアフィルター用・2026-04-22修正）
        if before_preds and before_preds[0].get('total_score') is not None:
            total_score = before_preds[0]['total_score']
        else:
            total_score = advance_preds[0].get('total_score') if advance_preds else None

        # 1着予測選手の登録番号を取得（逃げ率・バイアス指数フィルター用）
        first_pred_pit = old_pred[0] if old_pred else None
        first_racer_number = None
        if first_pred_pit:
            cursor.execute("""
                SELECT racer_number FROM entries
                WHERE race_id = ? AND pit_number = ?
            """, (race_id, first_pred_pit))
            racer_row = cursor.fetchone()
            if racer_row:
                first_racer_number = racer_row['racer_number']

        return {
            'confidence': advance_preds[0]['confidence'],
            'total_score': total_score,  # スコアフィルター用（2026-04-22追加）
            'old_prediction': old_pred,
            'new_prediction': new_pred,
            'first_racer_number': first_racer_number
        }

    def _get_advance_top3(self, cursor, race_id: int):
        """advance予測の1-2-3位ピット番号を取得（advance/beforeフィルタ用）

        Returns:
            list[int] or None: [1位pit, 2位pit, 3位pit] or None（advance予測なし）
        """
        cursor.execute("""
            SELECT pit_number, rank_prediction
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance' AND rank_prediction IN (1, 2, 3)
            ORDER BY rank_prediction
        """, (race_id,))
        rows = cursor.fetchall()
        if len(rows) < 3:
            return None
        rank_to_pit = {row['rank_prediction']: row['pit_number'] for row in rows}
        if 1 in rank_to_pit and 2 in rank_to_pit and 3 in rank_to_pit:
            return [rank_to_pit[1], rank_to_pit[2], rank_to_pit[3]]
        return None

    def _check_and_fetch_odds(self, race: Dict) -> bool:
        """
        オッズ再取得が必要かチェックし、必要なら取得して再評価

        締切30-50分前に、CANDIDATE または TARGET_ADVANCE のレースのオッズを再取得する。
        TARGET_ADVANCE は Eブロック（08:00）で一度収集済みだが、三連単オッズは締切直前まで
        大きく変動するため、直前に再取得して最新値に更新する。

        Args:
            race: レース情報

        Returns:
            bool: オッズを取得して再評価したらTrue
        """
        race_id = race['race_id']

        # 既に取得済みならスキップ
        if race_id in self.fetched_odds_races:
            return False

        # CANDIDATE または TARGET_ADVANCE のみ対象
        # TARGET_ADVANCE: Eブロック(08:00)で取得済みだが締切前に大きく変動するため再取得が必要
        bet_target = race['bet_target']
        if bet_target.status not in (BetStatus.CANDIDATE, BetStatus.TARGET_ADVANCE):
            return False

        deadline = self.parse_deadline(race['date'], race['deadline'])
        now = datetime.now()
        time_until_deadline = (deadline - now).total_seconds() / 60  # 分

        # 締切30-50分前にオッズ再取得（直前情報取得の前）
        if 28 <= time_until_deadline <= 55:
            print(f"オッズ再取得: {race_id} (締切まであと{time_until_deadline:.0f}分)")

            try:
                from src.scraper.odds_scraper import OddsScraper

                venue_code = race['venue_code']
                race_date = race['date'].replace('-', '')  # YYYYMMDD形式
                race_number = race['race_number']

                scraper = OddsScraper()
                odds_data = scraper.get_trifecta_odds(venue_code, race_date, race_number)
                scraper.close()

                if odds_data:
                    # DBに保存（既存行の created_at を保持するため ON CONFLICT DO UPDATE を使用）
                    conn = self.get_connection()
                    try:
                        cursor = conn.cursor()
                        for combo, odds_val in odds_data.items():
                            cursor.execute("""
                                INSERT INTO trifecta_odds
                                (race_id, combination, odds, fetched_at)
                                VALUES (?, ?, ?, ?)
                                ON CONFLICT(race_id, combination)
                                DO UPDATE SET odds = excluded.odds, fetched_at = excluded.fetched_at
                            """, (race_id, combo, odds_val, datetime.now().isoformat()))
                        conn.commit()
                    finally:
                        conn.close()

                    self.fetched_odds_races.add(race_id)

                    # 再評価
                    self._reevaluate_after_odds_fetch(race, odds_data)
                    return True
                else:
                    print(f"  [INFO] オッズ未公開: {race_id}")

            except Exception as e:
                print(f"[ERROR] オッズ再取得エラー: {race_id} - {e}")

        return False

    def _reevaluate_after_odds_fetch(self, race: Dict, new_odds_data: Dict) -> None:
        """
        オッズ取得後に購入判定を再評価し、キャッシュを更新

        Args:
            race: レース情報
            new_odds_data: 新しく取得したオッズデータ
        """
        race_id = race['race_id']

        try:
            conn = self.get_connection()
            try:
                cursor = conn.cursor()

                race_data = self._get_race_data(cursor, race_id)
                if not race_data:
                    return

                predictions = race.get('predictions') or self._get_predictions(cursor, race_id)
                if not predictions:
                    return

                has_beforeinfo = race_id in self.fetched_direct_info

                # advance予測の1-2-3位を取得（advance/beforeフィルタ用・before時のみ意味あり）
                advance_top3 = self._get_advance_top3(cursor, race_id) if has_beforeinfo else None

                bet_target = self.bet_evaluator.evaluate_race(
                    race_data=race_data,
                    predictions=predictions,
                    odds_data=new_odds_data,
                    has_beforeinfo=has_beforeinfo,
                    advance_top3=advance_top3
                )

                old_status = race['bet_target'].status
                new_status = bet_target.status

                if old_status != new_status:
                    print(f"  オッズ取得後ステータス変化: {race_id}: {old_status.value} → {new_status.value}")
                    if old_status == BetStatus.CANDIDATE and new_status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
                        self._notify_promotion(race, bet_target, "候補→対象(オッズ確認)")

                race['bet_target'] = bet_target
                self._bet_target_cache[race_id] = race

            finally:
                conn.close()

        except Exception as e:
            print(f"[ERROR] オッズ取得後の再評価エラー: {race_id} - {e}")

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
            # pit_numbersは常にリストのリスト形式に統一（2026-01-28修正）
            if bet_target.multi_bet_result and bet_target.multi_bet_result.bets:
                # パターンH（3点買い）- betsから各買い目を抽出
                pit_numbers = [[int(x) for x in bet.combination.split('-')] for bet in bet_target.multi_bet_result.bets]
            else:
                # 1点買いの場合もリストのリスト形式に統一
                pit_numbers = [[int(x) for x in bet_target.combination.split('-')]]

            prediction = {
                'pit_numbers': pit_numbers,
                'confidence': _CONFIDENCE_FLOAT_MAP.get(bet_target.confidence, 0.70) if isinstance(bet_target.confidence, str) else (float(bet_target.confidence) if bet_target.confidence is not None else 0.70)
            }

            # オッズ情報整形（2026-01-28修正: パターンH対応）
            if bet_target.multi_bet_result and bet_target.multi_bet_result.bets:
                # パターンH（3点買い）- 全買い目のオッズを含める
                odds_info = {
                    'trifecta_odds': bet_target.odds if bet_target.odds else 10.0,
                    'multi_bets': [
                        {'combination': bet.combination, 'odds': bet.odds}
                        for bet in bet_target.multi_bet_result.bets
                    ]
                }
            else:
                # 1点買い
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
            'odds_fetched': 0,
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
                    # オッズ再取得チェック（締切30-50分前、CANDIDATE対象）
                    if self._check_and_fetch_odds(race):
                        stats['odds_fetched'] += 1

                    # 直前情報取得チェック（締切15-25分前、取得後に再評価も実行）
                    if self.check_and_fetch_direct_info(race):
                        stats['direct_info_fetched'] += 1

                    # 通知チェック（締切8-12分前、再評価後のステータスで判定）
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
        if bet_target.multi_bet_result and bet_target.multi_bet_result.bets:
            bet_info = f"{len(bet_target.multi_bet_result.bets)}点買い"
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
    print(f"  オッズ取得: {stats['odds_fetched']}")
    print(f"  直前情報取得: {stats['direct_info_fetched']}")
    print(f"  通知送信: {stats['notifications_sent']}")
    print(f"  エラー: {stats['errors']}")


if __name__ == "__main__":
    main()
