"""
予測ロジック可視化モジュール

機能:
- 予測根拠をテキストで説明
- 各要因の寄与度を表示
- UI表示用のフォーマット生成
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import sqlite3
import json

from .rule_extractor import RuleExtractor


class PredictionExplainer:
    """予測根拠を説明するクラス"""

    # 会場コードと名前のマッピング
    VENUE_NAMES = {
        '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
        '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
        '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
        '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
        '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
        '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
    }

    def __init__(self, db_path: str = "boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path
        self.rule_extractor = RuleExtractor(db_path)

    def explain_prediction(
        self,
        prediction_data: Dict[str, Any],
        model_prob: float,
        feature_contributions: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        予測を説明

        Args:
            prediction_data: 予測対象のデータ
                - venue_code: 会場コード
                - pit_number: ピット番号
                - racer_name: 選手名
                - racer_rank: 選手ランク
                - nation_win_rate: 全国勝率
                - motor_2ren_rate: モーター2連率
                - wind_direction: 風向き
                - wind_speed: 風速
                - tide_status: 潮
            model_prob: モデルの予測確率
            feature_contributions: 特徴量の寄与度（SHAPなど）

        Returns:
            説明データ
        """
        explanations = []
        factors = []

        venue_code = prediction_data.get('venue_code', '')
        pit_number = prediction_data.get('pit_number', 1)
        venue_name = self.VENUE_NAMES.get(venue_code, venue_code)

        # 1. コース別基本情報
        course_factor = self._explain_course(pit_number)
        factors.append(course_factor)

        # 2. 選手情報
        racer_factor = self._explain_racer(prediction_data)
        factors.append(racer_factor)

        # 3. モーター・ボート
        equipment_factor = self._explain_equipment(prediction_data)
        if equipment_factor:
            factors.append(equipment_factor)

        # 4. 天候・潮汐
        condition_factor = self._explain_conditions(prediction_data)
        if condition_factor:
            factors.append(condition_factor)

        # 5. 適用ルール
        rule_factor = self._explain_rules(prediction_data)
        if rule_factor:
            factors.append(rule_factor)

        # 総合評価
        total_adjustment = sum(f.get('adjustment', 0) for f in factors)
        adjusted_prob = model_prob + total_adjustment

        # 範囲内に収める
        adjusted_prob = max(0.01, min(0.99, adjusted_prob))

        return {
            'venue_name': venue_name,
            'pit_number': pit_number,
            'model_probability': round(model_prob * 100, 1),
            'adjusted_probability': round(adjusted_prob * 100, 1),
            'total_adjustment': round(total_adjustment * 100, 1),
            'factors': factors,
            'summary': self._generate_summary(factors, model_prob, adjusted_prob)
        }

    def _explain_course(self, pit_number: int) -> Dict[str, Any]:
        """コース別の説明"""
        # コース別の一般的な勝率
        base_rates = {
            1: 0.55, 2: 0.14, 3: 0.12,
            4: 0.10, 5: 0.05, 6: 0.04
        }

        base_rate = base_rates.get(pit_number, 1/6)

        if pit_number == 1:
            description = "1号艇はインコース有利（逃げ戦法）"
            sentiment = "positive"
        elif pit_number in [2, 3]:
            description = f"{pit_number}号艇は差し・捲り狙い"
            sentiment = "neutral"
        else:
            description = f"{pit_number}号艇は外枠で不利"
            sentiment = "negative"

        return {
            'category': 'コース',
            'description': description,
            'value': f'{pit_number}号艇',
            'base_rate': round(base_rate * 100, 1),
            'adjustment': 0,  # ベースラインなので調整なし
            'sentiment': sentiment
        }

    def _explain_racer(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """選手情報の説明"""
        racer_name = data.get('racer_name', '不明')
        racer_rank = data.get('racer_rank', '')
        nation_win_rate = data.get('nation_win_rate', 0)
        local_win_rate = data.get('local_win_rate', 0)

        # ランク評価
        rank_str = str(racer_rank).upper() if racer_rank else ''
        if 'A1' in rank_str:
            rank_desc = 'A1級（トップクラス）'
            adjustment = 0.05
            sentiment = 'positive'
        elif 'A2' in rank_str:
            rank_desc = 'A2級（上位）'
            adjustment = 0.02
            sentiment = 'positive'
        elif 'B1' in rank_str:
            rank_desc = 'B1級（中堅）'
            adjustment = 0
            sentiment = 'neutral'
        else:
            rank_desc = 'B2級（下位）'
            adjustment = -0.03
            sentiment = 'negative'

        # 勝率評価
        win_rate = nation_win_rate or local_win_rate or 0
        if win_rate >= 7.0:
            win_desc = f'勝率{win_rate:.2f}（高い）'
            adjustment += 0.03
        elif win_rate >= 5.0:
            win_desc = f'勝率{win_rate:.2f}（普通）'
        else:
            win_desc = f'勝率{win_rate:.2f}（低い）'
            adjustment -= 0.02

        return {
            'category': '選手',
            'description': f'{racer_name} {rank_desc}',
            'value': win_desc,
            'adjustment': round(adjustment, 4),
            'sentiment': sentiment
        }

    def _explain_equipment(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """モーター・ボートの説明"""
        motor_rate = data.get('motor_2ren_rate', 0)
        boat_rate = data.get('boat_2ren_rate', 0)

        if not motor_rate and not boat_rate:
            return None

        adjustment = 0
        descriptions = []

        # モーター評価
        if motor_rate:
            if motor_rate >= 40:
                descriptions.append(f'モーター2連率{motor_rate:.1f}%（好調）')
                adjustment += 0.02
                sentiment = 'positive'
            elif motor_rate >= 30:
                descriptions.append(f'モーター2連率{motor_rate:.1f}%（普通）')
                sentiment = 'neutral'
            else:
                descriptions.append(f'モーター2連率{motor_rate:.1f}%（不調）')
                adjustment -= 0.02
                sentiment = 'negative'
        else:
            sentiment = 'neutral'

        # ボート評価
        if boat_rate:
            if boat_rate >= 40:
                descriptions.append(f'ボート2連率{boat_rate:.1f}%（好調）')
                adjustment += 0.01
            elif boat_rate < 30:
                descriptions.append(f'ボート2連率{boat_rate:.1f}%（不調）')
                adjustment -= 0.01

        return {
            'category': '機材',
            'description': '、'.join(descriptions),
            'value': '',
            'adjustment': round(adjustment, 4),
            'sentiment': sentiment
        }

    def _explain_conditions(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """天候・潮汐の説明"""
        wind_direction = data.get('wind_direction', '')
        wind_speed = data.get('wind_speed', 0)
        tide_status = data.get('tide_status', '')
        pit_number = data.get('pit_number', 1)

        descriptions = []
        adjustment = 0
        sentiment = 'neutral'

        # 風の影響
        if wind_direction:
            if wind_direction in ['追', '追い風']:
                if pit_number == 1:
                    descriptions.append('追い風（イン有利）')
                    adjustment += 0.03
                    sentiment = 'positive'
                else:
                    descriptions.append('追い風（アウト不利）')
                    adjustment -= 0.01
                    sentiment = 'negative'
            elif wind_direction in ['向', '向かい風']:
                if pit_number == 1:
                    descriptions.append('向かい風（イン不利）')
                    adjustment -= 0.03
                    sentiment = 'negative'
                else:
                    descriptions.append('向かい風（差し有利）')
                    adjustment += 0.02
                    sentiment = 'positive'
            else:
                descriptions.append(f'{wind_direction}風')

        # 風速の影響
        if wind_speed and wind_speed >= 5:
            descriptions.append(f'強風{wind_speed}m（荒れやすい）')
            if pit_number != 1:
                adjustment += 0.01

        # 潮の影響
        if tide_status:
            if tide_status in ['満潮', '上げ潮']:
                if pit_number == 1:
                    descriptions.append(f'{tide_status}（イン有利）')
                    adjustment += 0.02
                else:
                    descriptions.append(f'{tide_status}')
            elif tide_status in ['干潮', '下げ潮']:
                if pit_number != 1:
                    descriptions.append(f'{tide_status}（差し有利）')
                    adjustment += 0.01
                else:
                    descriptions.append(f'{tide_status}')

        if not descriptions:
            return None

        return {
            'category': '環境',
            'description': '、'.join(descriptions),
            'value': '',
            'adjustment': round(adjustment, 4),
            'sentiment': sentiment
        }

    def _explain_rules(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """適用ルールの説明"""
        venue_code = data.get('venue_code', '')
        pit_number = data.get('pit_number', 1)
        wind_direction = data.get('wind_direction')
        tide_status = data.get('tide_status')
        racer_rank = data.get('racer_rank')

        # 適用可能なルールを取得
        applicable = self.rule_extractor.get_applicable_rules(
            venue_code=venue_code,
            pit_number=pit_number,
            wind_direction=wind_direction,
            tide_status=tide_status,
            racer_rank=racer_rank
        )

        if not applicable:
            return None

        # 加算値計算
        total_adj, rule_names = self.rule_extractor.calculate_total_adjustment(applicable)

        # 上位3ルールを表示
        top_rules = sorted(applicable, key=lambda x: abs(x['adjustment']), reverse=True)[:3]
        descriptions = [r['rule_name'] for r in top_rules]

        if total_adj > 0:
            sentiment = 'positive'
        elif total_adj < 0:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'

        return {
            'category': 'パターン',
            'description': '、'.join(descriptions),
            'value': f'{len(applicable)}ルール適用',
            'adjustment': round(total_adj, 4),
            'sentiment': sentiment
        }

    def _generate_summary(
        self,
        factors: List[Dict[str, Any]],
        model_prob: float,
        adjusted_prob: float
    ) -> str:
        """サマリーテキストを生成"""
        # ポジティブ/ネガティブ要因をカウント
        positive = sum(1 for f in factors if f.get('sentiment') == 'positive')
        negative = sum(1 for f in factors if f.get('sentiment') == 'negative')

        if adjusted_prob >= 0.30:
            rating = "◎ 本命"
        elif adjusted_prob >= 0.20:
            rating = "○ 有力"
        elif adjusted_prob >= 0.15:
            rating = "▲ 注意"
        elif adjusted_prob >= 0.10:
            rating = "△ 穴"
        else:
            rating = "× 薄い"

        # 主要な要因を抽出
        main_factors = []
        for f in factors:
            if f.get('adjustment', 0) >= 0.02:
                main_factors.append(f'{f["category"]}:プラス')
            elif f.get('adjustment', 0) <= -0.02:
                main_factors.append(f'{f["category"]}:マイナス')

        if main_factors:
            factor_text = f"（{', '.join(main_factors)}）"
        else:
            factor_text = ""

        return f"{rating} {factor_text}"

    def format_for_ui(self, explanation: Dict[str, Any]) -> str:
        """
        UI表示用にフォーマット

        Args:
            explanation: 説明データ

        Returns:
            フォーマットされたテキスト
        """
        lines = []

        # ヘッダー
        venue = explanation.get('venue_name', '')
        pit = explanation.get('pit_number', 1)
        lines.append(f"【{venue} {pit}号艇 予測根拠】")
        lines.append("")

        # 確率
        model_prob = explanation.get('model_probability', 0)
        adjusted_prob = explanation.get('adjusted_probability', 0)
        total_adj = explanation.get('total_adjustment', 0)

        lines.append(f"モデル予測: {model_prob:.1f}%")
        if total_adj != 0:
            adj_sign = '+' if total_adj >= 0 else ''
            lines.append(f"調整後: {adjusted_prob:.1f}% ({adj_sign}{total_adj:.1f}%)")
        lines.append("")

        # 要因リスト
        for factor in explanation.get('factors', []):
            category = factor.get('category', '')
            description = factor.get('description', '')
            adjustment = factor.get('adjustment', 0)
            sentiment = factor.get('sentiment', 'neutral')

            # センチメントマーク
            if sentiment == 'positive':
                mark = '[+]'
            elif sentiment == 'negative':
                mark = '[-]'
            else:
                mark = '[ ]'

            # 調整値表示
            if adjustment != 0:
                adj_pct = adjustment * 100
                adj_str = f" ({adj_pct:+.1f}%)"
            else:
                adj_str = ""

            lines.append(f"{mark} {category}: {description}{adj_str}")

        lines.append("")

        # サマリー
        summary = explanation.get('summary', '')
        lines.append(f"評価: {summary}")

        return "\n".join(lines)

    def explain_race(
        self,
        race_id: int,
        model_predictions: Optional[Dict[int, float]] = None
    ) -> List[Dict[str, Any]]:
        """
        レース全体の予測を説明

        Args:
            race_id: レースID
            model_predictions: ピット番号 -> 予測確率 の辞書

        Returns:
            各艇の説明リスト
        """
        with sqlite3.connect(self.db_path) as conn:
            # レースデータ取得
            query = """
                SELECT
                    r.venue_code,
                    rd.pit_number,
                    rd.racer_name,
                    rd.racer_rank,
                    rd.nation_win_rate,
                    rd.local_win_rate,
                    rd.motor_2ren_rate,
                    rd.boat_2ren_rate,
                    w.wind_direction,
                    w.wind_speed,
                    t.tide_status
                FROM races r
                JOIN race_details rd ON r.race_id = rd.race_id
                LEFT JOIN weather w ON r.venue_code = w.venue_code
                    AND r.race_date = w.race_date
                LEFT JOIN tide t ON r.venue_code = t.venue_code
                    AND r.race_date = t.race_date
                WHERE r.race_id = ?
                ORDER BY rd.pit_number
            """
            df = pd.read_sql_query(query, conn, params=(race_id,))

        if len(df) == 0:
            return []

        explanations = []

        for _, row in df.iterrows():
            pit = row['pit_number']

            # モデル予測確率
            if model_predictions and pit in model_predictions:
                model_prob = model_predictions[pit]
            else:
                model_prob = 1 / 6  # デフォルト

            # 予測データを構築
            prediction_data = row.to_dict()

            # 説明生成
            explanation = self.explain_prediction(prediction_data, model_prob)
            explanations.append(explanation)

        return explanations


if __name__ == "__main__":
    # テスト
    print("予測ロジック可視化 テスト")
    print("-" * 40)

    explainer = PredictionExplainer()

    # サンプルデータ
    test_data = {
        'venue_code': '01',
        'pit_number': 1,
        'racer_name': '田中太郎',
        'racer_rank': 'A1',
        'nation_win_rate': 7.5,
        'local_win_rate': 8.0,
        'motor_2ren_rate': 42.5,
        'boat_2ren_rate': 38.0,
        'wind_direction': '追',
        'wind_speed': 3,
        'tide_status': '満潮'
    }

    # 説明生成
    explanation = explainer.explain_prediction(test_data, model_prob=0.35)

    # UI表示
    print(explainer.format_for_ui(explanation))
