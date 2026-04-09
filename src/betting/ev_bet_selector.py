# -*- coding: utf-8 -*-
"""
期待値ベース買い目選択システム

実際のオッズデータを使用して期待値の高い買い目のみを選択する。

修正履歴:
  2026-04-06: 5点バグ修正
    1. A信頼度の確率を追加（旧コードはデフォルト2%にフォールバックしていた）
    2. prediction_typeデフォルトを'advance'→'before'に修正
    3. バックテストのDBループ内接続を1接続に統合（パフォーマンス改善）
    4. 確率モデルを位置依存型に改善（全組み合わせに同じ確率を使っていた問題を修正）
    5. Plackett-Luceモデルを追加（total_score提供時に使用）
  2026-04-06: 改善1 - P-L確率のキャリブレーション後処理
    Isotonic Regressionによる補正モデルを適用。
    10%以上の確率帯で30-40%過大評価していた問題を修正。
    モデル: models/pl_calibrator.pkl（2020-2024年データで学習）
"""

import sqlite3
import math
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import itertools

# キャリブレーターのパス（プロジェクトルート基準）
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent.parent
_CALIBRATOR_PATH = _PROJECT_ROOT / 'models' / 'pl_calibrator.pkl'

# 起動時にキャリブレーターをロード（存在しない場合はNone）
_pl_calibrator = None
try:
    import joblib
    if _CALIBRATOR_PATH.exists():
        _pl_calibrator = joblib.load(_CALIBRATOR_PATH)
except Exception:
    pass


@dataclass
class EVBet:
    """期待値付き買い目"""
    combination: str  # "1-2-3"形式
    combination_tuple: Tuple[int, int, int]
    odds: float
    estimated_probability: float
    expected_value: float  # 1.0 = 損益分岐点
    confidence: str
    is_selected: bool = False

    def __repr__(self):
        return f"EVBet({self.combination}, odds={self.odds:.1f}, EV={self.expected_value:.3f})"


