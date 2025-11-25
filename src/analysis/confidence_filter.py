"""
信頼度フィルタ
信頼度に基づいて予測を除外・警告表示
"""

import json
from pathlib import Path
from typing import Dict, List, Optional


class ConfidenceFilter:
    """信頼度に基づく予測フィルタリング"""

    def __init__(self, config_path: Optional[str] = None):
        """
        Args:
            config_path: 設定ファイルのパス
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / 'config' / 'prediction_improvements.json'

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        self.enabled = config['confidence_filter']['enabled']
        self.exclude_e_level = config['confidence_filter']['exclude_e_level']
        self.min_display_level = config['confidence_filter']['min_display_level']
        self.min_data_completeness_for_e = config['confidence_filter']['min_data_completeness_for_e']

        # 信頼度レベルの順序
        self.confidence_levels = ['E', 'D', 'C', 'B', 'A']

    def should_display_prediction(
        self,
        confidence: str,
        data_completeness_score: float
    ) -> Dict[str, any]:
        """
        予測を表示すべきかを判定

        Args:
            confidence: 信頼度（A-E）
            data_completeness_score: データ充実度スコア（0-100）

        Returns:
            {
                'should_display': bool,  # 表示すべきか
                'reason': str,  # 判定理由
                'warning': str  # 警告メッセージ（あれば）
            }
        """
        if not self.enabled:
            return {
                'should_display': True,
                'reason': 'フィルタ無効',
                'warning': ''
            }

        # E判定の除外チェック
        if confidence == 'E' and self.exclude_e_level:
            # データ充実度も低い場合は完全除外
            if data_completeness_score < self.min_data_completeness_for_e:
                return {
                    'should_display': False,
                    'reason': f'信頼度E + データ不足（充実度{data_completeness_score:.1f}）',
                    'warning': ''
                }
            else:
                return {
                    'should_display': False,
                    'reason': '信頼度E（除外設定）',
                    'warning': ''
                }

        # 最小表示レベルチェック
        if self.min_display_level in self.confidence_levels:
            min_index = self.confidence_levels.index(self.min_display_level)
            current_index = self.confidence_levels.index(confidence) if confidence in self.confidence_levels else 0

            if current_index < min_index:
                return {
                    'should_display': False,
                    'reason': f'信頼度{confidence}（最小表示レベル{self.min_display_level}未満）',
                    'warning': ''
                }

        # 表示するが警告を付ける場合
        warning = ''
        if confidence in ['D', 'E']:
            warning = f'低信頼度（{confidence}）: 参考程度にとどめることを推奨'

        return {
            'should_display': True,
            'reason': f'表示可（信頼度{confidence}）',
            'warning': warning
        }

    def filter_predictions(
        self,
        predictions: List[Dict]
    ) -> Dict[str, any]:
        """
        予測リストをフィルタリング

        Args:
            predictions: 予測結果リスト

        Returns:
            {
                'filtered_predictions': List[Dict],  # フィルタ後の予測
                'excluded_predictions': List[Dict],  # 除外された予測
                'warnings': List[str]  # 警告メッセージ
            }
        """
        filtered = []
        excluded = []
        warnings = []

        for pred in predictions:
            confidence = pred.get('confidence', 'E')
            data_completeness = pred.get('data_completeness_score', 0.0)

            filter_result = self.should_display_prediction(confidence, data_completeness)

            if filter_result['should_display']:
                # 表示する予測
                pred['display_warning'] = filter_result['warning']
                filtered.append(pred)

                if filter_result['warning']:
                    warnings.append(f"{pred.get('pit_number', '?')}号艇: {filter_result['warning']}")
            else:
                # 除外する予測
                pred['exclusion_reason'] = filter_result['reason']
                excluded.append(pred)

        return {
            'filtered_predictions': filtered,
            'excluded_predictions': excluded,
            'warnings': warnings,
            'total_predictions': len(predictions),
            'displayed_count': len(filtered),
            'excluded_count': len(excluded)
        }

    def get_display_summary(self, filter_result: Dict) -> str:
        """
        フィルタ結果のサマリーを生成

        Args:
            filter_result: filter_predictions()の戻り値

        Returns:
            サマリー文字列
        """
        summary = []

        summary.append(f"予測総数: {filter_result['total_predictions']}")
        summary.append(f"表示: {filter_result['displayed_count']}")

        if filter_result['excluded_count'] > 0:
            summary.append(f"除外: {filter_result['excluded_count']}")

            # 除外理由の内訳
            reasons = {}
            for pred in filter_result['excluded_predictions']:
                reason = pred.get('exclusion_reason', '不明')
                reasons[reason] = reasons.get(reason, 0) + 1

            for reason, count in reasons.items():
                summary.append(f"  - {reason}: {count}件")

        if filter_result['warnings']:
            summary.append(f"\n警告:")
            for warning in filter_result['warnings']:
                summary.append(f"  - {warning}")

        return '\n'.join(summary)
