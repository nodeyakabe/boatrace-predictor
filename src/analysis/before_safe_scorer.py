"""
BEFORE_SAFE スコアラー v2

有効な直前情報のみを使用する安全版スコアリング
Phase 4で再設計したST・展示タイムを統合

改善項目:
- 進入コース: 37.8%（既存）
- 部品交換・体重: 39.2%（既存）
- ST: 会場別標準化+級別補正（Phase 4で再設計）
- 展示タイム: 順位重視+標準化（Phase 4で再設計）
"""

from typing import Dict, Optional
import sqlite3
from src.utils.db_connection_pool import get_connection
from src.scoring.st_scorer_v2 import STScorerV2
from src.scoring.exhibition_scorer_v2 import ExhibitionScorerV2


class BeforeSafeScorer:
    """BEFORE_SAFE スコアラー（安全版直前情報スコアリング）"""

    def __init__(self, db_path: str = "data/boatrace.db", use_st_exhibition: bool = True):
        """
        初期化

        Args:
            db_path: データベースパス
            use_st_exhibition: STと展示タイムを使用するか（Phase 4で再設計版）
        """
        self.db_path = db_path
        self.use_st_exhibition = use_st_exhibition

        # スコアラーv2の初期化（Phase 4で再設計）
        if use_st_exhibition:
            self.st_scorer = STScorerV2(db_path=db_path)
            self.exhibition_scorer = ExhibitionScorerV2(db_path=db_path)
        else:
            self.st_scorer = None
            self.exhibition_scorer = None

        # スコア配分（Phase 5版 - 重み調整）
        if use_st_exhibition:
            # 4項目統合版（Phase 5で重み引き上げ）
            self.ENTRY_WEIGHT = 0.20      # 進入コース（37.8%的中）
            self.PARTS_WEIGHT = 0.20      # 部品交換・体重（39.2%的中）
            self.ST_WEIGHT = 0.30         # ST（Phase 4で再設計、Phase 5で重み増）
            self.EXHIBITION_WEIGHT = 0.30 # 展示タイム（Phase 4で再設計、Phase 5で重み増）
        else:
            # 2項目のみ版（Phase 3互換）
            self.ENTRY_WEIGHT = 0.6   # 進入コース（37.8%的中）
            self.PARTS_WEIGHT = 0.4   # 部品交換・体重（39.2%的中）
            self.ST_WEIGHT = 0.0
            self.EXHIBITION_WEIGHT = 0.0

    def calculate_before_safe_score(
        self,
        race_id: int,
        pit_number: int,
        beforeinfo_data: Optional[Dict] = None
    ) -> Dict:
        """
        BEFORE_SAFEスコアを計算

        Args:
            race_id: レースID
            pit_number: 艇番（1-6）
            beforeinfo_data: 直前情報データ（Noneの場合はDBから読み込み）

        Returns:
            dict: {
                'total_score': float,       # 総合スコア（-20〜+20程度）
                'entry_score': float,       # 進入コーススコア
                'parts_score': float,       # 部品交換スコア
                'weight_score': float,      # 体重スコア
                'st_score': float,          # STスコア（Phase 4）
                'exhibition_score': float,  # 展示タイムスコア（Phase 4）
                'confidence': float,        # 信頼度（0.0-1.0）
                'data_completeness': float  # データ充実度（0.0-1.0）
            }
        """
        # データ取得
        if beforeinfo_data is None:
            beforeinfo_data = self._load_beforeinfo_from_db(race_id)

        if not beforeinfo_data or not beforeinfo_data.get('is_published'):
            # 直前情報がない場合は0点
            return self._get_empty_score()

        # 会場コード取得（DBから）
        venue_code = self._get_venue_code(race_id)

        # 各項目のスコア計算
        entry_score = self._calc_entry_score(
            pit_number, beforeinfo_data.get('exhibition_courses', {})
        )
        parts_score, weight_score = self._calc_parts_weight_score(
            pit_number, beforeinfo_data
        )

        # Phase 4: STスコア計算（再設計版）
        st_score = 0.0
        if self.use_st_exhibition and self.st_scorer:
            racer_data = self._get_racer_data_for_pit(race_id, pit_number)
            st_result = self.st_scorer.calculate_st_score(
                venue_code=venue_code,
                pit_number=pit_number,
                beforeinfo_data=beforeinfo_data,
                racer_data=racer_data
            )
            st_score = st_result.get('st_score', 0.0)

        # Phase 4: 展示タイムスコア計算（再設計版）
        exhibition_score = 0.0
        if self.use_st_exhibition and self.exhibition_scorer:
            racer_data = self._get_racer_data_for_pit(race_id, pit_number)
            exhibition_result = self.exhibition_scorer.calculate_exhibition_score(
                venue_code=venue_code,
                pit_number=pit_number,
                beforeinfo_data=beforeinfo_data,
                racer_data=racer_data
            )
            exhibition_score = exhibition_result.get('exhibition_score', 0.0)

        # データ充実度を計算
        completeness_items = 0
        completeness_count = 0

        # 進入コースデータ
        if pit_number in beforeinfo_data.get('exhibition_courses', {}):
            completeness_items += 1
        completeness_count += 1

        # 部品交換・体重データ
        if beforeinfo_data.get('parts_exchange') or beforeinfo_data.get('weight_adjustments'):
            completeness_items += 1
        completeness_count += 1

        # STデータ（Phase 4）
        if self.use_st_exhibition:
            if pit_number in beforeinfo_data.get('st_times', {}):
                completeness_items += 1
            completeness_count += 1

        # 展示タイムデータ（Phase 4）
        if self.use_st_exhibition:
            if pit_number in beforeinfo_data.get('exhibition_times', {}):
                completeness_items += 1
            completeness_count += 1

        data_completeness = completeness_items / completeness_count if completeness_count > 0 else 0.0

        # 総合スコアを計算（重み付き平均）
        total_score = (
            self.ENTRY_WEIGHT * entry_score +
            self.PARTS_WEIGHT * (parts_score + weight_score) +
            self.ST_WEIGHT * st_score +
            self.EXHIBITION_WEIGHT * exhibition_score
        )

        # 信頼度を計算（データ充実度ベース）
        confidence = data_completeness

        return {
            'total_score': total_score,
            'entry_score': entry_score,
            'parts_score': parts_score,
            'weight_score': weight_score,
            'st_score': st_score,
            'exhibition_score': exhibition_score,
            'confidence': confidence,
            'data_completeness': data_completeness
        }

    def _calc_entry_score(
        self,
        pit_number: int,
        exhibition_courses: Dict[int, int]
    ) -> float:
        """
        進入コーススコア計算

        Args:
            pit_number: 艇番
            exhibition_courses: 進入コース情報 {pit_number: course}

        Returns:
            スコア（-10〜+12点）
        """
        if not exhibition_courses or pit_number not in exhibition_courses:
            return 0.0

        course = exhibition_courses[pit_number]
        expected_course = pit_number  # 枠なりの場合

        # 進入変更の評価
        if course == 1 and pit_number != 1:
            # 1コース奪取（イン逃げ狙い）
            return 12.0
        elif course == 2 and pit_number >= 3:
            # 2コース奪取（前づけ成功）
            return 8.0
        elif course == 3 and pit_number >= 4:
            # 3コース奪取
            return 5.0
        elif course == expected_course:
            # 枠なり
            return 0.0
        elif course > expected_course:
            # 外に追いやられる（不利）
            if course - expected_course >= 3:
                # 深く追いやられる
                return -10.0
            else:
                return -5.0
        else:
            # 内に入る（有利）
            return 3.0

    def _calc_parts_weight_score(
        self,
        pit_number: int,
        beforeinfo_data: Dict
    ) -> tuple:
        """
        部品交換・体重スコア計算

        Args:
            pit_number: 艇番
            beforeinfo_data: 直前情報データ

        Returns:
            (parts_score, weight_score): 部品交換スコア、体重スコア
        """
        parts_score = 0.0
        weight_score = 0.0

        # 部品交換スコア
        parts_exchange = beforeinfo_data.get('parts_exchange', {})
        if pit_number in parts_exchange:
            pit_parts = parts_exchange[pit_number]

            # ピストン交換: モーター不調の兆候
            if pit_parts.get('piston', False) or pit_parts.get('P', False):
                parts_score -= 12.0

            # リング交換: やや不調の兆候
            if pit_parts.get('ring', False) or pit_parts.get('R', False):
                parts_score -= 8.0

            # シリンダー交換: 大きな不調
            if pit_parts.get('cylinder', False) or pit_parts.get('C', False):
                parts_score -= 18.0

            # キャブレター交換
            if pit_parts.get('carburetor', False):
                parts_score -= 5.0

            # ギアケース交換
            if pit_parts.get('gear_case', False):
                parts_score -= 5.0

        # 体重スコア
        weight_adjustments = beforeinfo_data.get('weight_adjustments', {})
        if pit_number in weight_adjustments:
            weight_delta = weight_adjustments[pit_number]

            # 体重が重いほど不利（+1kgで-1点）
            weight_score = -1.0 * weight_delta

        return parts_score, weight_score

    def _get_venue_code(self, race_id: int) -> str:
        """
        レースの会場コードを取得

        Args:
            race_id: レースID

        Returns:
            会場コード（"01"-"24"）
        """
        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            query = "SELECT venue_code FROM races WHERE id = ?"
            cursor.execute(query, (race_id,))
            row = cursor.fetchone()
            cursor.close()

            if row and row[0]:
                # venue_codeを2桁文字列に変換（例: "1" → "01"）
                venue_code = str(row[0]).zfill(2)
                return venue_code
            return "01"  # デフォルト値
        except Exception as e:
            print(f"Warning: 会場コード取得エラー (race_id={race_id}): {e}")
            return "01"

    def _get_racer_data_for_pit(self, race_id: int, pit_number: int) -> Optional[Dict]:
        """
        特定艇の選手データを取得（級別補正用）

        Args:
            race_id: レースID
            pit_number: 艇番

        Returns:
            選手データ辞書（{'rank': 'A1'}など）、なければNone
        """
        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            query = """
                SELECT racer_rank
                FROM race_entries
                WHERE race_id = ? AND pit_number = ?
            """
            cursor.execute(query, (race_id, pit_number))
            row = cursor.fetchone()
            cursor.close()

            if row and row[0]:
                return {'rank': row[0]}
            return None
        except Exception as e:
            print(f"Warning: 選手データ取得エラー (race_id={race_id}, pit={pit_number}): {e}")
            return None

    def _load_beforeinfo_from_db(self, race_id: int) -> Dict:
        """
        DBから直前情報を読み込み

        Args:
            race_id: レースID

        Returns:
            直前情報データ辞書
        """
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 進入コース情報
        cursor.execute("""
            SELECT pit_number, exhibition_course
            FROM race_details
            WHERE race_id = ? AND exhibition_course IS NOT NULL
        """, (race_id,))

        exhibition_courses = {}
        for row in cursor.fetchall():
            exhibition_courses[row['pit_number']] = row['exhibition_course']

        # ST情報（Phase 4で追加）
        st_times = {}
        if self.use_st_exhibition:
            cursor.execute("""
                SELECT pit_number, st_time
                FROM race_details
                WHERE race_id = ? AND st_time IS NOT NULL
            """, (race_id,))
            for row in cursor.fetchall():
                st_times[row['pit_number']] = row['st_time']

        # 展示タイム情報（Phase 4で追加）
        exhibition_times = {}
        if self.use_st_exhibition:
            cursor.execute("""
                SELECT pit_number, exhibition_time
                FROM race_details
                WHERE race_id = ? AND exhibition_time IS NOT NULL
            """, (race_id,))
            for row in cursor.fetchall():
                exhibition_times[row['pit_number']] = row['exhibition_time']

        # 部品交換情報（今後DBに追加予定）
        parts_exchange = {}

        # 体重調整情報（今後DBに追加予定）
        weight_adjustments = {}

        cursor.close()

        return {
            'is_published': len(exhibition_courses) > 0,
            'exhibition_courses': exhibition_courses,
            'st_times': st_times,
            'exhibition_times': exhibition_times,
            'parts_exchange': parts_exchange,
            'weight_adjustments': weight_adjustments
        }

    def _get_empty_score(self) -> Dict:
        """
        空スコアを返す（直前情報がない場合）

        Returns:
            全項目が0のスコア辞書
        """
        return {
            'total_score': 0.0,
            'entry_score': 0.0,
            'parts_score': 0.0,
            'weight_score': 0.0,
            'st_score': 0.0,
            'exhibition_score': 0.0,
            'confidence': 0.0,
            'data_completeness': 0.0
        }