class EVBetSelector:
    """
    期待値ベースの買い目選択クラス

    確率モデル:
    - total_scoreが提供される場合: Plackett-Luceモデルで全120通りの確率を算出
    - total_scoreなしの場合: DB実績値（位置別確率テーブル）を使用
    """

    # Fix 1: A信頼度を追加。値はDB実績（2020-2025 before予測 1-2-3的中率）
    CONFIDENCE_PROBABILITIES = {
        'A': 0.1048,  # 10.48%（DB実績 77,476件）
        'B': 0.0952,  # 9.52% （DB実績 63,695件）
        'C': 0.0587,  # 5.87% （DB実績 132,982件）
        'D': 0.0282,  # 2.82% （DB実績 31,487件）
        'E': 0.0100,  # 推定
    }

    # Fix 4: 組み合わせ位置別の確率（DB実績 2020-2025 before予測）
    # キー: (2着予測順位, 3着予測順位)
    # 1-2-3 = (2,3), 1-2-4 = (2,4), 1-2-5 = (2,5)
    RANK_COMBO_PROBABILITIES = {
        'A': {(2, 3): 0.1048, (2, 4): 0.0811, (2, 5): 0.0567},
        'B': {(2, 3): 0.0952, (2, 4): 0.0695, (2, 5): 0.0479},
        'C': {(2, 3): 0.0587, (2, 4): 0.0446, (2, 5): 0.0319},
        'D': {(2, 3): 0.0282, (2, 4): 0.0232, (2, 5): 0.0173},
        'E': {(2, 3): 0.0100, (2, 4): 0.0080, (2, 5): 0.0060},
    }

    # 信頼度別の損益分岐オッズ（1-2-3確率ベース）
    BREAKEVEN_ODDS = {
        'A': 9.5,
        'B': 10.5,
        'C': 17.0,
        'D': 35.5,
        'E': 100.0,
    }

    def __init__(
        self,
        db_path: str = 'data/boatrace.db',
        min_ev: float = 0.8,
        max_bets: int = 5,
        use_top_n: bool = True
    ):
        self.db_path = db_path
        self.min_ev = min_ev
        self.max_bets = max_bets
        self.use_top_n = use_top_n

    def get_race_odds(self, race_id: int, cursor=None) -> Dict[str, float]:
        """
        レースの3連単オッズを取得

        Args:
            race_id: レースID
            cursor: 既存のDBカーソル（Noneの場合は新規接続）
        """
        if cursor:
            cursor.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id = ?', (race_id,))
            return {row[0]: row[1] for row in cursor.fetchall()}
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id = ?', (race_id,))
            return {row[0]: row[1] for row in cur.fetchall()}

    def get_odds_by_venue_race(
        self,
        venue_code: str,
        race_date: str,
        race_number: int
    ) -> Dict[str, float]:
        """会場・日付・レース番号からオッズを取得"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT t.combination, t.odds
                FROM trifecta_odds t
                JOIN races r ON t.race_id = r.id
                WHERE r.venue_code = ? AND r.race_date = ? AND r.race_number = ?
            ''', (venue_code, race_date, race_number))
            return {row[0]: row[1] for row in cursor.fetchall()}

    def get_combo_probability(
        self,
        confidence: str,
        predicted_rank_2nd: int,
        predicted_rank_3rd: int
    ) -> float:
        """
        組み合わせの的中確率を返す（位置別確率テーブル使用）

        DB実績値がある場合はそれを使用。ない場合は減衰率で推定。
        """
        table = self.RANK_COMBO_PROBABILITIES.get(confidence, {})
        key = (predicted_rank_2nd, predicted_rank_3rd)
        if key in table:
            return table[key]

        # 実績値がない組み合わせ: ベース確率に減衰を適用
        base = table.get((2, 3), self.CONFIDENCE_PROBABILITIES.get(confidence, 0.02))
        # 2着が予測順位から外れるほど・3着が下位ほど確率が下がる
        decay_2nd = 0.80 ** (predicted_rank_2nd - 2)
        decay_3rd = 0.75 ** (predicted_rank_3rd - 3)
        return base * decay_2nd * decay_3rd

    def calculate_plackett_luce_probability(
        self,
        scores: Dict[int, float],
        combo: Tuple[int, int, int],
        apply_calibration: bool = True
    ) -> float:
        """
        Plackett-Luceモデルで三連単確率を計算（キャリブレーション付き）

        Args:
            scores: {pit_number: total_score} 全6艇のスコア
            combo: (1着艇番, 2着艇番, 3着艇番)
            apply_calibration: Isotonic Regressionによる補正を適用するか

        Returns:
            その組み合わせの的中確率（補正済み）
        """
        a, b, c = combo
        if a not in scores or b not in scores or c not in scores:
            return 0.0

        # 数値安定化のため最大値を引いてexpに変換
        # scale=20.0: 2025年データでP(1-2-3)平均7.84% vs 実績7.43%（比1.06x）
        max_score = max(scores.values())
        scale = 20.0
        exp_scores = {pit: math.exp((s - max_score) / scale) for pit, s in scores.items()}
        total = sum(exp_scores.values())

        # P(a 1着) × P(b 2着 | a 1着) × P(c 3着 | a 1着, b 2着)
        p_a = exp_scores[a] / total
        denom_b = total - exp_scores[a]
        if denom_b <= 0:
            return 0.0
        p_b = exp_scores[b] / denom_b
        denom_c = denom_b - exp_scores[b]
        if denom_c <= 0:
            return 0.0
        p_c = exp_scores[c] / denom_c

        raw_prob = p_a * p_b * p_c

        # キャリブレーション後処理（Isotonic Regression）
        if apply_calibration and _pl_calibrator is not None:
            try:
                import numpy as np
                calibrated = _pl_calibrator.transform(np.array([raw_prob]))[0]
                return float(calibrated)
            except Exception:
                pass  # 失敗時は生の確率を使用

        return raw_prob

    def calculate_expected_value(self, odds: float, confidence: str) -> float:
        """後方互換用: 信頼度別固定確率でEVを計算（1-2-3ベース）"""
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
              '1-234-234'   : 6通り（1着固定）
              '1-234-2345'  : 9通り（1着固定、デフォルト）
              '1-2345-2345' : 12通り（1着固定）
              'all120'      : 全120通り（改善2: 1着固定を外す）

        Returns:
            [(1着, 2着, 3着), ...] のリスト
        """
        p = predicted_ranks

        if pattern == 'all120':
            # 改善2: 全120通り。P-Lが全艇の確率を計算するため1着固定不要
            combos = []
            pits = list(p)  # 全艇番（予測順）
            for a in pits:
                for b in pits:
                    if b == a:
                        continue
                    for c in pits:
                        if c == a or c == b:
                            continue
                        combos.append((a, b, c))
            return combos

        if pattern == '1-234-234':
            seconds = [p[1], p[2], p[3]]
            thirds = [p[1], p[2], p[3]]
        elif pattern == '1-234-2345':
            seconds = [p[1], p[2], p[3]]
            thirds = [p[1], p[2], p[3], p[4]]
        elif pattern == '1-2345-2345':
            seconds = [p[1], p[2], p[3], p[4]]
            thirds = [p[1], p[2], p[3], p[4]]
        else:
            seconds = [p[1], p[2], p[3]]
            thirds = [p[1], p[2], p[3], p[4]]

        combos = []
        for s in seconds:
            for t in thirds:
                if s != t and t != p[0] and s != p[0]:
                    combos.append((p[0], s, t))

        return combos

    def select_bets(
        self,
        predicted_ranks: List[int],
        confidence: str,
        odds_data: Dict[str, float],
        pattern: str = '1-234-2345',
        scores: Optional[Dict[int, float]] = None,
        odds_max_per_bet: Optional[float] = None
    ) -> List['EVBet']:
        """
        期待値ベースで買い目を選択

        Args:
            predicted_ranks: 予測順位の艇番リスト
            confidence: 信頼度
            odds_data: オッズデータ
            pattern: 買い目パターン（'all120'で全120通り対象）
            scores: {pit_number: total_score}（Plackett-Luce使用時に指定）
            odds_max_per_bet: 各買い目のオッズ上限（超える組み合わせは除外）
                              改善2: 高オッズの偶然依存を排除するために使用

        Returns:
            選択された買い目リスト（期待値順）
        """
        combos = self.generate_bet_combinations(predicted_ranks, pattern)
        rank_of = {pit: i + 1 for i, pit in enumerate(predicted_ranks)}

        ev_bets = []
        for combo in combos:
            combo_str = f'{combo[0]}-{combo[1]}-{combo[2]}'
            if combo_str not in odds_data:
                continue

            odds = odds_data[combo_str]

            # 改善2: 各買い目オッズ上限フィルター
            if odds_max_per_bet is not None and odds > odds_max_per_bet:
                continue

            # 確率モデルの選択
            if scores:
                prob = self.calculate_plackett_luce_probability(scores, combo)
            else:
                r2nd = rank_of.get(combo[1], 6)
                r3rd = rank_of.get(combo[2], 6)
                prob = self.get_combo_probability(confidence, r2nd, r3rd)

            ev = prob * odds

            ev_bets.append(EVBet(
                combination=combo_str,
                combination_tuple=combo,
                odds=odds,
                estimated_probability=prob,
                expected_value=ev,
                confidence=confidence
            ))

        # 期待値でソート（降順）
        ev_bets.sort(key=lambda x: x.expected_value, reverse=True)

        if self.use_top_n:
            selected = ev_bets[:self.max_bets]
        else:
            selected = [b for b in ev_bets if b.expected_value >= self.min_ev][:self.max_bets]

        for bet in selected:
            bet.is_selected = True

        return selected

    def get_bet_recommendation(
        self,
        race_id: int,
        predicted_ranks: List[int],
        confidence: str,
        pattern: str = '1-234-2345',
        scores: Optional[Dict[int, float]] = None
    ) -> Dict:
        """レースの買い目推奨を取得"""
        odds_data = self.get_race_odds(race_id)

        if not odds_data:
            return {'status': 'no_odds', 'message': 'オッズデータがありません', 'selected_bets': [], 'all_bets': []}

        combos = self.generate_bet_combinations(predicted_ranks, pattern)
        rank_of = {pit: i + 1 for i, pit in enumerate(predicted_ranks)}
        all_bets = []

        for combo in combos:
            combo_str = f'{combo[0]}-{combo[1]}-{combo[2]}'
            if combo_str not in odds_data:
                continue
            odds = odds_data[combo_str]
            if scores:
                prob = self.calculate_plackett_luce_probability(scores, combo)
            else:
                r2nd = rank_of.get(combo[1], 6)
                r3rd = rank_of.get(combo[2], 6)
                prob = self.get_combo_probability(confidence, r2nd, r3rd)
            ev = prob * odds
            all_bets.append(EVBet(
                combination=combo_str, combination_tuple=combo,
                odds=odds, estimated_probability=prob,
                expected_value=ev, confidence=confidence
            ))

        all_bets.sort(key=lambda x: x.expected_value, reverse=True)
        selected_bets = self.select_bets(predicted_ranks, confidence, odds_data, pattern, scores)

        avg_ev = sum(b.expected_value for b in selected_bets) / len(selected_bets) if selected_bets else 0
        total_bet = len(selected_bets) * 100

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
        """推奨情報を整形して文字列で返す"""
        if recommendation['status'] != 'ok':
            return f"[{recommendation['status']}] {recommendation.get('message', '')}"

        lines = [
            "=== 期待値ベース買い目推奨 ===",
            f"信頼度: {recommendation['confidence']}",
            f"パターン: {recommendation['pattern']}",
            f"損益分岐オッズ: {recommendation['breakeven_odds']:.1f}倍以上",
            "",
            f"【選択買い目】 ({recommendation['num_selected']}/{recommendation['num_total']}点)",
            f"平均期待値: {recommendation['avg_ev']:.3f}",
            f"合計金額: {recommendation['total_bet']}円",
            "",
        ]
        for i, bet in enumerate(recommendation['selected_bets'], 1):
            ev_mark = "+" if bet.expected_value >= 1.0 else ""
            lines.append(f"  {i}. {bet.combination}: オッズ{bet.odds:>6.1f}倍, EV={ev_mark}{bet.expected_value:.3f}")

        if recommendation['all_bets']:
            lines += ["", "【全候補（上位10）】"]
            for bet in recommendation['all_bets'][:10]:
                sel = "*" if bet.is_selected else " "
                ev_mark = "+" if bet.expected_value >= 1.0 else ""
                lines.append(f"  {sel} {bet.combination}: オッズ{bet.odds:>6.1f}倍, EV={ev_mark}{bet.expected_value:.3f}")

        return "\n".join(lines)


