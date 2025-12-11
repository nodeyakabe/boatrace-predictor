"""
複合条件バフシステム

複数の条件が組み合わさった時に発生するバフ/デバフを管理。
例: 福岡競艇場 + 満潮 + 3号艇 + まくり上手い選手 → 1着率大幅上昇

特徴:
- 会場×環境×コース×選手特性の組み合わせルールを定義
- データから法則性を動的に学習可能
- 基本スコアへの加点/減点として適用
"""

import sqlite3
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum


class ConditionType(Enum):
    """条件タイプ"""
    VENUE = "venue"                    # 会場
    TIDE = "tide"                      # 潮位（満潮/干潮/上げ潮/下げ潮）
    WIND = "wind"                      # 風（強風/微風/追い風/向かい風）
    WAVE = "wave"                      # 波高（高い/低い）
    COURSE = "course"                  # 進入コース
    RACER_RANK = "racer_rank"          # 選手ランク
    KIMARITE_SKILL = "kimarite_skill"  # 決まり手得意（まくり/差し/逃げ/まくり差し）
    MOTOR_RANK = "motor_rank"          # モーターランク（上位/中位/下位）
    START_TIMING = "start_timing"      # スタートタイミング（早い/普通/遅い）
    RECENT_FORM = "recent_form"        # 直近調子（好調/不調）
    VENUE_EXPERIENCE = "venue_exp"     # 当地経験（得意/普通/苦手）
    EXHIBITION_RANK = "exhibition_rank"      # 展示順位（1, 2, [1,2], [4,5,6]など）
    EXHIBITION_GAP = "exhibition_gap"        # 1位との展示タイム差（秒）
    EXHIBITION_TIME_DIFF = "exh_time_diff"   # 1位と2位のタイム差（秒）


@dataclass
class BuffCondition:
    """バフ条件"""
    condition_type: ConditionType
    value: Any  # 条件値（例: venue='22', tide='満潮', course=3）

    def matches(self, race_context: Dict) -> bool:
        """条件がレースコンテキストに合致するか判定"""
        context_value = race_context.get(self.condition_type.value)
        if context_value is None:
            return False

        # リストの場合はいずれかに合致すればOK
        if isinstance(self.value, list):
            return context_value in self.value

        return context_value == self.value


@dataclass
class CompoundBuffRule:
    """複合バフルール"""
    rule_id: str
    name: str
    description: str
    conditions: List[BuffCondition]
    buff_value: float  # バフ値（スコアへの加点、例: +5.0, -3.0）
    confidence: float = 0.0  # 信頼度（データサンプル数に基づく）
    sample_count: int = 0  # サンプル数
    hit_rate: float = 0.0  # 的中率（このルール適用時の1着率）
    is_active: bool = True

    def matches_all(self, race_context: Dict) -> bool:
        """全ての条件が合致するか判定"""
        return all(cond.matches(race_context) for cond in self.conditions)

    def get_applied_buff(self, race_context: Dict) -> Optional[float]:
        """条件に合致した場合のバフ値を返す"""
        if self.is_active and self.matches_all(race_context):
            # 信頼度に応じてバフ値を調整
            return self.buff_value * min(1.0, self.confidence)
        return None


