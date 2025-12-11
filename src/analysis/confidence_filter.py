"""
信頼度フィルタ
信頼度に基づいて予測を除外・警告表示
信頼度B専用の会場・季節フィルター機能を含む
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


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


class ConfidenceBFilter:
    """
    信頼度B専用フィルター

    分析結果に基づく会場・季節フィルタリング:
    - 除外会場: 江戸川(2.69%)、戸田(2.75%)、平和島(3.64%)
    - 低調期間: 1-4月（的中率5-6%台）
    - 推奨期間: 5-12月（的中率8-10%台）
    """

    # 会場別的中率データ（分析結果より）
    VENUE_STATS = {
        1: {'name': '桐生', 'hit_rate': 10.15},
        2: {'name': '戸田', 'hit_rate': 2.75},      # 除外推奨
        3: {'name': '江戸川', 'hit_rate': 2.69},    # 除外推奨
        4: {'name': '平和島', 'hit_rate': 3.64},    # 除外推奨
        5: {'name': '多摩川', 'hit_rate': 5.63},
        6: {'name': '浜名湖', 'hit_rate': 7.45},
        7: {'name': '蒲郡', 'hit_rate': 11.04},
        8: {'name': '常滑', 'hit_rate': 9.69},
        9: {'name': '津', 'hit_rate': 8.33},
        10: {'name': '三国', 'hit_rate': 8.24},
        11: {'name': 'びわこ', 'hit_rate': 11.79},
        12: {'name': '住之江', 'hit_rate': 10.61},
        13: {'name': '尼崎', 'hit_rate': 7.69},
        14: {'name': '鳴門', 'hit_rate': 4.95},
        15: {'name': '丸亀', 'hit_rate': 10.47},
        16: {'name': '児島', 'hit_rate': 15.94},
        17: {'name': '宮島', 'hit_rate': 7.41},
        18: {'name': '徳山', 'hit_rate': 8.60},
        19: {'name': '下関', 'hit_rate': 9.23},
        20: {'name': '若松', 'hit_rate': 10.00},
        21: {'name': '芦屋', 'hit_rate': 10.60},
        22: {'name': '福岡', 'hit_rate': 5.40},
        23: {'name': '唐津', 'hit_rate': 6.25},
        24: {'name': '大村', 'hit_rate': 12.33},
    }

    # 月別的中率データ（分析結果より）
    MONTHLY_STATS = {
        1: 5.11,    # 低調
        2: 6.45,    # 低調
        3: 6.57,    # 低調
        4: 5.78,    # 低調
        5: 10.13,   # 最高
        6: 7.05,
        7: 8.77,
        8: 9.75,
        9: 8.03,
        10: 8.73,
        11: 8.29,
        12: 9.70,
    }

    def __init__(
        self,
        exclude_low_venues: bool = True,
        venue_threshold: float = 5.0,
        seasonal_adjustment: bool = True,
        low_season_score_boost: float = 2.0
    ):
        """
        Args:
            exclude_low_venues: 低的中率会場を除外するか
            venue_threshold: 会場除外の的中率閾値（%）
            seasonal_adjustment: 季節調整を行うか
            low_season_score_boost: 低調期間の信頼度スコア加算値（1-4月に適用）
        """
        self.exclude_low_venues = exclude_low_venues
        self.venue_threshold = venue_threshold
        self.seasonal_adjustment = seasonal_adjustment
        self.low_season_score_boost = low_season_score_boost

        # 除外会場リスト
        self.excluded_venues = [
            code for code, stats in self.VENUE_STATS.items()
            if stats['hit_rate'] < venue_threshold
        ]

    def should_accept_bet(
        self,
        venue_code: int,
        race_date: str,
        confidence_score: float = None
    ) -> Dict[str, any]:
        """
        信頼度Bの買い目を受け入れるべきか判定

        Args:
            venue_code: 会場コード
            race_date: レース日（YYYY-MM-DD形式）
            confidence_score: 信頼度スコア（オプション）

        Returns:
            {
                'accept': bool,  # 買い目として受け入れるか
                'reason': str,  # 判定理由
                'expected_hit_rate': float,  # 期待的中率（%）
                'venue_name': str,  # 会場名
                'adjustment': str  # 調整内容
            }
        """
        venue_stats = self.VENUE_STATS.get(venue_code, {'name': '不明', 'hit_rate': 0.0})
        venue_name = venue_stats['name']
        venue_hit_rate = venue_stats['hit_rate']

        # 日付解析
        try:
            date_obj = datetime.strptime(race_date, '%Y-%m-%d')
            month = date_obj.month
        except:
            month = 1

        monthly_hit_rate = self.MONTHLY_STATS.get(month, 8.29)

        # 会場フィルター
        if self.exclude_low_venues and venue_code in self.excluded_venues:
            return {
                'accept': False,
                'reason': f'低的中率会場（{venue_name}: {venue_hit_rate:.2f}%）',
                'expected_hit_rate': venue_hit_rate,
                'venue_name': venue_name,
                'adjustment': 'EXCLUDED_VENUE'
            }

        # 季節調整
        adjustment = 'NORMAL'
        accept = True
        reason = f'通常受け入れ（{venue_name}）'

        if self.seasonal_adjustment:
            # 低調期間（1-4月）
            if month in [1, 2, 3, 4]:
                # スコアが高い場合のみ受け入れ
                if confidence_score is not None:
                    required_score = 70 + self.low_season_score_boost
                    if confidence_score < required_score:
                        accept = False
                        reason = f'低調期間（{month}月: {monthly_hit_rate:.2f}%）かつスコア不足'
                        adjustment = 'LOW_SEASON_REJECTED'
                    else:
                        accept = True
                        reason = f'低調期間だがスコア高（{confidence_score:.1f}点）で受け入れ'
                        adjustment = 'LOW_SEASON_ACCEPTED'
                else:
                    # スコア情報がない場合は慎重に
                    accept = True
                    reason = f'低調期間（{month}月）- 慎重推奨'
                    adjustment = 'LOW_SEASON_CAUTION'

        # 期待的中率（会場と月の平均）
        expected_hit_rate = (venue_hit_rate + monthly_hit_rate) / 2

        return {
            'accept': accept,
            'reason': reason,
            'expected_hit_rate': expected_hit_rate,
            'venue_name': venue_name,
            'adjustment': adjustment,
            'venue_hit_rate': venue_hit_rate,
            'monthly_hit_rate': monthly_hit_rate
        }

    def filter_race_list(
        self,
        races: List[Dict]
    ) -> Dict[str, any]:
        """
        レースリストをフィルタリング

        Args:
            races: レース情報リスト（各要素は venue_code, race_date, confidence_score を含む）

        Returns:
            {
                'accepted_races': List[Dict],  # 受け入れられたレース
                'rejected_races': List[Dict],  # 除外されたレース
                'summary': Dict  # サマリー統計
            }
        """
        accepted = []
        rejected = []

        for race in races:
            venue_code = race.get('venue_code')
            race_date = race.get('race_date')
            confidence_score = race.get('confidence_score')

            filter_result = self.should_accept_bet(venue_code, race_date, confidence_score)

            race_info = {
                **race,
                'filter_result': filter_result
            }

            if filter_result['accept']:
                accepted.append(race_info)
            else:
                rejected.append(race_info)

        # サマリー統計
        summary = {
            'total': len(races),
            'accepted': len(accepted),
            'rejected': len(rejected),
            'acceptance_rate': len(accepted) / len(races) * 100 if races else 0,
            'expected_avg_hit_rate': sum(r['filter_result']['expected_hit_rate'] for r in accepted) / len(accepted) if accepted else 0
        }

        return {
            'accepted_races': accepted,
            'rejected_races': rejected,
            'summary': summary
        }

    def get_venue_summary(self) -> str:
        """会場別推奨・除外リストを取得"""
        lines = []
        lines.append("=" * 60)
        lines.append("信頼度B 会場別フィルター設定")
        lines.append("=" * 60)

        # 除外会場
        if self.excluded_venues:
            lines.append("\n【除外会場】")
            for code in sorted(self.excluded_venues):
                stats = self.VENUE_STATS[code]
                lines.append(f"  {code:2d}. {stats['name']:8s} - 的中率 {stats['hit_rate']:5.2f}%")

        # 推奨会場（10%以上）
        recommended = [
            (code, stats) for code, stats in self.VENUE_STATS.items()
            if stats['hit_rate'] >= 10.0
        ]
        if recommended:
            lines.append("\n【高的中率会場（10%以上）】")
            for code, stats in sorted(recommended, key=lambda x: x[1]['hit_rate'], reverse=True):
                lines.append(f"  {code:2d}. {stats['name']:8s} - 的中率 {stats['hit_rate']:5.2f}%")

        return '\n'.join(lines)
