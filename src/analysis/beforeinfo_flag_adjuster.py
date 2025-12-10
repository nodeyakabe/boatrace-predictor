"""
直前情報フラグ調整モジュール

BEFOREデータを状態フラグとして扱い、PRE_SCOREを補正する。
スコア統合ではなく、「その日の状態変化」を反映する。
"""

from typing import Dict, Optional
import sqlite3
from src.utils.db_connection_pool import get_connection


class BeforeInfoFlagAdjuster:
    """直前情報フラグ調整クラス"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path

    def calculate_adjustment_factors(
        self,
        race_id: int,
        pit_number: int
    ) -> Dict:
        """
        直前情報フラグに基づく調整係数を計算

        Args:
            race_id: レースID
            pit_number: 艇番（1-6）

        Returns:
            dict: {
                'score_multiplier': float,      # PRE_SCOREへの乗算係数（0.7-1.2）
                'confidence_multiplier': float, # 信頼度への乗算係数（0.5-1.0）
                'flags': {
                    'has_fl': bool,             # F/Lフラグ
                    'makuri_setup': bool,       # まくり狙いフラグ
                    'entry_risk': bool,         # 進入変化リスクフラグ
                    'exhibition_good': bool,    # 展示タイム好調フラグ
                    'parts_replaced': bool      # 部品交換フラグ
                },
                'reasons': [str]                # 調整理由のリスト
            }
        """
        # DB接続を取得（全メソッドで共有）
        conn = get_connection(self.db_path)

        try:
            # データ取得
            beforeinfo = self._load_beforeinfo(conn, race_id, pit_number)

            if not beforeinfo:
                return self._get_neutral_adjustment()

            # 各フラグを判定
            flags = {
                'has_fl': self._check_fl_flag(beforeinfo),
                'makuri_setup': self._check_makuri_setup_flag(conn, beforeinfo, race_id, pit_number),
                'entry_risk': self._check_entry_risk_flag(beforeinfo, race_id, pit_number),
                'exhibition_good': self._check_exhibition_good_flag(conn, beforeinfo, race_id, pit_number),
                'parts_replaced': self._check_parts_replaced_flag(beforeinfo)
            }

            # 調整係数を計算
            score_multiplier = 1.0
            confidence_multiplier = 1.0
            reasons = []

            # F/Lフラグ: PRE_SCORE × 0.7
            if flags['has_fl']:
                score_multiplier *= 0.7
                reasons.append("F/L発生 (-30%)")

            # まくり狙いフラグ: PRE_SCORE × 1.2
            if flags['makuri_setup']:
                score_multiplier *= 1.2
                reasons.append("まくり狙いセットアップ (+20%)")

            # 進入変化リスクフラグ: 信頼度 × 0.5
            if flags['entry_risk']:
                confidence_multiplier *= 0.5
                reasons.append("進入変化リスク (信頼度-50%)")

            # 展示タイム好調フラグ: PRE_SCORE × 1.1
            if flags['exhibition_good']:
                score_multiplier *= 1.1
                reasons.append("展示タイム好調 (+10%)")

            # 部品交換フラグ: PRE_SCORE × 0.9
            if flags['parts_replaced']:
                score_multiplier *= 0.9
                reasons.append("部品交換あり (-10%)")

            return {
                'score_multiplier': score_multiplier,
                'confidence_multiplier': confidence_multiplier,
                'flags': flags,
                'reasons': reasons
            }
        finally:
            # 接続プールを使用しているため、明示的にcloseしない
            # conn.close()は不要（プール管理に任せる）
            pass

    def _check_fl_flag(self, beforeinfo: Dict) -> bool:
        """
        F/Lフラグの判定

        Args:
            beforeinfo: 直前情報データ

        Returns:
            bool: F/Lがある場合True
        """
        st = beforeinfo.get('start_timing')
        if st is None:
            return False

        # F (フライング): 0.01秒未満
        # L (出遅れ): 1.0秒以上
        return st < 0.01 or st >= 1.0

    def _check_makuri_setup_flag(
        self,
        conn: sqlite3.Connection,
        beforeinfo: Dict,
        race_id: int,
        pit_number: int
    ) -> bool:
        """
        まくり狙いフラグの判定

        チルト角度が高い + まくり適性のある選手 + まくりやすい場

        Args:
            conn: DB接続
            beforeinfo: 直前情報データ
            race_id: レースID
            pit_number: 艇番

        Returns:
            bool: まくり狙いと判定される場合True
        """
        tilt = beforeinfo.get('tilt_angle')
        if tilt is None or tilt <= 0:
            return False

        # チルト角度が高い（+0.5度以上）
        if tilt < 0.5:
            return False

        # 選手のまくり率を取得
        cursor = conn.cursor()

        cursor.execute('''
            SELECT racer_id FROM race_details
            WHERE race_id = ? AND pit_number = ?
        ''', (race_id, pit_number))
        row = cursor.fetchone()

        if not row:
            return False

        racer_id = row[0]

        # まくり決まり手の割合を取得
        cursor.execute('''
            SELECT
                COUNT(CASE WHEN rd.winning_technique = 2 THEN 1 END) * 1.0 / COUNT(*) as makuri_rate
            FROM results r
            JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number
            WHERE rd.racer_id = ? AND r.rank = '1'
        ''', (racer_id,))
        row = cursor.fetchone()

        if not row or row[0] is None:
            return False

        makuri_rate = row[0]

        # まくり率が30%以上ならまくり狙いと判定
        return makuri_rate >= 0.3

    def _check_entry_risk_flag(
        self,
        beforeinfo: Dict,
        race_id: int,
        pit_number: int
    ) -> bool:
        """
        進入変化リスクフラグの判定

        展示航走と本番予測の進入コースが異なる場合

        Args:
            beforeinfo: 直前情報データ
            race_id: レースID
            pit_number: 艇番

        Returns:
            bool: 進入変化リスクがある場合True
        """
        exhibition_course = beforeinfo.get('exhibition_course')
        if exhibition_course is None:
            # 展示航走データがない場合はリスクあり
            return True

        # 進入予測モデルから本番予測を取得
        # ここでは簡易的に、艇番と展示コースが一致しない場合をリスクとする
        # （進入予測モデルの詳細実装は別途必要）

        # 簡易判定: 展示航走で艇番通りでない場合はリスク
        return exhibition_course != pit_number

    def _check_exhibition_good_flag(
        self,
        conn: sqlite3.Connection,
        beforeinfo: Dict,
        race_id: int,
        pit_number: int
    ) -> bool:
        """
        展示タイム好調フラグの判定

        展示タイムがレース内で1-2位の場合

        Args:
            conn: DB接続
            beforeinfo: 直前情報データ
            race_id: レースID
            pit_number: 艇番

        Returns:
            bool: 展示タイム好調の場合True
        """
        exhibition_time = beforeinfo.get('exhibition_time')
        if exhibition_time is None:
            return False

        # レース内の全艇の展示タイムを取得
        cursor = conn.cursor()

        cursor.execute('''
            SELECT pit_number, exhibition_time
            FROM race_details
            WHERE race_id = ? AND exhibition_time IS NOT NULL
            ORDER BY exhibition_time
        ''', (race_id,))
        times = cursor.fetchall()

        if len(times) < 3:
            return False

        # 上位2位以内ならTrue
        for i, (pit, time) in enumerate(times[:2], 1):
            if pit == pit_number:
                return True

        return False

    def _check_parts_replaced_flag(self, beforeinfo: Dict) -> bool:
        """
        部品交換フラグの判定

        Args:
            beforeinfo: 直前情報データ

        Returns:
            bool: 部品交換がある場合True
        """
        parts = beforeinfo.get('parts_replacement')
        if parts is None:
            return False

        # プロペラ、電気系統、ギヤケースのいずれかが交換されている
        return parts in ['プロペラ', '電気一式', 'ギヤケース', '\\1', '\\2', '\\3']

    def _load_beforeinfo(self, conn: sqlite3.Connection, race_id: int, pit_number: int) -> Optional[Dict]:
        """
        直前情報をDBから読み込み

        Args:
            conn: DB接続
            race_id: レースID
            pit_number: 艇番

        Returns:
            dict: 直前情報データ
        """
        cursor = conn.cursor()

        cursor.execute('''
            SELECT
                exhibition_time,
                st_time,
                exhibition_course,
                tilt_angle,
                parts_replacement
            FROM race_details
            WHERE race_id = ? AND pit_number = ?
        ''', (race_id, pit_number))

        row = cursor.fetchone()

        if not row:
            return None

        result = {
            'exhibition_time': row[0],
            'start_timing': row[1],  # st_timeを使用
            'exhibition_course': row[2],
            'tilt_angle': row[3],
            'parts_replacement': row[4]
        }

        return result

    def _get_neutral_adjustment(self) -> Dict:
        """
        ニュートラルな調整係数（データなし時）

        Returns:
            dict: 調整係数（すべて1.0）
        """
        return {
            'score_multiplier': 1.0,
            'confidence_multiplier': 1.0,
            'flags': {
                'has_fl': False,
                'makuri_setup': False,
                'entry_risk': False,
                'exhibition_good': False,
                'parts_replaced': False
            },
            'reasons': []
        }