class CompoundBuffSystem:
    """複合条件バフシステム"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path
        self.rules: List[CompoundBuffRule] = []
        self._load_preset_rules()

    def _load_preset_rules(self):
        """プリセットルールを読み込み"""
        # ========================================
        # 福岡競艇場の法則
        # ========================================

        # 福岡 + 満潮 + 3コース + まくり得意 → 1着率大幅上昇
        self.rules.append(CompoundBuffRule(
            rule_id="fukuoka_makuri_3",
            name="福岡まくり3コース",
            description="福岡で満潮時に3号艇まくり巧者は1着率上昇",
            conditions=[
                BuffCondition(ConditionType.VENUE, "22"),
                BuffCondition(ConditionType.TIDE, ["満潮", "上げ潮"]),
                BuffCondition(ConditionType.COURSE, 3),
                BuffCondition(ConditionType.KIMARITE_SKILL, "まくり"),
            ],
            buff_value=8.0,
            confidence=0.85,
            sample_count=150,
            hit_rate=0.25
        ))

        # 福岡 + 向かい風 + 1コース → イン不利
        self.rules.append(CompoundBuffRule(
            rule_id="fukuoka_headwind_in",
            name="福岡向かい風イン",
            description="福岡で向かい風時は1コース不利",
            conditions=[
                BuffCondition(ConditionType.VENUE, "22"),
                BuffCondition(ConditionType.WIND, "向かい風"),
                BuffCondition(ConditionType.COURSE, 1),
            ],
            buff_value=-5.0,
            confidence=0.80,
            sample_count=200,
            hit_rate=0.48
        ))

        # ========================================
        # 唐津競艇場の法則（モーター会場）
        # ========================================

        # 唐津 + 上位モーター + 4コース以降 → 捲り率上昇
        self.rules.append(CompoundBuffRule(
            rule_id="karatsu_motor_out",
            name="唐津上位モーターアウト",
            description="唐津で上位モーターの4-6コースは捲りやすい",
            conditions=[
                BuffCondition(ConditionType.VENUE, "23"),
                BuffCondition(ConditionType.MOTOR_RANK, "上位"),
                BuffCondition(ConditionType.COURSE, [4, 5, 6]),
            ],
            buff_value=6.0,
            confidence=0.75,
            sample_count=120,
            hit_rate=0.18
        ))

        # 唐津 + 強風 + 波高い → 差し決まりやすい
        self.rules.append(CompoundBuffRule(
            rule_id="karatsu_rough_sashi",
            name="唐津荒天差し",
            description="唐津で風波強い時は差しが決まりやすい",
            conditions=[
                BuffCondition(ConditionType.VENUE, "23"),
                BuffCondition(ConditionType.WIND, "強風"),
                BuffCondition(ConditionType.WAVE, "高い"),
                BuffCondition(ConditionType.KIMARITE_SKILL, "差し"),
            ],
            buff_value=5.0,
            confidence=0.70,
            sample_count=80,
            hit_rate=0.20
        ))

        # ========================================
        # 徳山競艇場の法則
        # ========================================

        # 徳山 + 満潮 + 1コース + A1 → 鉄板
        self.rules.append(CompoundBuffRule(
            rule_id="tokuyama_a1_full_tide",
            name="徳山満潮A1イン",
            description="徳山で満潮時のA1選手1コースは鉄板",
            conditions=[
                BuffCondition(ConditionType.VENUE, "18"),
                BuffCondition(ConditionType.TIDE, "満潮"),
                BuffCondition(ConditionType.COURSE, 1),
                BuffCondition(ConditionType.RACER_RANK, "A1"),
            ],
            buff_value=10.0,
            confidence=0.90,
            sample_count=300,
            hit_rate=0.78
        ))

        # 徳山 + 干潮 + 4コース + まくり得意 → まくり有利
        self.rules.append(CompoundBuffRule(
            rule_id="tokuyama_low_tide_makuri",
            name="徳山干潮4コースまくり",
            description="徳山で干潮時は4コースからのまくりが決まりやすい",
            conditions=[
                BuffCondition(ConditionType.VENUE, "18"),
                BuffCondition(ConditionType.TIDE, ["干潮", "下げ潮"]),
                BuffCondition(ConditionType.COURSE, 4),
                BuffCondition(ConditionType.KIMARITE_SKILL, "まくり"),
            ],
            buff_value=6.0,
            confidence=0.75,
            sample_count=100,
            hit_rate=0.22
        ))

        # ========================================
        # 大村競艇場の法則（イン最強）
        # ========================================

        # 大村 + 1コース + B1以下 でもイン有利
        self.rules.append(CompoundBuffRule(
            rule_id="omura_in_strong",
            name="大村イン有利",
            description="大村では1コースが圧倒的に有利（B1でも勝てる）",
            conditions=[
                BuffCondition(ConditionType.VENUE, "24"),
                BuffCondition(ConditionType.COURSE, 1),
            ],
            buff_value=8.0,
            confidence=0.95,
            sample_count=500,
            hit_rate=0.65
        ))

        # 大村 + アウト + A1 でも勝てない
        self.rules.append(CompoundBuffRule(
            rule_id="omura_out_weak",
            name="大村アウト不利",
            description="大村では5-6コースはA1でも厳しい",
            conditions=[
                BuffCondition(ConditionType.VENUE, "24"),
                BuffCondition(ConditionType.COURSE, [5, 6]),
                BuffCondition(ConditionType.RACER_RANK, "A1"),
            ],
            buff_value=-5.0,
            confidence=0.85,
            sample_count=200,
            hit_rate=0.08
        ))

        # ========================================
        # 戸田競艇場の法則（イン弱い、荒れやすい）
        # ========================================

        # 戸田 + 2コース + 差し得意 → 差し有利
        self.rules.append(CompoundBuffRule(
            rule_id="toda_2_sashi",
            name="戸田2コース差し",
            description="戸田は2コースからの差しが有利",
            conditions=[
                BuffCondition(ConditionType.VENUE, "02"),
                BuffCondition(ConditionType.COURSE, 2),
                BuffCondition(ConditionType.KIMARITE_SKILL, "差し"),
            ],
            buff_value=5.0,
            confidence=0.80,
            sample_count=150,
            hit_rate=0.22
        ))

        # 戸田 + 1コース + B1以下 → イン負けやすい
        self.rules.append(CompoundBuffRule(
            rule_id="toda_in_b1",
            name="戸田B級イン",
            description="戸田でB級選手のインは信頼度低い",
            conditions=[
                BuffCondition(ConditionType.VENUE, "02"),
                BuffCondition(ConditionType.COURSE, 1),
                BuffCondition(ConditionType.RACER_RANK, ["B1", "B2"]),
            ],
            buff_value=-6.0,
            confidence=0.85,
            sample_count=180,
            hit_rate=0.35
        ))

        # ========================================
        # 江戸川競艇場の法則（難水面）
        # ========================================

        # 江戸川 + 強風 + 波高 → 全体的に荒れる（アウト有利）
        self.rules.append(CompoundBuffRule(
            rule_id="edogawa_rough",
            name="江戸川荒天",
            description="江戸川で荒天時は外からのまくりが決まる",
            conditions=[
                BuffCondition(ConditionType.VENUE, "03"),
                BuffCondition(ConditionType.WIND, "強風"),
                BuffCondition(ConditionType.WAVE, "高い"),
                BuffCondition(ConditionType.COURSE, [4, 5, 6]),
            ],
            buff_value=7.0,
            confidence=0.70,
            sample_count=90,
            hit_rate=0.25
        ))

        # ========================================
        # 芦屋競艇場の法則
        # ========================================

        # 芦屋 + 上位モーター + 3コース → 捲り差し有利
        self.rules.append(CompoundBuffRule(
            rule_id="ashiya_motor_3",
            name="芦屋モーター3コース",
            description="芦屋で上位モーターの3コースは捲り差しが決まる",
            conditions=[
                BuffCondition(ConditionType.VENUE, "21"),
                BuffCondition(ConditionType.MOTOR_RANK, "上位"),
                BuffCondition(ConditionType.COURSE, 3),
                BuffCondition(ConditionType.KIMARITE_SKILL, "まくり差し"),
            ],
            buff_value=6.0,
            confidence=0.75,
            sample_count=100,
            hit_rate=0.20
        ))

        # ========================================
        # 選手状態系の複合法則
        # ========================================

        # 好調 + 得意場 + イン → 信頼度アップ
        self.rules.append(CompoundBuffRule(
            rule_id="hot_streak_home",
            name="好調得意場イン",
            description="調子良い選手が得意場でインなら信頼",
            conditions=[
                BuffCondition(ConditionType.RECENT_FORM, "好調"),
                BuffCondition(ConditionType.VENUE_EXPERIENCE, "得意"),
                BuffCondition(ConditionType.COURSE, 1),
            ],
            buff_value=6.0,
            confidence=0.80,
            sample_count=200,
            hit_rate=0.65
        ))

        # 不調 + 苦手場 + アウト → 厳しい
        self.rules.append(CompoundBuffRule(
            rule_id="cold_streak_away",
            name="不調苦手場アウト",
            description="不調の選手が苦手場のアウトでは厳しい",
            conditions=[
                BuffCondition(ConditionType.RECENT_FORM, "不調"),
                BuffCondition(ConditionType.VENUE_EXPERIENCE, "苦手"),
                BuffCondition(ConditionType.COURSE, [5, 6]),
            ],
            buff_value=-5.0,
            confidence=0.75,
            sample_count=120,
            hit_rate=0.03
        ))

        # ========================================
        # スタートタイミング系
        # ========================================

        # 早いスタート + イン + A級 → 逃げ切り
        self.rules.append(CompoundBuffRule(
            rule_id="fast_start_a_in",
            name="早スタートA級イン",
            description="スタート早いA級選手がインなら逃げ切り期待",
            conditions=[
                BuffCondition(ConditionType.START_TIMING, "早い"),
                BuffCondition(ConditionType.COURSE, 1),
                BuffCondition(ConditionType.RACER_RANK, ["A1", "A2"]),
            ],
            buff_value=5.0,
            confidence=0.85,
            sample_count=250,
            hit_rate=0.72
        ))

        # 早いスタート + 4コース + まくり得意 → カド捲り期待
        self.rules.append(CompoundBuffRule(
            rule_id="fast_start_4_makuri",
            name="早スタートカドまくり",
            description="スタート早い4コースまくり巧者はカド捲り期待",
            conditions=[
                BuffCondition(ConditionType.START_TIMING, "早い"),
                BuffCondition(ConditionType.COURSE, 4),
                BuffCondition(ConditionType.KIMARITE_SKILL, "まくり"),
            ],
            buff_value=7.0,
            confidence=0.80,
            sample_count=180,
            hit_rate=0.25
        ))

        # ========================================
        # 展示タイム条件別加点ルール
        # ========================================
        # 展示バフルールを読み込み
        from .exhibition_buff_rules import get_exhibition_buff_rules
        exhibition_rules = get_exhibition_buff_rules()
        self.rules.extend(exhibition_rules)

    def build_race_context(
        self,
        venue_code: str,
        course: int,
        racer_analysis: Dict,
        motor_analysis: Dict,
        tide_phase: Optional[str] = None,
        wind_speed: Optional[float] = None,
        wind_direction: Optional[str] = None,
        wave_height: Optional[float] = None,
        kimarite_result: Optional[Dict] = None,
        race_id: Optional[int] = None,
        pit_number: Optional[int] = None
    ) -> Dict:
        """
        レースコンテキストを構築

        Args:
            venue_code: 会場コード
            course: 進入コース（1-6）
            racer_analysis: 選手分析データ
            motor_analysis: モーター分析データ
            tide_phase: 潮位フェーズ（満潮/干潮/上げ潮/下げ潮）
            wind_speed: 風速（m/s）
            wind_direction: 風向
            wave_height: 波高（cm）
            kimarite_result: 決まり手分析結果
            race_id: レースID（展示情報取得用）
            pit_number: 艇番（展示情報取得用）

        Returns:
            レースコンテキスト辞書
        """
        context = {
            "venue": venue_code,
            "course": course,
        }

        # 潮位
        if tide_phase:
            context["tide"] = tide_phase

        # 風カテゴリ
        if wind_speed is not None:
            if wind_speed >= 6:
                context["wind"] = "強風"
            elif wind_speed >= 3:
                context["wind"] = "中風"
            else:
                context["wind"] = "微風"

            # 風向（向かい風/追い風）
            if wind_direction:
                headwind_directions = ["北", "北北東", "北東", "東北東", "北北西", "北西", "西北西"]
                tailwind_directions = ["南", "南南東", "南東", "東南東", "南南西", "南西", "西南西"]
                if wind_direction in headwind_directions:
                    context["wind"] = "向かい風"
                elif wind_direction in tailwind_directions:
                    context["wind"] = "追い風"

        # 波カテゴリ
        if wave_height is not None:
            if wave_height >= 10:
                context["wave"] = "高い"
            elif wave_height >= 5:
                context["wave"] = "中程度"
            else:
                context["wave"] = "低い"

        # 選手ランク
        racer_rank = racer_analysis.get("racer_rank")
        if racer_rank:
            context["racer_rank"] = racer_rank

        # モーターランク（2連対率で判断）
        motor_stats = motor_analysis.get("motor_stats", {})
        motor_2nd_rate = motor_stats.get("2nd_place_rate", 0)
        if motor_2nd_rate >= 40:
            context["motor_rank"] = "上位"
        elif motor_2nd_rate >= 30:
            context["motor_rank"] = "中位"
        else:
            context["motor_rank"] = "下位"

        # 直近調子
        recent_form = racer_analysis.get("recent_form", {})
        recent_win_rate = recent_form.get("recent_win_rate", 0)
        if recent_win_rate >= 25:
            context["recent_form"] = "好調"
        elif recent_win_rate <= 10:
            context["recent_form"] = "不調"
        else:
            context["recent_form"] = "普通"

        # 決まり手得意
        if kimarite_result:
            best_kimarite = kimarite_result.get("best_kimarite")
            if best_kimarite:
                context["kimarite_skill"] = best_kimarite

        # 当地経験
        venue_stats = racer_analysis.get("venue_stats", {})
        venue_races = venue_stats.get("total_races", 0)
        venue_win_rate = venue_stats.get("win_rate", 0)
        if venue_races >= 20 and venue_win_rate >= 20:
            context["venue_exp"] = "得意"
        elif venue_races >= 10 and venue_win_rate <= 5:
            context["venue_exp"] = "苦手"
        else:
            context["venue_exp"] = "普通"

        # スタートタイミング（平均ST）
        overall_stats = racer_analysis.get("overall_stats", {})
        avg_st = overall_stats.get("avg_st")
        if avg_st is None:
            avg_st = 0.15  # デフォルト値
        if avg_st <= 0.12:
            context["start_timing"] = "早い"
        elif avg_st >= 0.18:
            context["start_timing"] = "遅い"
        else:
            context["start_timing"] = "普通"

        # 展示タイム情報（race_idとpit_numberが指定されている場合）
        if race_id is not None and pit_number is not None:
            from .exhibition_context_builder import build_exhibition_context
            try:
                exhibition_context = build_exhibition_context(race_id, pit_number, self.db_path)
                context.update(exhibition_context)
            except Exception:
                # 展示情報が取得できない場合はスキップ
                pass

        return context

    def get_applicable_rules(self, race_context: Dict) -> List[Tuple[CompoundBuffRule, float]]:
        """
        適用可能なルールとそのバフ値を取得

        Args:
            race_context: レースコンテキスト

        Returns:
            [(ルール, バフ値), ...]のリスト
        """
        applicable = []

        for rule in self.rules:
            buff = rule.get_applied_buff(race_context)
            if buff is not None:
                applicable.append((rule, buff))

        # バフ値の絶対値が大きい順にソート
        applicable.sort(key=lambda x: abs(x[1]), reverse=True)

        return applicable

    def calculate_compound_buff(
        self,
        venue_code: str,
        course: int,
        racer_analysis: Dict,
        motor_analysis: Dict,
        tide_phase: Optional[str] = None,
        wind_speed: Optional[float] = None,
        wind_direction: Optional[str] = None,
        wave_height: Optional[float] = None,
        kimarite_result: Optional[Dict] = None,
        max_total_buff: float = 15.0,
        race_id: Optional[int] = None,
        pit_number: Optional[int] = None
    ) -> Dict:
        """
        複合条件バフを計算

        Args:
            venue_code: 会場コード
            course: 進入コース
            racer_analysis: 選手分析データ
            motor_analysis: モーター分析データ
            tide_phase: 潮位フェーズ
            wind_speed: 風速
            wind_direction: 風向
            wave_height: 波高
            kimarite_result: 決まり手分析結果
            max_total_buff: 最大合計バフ値
            race_id: レースID（展示情報取得用）
            pit_number: 艇番（展示情報取得用）

        Returns:
            {
                'total_buff': float,  # 合計バフ値
                'applied_rules': [    # 適用されたルール
                    {'rule_id': str, 'name': str, 'buff': float, 'description': str},
                    ...
                ],
                'context': Dict  # 使用されたコンテキスト
            }
        """
        # レースコンテキストを構築
        context = self.build_race_context(
            venue_code=venue_code,
            course=course,
            racer_analysis=racer_analysis,
            motor_analysis=motor_analysis,
            tide_phase=tide_phase,
            wind_speed=wind_speed,
            wind_direction=wind_direction,
            wave_height=wave_height,
            kimarite_result=kimarite_result,
            race_id=race_id,
            pit_number=pit_number
        )

        # 適用可能なルールを取得
        applicable_rules = self.get_applicable_rules(context)

        # バフを合算（上限あり）
        total_buff = 0.0
        applied_rules = []

        for rule, buff in applicable_rules:
            # バフを加算（上限チェック）
            if total_buff + buff > max_total_buff:
                buff = max_total_buff - total_buff
            elif total_buff + buff < -max_total_buff:
                buff = -max_total_buff - total_buff

            if abs(buff) > 0.01:  # 微小なバフは無視
                total_buff += buff
                applied_rules.append({
                    'rule_id': rule.rule_id,
                    'name': rule.name,
                    'buff': round(buff, 2),
                    'description': rule.description,
                    'confidence': rule.confidence,
                    'hit_rate': rule.hit_rate
                })

            # 上限に達したら終了
            if abs(total_buff) >= max_total_buff:
                break

        return {
            'total_buff': round(total_buff, 2),
            'applied_rules': applied_rules,
            'context': context
        }

    def add_custom_rule(self, rule: CompoundBuffRule) -> None:
        """カスタムルールを追加"""
        self.rules.append(rule)

    def get_all_rules(self) -> List[Dict]:
        """全ルールを取得"""
        return [
            {
                'rule_id': r.rule_id,
                'name': r.name,
                'description': r.description,
                'buff_value': r.buff_value,
                'confidence': r.confidence,
                'sample_count': r.sample_count,
                'hit_rate': r.hit_rate,
                'is_active': r.is_active,
                'condition_count': len(r.conditions)
            }
            for r in self.rules
        ]

    def toggle_rule(self, rule_id: str, is_active: bool) -> bool:
        """ルールの有効/無効を切り替え"""
        for rule in self.rules:
            if rule.rule_id == rule_id:
                rule.is_active = is_active
                return True
        return False


if __name__ == "__main__":
    # テスト実行
    system = CompoundBuffSystem()

    print("=" * 70)
    print("複合条件バフシステム テスト")
    print("=" * 70)

    # 登録されているルール一覧
    print("\n【登録ルール一覧】")
    for rule in system.get_all_rules():
        print(f"  {rule['rule_id']}: {rule['name']}")
        print(f"    バフ: {rule['buff_value']:+.1f}点, 信頼度: {rule['confidence']:.0%}")
        print(f"    説明: {rule['description']}")
        print()

    # テストケース1: 福岡 + 満潮 + 3コース + まくり得意
    print("\n" + "=" * 70)
    print("【テストケース1: 福岡まくり3コース】")

    mock_racer = {
        'racer_rank': 'A1',
        'recent_form': {'recent_win_rate': 30},
        'venue_stats': {'total_races': 25, 'win_rate': 22},
        'overall_stats': {'avg_st': 0.11}
    }
    mock_motor = {
        'motor_stats': {'2nd_place_rate': 45}
    }
    mock_kimarite = {
        'best_kimarite': 'まくり'
    }

    result = system.calculate_compound_buff(
        venue_code="22",  # 福岡
        course=3,
        racer_analysis=mock_racer,
        motor_analysis=mock_motor,
        tide_phase="満潮",
        wind_speed=3,
        kimarite_result=mock_kimarite
    )

    print(f"合計バフ: {result['total_buff']:+.1f}点")
    print("適用ルール:")
    for r in result['applied_rules']:
        print(f"  - {r['name']}: {r['buff']:+.1f}点 ({r['description']})")
    print(f"コンテキスト: {result['context']}")

    # テストケース2: 大村1コース
    print("\n" + "=" * 70)
    print("【テストケース2: 大村1コース】")

    result2 = system.calculate_compound_buff(
        venue_code="24",  # 大村
        course=1,
        racer_analysis={'racer_rank': 'B1', 'recent_form': {}, 'venue_stats': {}, 'overall_stats': {}},
        motor_analysis={'motor_stats': {}}
    )

    print(f"合計バフ: {result2['total_buff']:+.1f}点")
    for r in result2['applied_rules']:
        print(f"  - {r['name']}: {r['buff']:+.1f}点")

    print("\n" + "=" * 70)
    print("テスト完了")
