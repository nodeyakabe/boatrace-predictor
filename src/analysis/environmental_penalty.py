# -*- coding: utf-8 -*-
"""
環境要因減点システム

信頼度Bの予測に対して、環境要因（会場、時間帯、風向、風速、波高、天候）に基づき
減点を適用し、調整後スコアを算出する
"""

import pandas as pd
import yaml
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime


class EnvironmentalPenaltySystem:
    """
    環境要因減点システム

    2025年BEFORE予測データの分析結果に基づく減点ルールを適用
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        減点ルール初期化

        Args:
            config_path: 設定ファイルパス（Noneの場合はデフォルトパスを使用）
        """
        if config_path is None:
            # デフォルトの設定ファイルパス
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / 'config' / 'environmental_penalty_rules.yaml'

        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.rules = self._initialize_rules()
        self.thresholds = self.config.get('thresholds', {})
        self.system_config = self.config.get('system', {})

    def _load_config(self) -> Dict:
        """YAMLファイルから設定を読み込み"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"設定ファイルが見つかりません: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        return config

    def _initialize_rules(self) -> List[Dict]:
        """
        YAMLファイルから減点ルールを読み込み

        Returns:
            有効な減点ルールのリスト
        """
        yaml_rules = self.config.get('rules', [])

        # 有効なルールのみ抽出し、内部形式に変換
        rules = []
        for rule in yaml_rules:
            if not rule.get('enabled', True):
                continue  # 無効なルールはスキップ

            # YAMLのキーを内部キーにマッピング
            internal_rule = {
                'penalty': rule['penalty'],
                'description': rule['description']
            }

            # 条件をマッピング
            if 'venue' in rule:
                internal_rule['venue'] = rule['venue']
            if 'time' in rule:
                internal_rule['time'] = rule['time']
            if 'wind_direction' in rule:
                internal_rule['wind_dir'] = rule['wind_direction']
            if 'wind_category' in rule:
                internal_rule['wind_cat'] = rule['wind_category']
            if 'wave' in rule:
                internal_rule['wave'] = rule['wave']
            if 'weather' in rule:
                internal_rule['weather'] = rule['weather']

            rules.append(internal_rule)

        return rules

    def _categorize_time(self, race_time: str) -> str:
        """時間帯の分類（YAMLの閾値設定を使用）"""
        if not race_time or pd.isna(race_time):
            return 'unknown'
        try:
            from datetime import datetime
            time_obj = datetime.strptime(race_time, '%H:%M').time()

            # YAMLから時間帯設定を取得（フォールバック付き）
            time_thresholds = self.thresholds.get('time', {
                '早朝': {'start': '00:00', 'end': '10:00'},
                '午前': {'start': '10:00', 'end': '13:00'},
                '午後': {'start': '13:00', 'end': '16:00'},
                '夕方': {'start': '16:00', 'end': '23:59'}
            })

            for category, times in time_thresholds.items():
                start_time = datetime.strptime(times['start'], '%H:%M').time()
                end_time = datetime.strptime(times['end'], '%H:%M').time()
                if start_time <= time_obj < end_time:
                    return category

            return 'unknown'
        except:
            return 'unknown'

    def _categorize_wind(self, wind_speed: float) -> str:
        """風速の分類（YAMLの閾値設定を使用）"""
        if pd.isna(wind_speed):
            return 'unknown'

        # YAMLから風速設定を取得（フォールバック付き）
        wind_thresholds = self.thresholds.get('wind_speed', {
            '無風': {'min': 0, 'max': 2},
            '微風': {'min': 2, 'max': 4},
            '強風': {'min': 4, 'max': 6},
            '暴風': {'min': 6, 'max': 999}
        })

        for category, limits in wind_thresholds.items():
            if limits['min'] <= wind_speed < limits['max']:
                return category

        return 'unknown'

    def _categorize_wave(self, wave_height: float) -> str:
        """波高の分類（YAMLの閾値設定を使用）"""
        if pd.isna(wave_height):
            return 'unknown'

        # YAMLから波高設定を取得（フォールバック付き）
        wave_thresholds = self.thresholds.get('wave_height', {
            '穏やか': {'min': 0, 'max': 2},
            '小波': {'min': 2, 'max': 5},
            '中波': {'min': 5, 'max': 10},
            '大波': {'min': 10, 'max': 999}
        })

        for category, limits in wave_thresholds.items():
            if limits['min'] <= wave_height < limits['max']:
                return category

        return 'unknown'

    def calculate_penalty(
        self,
        venue_code: str,
        race_time: str,
        wind_direction: Optional[str],
        wind_speed: Optional[float],
        wave_height: Optional[float],
        weather: Optional[str]
    ) -> Tuple[int, List[Dict]]:
        """
        環境要因から減点ポイントを計算

        Args:
            venue_code: 会場コード（'01'-'24'）
            race_time: レース時刻（'HH:MM'形式）
            wind_direction: 風向
            wind_speed: 風速（m/s）
            wave_height: 波高（cm）
            weather: 天候

        Returns:
            tuple: (総減点ポイント, 適用されたルールのリスト)
        """
        total_penalty = 0
        applied_rules = []

        # カテゴリ化
        time_cat = self._categorize_time(race_time)
        wind_cat = self._categorize_wind(wind_speed)
        wave_cat = self._categorize_wave(wave_height)

        # 各ルールをチェック
        for rule in self.rules:
            match = True

            # 条件チェック
            if 'venue' in rule and rule['venue'] != venue_code:
                match = False
            if 'time' in rule and rule['time'] != time_cat:
                match = False
            if 'wind_dir' in rule and rule['wind_dir'] != wind_direction:
                match = False
            if 'wind_cat' in rule and rule['wind_cat'] != wind_cat:
                match = False
            if 'wave' in rule and rule['wave'] != wave_cat:
                match = False
            if 'weather' in rule and rule['weather'] != weather:
                match = False

            if match:
                total_penalty += rule['penalty']
                applied_rules.append(rule)

        return total_penalty, applied_rules

    def adjust_confidence_score(
        self,
        original_score: float,
        penalty: int
    ) -> Tuple[float, str]:
        """
        元のスコアから減点を適用して調整後スコアと信頼度を算出（YAMLの閾値を使用）

        Args:
            original_score: 元の信頼度スコア
            penalty: 減点ポイント

        Returns:
            tuple: (調整後スコア, 調整後信頼度)
        """
        adjusted_score = original_score - penalty

        # YAMLから信頼度閾値を取得（フォールバック付き）
        conf_thresholds = self.config.get('confidence_thresholds', {
            'B': {'min_score': 100},
            'C': {'min_score': 80, 'max_score': 99},
            'D': {'min_score': 0, 'max_score': 79}
        })

        # 信頼度再判定
        if adjusted_score >= conf_thresholds.get('B', {}).get('min_score', 100):
            new_confidence = 'B'
        elif adjusted_score >= conf_thresholds.get('C', {}).get('min_score', 80):
            new_confidence = 'C'
        else:
            new_confidence = 'D'

        return adjusted_score, new_confidence

    def should_accept_bet(
        self,
        venue_code: str,
        race_time: str,
        wind_direction: Optional[str],
        wind_speed: Optional[float],
        wave_height: Optional[float],
        weather: Optional[str],
        original_score: float,
        min_threshold: float = 80.0
    ) -> Dict:
        """
        減点システムを適用してベット可否を判定

        Args:
            venue_code: 会場コード
            race_time: レース時刻
            wind_direction: 風向
            wind_speed: 風速
            wave_height: 波高
            weather: 天候
            original_score: 元の信頼度スコア
            min_threshold: 最低スコア閾値（これ未満は投票対象外）

        Returns:
            dict: {
                'accept': bool,  # 投票対象とするか
                'original_score': float,
                'penalty': int,
                'adjusted_score': float,
                'original_confidence': str,
                'adjusted_confidence': str,
                'applied_rules': list,
                'reason': str
            }
        """
        # 元の信頼度
        if original_score >= 100:
            original_confidence = 'B'
        elif original_score >= 80:
            original_confidence = 'C'
        else:
            original_confidence = 'D'

        # 減点計算
        penalty, applied_rules = self.calculate_penalty(
            venue_code, race_time, wind_direction,
            wind_speed, wave_height, weather
        )

        # 調整後スコアと信頼度
        adjusted_score, adjusted_confidence = self.adjust_confidence_score(
            original_score, penalty
        )

        # ベット可否判定
        accept = adjusted_score >= min_threshold

        # 理由生成
        if not accept:
            reason = f"調整後スコア{adjusted_score:.1f} < 閾値{min_threshold}（減点{penalty}pt適用）"
        elif penalty > 0:
            reason = f"減点{penalty}pt適用、信頼度{original_confidence}→{adjusted_confidence}"
        else:
            reason = "減点なし"

        return {
            'accept': accept,
            'original_score': original_score,
            'penalty': penalty,
            'adjusted_score': adjusted_score,
            'original_confidence': original_confidence,
            'adjusted_confidence': adjusted_confidence,
            'applied_rules': applied_rules,
            'reason': reason
        }

    def get_rule_summary(self) -> str:
        """減点ルールのサマリーを取得"""
        summary = []
        summary.append("=" * 80)
        summary.append("環境要因減点ルール一覧")
        summary.append("=" * 80)
        summary.append(f"総ルール数: {len(self.rules)}")
        summary.append("")

        # 減点レベル別に分類
        high_risk = [r for r in self.rules if r['penalty'] >= 7]
        mid_risk = [r for r in self.rules if 4 <= r['penalty'] < 7]
        low_risk = [r for r in self.rules if r['penalty'] < 4]

        summary.append(f"■ 危険度：最高（減点7pt以上）: {len(high_risk)}件")
        for rule in high_risk:
            summary.append(f"  - [{rule['penalty']:2d}pt] {rule['description']}")

        summary.append("")
        summary.append(f"■ 危険度：高（減点4-6pt）: {len(mid_risk)}件")
        for rule in mid_risk:
            summary.append(f"  - [{rule['penalty']:2d}pt] {rule['description']}")

        summary.append("")
        summary.append(f"■ 危険度：中（減点2-3pt）: {len(low_risk)}件")
        for rule in low_risk:
            summary.append(f"  - [{rule['penalty']:2d}pt] {rule['description']}")

        summary.append("")
        summary.append("=" * 80)

        return "\n".join(summary)


if __name__ == "__main__":
    # テスト
    penalty_system = EnvironmentalPenaltySystem()

    print(penalty_system.get_rule_summary())

    print("\n" + "=" * 80)
    print("テストケース")
    print("=" * 80)

    # テスト1: 戸田×午前（高リスク）
    result = penalty_system.should_accept_bet(
        venue_code='02',
        race_time='11:30',
        wind_direction='北',
        wind_speed=3.0,
        wave_height=5.0,
        weather='晴',
        original_score=105.0
    )
    print(f"\n【テスト1】戸田×午前、元スコア105")
    print(f"  判定: {'投票対象' if result['accept'] else '投票対象外'}")
    print(f"  減点: {result['penalty']}pt")
    print(f"  調整後スコア: {result['adjusted_score']:.1f}")
    print(f"  信頼度: {result['original_confidence']} → {result['adjusted_confidence']}")
    print(f"  理由: {result['reason']}")

    # テスト2: 江戸川×夕方×東×暴風（超高リスク）
    result = penalty_system.should_accept_bet(
        venue_code='03',
        race_time='17:00',
        wind_direction='東',
        wind_speed=8.0,
        wave_height=12.0,
        weather='雨',
        original_score=110.0
    )
    print(f"\n【テスト2】江戸川×夕方×東×暴風×大波×雨、元スコア110")
    print(f"  判定: {'投票対象' if result['accept'] else '投票対象外'}")
    print(f"  減点: {result['penalty']}pt")
    print(f"  調整後スコア: {result['adjusted_score']:.1f}")
    print(f"  信頼度: {result['original_confidence']} → {result['adjusted_confidence']}")
    print(f"  理由: {result['reason']}")
    if result['applied_rules']:
        print(f"  適用ルール:")
        for rule in result['applied_rules']:
            print(f"    - {rule['description']}")

    # テスト3: 優良条件（減点なし）
    result = penalty_system.should_accept_bet(
        venue_code='07',  # 蒲郡
        race_time='14:30',
        wind_direction='北',
        wind_speed=1.5,
        wave_height=3.0,
        weather='晴',
        original_score=105.0
    )
    print(f"\n【テスト3】蒲郡×午後×微風×晴、元スコア105")
    print(f"  判定: {'投票対象' if result['accept'] else '投票対象外'}")
    print(f"  減点: {result['penalty']}pt")
    print(f"  調整後スコア: {result['adjusted_score']:.1f}")
    print(f"  信頼度: {result['original_confidence']} → {result['adjusted_confidence']}")
    print(f"  理由: {result['reason']}")