class EVBetAnalyzer:
    """期待値ベース戦略の分析・検証クラス"""

    def __init__(self, db_path: str = 'data/boatrace.db'):
        self.db_path = db_path
        self.selector = EVBetSelector(db_path)

    def backtest(
        self,
        start_date: str,
        end_date: str,
        max_bets: int = 5,
        min_ev: float = 0.0,
        prediction_type: str = 'before',  # Fix 2: 'advance' → 'before'
        use_plackett_luce: bool = True,
        ev_threshold: float = 1.0
    ) -> Dict:
        """
        過去データでバックテスト

        Args:
            start_date: 開始日（YYYY-MM-DD）
            end_date: 終了日（YYYY-MM-DD）
            max_bets: 最大買い目数
            min_ev: 最小期待値（use_top_n=Falseの場合）
            prediction_type: 予測タイプ（デフォルト: 'before'）
            use_plackett_luce: Plackett-Luceで確率計算するか
            ev_threshold: この値以上のEVのみ購入（デフォルト1.0 = 損益分岐）
        """
        selector = EVBetSelector(
            self.db_path,
            min_ev=ev_threshold,
            max_bets=max_bets,
            use_top_n=False  # EV閾値方式
        )

        results = {
            'total_races': 0,
            'total_bets': 0,
            'total_bet_amount': 0,
            'total_hits': 0,
            'total_payout': 0,
            'by_confidence': {},
            'details': []
        }

        # Fix 3: DBループ外で1接続に統合
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # オッズデータがあるレースを取得
            cursor.execute('''
                SELECT DISTINCT t.race_id
                FROM trifecta_odds t
                JOIN races r ON t.race_id = r.id
                WHERE r.race_date >= ? AND r.race_date <= ?
                ORDER BY r.race_date
            ''', (start_date, end_date))
            race_ids = [row[0] for row in cursor.fetchall()]

            for race_id in race_ids:
                # 予測データ取得（スコア含む）
                cursor.execute('''
                    SELECT pit_number, rank_prediction, confidence, total_score
                    FROM race_predictions
                    WHERE race_id = ? AND prediction_type = ?
                    ORDER BY rank_prediction
                ''', (race_id, prediction_type))
                preds = cursor.fetchall()

                if len(preds) < 5:
                    continue

                preds_sorted = sorted(preds, key=lambda x: x[1])
                predicted_ranks = [x[0] for x in preds_sorted]
                confidence = preds_sorted[0][2]

                # Plackett-Luce用スコアマップ
                scores = None
                if use_plackett_luce:
                    scores = {x[0]: (x[3] or 0.0) for x in preds_sorted}

                # 実際の結果取得
                cursor.execute('''
                    SELECT pit_number FROM results
                    WHERE race_id = ? AND is_invalid = 0 AND rank IN ('1','2','3')
                    ORDER BY rank
                ''', (race_id,))
                actual = cursor.fetchall()

                if len(actual) < 3:
                    continue

                actual_combo = f'{actual[0][0]}-{actual[1][0]}-{actual[2][0]}'

                # 払戻取得（payoutsテーブル）
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta'
                ''', (race_id,))
                payout_row = cursor.fetchone()
                payout = payout_row[0] if payout_row else 0

                # オッズ取得
                odds_data = selector.get_race_odds(race_id, cursor)
                if not odds_data:
                    continue

                # 買い目選択
                selected_bets = selector.select_bets(
                    predicted_ranks, confidence, odds_data, '1-234-2345', scores
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
                c = confidence
                if c not in results['by_confidence']:
                    results['by_confidence'][c] = {'races': 0, 'hits': 0, 'bet': 0, 'payout': 0}
                results['by_confidence'][c]['races'] += 1
                results['by_confidence'][c]['bet'] += bet_amount
                if hit:
                    results['by_confidence'][c]['hits'] += 1
                    results['by_confidence'][c]['payout'] += payout

        if results['total_races'] > 0:
            results['hit_rate'] = results['total_hits'] / results['total_races'] * 100
            results['roi'] = results['total_payout'] / results['total_bet_amount'] * 100 if results['total_bet_amount'] > 0 else 0
            results['profit'] = results['total_payout'] - results['total_bet_amount']

        return results

    def format_backtest_result(self, result: Dict) -> str:
        """バックテスト結果を整形"""
        lines = [
            "=" * 70,
            "期待値ベース戦略 バックテスト結果",
            "=" * 70,
            f"総レース数: {result['total_races']:,}",
            f"総買い目数: {result['total_bets']:,}",
            f"的中数: {result['total_hits']}",
            f"的中率: {result.get('hit_rate', 0):.2f}%",
            f"投資額: {result['total_bet_amount']:,}円",
            f"払戻額: {result['total_payout']:,}円",
            f"収支: {result.get('profit', 0):+,}円",
            f"ROI: {result.get('roi', 0):.1f}%",
            "",
            "[信頼度別]",
        ]
        for conf in ['A', 'B', 'C', 'D', 'E']:
            if conf in result['by_confidence']:
                data = result['by_confidence'][conf]
                if data['races'] > 0:
                    hit_rate = data['hits'] / data['races'] * 100
                    roi = data['payout'] / data['bet'] * 100 if data['bet'] > 0 else 0
                    lines.append(f"  {conf}: {data['races']:,}R, 的中{data['hits']}, 率{hit_rate:.1f}%, ROI {roi:.1f}%")
        return "\n".join(lines)


if __name__ == "__main__":
    print("=" * 70)
    print("期待値ベース買い目選択システム テスト")
    print("=" * 70)

    analyzer = EVBetAnalyzer()

    print("\n[EV>=1.0 - 2025 Plackett-Luce]")
    result = analyzer.backtest('2025-01-01', '2025-12-31', max_bets=9, ev_threshold=1.0, use_plackett_luce=True)
    print(analyzer.format_backtest_result(result))

    print("\n[EV>=1.0 - 2024 Plackett-Luce]")
    result2 = analyzer.backtest('2024-01-01', '2024-12-31', max_bets=9, ev_threshold=1.0, use_plackett_luce=True)
    print(analyzer.format_backtest_result(result2))
