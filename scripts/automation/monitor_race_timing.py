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
    send_discord_notification_dual,
    format_race_notification,
    format_race_notification_short,
    format_detail_message,
    calc_prediction_score,
)
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus
from src.betting.multi_bet_generator import MultiBetPattern
from src.betting.evaluator_helpers import create_standard_evaluator
from src.scraper.beforeinfo_scraper import BeforeInfoScraper


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
        self.fetched_odds_races: Dict[int, datetime] = {}  # オッズ再取得済み: {race_id: 取得時刻}
        self.late_fetched_races: set = set()  # 後期オッズ確認済みレースID
        self.fetched_direct_info_universal = set()  # Gap1対応: 全レース直前情報チェック済み
        self._monitoring_active = False  # 重複実行防止（前サイクルが終わっていない場合はスキップ）
        self._bet_target_cache = {}       # {race_id: race_dict} - 購入判定キャッシュ
        self._cache_date = None           # キャッシュの日付

        # BetTargetEvaluatorを初期化（標準設定を使用 - generate_daily_predictions.py と同じ設定）
        self.bet_evaluator = create_standard_evaluator(db_path=db_path)

        # PredictionUpdaterを起動時に1回だけ初期化（モデルの繰り返しロードを防ぐ）
        from src.analysis.prediction_updater import PredictionUpdater
        self.prediction_updater = PredictionUpdater(db_path=db_path)

    def get_connection(self) -> sqlite3.Connection:
        """DB接続を取得"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _save_bet_notification(
        self,
        race_id: int,
        combinations: str,
        odds: float,
        bet_amount: int,
        condition_id: str,
        notification_type: str = 'confirmed',
        bet_amounts: str = '',
    ) -> None:
        """
        通知済みレースをbet_notificationsテーブルに記録する。
        翌朝のreconcile_yesterday_betsで使用し、通知時オッズと実結果を突合せる。

        bet_amounts: 組合せごとの投資額（カンマ区切り）。例: "200,100,100" / "100"
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bet_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    race_id INTEGER NOT NULL,
                    combinations TEXT NOT NULL,
                    odds_at_notification REAL,
                    bet_amount INTEGER DEFAULT 100,
                    bet_amounts TEXT,
                    condition_id TEXT,
                    notified_at TEXT NOT NULL,
                    notification_type TEXT DEFAULT 'confirmed',
                    UNIQUE(race_id, notification_type)
                )
            """)
            # 既存テーブルへの bet_amounts カラム追加（移行対応）
            try:
                conn.execute("ALTER TABLE bet_notifications ADD COLUMN bet_amounts TEXT")
            except Exception:
                pass
            conn.execute("""
                INSERT OR REPLACE INTO bet_notifications
                    (race_id, combinations, odds_at_notification, bet_amount,
                     bet_amounts, condition_id, notified_at, notification_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                race_id,
                combinations,
                odds,
                bet_amount,
                bet_amounts,
                condition_id,
                datetime.now().isoformat(),
                notification_type,
            ))
            conn.commit()
            conn.close()
            print(f"  [BET_LOG] 通知記録保存: race_id={race_id} type={notification_type} combos={combinations} amounts={bet_amounts}")
        except Exception as e:
            print(f"  [WARN] 通知記録保存失敗: {e}")

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
            self.fetched_direct_info_universal = set()
            self.notified_races = set()
            self.fetched_direct_info = set()
            self.fetched_odds_races = {}
            self.late_fetched_races = set()
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
                        # 発走時刻は当日変更される可能性があるため毎回DBから最新値を反映する
                        if cached['deadline'] != row['race_time']:
                            print(f"  [INFO] 発走時刻変更: race_id={race_id} 会場{cached.get('venue_code', '??')} {cached.get('race_number', '?')}R {cached['deadline']} → {row['race_time']}")
                        cached['deadline'] = row['race_time']
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

    def _get_all_today_races_simple(self) -> List[Dict]:
        """
        本日の全レースを最小限の情報で取得（Gap1対応）

        Returns:
            List[Dict]: race_id / race_date / venue_code / race_number / race_time
        """
        today = datetime.now().strftime('%Y-%m-%d')
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT r.id AS race_id, r.race_date, r.venue_code, r.race_number, r.race_time
                FROM races r
                WHERE r.race_date = ?
                ORDER BY r.race_time
            """, (today,))
            return [
                {
                    'race_id': row['race_id'],
                    'race_date': row['race_date'],
                    'venue_code': (
                        f"{row['venue_code']:02d}"
                        if isinstance(row['venue_code'], int)
                        else str(row['venue_code']).zfill(2)
                    ),
                    'race_number': row['race_number'],
                    'race_time': row['race_time'],
                }
                for row in cursor.fetchall()
            ]
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
                r.race_time,
                r.race_grade,
                r.is_rookie
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

        # 展示STタイムを取得（pit1/pit2: D_ST_CONTRAST条件のフィルター用）
        cursor.execute("""
            SELECT pit_number, st_time
            FROM race_details
            WHERE race_id = ? AND pit_number IN (1, 2)
        """, (race_id,))
        pit1_st = None
        pit2_st = None
        for st_row in cursor.fetchall():
            if st_row['pit_number'] == 1:
                pit1_st = st_row['st_time']
            elif st_row['pit_number'] == 2:
                pit2_st = st_row['st_time']

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
            'race_grade': race_row['race_grade'],
            'is_rookie': race_row['is_rookie'] or 0,
            'wind_speed': wind_speed,
            'pit1_st': pit1_st,
            'pit2_st': pit2_st,
            'entries': entries
        }

    def _get_predictions(self, cursor, race_id: int) -> Optional[Dict]:
        """予測データを取得（before優先、なければadvanceにフォールバック）"""
        _SUB_COLS = "pit_number, rank_prediction, confidence, total_score, course_score, racer_score, motor_score, kimarite_score, grade_score"
        cursor.execute(f"""
            SELECT {_SUB_COLS}
            FROM race_predictions
            WHERE race_id = ?
              AND prediction_type = 'before'
            ORDER BY rank_prediction
        """, (race_id,))

        predictions = [dict(row) for row in cursor.fetchall()]

        # before予測がなければadvance予測にフォールバック
        if len(predictions) < 3:
            cursor.execute(f"""
                SELECT {_SUB_COLS}
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

        r1_score = predictions[0].get('total_score')
        r2_score = predictions[1].get('total_score') if len(predictions) > 1 else None
        r3_score = predictions[2].get('total_score') if len(predictions) > 2 else None
        r4_score = predictions[3].get('total_score') if len(predictions) > 3 else None
        score_gap  = (r1_score - r2_score) if r1_score is not None and r2_score is not None else None
        score_gap34 = (r3_score - r4_score) if r3_score is not None and r4_score is not None else None

        sub_scores = {
            'course_score':   predictions[0].get('course_score'),
            'racer_score':    predictions[0].get('racer_score'),
            'motor_score':    predictions[0].get('motor_score'),
            'kimarite_score': predictions[0].get('kimarite_score'),
            'grade_score':    predictions[0].get('grade_score'),
        }

        return {
            'confidence': predictions[0]['confidence'],
            'total_score': r1_score,
            'score_gap': score_gap,
            'score_gap34': score_gap34,
            'old_prediction': all_pred,
            'new_prediction': all_pred,  # 事前予測の段階では同じ
            'first_racer_number': first_racer_number,
            'sub_scores': sub_scores,
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
        """候補レースが購入対象に昇格した際の即時Discord通知

        通常の昇格（CANDIDATE/ADVANCE→CONFIRMED）は静音化。
        締切10分前通知（check_and_notify）で同内容が流れるため重複を避ける。
        Gap1（朝の見通しにないレースが新規昇格）のみ「新規購入発生」として通知。
        """
        # Gap1以外の通常昇格は静音化（ログのみ）
        if not label.startswith("Gap1"):
            print(f"  [INFO] 昇格(静音): {race['race_id']} - {label}")
            return

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
                        {'combination': bet.combination, 'odds': bet.odds, 'bet_amount': bet.bet_amount}
                        for bet in bet_target.multi_bet_result.bets
                    ],
                    'bet_amount': sum(b.bet_amount for b in bet_target.multi_bet_result.bets),
                    'expected_roi': bet_target.expected_roi,
                    'reason': bet_target.reason,
                }
            else:
                if not bet_target.combination:
                    print(f"[WARNING] 昇格通知スキップ（組み合わせ未設定）: {race_id}")
                    return
                pit_numbers = [[int(x) for x in bet_target.combination.split('-')]]
                odds_info = {
                    'trifecta_odds': bet_target.odds if bet_target.odds else 10.0,
                    'bet_amount': bet_target.bet_amount,
                    'expected_roi': bet_target.expected_roi,
                    'reason': bet_target.reason,
                }

            preds = race.get('predictions') or {}
            rank1_pit = (preds.get('old_prediction') or [None])[0]
            entries = (race.get('race_data') or {}).get('entries', [])
            rank1_entry = next((e for e in entries if e.get('pit_number') == rank1_pit), None)
            prediction = {
                'pit_numbers': pit_numbers,
                'prediction_score': calc_prediction_score(
                    bet_target.confidence,
                    preds.get('score_gap'),
                    preds.get('score_gap34'),
                ),
                'rank1_name': rank1_entry['racer_name'] if rank1_entry else None,
            }

            status_name = bet_target.status.name if bet_target.status else None
            log_base = format_race_notification(race_info, prediction, odds_info, status=status_name)
            log_msg = f"🆕 **朝の見通しにないレース** {log_base}\n_締切10分前に改めて購入通知が届きます_"
            alert_msg = format_race_notification_short(race_info, prediction, odds_info, status=status_name, gap1=True)
            alert_msg += "\n_（10分前に改めて通知）_"
            send_discord_notification_dual(alert_msg, log_msg,
                                           primary_channel='buy', secondary_channel='log')
            print(f"  Gap1新規発生通知送信: {race_id}")

        except Exception as e:
            print(f"[ERROR] 昇格通知送信失敗: {race_id} - {e}")

    def _notify_demotion(self, race: Dict, new_status, label: str) -> None:
        """暫定購入対象が降格した際の処理（静音化済み・ログのみ）"""
        status_str = "候補" if new_status == BetStatus.CANDIDATE else "対象外"
        print(f"  [INFO] 降格(静音): {race['race_id']} - {label} → {status_str}")

    def _fetch_beforeinfo_for_race(self, race: Dict, deadline_minutes: float = 999) -> bool:
        """
        特定レースの直前情報を取得してDBに保存

        Args:
            race: レース情報（venue_code, date, race_number, race_id を含む）
            deadline_minutes: 締切までの残り分数。12分以内なら展示タイム未掲載でも保存（ナイター対応）

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
                # 展示タイムが未掲載の場合
                # - 締切12分超: 次サイクルで再試行（公開待ち）
                # - 締切12分以内: ナイターでは展示タイム公開が特に遅い会場があるため、
                #   展示タイムなしのまま保存してbefore予測を生成する
                if not result.get('exhibition_times'):
                    if deadline_minutes > 12:
                        print(f"  [INFO] 展示タイム未掲載（再試行待ち）: 会場{venue_code} {race_number}R")
                        scraper.close()
                        return False
                    print(f"  [INFO] 展示タイム未掲載・タイムリミット到達→そのまま保存: 会場{venue_code} {race_number}R")

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

        # 締切10-25分前に直前情報取得（展示タイム未掲載時の再試行を考慮して下限を10分に拡張）
        if 10 <= time_until_deadline <= 25:
            print(f"直前情報取得: {race_id} (締切まであと{time_until_deadline:.0f}分)")

            try:
                # 直前情報取得を実行（締切残時間を渡してナイター対応）
                success = self._fetch_beforeinfo_for_race(race, deadline_minutes=time_until_deadline)

                if success:
                    # ナイター対応: 展示タイムなし保存の場合はfetched_direct_infoを立てず次サイクルで再試行可能にする
                    # ただしfetched_direct_info_universalを立てることでGap1ループの二重処理は防ぐ
                    has_exhibition = self.prediction_updater.check_beforeinfo_exists(race_id)
                    if has_exhibition:
                        self.fetched_direct_info.add(race_id)
                    else:
                        self.fetched_direct_info_universal.add(race_id)

                    # 修正E: CANDIDATEのままbeforeinfo取得した場合、Webオッズも先に更新する
                    # 通常は修正Aによりループ先頭で既にfetched_odds_racesに登録済みだが、
                    # Gap1経由でwatchlist入りした直後や13分前ぎりぎりの初回サイクル等の
                    # エッジケースに備えて再チェック。登録済みなら内部ガードで自動スキップ（二重取得なし）
                    if race['bet_target'].status == BetStatus.CANDIDATE:
                        self._check_and_fetch_odds(race)

                    # 直前情報取得後、購入判定を再評価（展示タイムなし保存時はforce_before=Trueで強制生成）
                    self._reevaluate_after_beforeinfo(race, force_before=not has_exhibition)

                    return True
                else:
                    print(f"  [WARNING] 直前情報取得失敗: {race_id}")
                    return False

            except Exception as e:
                print(f"[ERROR] 直前情報取得エラー: {race_id} - {e}")
                send_error_notification("直前情報取得失敗", f"レースID: {race_id}\nエラー: {str(e)}")
                return False

        return False

    def _check_universal_beforeinfo(self, race_simple: Dict) -> bool:
        """
        Gap1対応: watchlistに入っていないレースにも直前情報取得・before予測生成・再評価を行う。
        advance予測では対象外だったレースが before予測後にTARGET_CONFIRMEDになる場合に通知する。

        Args:
            race_simple: {'race_id', 'race_date', 'venue_code', 'race_number', 'race_time'}

        Returns:
            bool: 直前情報取得を試みたらTrue
        """
        race_id = race_simple['race_id']

        # watchlist経由で既に処理済みならスキップ
        if race_id in self.fetched_direct_info:
            return False
        # universal経由で既に処理済みならスキップ
        if race_id in self.fetched_direct_info_universal:
            return False

        # 締切10-25分前のみ対象
        # 展示タイムは通常10-15分前に公開されるため、15分前の初回試行で未掲載でも
        # 10-15分前の再試行で取得できるよう下限を10分に拡張
        deadline = self.parse_deadline(race_simple['race_date'], race_simple['race_time'])
        now = datetime.now()
        time_until = (deadline - now).total_seconds() / 60
        if not (10 <= time_until <= 25):
            return False

        print(f"[GAP1] 直前情報取得: race_id={race_id} 会場{race_simple['venue_code']} {race_simple['race_number']}R (締切まで{time_until:.0f}分)")

        # beforeinfo取得（失敗時はフラグを立てず次サイクルで再試行）
        race_for_scraper = {
            'race_id': race_id,
            'venue_code': race_simple['venue_code'],
            'date': race_simple['race_date'],
            'race_number': race_simple['race_number'],
        }
        if not self._fetch_beforeinfo_for_race(race_for_scraper, deadline_minutes=time_until):
            print(f"  [GAP1] beforeinfo未公開または取得失敗: race_id={race_id}")
            return True
        # ナイター対応: 展示タイムなし保存の場合はフラグを立てず次サイクルで再試行可能にする
        has_exhibition_univ = self.prediction_updater.check_beforeinfo_exists(race_id)
        if has_exhibition_univ:
            self.fetched_direct_info_universal.add(race_id)

        # batch_loader の日次データが未ロードなら初期化（初回呼び出し時のみ）
        today = datetime.now().strftime('%Y-%m-%d')
        try:
            bl = self.prediction_updater.predictor.batch_loader
            if bl and getattr(bl, '_loaded_date', None) != today:
                bl.load_daily_data(today)
                bl._loaded_date = today
        except Exception:
            pass

        # before予測生成（展示タイムなし保存の場合はforce=Trueで強制生成）
        try:
            self.prediction_updater.update_to_before_prediction(race_id, force=not has_exhibition_univ)
        except Exception as e:
            print(f"  [GAP1][WARNING] before予測生成エラー: race_id={race_id} - {e}")
            return True

        # before予測でBetTargetEvaluator再評価
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            race_data = self._get_race_data(cursor, race_id)
            if not race_data:
                return True
            predictions = self._get_predictions_with_beforeinfo(cursor, race_id)
            if not predictions:
                return True
            odds_data = self._get_odds_data(cursor, race_id, predictions)
            advance_top3 = self._get_advance_top3(cursor, race_id)

            bet_target = self.bet_evaluator.evaluate_race(
                race_data=race_data,
                predictions=predictions,
                odds_data=odds_data,
                has_beforeinfo=True,
                advance_top3=advance_top3
            )

            print(f"  [GAP1] 評価結果: race_id={race_id} → {bet_target.status.value}")

            if bet_target.status in (BetStatus.TARGET_CONFIRMED, BetStatus.CANDIDATE):
                # Gap1捕捉: watchlistに追加（TARGET_CONFIRMEDは即通知、CANDIDATEは以降のオッズ更新で昇格可能）
                race_info = {
                    'race_id': race_id,
                    'date': race_simple['race_date'],
                    'venue_code': race_simple['venue_code'],
                    'race_number': race_simple['race_number'],
                    'deadline': race_simple['race_time'],
                    'bet_target': bet_target,
                    'race_data': race_data,
                    'predictions': predictions,
                }
                self._bet_target_cache[race_id] = race_info
                self.fetched_direct_info.add(race_id)
                # Gap1: DBの朝オッズが古いためWebから最新オッズを即時取得・再評価
                self._check_and_fetch_odds(race_info)
                # odds再評価後のステータスで昇格判定（fetched_odds後にrace_infoが更新済み）
                if race_info['bet_target'].status == BetStatus.TARGET_CONFIRMED:
                    print(f"  [GAP1] 購入対象昇格: race_id={race_id}")
                    self._notify_promotion(race_info, race_info['bet_target'], "Gap1-before昇格")
                else:
                    print(f"  [GAP1] 候補昇格（オッズ更新待ち）: race_id={race_id}")

        finally:
            conn.close()

        return True

    def _reevaluate_after_beforeinfo(self, race: Dict, force_before: bool = False) -> None:
        """
        直前情報取得後に購入判定を再評価

        Args:
            race: レース情報
            force_before: Trueの場合、展示タイムなしでもbefore予測を強制生成（ナイター対応）
        """
        race_id = race['race_id']

        try:
            # before予測を自動生成（直前情報取得後・未生成の場合のみ）
            try:
                updated = self.prediction_updater.update_to_before_prediction(race_id, force=force_before)
                if updated:
                    print(f"  [INFO] before予測生成完了: {race_id}")
            except Exception as e:
                print(f"  [WARNING] before予測生成エラー: {race_id} - {e}")

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
                    elif old_status == BetStatus.TARGET_ADVANCE and new_status in [BetStatus.EXCLUDED, BetStatus.CANDIDATE]:
                        demotion_label = "暫定→候補" if new_status == BetStatus.CANDIDATE else "暫定→対象外"
                        print(f"  暫定購入対象が降格: {race_id} ({demotion_label})")
                        self._notify_demotion(race, new_status, demotion_label)

                # ステータス変化に関わらず常にキャッシュ更新（has_beforeinfo=True の評価結果を反映）
                race['bet_target'] = bet_target
                race['predictions'] = predictions  # 最新 gap 値を check_and_notify で使うため更新
                self._bet_target_cache[race_id] = race

            finally:
                conn.close()

        except Exception as e:
            print(f"[ERROR] 再評価エラー: {race_id} - {e}")

    def _get_predictions_with_beforeinfo(self, cursor, race_id: int) -> Optional[Dict]:
        """直前予測を含む予測データを取得"""
        # 事前予測
        cursor.execute("""
            SELECT pit_number, rank_prediction, confidence, total_score,
                   course_score, racer_score, motor_score, kimarite_score, grade_score
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
        """, (race_id,))
        advance_preds = [dict(row) for row in cursor.fetchall()]

        # 直前予測（before予測から順位・スコア・confidence・サブスコア取得 - 2026-04-23修正）
        cursor.execute("""
            SELECT pit_number, rank_prediction, total_score, confidence,
                   course_score, racer_score, motor_score, kimarite_score, grade_score
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

        # confidenceはbefore予測優先、なければadvance予測から取得（バックテストはbefore由来・2026-04-23修正）
        if before_preds and before_preds[0].get('confidence') is not None:
            confidence = before_preds[0]['confidence']
        else:
            confidence = advance_preds[0]['confidence']

        # 1着予測選手の登録番号を取得（逃げ率・バイアス指数フィルター用）
        # before予測優先（バックテストのrp1.pit_numberはbefore由来・2026-04-23修正）
        first_pred_pit = new_pred[0] if new_pred else old_pred[0] if old_pred else None
        first_racer_number = None
        if first_pred_pit:
            cursor.execute("""
                SELECT racer_number FROM entries
                WHERE race_id = ? AND pit_number = ?
            """, (race_id, first_pred_pit))
            racer_row = cursor.fetchone()
            if racer_row:
                first_racer_number = racer_row['racer_number']

        # rank2-rank4スコア（gap計算用）: before/advanceを混在させずソースを統一する
        # 混在するとスコアの絶対値スケールが異なり gap34 が無意味な値になるため
        def _get_gap_scores(b_list, a_list, indices):
            if all(len(b_list) > i and b_list[i].get('total_score') is not None for i in indices):
                return [b_list[i]['total_score'] for i in indices]
            if all(len(a_list) > i and a_list[i].get('total_score') is not None for i in indices):
                return [a_list[i]['total_score'] for i in indices]
            return [None] * len(indices)

        r2_score, r3_score, r4_score = _get_gap_scores(before_preds, advance_preds, [1, 2, 3])
        score_gap   = (total_score - r2_score) if total_score is not None and r2_score is not None else None
        score_gap34 = (r3_score - r4_score)    if r3_score   is not None and r4_score is not None else None

        # サブスコア（採点詳細通知用）: before優先、なければadvanceから取得
        rank1_row = (before_preds or advance_preds)[0] if (before_preds or advance_preds) else {}
        sub_scores = {
            'course_score':   rank1_row.get('course_score'),
            'racer_score':    rank1_row.get('racer_score'),
            'motor_score':    rank1_row.get('motor_score'),
            'kimarite_score': rank1_row.get('kimarite_score'),
            'grade_score':    rank1_row.get('grade_score'),
        }

        return {
            'confidence': confidence,
            'total_score': total_score,
            'score_gap': score_gap,
            'score_gap34': score_gap34,
            'old_prediction': old_pred,
            'new_prediction': new_pred,
            'first_racer_number': first_racer_number,
            'sub_scores': sub_scores,
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

    def _fetch_web_odds(self, race: Dict) -> Optional[Dict[str, float]]:
        """WebからオッズをスクレイピングしてDBに保存する共通処理

        Returns:
            dict: {combination: odds} または None（取得失敗・データなし時）
        """
        from src.scraper.odds_scraper import OddsScraper
        race_id = race['race_id']
        try:
            scraper = OddsScraper()
            odds_data = scraper.get_trifecta_odds(
                race['venue_code'],
                race['date'].replace('-', ''),
                race['race_number'],
            )
            scraper.close()
            if odds_data:
                conn = self.get_connection()
                try:
                    cursor = conn.cursor()
                    for combo, odds_val in odds_data.items():
                        cursor.execute("""
                            INSERT INTO trifecta_odds (race_id, combination, odds, fetched_at)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(race_id, combination)
                            DO UPDATE SET odds = excluded.odds, fetched_at = excluded.fetched_at
                        """, (race_id, combo, odds_val, datetime.now().isoformat()))
                    conn.commit()
                finally:
                    conn.close()
            return odds_data or None
        except Exception as e:
            print(f"  [WARNING] Webオッズ取得失敗: race_id={race_id} - {e}")
            return None

    def _check_and_fetch_odds(self, race: Dict) -> bool:
        """
        オッズ再取得が必要かチェックし、必要なら取得して再評価

        締切13-25分前に、CANDIDATE または TARGET_ADVANCE のレースのオッズを再取得する。
        直前情報取得（15-25分前）と同タイミングのため、ループ内でオッズ再取得が先に実行され、
        続くbefore予測の再評価で最新オッズが使われる。

        Args:
            race: レース情報

        Returns:
            bool: オッズを取得して再評価したらTrue
        """
        race_id = race['race_id']

        # 既に取得済みならスキップ
        if race_id in self.fetched_odds_races:
            return False

        # EXCLUDED のみスキップ。TARGET_CONFIRMEDも対象に含める。
        # 理由: beforeinfo再評価でTARGET_CONFIRMEDになった場合、その時点でのDBオッズは
        # 朝のEブロック取得値のまま（古い）なのでWebから再取得が必要。
        bet_target = race['bet_target']
        if bet_target.status == BetStatus.EXCLUDED:
            return False

        deadline = self.parse_deadline(race['date'], race['deadline'])
        now = datetime.now()
        time_until_deadline = (deadline - now).total_seconds() / 60  # 分

        # 締切10-25分前にオッズ再取得（直前情報取得と同タイミング・ループ内でオッズが先に処理されるため最新値でbefore再評価される）
        if 10 <= time_until_deadline <= 25:
            print(f"オッズ再取得: {race_id} (締切まであと{time_until_deadline:.0f}分)")

            odds_data = self._fetch_web_odds(race)
            if odds_data:
                fetch_time = datetime.now()
                self.fetched_odds_races[race_id] = fetch_time
                race['odds_fetched_at'] = fetch_time
                self._reevaluate_after_odds_fetch(race, odds_data)
                return True
            else:
                print(f"  [INFO] オッズ未公開: {race_id}")

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

                has_beforeinfo = race_id in self.fetched_direct_info

                # before予測取得済みならbefore/advance両方を含む predictions を使う（advance/beforeフィルタが正しく機能するため）
                if has_beforeinfo:
                    predictions = self._get_predictions_with_beforeinfo(cursor, race_id)
                else:
                    predictions = race.get('predictions') or self._get_predictions(cursor, race_id)
                if not predictions:
                    return

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
                race['predictions'] = predictions  # 最新 gap 値を check_and_notify で使うため更新
                self._bet_target_cache[race_id] = race

            finally:
                conn.close()

        except Exception as e:
            print(f"[ERROR] オッズ取得後の再評価エラー: {race_id} - {e}")

    def check_and_notify(self, race: Dict) -> bool:
        """
        締切7-9分前に最新Webオッズを取得して最終購入判定・通知

        旧: 8-12分前に通知（オッズ取得は別途10-25分前）
        新: 7-9分前に最新Webオッズ取得 → 再評価 → 通知
            対象外になった場合は「見送り」通知を送信してnotified_racesに追加（再チェックなし）

        Args:
            race: レース情報

        Returns:
            bool: 購入通知を送信したらTrue
        """
        race_id = race['race_id']

        # 既に通知済みならスキップ
        if race_id in self.notified_races:
            return False

        # 購入対象（TARGET_ADVANCE または TARGET_CONFIRMED）のみ処理
        bet_target = race['bet_target']
        if bet_target.status not in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            return False

        deadline = self.parse_deadline(race['date'], race['deadline'])
        now = datetime.now()
        time_until_deadline = (deadline - now).total_seconds() / 60

        # 締切6-10分前に最終判定・通知（4分窓: 旧8-12分前の4分窓を維持しつつ締め切りに寄せ）
        if not (6 <= time_until_deadline <= 10):
            return False

        print(f"最終オッズ確認・通知: {race_id} (締切まであと{time_until_deadline:.0f}分)")

        # 最新Webオッズを取得して最終評価
        final_odds_data = self._fetch_web_odds(race)
        if final_odds_data is None:
            print(f"  [WARNING] 最新オッズ取得失敗: {race_id} - 10-25分前のDBオッズで代替評価")
        has_beforeinfo = race_id in self.fetched_direct_info

        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            race_data = self._get_race_data(cursor, race_id)
            if not race_data:
                return False
            predictions = (
                self._get_predictions_with_beforeinfo(cursor, race_id)
                if has_beforeinfo
                else race.get('predictions') or self._get_predictions(cursor, race_id)
            )
            if not predictions:
                return False
            advance_top3 = self._get_advance_top3(cursor, race_id) if has_beforeinfo else None
            odds_for_eval = final_odds_data if final_odds_data else self._get_odds_data(cursor, race_id, predictions)
            final_bet_target = self.bet_evaluator.evaluate_race(
                race_data=race_data,
                predictions=predictions,
                odds_data=odds_for_eval,
                has_beforeinfo=has_beforeinfo,
                advance_top3=advance_top3,
            )
        finally:
            conn.close()

        # キャッシュ更新
        old_status = bet_target.status
        race['bet_target'] = final_bet_target
        race['predictions'] = predictions
        if final_odds_data:
            race['odds_fetched_at'] = datetime.now()
        self._bet_target_cache[race_id] = race

        # 最終評価で購入対象外になった場合: 見送り通知
        if final_bet_target.status not in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            venue_name = self.get_venue_name(race['venue_code'])
            msg = (
                f"⚪ **{venue_name} {race['race_number']}R** 締切{race['deadline']}\n"
                f"最終確認でオッズ範囲外のため見送り"
            )
            send_discord_notification(msg, channel='log')
            print(f"  [見送り] {race_id}: 最終確認で対象外 ({old_status.value} → {final_bet_target.status.value})")
            self.notified_races.add(race_id)  # 再チェックしない
            return False

        # --- 購入通知送信 ---
        race_info = {
            'venue': self.get_venue_name(race['venue_code']),
            'race_number': race['race_number'],
            'deadline': race['deadline'],
            'race_id': race_id
        }

        if final_bet_target.multi_bet_result and final_bet_target.multi_bet_result.bets:
            pit_numbers = [[int(x) for x in bet.combination.split('-')] for bet in final_bet_target.multi_bet_result.bets]
        else:
            pit_numbers = [[int(x) for x in final_bet_target.combination.split('-')]]

        preds = race.get('predictions') or {}
        rank1_pit = (preds.get('old_prediction') or [None])[0]
        entries = (race.get('race_data') or {}).get('entries', [])
        rank1_entry = next((e for e in entries if e.get('pit_number') == rank1_pit), None)
        prediction = {
            'pit_numbers': pit_numbers,
            'prediction_score': calc_prediction_score(
                final_bet_target.confidence,
                preds.get('score_gap'),
                preds.get('score_gap34'),
            ),
            'rank1_name': rank1_entry['racer_name'] if rank1_entry else None,
        }

        if final_bet_target.multi_bet_result and final_bet_target.multi_bet_result.bets:
            odds_info = {
                'trifecta_odds': final_bet_target.odds if final_bet_target.odds else 10.0,
                'multi_bets': [
                    {'combination': bet.combination, 'odds': bet.odds, 'bet_amount': bet.bet_amount}
                    for bet in final_bet_target.multi_bet_result.bets
                ],
                'bet_amount': sum(b.bet_amount for b in final_bet_target.multi_bet_result.bets),
                'expected_roi': final_bet_target.expected_roi,
                'reason': final_bet_target.reason,
                'odds_fetch_elapsed': None,  # 直前取得のため経過時間は不要
            }
        else:
            odds_info = {
                'trifecta_odds': final_bet_target.odds if final_bet_target.odds else 10.0,
                'bet_amount': final_bet_target.bet_amount,
                'expected_roi': final_bet_target.expected_roi,
                'reason': final_bet_target.reason,
                'odds_fetch_elapsed': None,
            }

        try:
            success = send_race_notification(
                race_info, prediction, odds_info, None,
                status=final_bet_target.status.name if hasattr(final_bet_target.status, 'name') else str(final_bet_target.status)
            )
            if success:
                self.notified_races.add(race_id)
                # 後期オッズ確認用に通知時点の買い目オッズを保存
                if final_bet_target.multi_bet_result and final_bet_target.multi_bet_result.bets:
                    race['notified_odds_map'] = {
                        bet.combination: bet.odds for bet in final_bet_target.multi_bet_result.bets
                    }
                else:
                    race['notified_odds_map'] = (
                        {final_bet_target.combination: final_bet_target.odds} if final_bet_target.combination else {}
                    )
                # 通知記録をDBに保存（翌日reconcile用）
                try:
                    if final_bet_target.multi_bet_result and final_bet_target.multi_bet_result.bets:
                        _combos = ','.join(b.combination for b in final_bet_target.multi_bet_result.bets)
                        _amounts = ','.join(str(b.bet_amount) for b in final_bet_target.multi_bet_result.bets)
                        _amount = sum(b.bet_amount for b in final_bet_target.multi_bet_result.bets)
                    else:
                        _combos = final_bet_target.combination or ''
                        _amounts = str(final_bet_target.bet_amount or 100)
                        _amount = final_bet_target.bet_amount or 100
                    _cond_id = (final_bet_target.reason or '').split('|')[0].strip()
                    self._save_bet_notification(
                        race_id, _combos, final_bet_target.odds or 0.0,
                        _amount, _cond_id, 'confirmed', _amounts
                    )
                except Exception as _log_err:
                    print(f"  [WARN] 通知記録失敗(confirmed): {_log_err}")
                # 採点詳細を detail チャンネルへ送信
                try:
                    detail_msg = format_detail_message(race_info, final_bet_target, preds)
                    send_discord_notification(detail_msg, channel='detail')
                except Exception as detail_err:
                    print(f"  [WARN] 採点詳細送信失敗: {detail_err}")
                return True
            else:
                print(f"[ERROR] 通知送信失敗: {race_id}")
                return False
        except Exception as e:
            print(f"[ERROR] 通知送信エラー: {race_id} - {e}")
            send_error_notification("レース通知失敗", f"レースID: {race_id}\nエラー: {str(e)}")
            return False

    @staticmethod
    def _parse_odds_range(odds_range: str) -> tuple:
        """
        odds_range文字列を (min, max) のタプルにパースする。

        例:
            "100-200倍" -> (100.0, 200.0)
            "100倍+"    -> (100.0, None)
            "-"         -> (None, None)

        Returns:
            (Optional[float], Optional[float]): (下限, 上限)。上限なしは None
        """
        if not odds_range or odds_range == '-':
            return (None, None)
        try:
            s = odds_range.replace('倍', '').strip()
            if s.endswith('+'):
                return (float(s[:-1]), None)
            if '-' in s:
                lo, hi = s.split('-', 1)
                return (float(lo), float(hi))
        except (ValueError, AttributeError):
            pass
        return (None, None)

    def _check_and_refresh_odds_late(self, race: Dict) -> Dict:
        """
        締切3-5分前の最終オッズ確認。購入対象の組み合わせが条件のオッズ範囲外に変動した場合に
        「キャンセル検討」通知を送信。

        旧: 変動率30%以上で補足通知
        新: 購入条件のodds_range外に出たかどうかで判定

        Returns:
            dict: {'checked': bool, 'alerted': int}
        """
        race_id = race['race_id']
        result = {'checked': False, 'alerted': 0}

        # 購入通知済みレースのみ対象
        if race_id not in self.notified_races:
            return result
        # 既に後期確認済みならスキップ
        if race_id in self.late_fetched_races:
            return result

        deadline = self.parse_deadline(race['date'], race['deadline'])
        now = datetime.now()
        time_until = (deadline - now).total_seconds() / 60

        if not (2 <= time_until <= 6):
            return result

        try:
            new_odds_data = self._fetch_web_odds(race)
            result['checked'] = True

            if not new_odds_data:
                # 取得失敗の場合は再試行可能にするためaddしない
                return result

            self.late_fetched_races.add(race_id)

            bet_target = race['bet_target']
            min_v, max_v = self._parse_odds_range(getattr(bet_target, 'odds_range', None) or '-')
            # odds_range未設定のレースは判定不能なのでスキップ
            if min_v is None and max_v is None:
                return result
            venue_name = self.get_venue_name(race['venue_code'])
            out_of_range = []

            # 通知時の買い目それぞれについて範囲外チェック
            # 購入判定と整合させるため上限は半開区間（odds_min <= odds < odds_max）
            notified_odds_map = race.get('notified_odds_map', {})
            for combination in notified_odds_map:
                current_odds = new_odds_data.get(combination, 0.0)
                if current_odds <= 0:
                    continue
                is_out = (
                    (min_v is not None and current_odds < min_v) or
                    (max_v is not None and current_odds >= max_v)
                )
                if is_out:
                    out_of_range.append((combination, current_odds))
                    print(f"  [範囲外] {race_id} {combination}: {current_odds:.1f}倍 (範囲{min_v}-{max_v}倍)")

            if out_of_range:
                combo_str = '、'.join(f"`{c}` {o:.1f}倍" for c, o in out_of_range)
                range_str = f"{min_v}-{max_v}倍" if min_v and max_v else '-'
                msg = (
                    f"⚠️ **{venue_name} {race['race_number']}R** 締切{race['deadline']}\n"
                    f"購入対象オッズが範囲外に変動（キャンセル検討）\n"
                    f"{combo_str}　条件範囲: {range_str}"
                )
                send_discord_notification(msg, channel='buy')
                result['alerted'] += len(out_of_range)

        except Exception as e:
            print(f"[ERROR] 後期オッズ確認エラー: {race_id} - {e}")

        return result

    def monitor_once(self) -> Dict[str, int]:
        """
        1回の監視サイクルを実行

        重複実行防止: 前サイクルが終わっていない場合はスキップ

        Returns:
            Dict[str, int]: 実行結果統計
        """
        # 前サイクルがまだ実行中なら即スキップ
        if self._monitoring_active:
            print("[INFO] 前サイクルが実行中のためスキップ")
            return {'total_races': 0, 'odds_fetched': 0, 'direct_info_fetched': 0,
                    'notifications_sent': 0, 'late_odds_checks': 0, 'odds_change_alerts': 0, 'errors': 0}

        self._monitoring_active = True
        stats = {
            'total_races': 0,
            'odds_fetched': 0,
            'direct_info_fetched': 0,
            'notifications_sent': 0,
            'late_odds_checks': 0,
            'odds_change_alerts': 0,
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
                    # オッズ再取得チェック（締切10-25分前）
                    # ※ 直前情報取得より先に実行することで _reevaluate_after_beforeinfo() が
                    #   最新DBオッズで再評価できる（CANDIDATE→EXCLUDED 取りこぼし防止）
                    if self._check_and_fetch_odds(race):
                        stats['odds_fetched'] += 1

                    # 直前情報取得チェック（締切10-25分前、取得後にbefore予測生成+再評価）
                    if self.check_and_fetch_direct_info(race):
                        stats['direct_info_fetched'] += 1

                    # 最終判定・通知（締切7-9分前、最新Webオッズ取得→再評価→購入通知 or 見送り通知）
                    if self.check_and_notify(race):
                        stats['notifications_sent'] += 1

                    # 後期オッズ確認（締切3-5分前、購入通知済みレースのみ・範囲外変動で警告通知）
                    late_result = self._check_and_refresh_odds_late(race)
                    stats['late_odds_checks'] += late_result['checked']
                    stats['odds_change_alerts'] += late_result['alerted']

                except Exception as e:
                    print(f"[ERROR] レース処理エラー: {race['race_id']} - {e}")
                    stats['errors'] += 1

            # Gap1対応: watchlist外の全レースの直前情報チェック
            # advance予測では対象外でも、before予測で購入対象になるレースを捕捉する
            all_today_races = self._get_all_today_races_simple()
            for race_simple in all_today_races:
                if race_simple['race_id'] not in self.fetched_direct_info:
                    try:
                        if self._check_universal_beforeinfo(race_simple):
                            stats['direct_info_fetched'] += 1
                    except Exception as e:
                        print(f"[ERROR] Gap1チェックエラー: race_id={race_simple['race_id']} - {e}")
                        stats['errors'] += 1

        except Exception as e:
            print(f"[ERROR] 監視サイクルエラー: {e}")
            send_error_notification("監視サイクル失敗", str(e), severity='critical')
            stats['errors'] += 1

        finally:
            self._monitoring_active = False

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
