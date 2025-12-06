# -*- coding: utf-8 -*-
"""
期待値ベース買い目選択システム

実際のオッズデータを使用して期待値の高い買い目のみを選択する。
分析結果：Top 5 EV戦略でROI 144.9%を達成。
"""

import sqlite3
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import itertools


@dataclass
class EVBet:
    """期待値付き買い目"""
    combination: str  # "1-2-3"形式
    combination_tuple: Tuple[int, int, int]
    odds: float
    estimated_probability: float
    expected_value: float  # 1.0 = 損益分岐点
    confidence: str  # B, C, D, E
    is_selected: bool = False

    def __repr__(self):
        return f"EVBet({self.combination}, odds={self.odds:.1f}, EV={self.expected_value:.3f})"


class EVBetSelector:
    """
    期待値ベースの買い目選択クラス

    分析結果に基づく推奨設定:
    - Top 5 EV: ROI 144.9%
    - Top 3 EV: ROI 129.8%
    """

    # 信頼度別の1組み合わせあたりの的中確率（11月データから算出）
    CONFIDENCE_PROBABILITIES = {
        'B': 0.0513,  # 5.13%
        'C': 0.0354,  # 3.54%
        'D': 0.0171,  # 1.71%
        'E': 0.0100,  # 1.00%（推定）
    }

    # 信頼度別の損益分岐オッズ
    BREAKEVEN_ODDS = {
        'B': 19.5,
        'C': 28.2,
        'D': 58.5,
        'E': 100.0,
    }

    def __init__(
        self,
        db_path: str = 'data/boatrace.db',
        min_ev: float = 0.8,
        max_bets: int = 5,
        use_top_n: bool = True
    ):
        """
        初期化

        Args:
            db_path: データベースパス
            min_ev: 最小期待値（デフォルト0.8）
            max_bets: 最大買い目数（デフォルト5）
            use_top_n: True=上位N個を選択、False=閾値以上を全て選択
        """
        self.db_path = db_path
        self.min_ev = min_ev
        self.max_bets = max_bets
        self.use_top_n = use_top_n

    def get_race_odds(self, race_id: int) -> Dict[str, float]:
        """
        レースの3連単オッズを取得

        Args:
            race_id: レースID

        Returns:
            {'1-2-3': 10.5, ...} 形式のオッズデータ
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT combination, odds
                FROM trifecta_odds
                WHERE race_id = ?
            ''', (race_id,))
            return {row[0]: row[1] for row in cursor.fetchall()}

    def get_odds_by_venue_race(
        self,
        venue_code: str,
        race_date: str,
        race_number: int
    ) -> Dict[str, float]:
        """
        会場・日付・レース番号からオッズを取得

        Args:
            venue_code: 会場コード
            race_date: 日付（YYYY-MM-DD）
            race_number: レース番号

        Returns:
            オッズデータ
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT t.combination, t.odds
                FROM trifecta_odds t
                JOIN races r ON t.race_id = r.id
                WHERE r.venue_code = ?
                  AND r.race_date = ?
                  AND r.race_number = ?
            ''', (venue_code, race_date, race_number))
            return {row[0]: row[1] for row in cursor.fetchall()}

    def calculate_expected_value(
        self,
        odds: float,
        confidence: str
    ) -> float:
        """
        期待値を計算

        Args:
            odds: オッズ
            confidence: 信頼度（B/C/D/E）

        Returns:
            期待値（1.0 = 損益分岐点）
        """
        prob = self.CONFIDENCE_PROBABILITIES.get(confidence, 0.02)
        return prob * odds

    def generate_bet_combinations(
        self,
        predicted_ranks: List[int],
        pattern: str = '1-234-2345'
    ) -> List[Tuple[int, int, int]]:
        """
        買い目の組み合わせを生成

        Args:
            predicted_ranks: 予測順位の艇番リスト [1位艇番, 2位艇番, ...]
            pattern: 買い目パターン

        Returns:
            [(1着, 2着, 3着), ...] のリスト
        """
        p = predicted_ranks

        if pattern == '1-234-234':
            # 6点
            seconds = [p[1], p[2], p[3]]
            thirds = [p[1], p[2], p[3]]
        elif pattern == '1-234-2345':
            # 9点
            seconds = [p[1], p[2], p[3]]
            thirds = [p[1], p[2], p[3], p[4]]
        elif pattern == '1-2345-2345':
            # 12点
            seconds = [p[1], p[2], p[3], p[4]]
            thirds = [p[1], p[2], p[3], p[4]]
        else:
            # デフォルト: 9点
            seconds = [p[1], p[2], p[3]]
            thirds = [p[1], p[2], p[3], p[4]]

        combos = []
        for s in seconds:
            for t in thirds:
                if s != t and t != p[0]:
                    combos.append((p[0], s, t))

        return combos

    def select_bets(
        self,
        predicted_ranks: List[int],
        confidence: str,
        odds_data: Dict[str, float],
        pattern: str = '1-234-2345'
    ) -> List[EVBet]:
        """
        期待値ベースで買い目を選択

        Args:
            predicted_ranks: 予測順位の艇番リスト
            confidence: 信頼度
            odds_data: オッズデータ
            pattern: 買い目パターン

        Returns:
            選択された買い目リスト（期待値順）
        """
        # 買い目候補を生成
        combos = self.generate_bet_combinations(predicted_ranks, pattern)

        # 各買い目の期待値を計算
        ev_bets = []
        for combo in combos:
            combo_str = f'{combo[0]}-{combo[1]}-{combo[2]}'

            if combo_str not in odds_data:
                continue

            odds = odds_data[combo_str]
            ev = self.calculate_expected_value(odds, confidence)

            ev_bets.append(EVBet(
                combination=combo_str,
                combination_tuple=combo,
                odds=odds,
                estimated_probability=self.CONFIDENCE_PROBABILITIES.get(confidence, 0.02),
                expected_value=ev,
                confidence=confidence
            ))

        # 期待値でソート（降順）
        ev_bets.sort(key=lambda x: x.expected_value, reverse=True)

        # 選択
        if self.use_top_n:
            # 上位N個を選択
            selected = ev_bets[:self.max_bets]
        else:
            # 閾値以上を全て選択（最大max_bets個）
            selected = [b for b in ev_bets if b.expected_value >= self.min_ev][:self.max_bets]

        # 選択フラグを設定
        for bet in selected:
            bet.is_selected = True

        return selected

    def get_bet_recommendation(
        self,
        race_id: int,
        predicted_ranks: List[int],
        confidence: str,
        pattern: str = '1-234-2345'
    ) -> Dict:
        """
        レースの買い目推奨を取得

        Args:
            race_id: レースID
            predicted_ranks: 予測順位の艇番リスト
            confidence: 信頼度
            pattern: 買い目パターン

        Returns:
            推奨情報の辞書
        """
        # オッズ取得
        odds_data = self.get_race_odds(race_id)

        if not odds_data:
            return {
                'status': 'no_odds',
                'message': 'オッズデータがありません',
                'selected_bets': [],
                'all_bets': []
            }

        # 全買い目候補を生成
        combos = self.generate_bet_combinations(predicted_ranks, pattern)
        all_bets = []

        for combo in combos:
            combo_str = f'{combo[0]}-{combo[1]}-{combo[2]}'
            if combo_str in odds_data:
                odds = odds_data[combo_str]
                ev = self.calculate_expected_value(odds, confidence)
                all_bets.append(EVBet(
                    combination=combo_str,
                    combination_tuple=combo,
                    odds=odds,
                    estimated_probability=self.CONFIDENCE_PROBABILITIES.get(confidence, 0.02),
                    expected_value=ev,
                    confidence=confidence
                ))

        # 期待値でソート
        all_bets.sort(key=lambda x: x.expected_value, reverse=True)

        # 選択
        selected_bets = self.select_bets(predicted_ranks, confidence, odds_data, pattern)

        # 統計
        avg_ev = sum(b.expected_value for b in selected_bets) / len(selected_bets) if selected_bets else 0
        total_bet = len(selected_bets) * 100  # 1点100円

        return {
            'status': 'ok',
            'race_id': race_id,
            'confidence': confidence,
            'pattern': pattern,
            'selected_bets': selected_bets,
            'all_bets': all_bets,
            'num_selected': len(selected_bets),
            'num_total': len(all_bets),
            'avg_ev': avg_ev,
            'total_bet': total_bet,
            'breakeven_odds': self.BREAKEVEN_ODDS.get(confidence, 50),
        }

    def format_recommendation(self, recommendation: Dict) -> str:
        """
        推奨情報を整形して文字列で返す

        Args:
            recommendation: get_bet_recommendation()の戻り値

        Returns:
            整形された文字列
        """
        if recommendation['status'] != 'ok':
            return f"[{recommendation['status']}] {recommendation.get('message', '')}"

        lines = []
        lines.append(f"=== 期待値ベース買い目推奨 ===")
        lines.append(f"信頼度: {recommendation['confidence']}")
        lines.append(f"パターン: {recommendation['pattern']}")
        lines.append(f"損益分岐オッズ: {recommendation['breakeven_odds']:.1f}倍以上")
        lines.append(f"")
        lines.append(f"【選択買い目】 ({recommendation['num_selected']}/{recommendation['num_total']}点)")
        lines.append(f"平均期待値: {recommendation['avg_ev']:.3f}")
        lines.append(f"合計金額: {recommendation['total_bet']}円")
        lines.append(f"")

        for i, bet in enumerate(recommendation['selected_bets'], 1):
            ev_mark = "+" if bet.expected_value >= 1.0 else ""
            lines.append(f"  {i}. {bet.combination}: オッズ{bet.odds:>6.1f}倍, EV={ev_mark}{bet.expected_value:.3f}")

        if recommendation['all_bets']:
            lines.append(f"")
            lines.append(f"【全候補】")
            for bet in recommendation['all_bets'][:10]:
                selected = "*" if bet.is_selected else " "
                ev_mark = "+" if bet.expected_value >= 1.0 else ""
                lines.append(f"  {selected} {bet.combination}: オッズ{bet.odds:>6.1f}倍, EV={ev_mark}{bet.expected_value:.3f}")

        return "\n".join(lines)


class EVBetAnalyzer:
    """
    期待値ベース戦略の分析・検証クラス
    """

    def __init__(self, db_path: str = 'data/boatrace.db'):
        self.db_path = db_path
        self.selector = EVBetSelector(db_path)

    def backtest(
        self,
        start_date: str,
        end_date: str,
        max_bets: int = 5,
        min_ev: float = 0.0,
        prediction_type: str = 'advance'
    ) -> Dict:
        """
        過去データでバックテスト

        Args:
            start_date: 開始日（YYYY-MM-DD）
            end_date: 終了日（YYYY-MM-DD）
            max_bets: 最大買い目数
            min_ev: 最小期待値
            prediction_type: 予測タイプ

        Returns:
            バックテスト結果
        """
        selector = EVBetSelector(
            self.db_path,
            min_ev=min_ev,
            max_bets=max_bets,
            use_top_n=True
        )

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # オッズデータがあるレースを取得
            cursor.execute('''
                SELECT DISTINCT t.race_id
                FROM trifecta_odds t
                JOIN races r ON t.race_id = r.id
                WHERE r.race_date >= ? AND r.race_date <= ?
            ''', (start_date, end_date))
            race_ids = [row[0] for row in cursor.fetchall()]

        results = {
            'total_races': 0,
            'total_bets': 0,
            'total_bet_amount': 0,
            'total_hits': 0,
            'total_payout': 0,
            'by_confidence': {},
            'details': []
        }

        for race_id in race_ids:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 予測データ取得
                cursor.execute('''
                    SELECT pit_number, rank_prediction, confidence, total_score
                    FROM race_predictions
                    WHERE race_id = ? AND prediction_type = ?
                    ORDER BY rank_prediction
                ''', (race_id, prediction_type))
                preds = cursor.fetchall()

                if len(preds) < 6:
                    continue

                preds_sorted = sorted(preds, key=lambda x: x[1])
                predicted_ranks = [x[0] for x in preds_sorted]
                confidence = preds_sorted[0][2]

                # 実際の結果取得
                cursor.execute('''
                    SELECT pit_number FROM results
                    WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
                    ORDER BY rank
                ''', (race_id,))
                actual = cursor.fetchall()

                if len(actual) < 3:
                    continue

                actual_combo = f'{actual[0][0]}-{actual[1][0]}-{actual[2][0]}'

                # 配当取得
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta'
                ''', (race_id,))
                payout_row = cursor.fetchone()
                payout = payout_row[0] if payout_row else 0

                # オッズ取得
                odds_data = selector.get_race_odds(race_id)
                if not odds_data:
                    continue

                # 買い目選択
                selected_bets = selector.select_bets(
                    predicted_ranks, confidence, odds_data, '1-234-2345'
                )

                if not selected_bets:
                    continue

                # 結果判定
                hit = any(b.combination == actual_combo for b in selected_bets)
                bet_amount = len(selected_bets) * 100

                results['total_races'] += 1
                results['total_bets'] += len(selected_bets)
                results['total_bet_amount'] += bet_amount

                if hit:
                    results['total_hits'] += 1
                    results['total_payout'] += payout

                # 信頼度別集計
                if confidence not in results['by_confidence']:
                    results['by_confidence'][confidence] = {
                        'races': 0, 'hits': 0, 'bet': 0, 'payout': 0
                    }
                results['by_confidence'][confidence]['races'] += 1
                results['by_confidence'][confidence]['bet'] += bet_amount
                if hit:
                    results['by_confidence'][confidence]['hits'] += 1
                    results['by_confidence'][confidence]['payout'] += payout

        # 統計計算
        if results['total_races'] > 0:
            results['hit_rate'] = results['total_hits'] / results['total_races'] * 100
            results['roi'] = results['total_payout'] / results['total_bet_amount'] * 100 if results['total_bet_amount'] > 0 else 0
            results['profit'] = results['total_payout'] - results['total_bet_amount']

        return results

    def format_backtest_result(self, result: Dict) -> str:
        """バックテスト結果を整形"""
        lines = []
        lines.append("=" * 70)
        lines.append("期待値ベース戦略 バックテスト結果")
        lines.append("=" * 70)
        lines.append(f"総レース数: {result['total_races']}")
        lines.append(f"総買い目数: {result['total_bets']}")
        lines.append(f"的中数: {result['total_hits']}")
        lines.append(f"的中率: {result.get('hit_rate', 0):.2f}%")
        lines.append(f"投資額: {result['total_bet_amount']:,}円")
        lines.append(f"払戻額: {result['total_payout']:,}円")
        lines.append(f"収支: {result.get('profit', 0):+,}円")
        lines.append(f"ROI: {result.get('roi', 0):.1f}%")
        lines.append("")
        lines.append("[信頼度別]")

        for conf in ['B', 'C', 'D', 'E']:
            if conf in result['by_confidence']:
                data = result['by_confidence'][conf]
                if data['races'] > 0:
                    hit_rate = data['hits'] / data['races'] * 100
                    roi = data['payout'] / data['bet'] * 100 if data['bet'] > 0 else 0
                    lines.append(f"  {conf}: {data['races']}R, 的中{data['hits']}, 率{hit_rate:.1f}%, ROI {roi:.1f}%")

        return "\n".join(lines)


if __name__ == "__main__":
    # テスト実行
    print("=" * 70)
    print("期待値ベース買い目選択システム テスト")
    print("=" * 70)

    # バックテスト
    analyzer = EVBetAnalyzer()

    print("\n[Top 5 EV戦略 - 11月バックテスト]")
    result = analyzer.backtest('2025-11-01', '2025-11-30', max_bets=5)
    print(analyzer.format_backtest_result(result))

    print("\n[Top 3 EV戦略 - 11月バックテスト]")
    result3 = analyzer.backtest('2025-11-01', '2025-11-30', max_bets=3)
    print(analyzer.format_backtest_result(result3))

    print("\n" + "=" * 70)
    print("テスト完了")
