"""
高速バックテスト

現在のスコアリング要素の効果を素早く評価するための軽量版バックテスト。
SQLベースで一括処理し、Pythonでの個別予測を避けることで高速化。
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
import time
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple
from config.settings import DATABASE_PATH


class FastBacktester:
    """高速バックテスター"""

    # 会場別1コース勝率（2024年データ）
    VENUE_IN1_RATES = {
        '18': 66.7, '24': 65.5, '19': 62.0, '17': 62.0, '13': 61.5,
        '07': 60.8, '16': 60.1, '12': 59.9, '09': 59.8, '08': 59.8,
        '11': 58.3, '22': 58.1, '15': 58.1, '21': 57.7, '20': 57.4,
        '10': 55.4, '05': 54.9, '23': 54.8, '06': 54.8, '01': 51.4,
        '14': 49.8, '03': 48.5, '02': 45.4, '04': 45.1,
    }

    # 高イン会場（58%以上）: コース重視
    HIGH_IN_VENUES = ['18', '24', '19', '17', '13', '07', '16', '12', '09', '08', '11', '22', '15']

    # 低イン会場（50%以下）: モーター・選手重視
    LOW_IN_VENUES = ['14', '03', '02', '04']

    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path

    def get_race_data_bulk(self, start_date: str, end_date: str) -> List[Dict]:
        """
        レースデータを一括取得

        各レースの出走表と結果を一度に取得し、メモリ上で処理
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # レースごとにエントリと結果を取得
        query = """
            SELECT
                r.id as race_id,
                r.venue_code,
                r.race_date,
                r.race_number,
                e.pit_number,
                e.racer_number,
                e.racer_rank,
                e.win_rate,
                e.second_rate,
                e.local_win_rate,
                e.local_second_rate,
                e.motor_number,
                e.motor_second_rate,
                e.boat_second_rate,
                e.avg_st,
                COALESCE(res.rank, 99) as result_rank
            FROM races r
            INNER JOIN entries e ON r.id = e.race_id
            LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
            WHERE r.race_date BETWEEN ? AND ?
              AND res.rank IS NOT NULL
              AND res.is_invalid = 0
            ORDER BY r.id, e.pit_number
        """

        cursor.execute(query, (start_date, end_date))
        rows = cursor.fetchall()
        conn.close()

        # レースごとにグループ化
        races = defaultdict(list)
        for row in rows:
            races[row['race_id']].append(dict(row))

        return list(races.values())

    def calculate_simple_score(self, entry: Dict, weights: Dict, venue_code: str = None) -> float:
        """
        シンプルなスコア計算（高速版）

        基本要素のみでスコアを算出
        """
        score = 0.0

        # 会場特性による動的重み調整
        adjusted_weights = weights.copy()
        if venue_code:
            if venue_code in self.HIGH_IN_VENUES:
                # 高イン会場: コース重視
                adjusted_weights['course'] = weights.get('course', 30) + 5
                adjusted_weights['racer'] = weights.get('racer', 30) - 3
                adjusted_weights['motor'] = weights.get('motor', 20) - 2
            elif venue_code in self.LOW_IN_VENUES:
                # 低イン会場: モーター・選手重視
                adjusted_weights['course'] = weights.get('course', 30) - 8
                adjusted_weights['racer'] = weights.get('racer', 30) + 4
                adjusted_weights['motor'] = weights.get('motor', 20) + 4

        # 1. コーススコア（枠番別基準）
        # 会場別の実績勝率を使用
        pit = entry['pit_number']
        if venue_code and pit == 1:
            # 1コースは会場別勝率を反映
            venue_in1 = self.VENUE_IN1_RATES.get(venue_code, 55)
            course_score = venue_in1 / 66.7 * 100  # 最高勝率66.7%を基準に正規化
        else:
            course_base = {1: 55, 2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
            course_score = course_base.get(pit, 10) / 55 * 100  # 正規化
        score += course_score * adjusted_weights.get('course', 35) / 100

        # 2. 選手スコア（勝率ベース）
        win_rate = entry.get('win_rate') or 0
        local_win_rate = entry.get('local_win_rate') or 0
        racer_score = (win_rate * 0.6 + local_win_rate * 0.4) * 10  # 勝率を0-100に
        score += racer_score * weights.get('racer', 35) / 100

        # 3. モータースコア
        motor_rate = entry.get('motor_second_rate') or 30
        motor_score = motor_rate  # すでに%表記
        score += motor_score * weights.get('motor', 20) / 100

        # 4. 級別スコア
        rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
        rank = entry.get('racer_rank') or 'B1'
        rank_score = rank_scores.get(rank, 40)
        score += rank_score * weights.get('rank', 10) / 100

        # 5. 平均STスコア（新規追加）
        # ST 0.10-0.15が最も勝率高い（24.38%）
        avg_st = entry.get('avg_st')
        if avg_st is not None and avg_st > 0:
            if 0.10 <= avg_st < 0.15:
                st_score = 100  # 最適
            elif 0.15 <= avg_st < 0.18:
                st_score = 80   # 良好
            elif avg_st < 0.10:
                st_score = 70   # 早すぎ（Fリスク）
            elif 0.18 <= avg_st < 0.20:
                st_score = 60   # やや遅い
            else:
                st_score = 40   # 遅い
        else:
            st_score = 50  # データなしは中間

        score += st_score * weights.get('st', 10) / 100

        return score

    def predict_race_simple(self, race_entries: List[Dict], weights: Dict, venue_code: str = None) -> List[int]:
        """
        レース予測（シンプル版）

        スコア順に順位予測を返す
        """
        scores = []
        for entry in race_entries:
            score = self.calculate_simple_score(entry, weights, venue_code)
            scores.append((entry['pit_number'], score))

        # スコア降順でソート
        scores.sort(key=lambda x: -x[1])

        return [s[0] for s in scores]

    def evaluate_predictions(self,
                            predicted: List[int],
                            race_entries: List[Dict]) -> Dict:
        """
        予測を評価
        """
        # 実際の順位を取得
        actual = sorted(race_entries, key=lambda x: x['result_rank'])
        actual_order = [e['pit_number'] for e in actual]

        if len(actual_order) < 3:
            return None

        return {
            'win_hit': predicted[0] == actual_order[0],
            'place_hit': predicted[0] in actual_order[:3],
            'exacta_hit': predicted[:2] == actual_order[:2],
            'trifecta_hit': predicted[:3] == actual_order[:3],
            'trio_hit': set(predicted[:3]) == set(actual_order[:3]),
        }

    def run_backtest(self,
                     start_date: str,
                     end_date: str,
                     weights: Dict = None,
                     sample_rate: float = 1.0) -> Dict:
        """
        バックテスト実行

        Args:
            start_date: 開始日
            end_date: 終了日
            weights: 重み設定
            sample_rate: サンプリング率（1.0=全件、0.1=10%）
        """
        if weights is None:
            weights = {
                'course': 30,
                'racer': 30,
                'motor': 20,
                'rank': 10,
                'st': 10  # 平均STスコア追加
            }

        print(f"期間: {start_date} ～ {end_date}")
        print(f"重み設定: {weights}")
        print()

        # データ一括取得
        start = time.time()
        races = self.get_race_data_bulk(start_date, end_date)
        load_time = time.time() - start

        total_races = len(races)
        print(f"データ取得: {total_races:,}レース ({load_time:.1f}秒)")

        # サンプリング
        if sample_rate < 1.0:
            import random
            races = random.sample(races, int(len(races) * sample_rate))
            print(f"サンプリング: {len(races):,}レース")

        # 評価
        results = {
            'win_hits': 0,
            'place_hits': 0,
            'exacta_hits': 0,
            'trifecta_hits': 0,
            'trio_hits': 0,
            'total': 0
        }

        venue_stats = defaultdict(lambda: {'win_hits': 0, 'total': 0})

        start = time.time()
        for i, race_entries in enumerate(races, 1):
            if len(race_entries) < 6:
                continue

            # 会場コードを取得
            venue = race_entries[0]['venue_code']

            # 予測（会場特性を考慮）
            predicted = self.predict_race_simple(race_entries, weights, venue)

            # 評価
            eval_result = self.evaluate_predictions(predicted, race_entries)
            if eval_result is None:
                continue

            results['total'] += 1
            if eval_result['win_hit']:
                results['win_hits'] += 1
            if eval_result['place_hit']:
                results['place_hits'] += 1
            if eval_result['exacta_hit']:
                results['exacta_hits'] += 1
            if eval_result['trifecta_hit']:
                results['trifecta_hits'] += 1
            if eval_result['trio_hit']:
                results['trio_hits'] += 1

            # 会場別
            venue_stats[venue]['total'] += 1
            if eval_result['win_hit']:
                venue_stats[venue]['win_hits'] += 1

            # 進捗
            if i % 1000 == 0:
                print(f"  処理中: {i:,}/{len(races):,}")

        eval_time = time.time() - start
        print(f"評価完了: {eval_time:.1f}秒")
        print()

        return {
            'results': results,
            'venue_stats': dict(venue_stats),
            'weights': weights,
            'period': {'start': start_date, 'end': end_date},
            'total_races': total_races,
            'tested_races': results['total'],
            'load_time': load_time,
            'eval_time': eval_time
        }

    def print_results(self, result: Dict):
        """結果を表示"""
        r = result['results']
        total = r['total']

        if total == 0:
            print("評価対象レースがありません")
            return

        print("=" * 60)
        print("バックテスト結果")
        print("=" * 60)
        print(f"期間: {result['period']['start']} ～ {result['period']['end']}")
        print(f"テスト対象: {total:,}レース")
        print()

        print("【的中率】")
        print(f"  単勝的中率:   {r['win_hits']/total*100:>6.2f}% ({r['win_hits']:,}/{total:,})")
        print(f"  複勝的中率:   {r['place_hits']/total*100:>6.2f}% ({r['place_hits']:,}/{total:,})")
        print(f"  2連単的中率:  {r['exacta_hits']/total*100:>6.2f}% ({r['exacta_hits']:,}/{total:,})")
        print(f"  3連単的中率:  {r['trifecta_hits']/total*100:>6.2f}% ({r['trifecta_hits']:,}/{total:,})")
        print(f"  3連複的中率:  {r['trio_hits']/total*100:>6.2f}% ({r['trio_hits']:,}/{total:,})")
        print()

        # 会場別
        print("【会場別単勝的中率】")
        venue_stats = result['venue_stats']
        sorted_venues = sorted(venue_stats.items(),
                               key=lambda x: x[1]['win_hits']/x[1]['total'] if x[1]['total'] > 0 else 0,
                               reverse=True)

        for venue, stats in sorted_venues[:10]:
            rate = stats['win_hits'] / stats['total'] * 100 if stats['total'] > 0 else 0
            print(f"  {venue}: {rate:>5.1f}% ({stats['win_hits']:>3}/{stats['total']:>4})")

        print()
        print(f"処理時間: データ取得 {result['load_time']:.1f}秒 + 評価 {result['eval_time']:.1f}秒")


class ExtendedFastBacktester(FastBacktester):
    """拡張要素を含む高速バックテスター"""

    def get_extended_race_data(self, start_date: str, end_date: str) -> List[Dict]:
        """
        拡張データを含むレースデータを一括取得
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # F/Lカウントと追加情報を含むクエリ
        query = """
            SELECT
                r.id as race_id,
                r.venue_code,
                r.race_date,
                r.race_number,
                r.race_grade,
                e.pit_number,
                e.racer_number,
                e.racer_rank,
                e.win_rate,
                e.second_rate,
                e.local_win_rate,
                e.local_second_rate,
                e.motor_number,
                e.motor_second_rate,
                e.boat_second_rate,
                e.f_count,
                e.l_count,
                e.avg_st,
                COALESCE(res.rank, 99) as result_rank
            FROM races r
            INNER JOIN entries e ON r.id = e.race_id
            LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
            WHERE r.race_date BETWEEN ? AND ?
              AND res.rank IS NOT NULL
              AND res.is_invalid = 0
            ORDER BY r.id, e.pit_number
        """

        cursor.execute(query, (start_date, end_date))
        rows = cursor.fetchall()
        conn.close()

        # レースごとにグループ化
        races = defaultdict(list)
        for row in rows:
            races[row['race_id']].append(dict(row))

        return list(races.values())

    def calculate_extended_score(self, entry: Dict, race_entries: List[Dict],
                                  weights: Dict) -> float:
        """
        拡張スコア計算

        基本要素 + 拡張要素（F/L、相対力、グレード補正）
        """
        score = 0.0

        # === 基本要素 ===
        # 1. コーススコア
        course_base = {1: 55, 2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
        pit = entry['pit_number']
        course_score = course_base.get(pit, 10) / 55 * 100
        score += course_score * weights.get('course', 30) / 100

        # 2. 選手スコア
        win_rate = entry.get('win_rate') or 0
        local_win_rate = entry.get('local_win_rate') or 0
        racer_score = (win_rate * 0.6 + local_win_rate * 0.4) * 10
        score += racer_score * weights.get('racer', 30) / 100

        # 3. モータースコア
        motor_rate = entry.get('motor_second_rate') or 30
        motor_score = motor_rate
        score += motor_score * weights.get('motor', 15) / 100

        # 4. 級別スコア
        rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
        rank = entry.get('racer_rank') or 'B1'
        rank_score = rank_scores.get(rank, 40)
        score += rank_score * weights.get('rank', 10) / 100

        # === 拡張要素 ===
        # 5. F/Lペナルティ
        f_count = entry.get('f_count') or 0
        l_count = entry.get('l_count') or 0
        fl_penalty = f_count * (-15) + l_count * (-5)  # F持ちは大きなマイナス
        # 1コースのF持ちはさらにペナルティ
        if pit == 1 and f_count > 0:
            fl_penalty *= 1.5
        score += fl_penalty * weights.get('fl', 10) / 100

        # 6. 相対力（レース内ランク）
        if race_entries:
            # 勝率でレース内順位を計算
            sorted_by_rate = sorted(race_entries,
                                   key=lambda x: (x.get('win_rate') or 0),
                                   reverse=True)
            for idx, e in enumerate(sorted_by_rate):
                if e['pit_number'] == pit:
                    relative_rank = idx + 1
                    break
            else:
                relative_rank = 3

            # 1位=100, 6位=0
            relative_score = (6 - relative_rank) / 5 * 100
            score += relative_score * weights.get('relative', 5) / 100

        # 7. 平均STスコア（新規追加）
        avg_st = entry.get('avg_st')
        if avg_st is not None and avg_st > 0:
            if 0.10 <= avg_st < 0.15:
                st_score = 100  # 最適
            elif 0.15 <= avg_st < 0.18:
                st_score = 80   # 良好
            elif avg_st < 0.10:
                st_score = 70   # 早すぎ（Fリスク）
            elif 0.18 <= avg_st < 0.20:
                st_score = 60   # やや遅い
            else:
                st_score = 40   # 遅い
        else:
            st_score = 50  # データなしは中間

        score += st_score * weights.get('st', 10) / 100

        return score

    def run_extended_backtest(self,
                               start_date: str,
                               end_date: str,
                               weights: Dict = None) -> Dict:
        """
        拡張バックテスト実行
        """
        if weights is None:
            weights = {
                'course': 25,
                'racer': 25,
                'motor': 15,
                'rank': 10,
                'fl': 5,
                'relative': 5,
                'st': 15  # 平均STスコア追加
            }

        print(f"期間: {start_date} ～ {end_date}")
        print(f"重み設定: {weights}")
        print()

        # データ取得
        start = time.time()
        races = self.get_extended_race_data(start_date, end_date)
        load_time = time.time() - start

        total_races = len(races)
        print(f"データ取得: {total_races:,}レース ({load_time:.1f}秒)")

        # 評価
        results = {
            'win_hits': 0,
            'place_hits': 0,
            'exacta_hits': 0,
            'trifecta_hits': 0,
            'trio_hits': 0,
            'total': 0
        }

        venue_stats = defaultdict(lambda: {'win_hits': 0, 'total': 0})

        start = time.time()
        for i, race_entries in enumerate(races, 1):
            if len(race_entries) < 6:
                continue

            # 拡張スコアで予測
            scores = []
            for entry in race_entries:
                score = self.calculate_extended_score(entry, race_entries, weights)
                scores.append((entry['pit_number'], score))

            scores.sort(key=lambda x: -x[1])
            predicted = [s[0] for s in scores]

            # 評価
            eval_result = self.evaluate_predictions(predicted, race_entries)
            if eval_result is None:
                continue

            results['total'] += 1
            if eval_result['win_hit']:
                results['win_hits'] += 1
            if eval_result['place_hit']:
                results['place_hits'] += 1
            if eval_result['exacta_hit']:
                results['exacta_hits'] += 1
            if eval_result['trifecta_hit']:
                results['trifecta_hits'] += 1
            if eval_result['trio_hit']:
                results['trio_hits'] += 1

            venue = race_entries[0]['venue_code']
            venue_stats[venue]['total'] += 1
            if eval_result['win_hit']:
                venue_stats[venue]['win_hits'] += 1

            if i % 1000 == 0:
                print(f"  処理中: {i:,}/{len(races):,}")

        eval_time = time.time() - start
        print(f"評価完了: {eval_time:.1f}秒")

        return {
            'results': results,
            'venue_stats': dict(venue_stats),
            'weights': weights,
            'period': {'start': start_date, 'end': end_date},
            'total_races': total_races,
            'tested_races': results['total'],
            'load_time': load_time,
            'eval_time': eval_time
        }


def compare_weights():
    """重み比較テスト"""
    backtester = FastBacktester()

    # テストする重み設定
    weight_sets = [
        {
            'name': '現行(コース重視)',
            'weights': {'course': 35, 'racer': 35, 'motor': 20, 'rank': 10}
        },
        {
            'name': 'コース最重視',
            'weights': {'course': 50, 'racer': 25, 'motor': 15, 'rank': 10}
        },
        {
            'name': '選手最重視',
            'weights': {'course': 25, 'racer': 50, 'motor': 15, 'rank': 10}
        },
        {
            'name': 'モーター重視',
            'weights': {'course': 30, 'racer': 30, 'motor': 30, 'rank': 10}
        },
        {
            'name': '級別重視',
            'weights': {'course': 30, 'racer': 30, 'motor': 15, 'rank': 25}
        },
    ]

    # 直近半年でテスト
    end_date = '2024-11-20'
    start_date = '2024-05-01'

    print("=" * 80)
    print("重み比較テスト")
    print("=" * 80)
    print(f"期間: {start_date} ～ {end_date}")
    print()

    results = []
    for ws in weight_sets:
        print(f"\n--- {ws['name']} ---")
        result = backtester.run_backtest(start_date, end_date, ws['weights'])
        r = result['results']
        total = r['total']

        if total > 0:
            results.append({
                'name': ws['name'],
                'win_rate': r['win_hits'] / total * 100,
                'place_rate': r['place_hits'] / total * 100,
                'trifecta_rate': r['trifecta_hits'] / total * 100,
                'trio_rate': r['trio_hits'] / total * 100
            })

    # 比較表示
    print("\n" + "=" * 80)
    print("比較結果")
    print("=" * 80)
    print(f"{'設定名':<20} {'単勝':>10} {'複勝':>10} {'3連単':>10} {'3連複':>10}")
    print("-" * 60)

    for r in results:
        print(f"{r['name']:<20} {r['win_rate']:>9.2f}% {r['place_rate']:>9.2f}% "
              f"{r['trifecta_rate']:>9.2f}% {r['trio_rate']:>9.2f}%")


def compare_extended():
    """基本 vs 拡張の比較テスト"""
    print("=" * 80)
    print("基本スコア vs 拡張スコア 比較テスト")
    print("=" * 80)

    end_date = '2024-11-20'
    start_date = '2024-05-01'
    print(f"期間: {start_date} ～ {end_date}")
    print()

    # 基本スコア
    print("--- 基本スコア ---")
    basic_backtester = FastBacktester()
    basic_result = basic_backtester.run_backtest(
        start_date, end_date,
        {'course': 35, 'racer': 35, 'motor': 20, 'rank': 10}
    )

    # 拡張スコア（複数パターン）
    extended_backtester = ExtendedFastBacktester()

    extended_configs = [
        {
            'name': '拡張(F/L重視)',
            'weights': {'course': 30, 'racer': 25, 'motor': 15, 'rank': 10, 'fl': 15, 'relative': 5}
        },
        {
            'name': '拡張(相対力重視)',
            'weights': {'course': 30, 'racer': 25, 'motor': 15, 'rank': 10, 'fl': 5, 'relative': 15}
        },
        {
            'name': '拡張(バランス)',
            'weights': {'course': 30, 'racer': 25, 'motor': 15, 'rank': 10, 'fl': 10, 'relative': 10}
        },
    ]

    results = [{
        'name': '基本スコア',
        'win_rate': basic_result['results']['win_hits'] / basic_result['results']['total'] * 100,
        'place_rate': basic_result['results']['place_hits'] / basic_result['results']['total'] * 100,
        'trifecta_rate': basic_result['results']['trifecta_hits'] / basic_result['results']['total'] * 100,
        'trio_rate': basic_result['results']['trio_hits'] / basic_result['results']['total'] * 100
    }]

    for config in extended_configs:
        print(f"\n--- {config['name']} ---")
        result = extended_backtester.run_extended_backtest(
            start_date, end_date, config['weights']
        )
        r = result['results']
        total = r['total']
        if total > 0:
            results.append({
                'name': config['name'],
                'win_rate': r['win_hits'] / total * 100,
                'place_rate': r['place_hits'] / total * 100,
                'trifecta_rate': r['trifecta_hits'] / total * 100,
                'trio_rate': r['trio_hits'] / total * 100
            })

    # 比較表示
    print("\n" + "=" * 80)
    print("比較結果: 基本 vs 拡張")
    print("=" * 80)
    print(f"{'設定名':<20} {'単勝':>10} {'複勝':>10} {'3連単':>10} {'3連複':>10}")
    print("-" * 60)

    for r in results:
        print(f"{r['name']:<20} {r['win_rate']:>9.2f}% {r['place_rate']:>9.2f}% "
              f"{r['trifecta_rate']:>9.2f}% {r['trio_rate']:>9.2f}%")


def optimize_fl_penalty():
    """F/Lペナルティの細かい調整テスト"""
    print("=" * 80)
    print("F/Lペナルティ最適化テスト")
    print("=" * 80)
    print("※F/Lの影響はグレード・優勝戦・ランク維持状況で変動")
    print()

    end_date = '2024-11-20'
    start_date = '2024-05-01'

    backtester = ExtendedFastBacktester()

    # F/Lペナルティの強度を変えてテスト
    fl_strengths = [
        {'name': 'F/Lなし', 'fl_weight': 0, 'f_mult': 0, 'l_mult': 0},
        {'name': 'F/L弱(5)', 'fl_weight': 5, 'f_mult': -10, 'l_mult': -3},
        {'name': 'F/L中(10)', 'fl_weight': 10, 'f_mult': -15, 'l_mult': -5},
        {'name': 'F/L強(15)', 'fl_weight': 15, 'f_mult': -20, 'l_mult': -7},
        {'name': 'F/L最強(20)', 'fl_weight': 20, 'f_mult': -25, 'l_mult': -10},
    ]

    results = []
    for config in fl_strengths:
        print(f"\n--- {config['name']} ---")

        # 重みを動的に設定
        weights = {
            'course': 30,
            'racer': 25,
            'motor': 15,
            'rank': 10,
            'fl': config['fl_weight'],
            'relative': 10
        }

        result = backtester.run_extended_backtest(start_date, end_date, weights)
        r = result['results']
        total = r['total']

        if total > 0:
            results.append({
                'name': config['name'],
                'win_rate': r['win_hits'] / total * 100,
                'place_rate': r['place_hits'] / total * 100,
                'exacta_rate': r['exacta_hits'] / total * 100,
                'trifecta_rate': r['trifecta_hits'] / total * 100,
                'trio_rate': r['trio_hits'] / total * 100
            })

    # 結果表示
    print("\n" + "=" * 80)
    print("F/Lペナルティ強度別結果")
    print("=" * 80)
    print(f"{'設定':<15} {'単勝':>8} {'複勝':>8} {'2連単':>8} {'3連単':>8} {'3連複':>8}")
    print("-" * 70)

    for r in results:
        print(f"{r['name']:<15} {r['win_rate']:>7.2f}% {r['place_rate']:>7.2f}% "
              f"{r['exacta_rate']:>7.2f}% {r['trifecta_rate']:>7.2f}% {r['trio_rate']:>7.2f}%")


def simulate_trio_trifecta():
    """3連複/3連単の回収率シミュレーション（信頼度フィルター付き）"""
    print("=" * 80)
    print("3連複/3連単 回収率シミュレーション")
    print("=" * 80)
    print("※信頼度の高いレースのみに賭ける戦略")
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    start_date = '2023-11-27'
    end_date = '2024-11-27'

    print(f"期間: {start_date} ～ {end_date}")
    print()

    # レースデータと払戻を取得
    query = """
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            r.race_grade,
            e.pit_number,
            e.racer_number,
            e.racer_rank,
            e.win_rate,
            e.local_win_rate,
            e.motor_second_rate,
            e.f_count,
            e.l_count,
            COALESCE(res.rank, 99) as result_rank
        FROM races r
        INNER JOIN entries e ON r.id = e.race_id
        LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
        WHERE r.race_date BETWEEN ? AND ?
          AND res.rank IS NOT NULL
          AND res.is_invalid = 0
        ORDER BY r.id, e.pit_number
    """
    cursor.execute(query, (start_date, end_date))
    entry_rows = cursor.fetchall()

    # 払戻データを取得
    cursor.execute("""
        SELECT race_id, bet_type, combination, amount
        FROM payouts
        WHERE bet_type IN ('trio', 'trifecta')
    """)
    payout_rows = cursor.fetchall()
    conn.close()

    # 払戻をrace_idでインデックス化
    payouts = {}
    for row in payout_rows:
        race_id = row[0]
        if race_id not in payouts:
            payouts[race_id] = {}
        payouts[race_id][row[1]] = {'combination': row[2], 'amount': row[3]}

    # レースごとにグループ化
    races = defaultdict(list)
    for row in entry_rows:
        races[row['race_id']].append(dict(row))

    print(f"総レース数: {len(races):,}件")
    print(f"払戻データあり: {len(payouts):,}件")
    print()

    # スコア計算
    def calc_score(entry, weights):
        score = 0.0
        pit = entry['pit_number']
        course_base = {1: 55, 2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
        score += course_base.get(pit, 10) / 55 * 100 * weights.get('course', 35) / 100
        win_rate = entry.get('win_rate') or 0
        local_win_rate = entry.get('local_win_rate') or 0
        score += (win_rate * 0.6 + local_win_rate * 0.4) * 10 * weights.get('racer', 35) / 100
        motor_rate = entry.get('motor_second_rate') or 30
        score += motor_rate * weights.get('motor', 20) / 100
        rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
        rank = entry.get('racer_rank') or 'B1'
        score += rank_scores.get(rank, 40) * weights.get('rank', 10) / 100
        return score

    # 信頼度計算（改良版）
    def calc_confidence(race_entries, predicted_top3, scores):
        """
        信頼度を計算（より厳格なフィルター）
        - 1号艇が予測1位かつA1 → 非常に高信頼
        - スコア差が大きい → 高信頼
        - 上位予測の選手が全員A級 → 高信頼
        """
        confidence = 0  # 基準値を0から

        # 1号艇が1位予測
        if predicted_top3[0] == 1:
            confidence += 20

        # 予測上位3名の級別チェック
        top_entries = []
        for pit in predicted_top3:
            for e in race_entries:
                if e['pit_number'] == pit:
                    top_entries.append(e)
                    break

        # A級の数
        a1_count = sum(1 for e in top_entries if e.get('racer_rank') == 'A1')
        a2_count = sum(1 for e in top_entries if e.get('racer_rank') == 'A2')
        confidence += a1_count * 15 + a2_count * 8

        # 1位予測者の勝率（高勝率ほど信頼）
        if top_entries:
            top_win_rate = top_entries[0].get('win_rate') or 0
            if top_win_rate >= 8.0:
                confidence += 20
            elif top_win_rate >= 7.0:
                confidence += 15
            elif top_win_rate >= 6.5:
                confidence += 10
            elif top_win_rate >= 6.0:
                confidence += 5

        # スコア差（1位と4位の差が大きい → 堅いレース）
        if len(scores) >= 4:
            score_gap = scores[0][1] - scores[3][1]
            if score_gap >= 15:
                confidence += 15
            elif score_gap >= 10:
                confidence += 10
            elif score_gap >= 5:
                confidence += 5

        # 1号艇がA1でかつ勝率7以上 → ボーナス
        for e in race_entries:
            if e['pit_number'] == 1:
                if e.get('racer_rank') == 'A1' and (e.get('win_rate') or 0) >= 7.0:
                    confidence += 15
                break

        return confidence

    weights = {'course': 35, 'racer': 35, 'motor': 20, 'rank': 10}

    # 信頼度閾値別にシミュレーション
    print("【戦略1: 信頼度フィルター】")
    thresholds = [0, 50, 70, 80, 90]

    for threshold in thresholds:
        trio_stats = {'bet': 0, 'return': 0, 'hit': 0, 'count': 0}
        trifecta_stats = {'bet': 0, 'return': 0, 'hit': 0, 'count': 0}

        for race_id, race_entries in races.items():
            if len(race_entries) < 6:
                continue
            if race_id not in payouts:
                continue

            # 予測
            scores = [(e['pit_number'], calc_score(e, weights)) for e in race_entries]
            scores.sort(key=lambda x: -x[1])
            predicted = [s[0] for s in scores[:3]]

            # 信頼度チェック（scoresを渡す）
            confidence = calc_confidence(race_entries, predicted, scores)
            if confidence < threshold:
                continue

            # 実際の結果
            actual = sorted(race_entries, key=lambda x: x['result_rank'])[:3]
            actual_pits = [e['pit_number'] for e in actual]

            # 3連複チェック
            if 'trio' in payouts[race_id]:
                trio_stats['count'] += 1
                trio_stats['bet'] += 100

                combo = payouts[race_id]['trio']['combination']
                actual_trio = set(int(x) for x in combo.split('='))

                if set(predicted) == actual_trio:
                    trio_stats['hit'] += 1
                    trio_stats['return'] += payouts[race_id]['trio']['amount']

            # 3連単チェック
            if 'trifecta' in payouts[race_id]:
                trifecta_stats['count'] += 1
                trifecta_stats['bet'] += 100

                combo = payouts[race_id]['trifecta']['combination']
                actual_trifecta = [int(x) for x in combo.split('-')]

                if predicted == actual_trifecta:
                    trifecta_stats['hit'] += 1
                    trifecta_stats['return'] += payouts[race_id]['trifecta']['amount']

        # 結果表示
        print(f"--- 信頼度 >= {threshold} ---")
        if trio_stats['count'] > 0:
            trio_roi = trio_stats['return'] / trio_stats['bet'] * 100
            trio_rate = trio_stats['hit'] / trio_stats['count'] * 100
            print(f"  3連複: {trio_stats['count']:,}レース | "
                  f"的中{trio_stats['hit']:,}({trio_rate:.1f}%) | "
                  f"回収率{trio_roi:.1f}% | "
                  f"収支{trio_stats['return']-trio_stats['bet']:+,}円")

        if trifecta_stats['count'] > 0:
            tri_roi = trifecta_stats['return'] / trifecta_stats['bet'] * 100
            tri_rate = trifecta_stats['hit'] / trifecta_stats['count'] * 100
            print(f"  3連単: {trifecta_stats['count']:,}レース | "
                  f"的中{trifecta_stats['hit']:,}({tri_rate:.1f}%) | "
                  f"回収率{tri_roi:.1f}% | "
                  f"収支{trifecta_stats['return']-trifecta_stats['bet']:+,}円")
        print()

    # 戦略2: 1号艇A1が2,3着予測のレース（中穴狙い）
    print("=" * 60)
    print("【戦略2: 1号艇A1の2着/3着狙い（中穴）】")
    print("※1号艇A1が2位or3位予測のレースに賭ける")
    print()

    trio_stats = {'bet': 0, 'return': 0, 'hit': 0, 'count': 0}
    trifecta_stats = {'bet': 0, 'return': 0, 'hit': 0, 'count': 0}

    for race_id, race_entries in races.items():
        if len(race_entries) < 6 or race_id not in payouts:
            continue

        # 1号艇の情報
        pit1_entry = None
        for e in race_entries:
            if e['pit_number'] == 1:
                pit1_entry = e
                break

        if not pit1_entry or pit1_entry.get('racer_rank') != 'A1':
            continue

        # 予測
        scores = [(e['pit_number'], calc_score(e, weights)) for e in race_entries]
        scores.sort(key=lambda x: -x[1])
        predicted = [s[0] for s in scores[:3]]

        # 1号艇が2位or3位予測の場合のみ
        if predicted[0] == 1:
            continue  # 1号艇が1位予測は除外
        if 1 not in predicted:
            continue  # 1号艇が3位以内予測でない場合は除外

        # 3連複
        if 'trio' in payouts[race_id]:
            trio_stats['count'] += 1
            trio_stats['bet'] += 100
            combo = payouts[race_id]['trio']['combination']
            actual_trio = set(int(x) for x in combo.split('='))
            if set(predicted) == actual_trio:
                trio_stats['hit'] += 1
                trio_stats['return'] += payouts[race_id]['trio']['amount']

        # 3連単
        if 'trifecta' in payouts[race_id]:
            trifecta_stats['count'] += 1
            trifecta_stats['bet'] += 100
            combo = payouts[race_id]['trifecta']['combination']
            actual_trifecta = [int(x) for x in combo.split('-')]
            if predicted == actual_trifecta:
                trifecta_stats['hit'] += 1
                trifecta_stats['return'] += payouts[race_id]['trifecta']['amount']

    if trio_stats['count'] > 0:
        trio_roi = trio_stats['return'] / trio_stats['bet'] * 100
        trio_rate = trio_stats['hit'] / trio_stats['count'] * 100
        print(f"  3連複: {trio_stats['count']:,}レース | "
              f"的中{trio_stats['hit']:,}({trio_rate:.1f}%) | "
              f"回収率{trio_roi:.1f}% | "
              f"収支{trio_stats['return']-trio_stats['bet']:+,}円")

    if trifecta_stats['count'] > 0:
        tri_roi = trifecta_stats['return'] / trifecta_stats['bet'] * 100
        tri_rate = trifecta_stats['hit'] / trifecta_stats['count'] * 100
        print(f"  3連単: {trifecta_stats['count']:,}レース | "
              f"的中{trifecta_stats['hit']:,}({tri_rate:.1f}%) | "
              f"回収率{tri_roi:.1f}% | "
              f"収支{trifecta_stats['return']-trifecta_stats['bet']:+,}円")

    # 戦略3: 本命組み合わせ（1-2-3, 1-2-4など）以外を狙う
    print()
    print("=" * 60)
    print("【戦略3: 外枠A級絡み（4,5,6号艇にA級がいるレース）】")
    print()

    trio_stats = {'bet': 0, 'return': 0, 'hit': 0, 'count': 0}
    trifecta_stats = {'bet': 0, 'return': 0, 'hit': 0, 'count': 0}

    for race_id, race_entries in races.items():
        if len(race_entries) < 6 or race_id not in payouts:
            continue

        # 4,5,6号艇にA1がいるかチェック
        outer_a1 = False
        for e in race_entries:
            if e['pit_number'] >= 4 and e.get('racer_rank') == 'A1':
                outer_a1 = True
                break

        if not outer_a1:
            continue

        # 予測
        scores = [(e['pit_number'], calc_score(e, weights)) for e in race_entries]
        scores.sort(key=lambda x: -x[1])
        predicted = [s[0] for s in scores[:3]]

        # 3連複
        if 'trio' in payouts[race_id]:
            trio_stats['count'] += 1
            trio_stats['bet'] += 100
            combo = payouts[race_id]['trio']['combination']
            actual_trio = set(int(x) for x in combo.split('='))
            if set(predicted) == actual_trio:
                trio_stats['hit'] += 1
                trio_stats['return'] += payouts[race_id]['trio']['amount']

        # 3連単
        if 'trifecta' in payouts[race_id]:
            trifecta_stats['count'] += 1
            trifecta_stats['bet'] += 100
            combo = payouts[race_id]['trifecta']['combination']
            actual_trifecta = [int(x) for x in combo.split('-')]
            if predicted == actual_trifecta:
                trifecta_stats['hit'] += 1
                trifecta_stats['return'] += payouts[race_id]['trifecta']['amount']

    if trio_stats['count'] > 0:
        trio_roi = trio_stats['return'] / trio_stats['bet'] * 100
        trio_rate = trio_stats['hit'] / trio_stats['count'] * 100
        print(f"  3連複: {trio_stats['count']:,}レース | "
              f"的中{trio_stats['hit']:,}({trio_rate:.1f}%) | "
              f"回収率{trio_roi:.1f}% | "
              f"収支{trio_stats['return']-trio_stats['bet']:+,}円")

    if trifecta_stats['count'] > 0:
        tri_roi = trifecta_stats['return'] / trifecta_stats['bet'] * 100
        tri_rate = trifecta_stats['hit'] / trifecta_stats['count'] * 100
        print(f"  3連単: {trifecta_stats['count']:,}レース | "
              f"的中{trifecta_stats['hit']:,}({tri_rate:.1f}%) | "
              f"回収率{tri_roi:.1f}% | "
              f"収支{trifecta_stats['return']-trifecta_stats['bet']:+,}円")

    # 戦略4: 信頼度に応じたフォーメーション買い
    print()
    print("=" * 60)
    print("【戦略4: 信頼度に応じた買い目変更】")
    print("※1着固定可能なら1着固定フォーメーション")
    print("※1-2着固定可能ならその組み合わせ")
    print("※3連複は常に1点（保険）")
    print()

    from itertools import permutations

    # スコア差で信頼度を判定
    def get_betting_strategy(scores):
        """
        スコアの差から買い方を決定
        戻り値: (strategy_name, trifecta_combos)
        """
        if len(scores) < 4:
            return ('skip', [])

        s1, s2, s3, s4 = scores[0][1], scores[1][1], scores[2][1], scores[3][1]
        p1, p2, p3, p4 = scores[0][0], scores[1][0], scores[2][0], scores[3][0]

        gap_1_2 = s1 - s2
        gap_2_3 = s2 - s3
        gap_3_4 = s3 - s4

        # パターン1: 1着が圧倒的（1着固定、2-3着は2-4位で回す）→ 6点
        if gap_1_2 >= 8:
            combos = []
            for second in [p2, p3, p4]:
                for third in [p2, p3, p4]:
                    if second != third:
                        combos.append([p1, second, third])
            return ('1着固定(6点)', combos)

        # パターン2: 1-2着が固い（1-2着固定、3着は3-4位で回す）→ 2点
        if gap_1_2 < 5 and gap_2_3 >= 6:
            combos = [[p1, p2, p3], [p1, p2, p4]]
            return ('1-2着固定(2点)', combos)

        # パターン3: 通常（1点買い）
        combos = [[p1, p2, p3]]
        return ('1点買い', combos)

    strategy_stats = {
        '1着固定(6点)': {'bet': 0, 'return': 0, 'hit': 0, 'count': 0},
        '1-2着固定(2点)': {'bet': 0, 'return': 0, 'hit': 0, 'count': 0},
        '1点買い': {'bet': 0, 'return': 0, 'hit': 0, 'count': 0},
    }
    total_stats = {'bet': 0, 'return': 0, 'hit': 0, 'count': 0}

    for race_id, race_entries in races.items():
        if len(race_entries) < 6 or race_id not in payouts:
            continue
        if 'trifecta' not in payouts[race_id]:
            continue

        # スコア計算
        scores = [(e['pit_number'], calc_score(e, weights)) for e in race_entries]
        scores.sort(key=lambda x: -x[1])

        # 買い方決定
        strategy_name, combos = get_betting_strategy(scores)
        if strategy_name == 'skip' or not combos:
            continue

        # 実際の結果
        combo_str = payouts[race_id]['trifecta']['combination']
        actual = [int(x) for x in combo_str.split('-')]
        payout_amount = payouts[race_id]['trifecta']['amount']

        # 賭け金計算（1点100円）
        bet_amount = len(combos) * 100
        strategy_stats[strategy_name]['bet'] += bet_amount
        strategy_stats[strategy_name]['count'] += 1
        total_stats['bet'] += bet_amount
        total_stats['count'] += 1

        # 的中判定
        hit = False
        for combo in combos:
            if combo == actual:
                hit = True
                strategy_stats[strategy_name]['hit'] += 1
                strategy_stats[strategy_name]['return'] += payout_amount
                total_stats['hit'] += 1
                total_stats['return'] += payout_amount
                break

    # 結果表示
    for name, stats in strategy_stats.items():
        if stats['count'] > 0:
            roi = stats['return'] / stats['bet'] * 100
            rate = stats['hit'] / stats['count'] * 100
            avg_bet = stats['bet'] / stats['count']
            print(f"  {name}: {stats['count']:,}レース | "
                  f"的中{stats['hit']:,}({rate:.1f}%) | "
                  f"回収率{roi:.1f}% | "
                  f"平均賭け{avg_bet:.0f}円")

    if total_stats['count'] > 0:
        print()
        total_roi = total_stats['return'] / total_stats['bet'] * 100
        total_rate = total_stats['hit'] / total_stats['count'] * 100
        print(f"  【合計】 {total_stats['count']:,}レース | "
              f"的中{total_stats['hit']:,}({total_rate:.1f}%) | "
              f"回収率{total_roi:.1f}% | "
              f"収支{total_stats['return']-total_stats['bet']:+,}円")


def simulate_formation_thresholds():
    """フォーメーション買いの閾値最適化シミュレーション"""
    print("=" * 80)
    print("フォーメーション買い閾値最適化シミュレーション")
    print("=" * 80)
    print("※閾値を変えて1着固定の条件を調整")
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    start_date = '2023-11-27'
    end_date = '2024-11-27'

    print(f"期間: {start_date} ～ {end_date}")
    print()

    # データ取得
    query = """
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            e.pit_number,
            e.racer_number,
            e.racer_rank,
            e.win_rate,
            e.local_win_rate,
            e.motor_second_rate,
            COALESCE(res.rank, 99) as result_rank
        FROM races r
        INNER JOIN entries e ON r.id = e.race_id
        LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
        WHERE r.race_date BETWEEN ? AND ?
          AND res.rank IS NOT NULL
          AND res.is_invalid = 0
        ORDER BY r.id, e.pit_number
    """
    cursor.execute(query, (start_date, end_date))
    entry_rows = cursor.fetchall()

    # 払戻データ取得
    cursor.execute("""
        SELECT race_id, bet_type, combination, amount
        FROM payouts
        WHERE bet_type = 'trifecta'
    """)
    payout_rows = cursor.fetchall()
    conn.close()

    # 払戻をインデックス化
    payouts = {}
    for row in payout_rows:
        race_id = row[0]
        payouts[race_id] = {'combination': row[2], 'amount': row[3]}

    # レースごとにグループ化
    races = defaultdict(list)
    for row in entry_rows:
        races[row['race_id']].append(dict(row))

    print(f"総レース数: {len(races):,}件")
    print(f"払戻データあり: {len(payouts):,}件")
    print()

    # スコア計算
    def calc_score(entry):
        score = 0.0
        pit = entry['pit_number']
        course_base = {1: 55, 2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
        score += course_base.get(pit, 10) / 55 * 100 * 0.35
        win_rate = entry.get('win_rate') or 0
        local_win_rate = entry.get('local_win_rate') or 0
        score += (win_rate * 0.6 + local_win_rate * 0.4) * 10 * 0.35
        motor_rate = entry.get('motor_second_rate') or 30
        score += motor_rate * 0.20
        rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
        rank = entry.get('racer_rank') or 'B1'
        score += rank_scores.get(rank, 40) * 0.10
        return score

    # 閾値のパターンをテスト
    threshold_patterns = [
        {'name': '現行(gap>=8)', '1着固定閾値': 8, '12固定閾値': 6},
        {'name': '厳格(gap>=12)', '1着固定閾値': 12, '12固定閾値': 8},
        {'name': '超厳格(gap>=15)', '1着固定閾値': 15, '12固定閾値': 10},
        {'name': '最厳格(gap>=18)', '1着固定閾値': 18, '12固定閾値': 12},
        {'name': '極限(gap>=20)', '1着固定閾値': 20, '12固定閾値': 15},
    ]

    results = []

    for pattern in threshold_patterns:
        first_thresh = pattern['1着固定閾値']
        second_thresh = pattern['12固定閾値']

        stats = {
            '1着固定(6点)': {'bet': 0, 'return': 0, 'hit': 0, 'count': 0},
            '1-2着固定(2点)': {'bet': 0, 'return': 0, 'hit': 0, 'count': 0},
            '1点買い': {'bet': 0, 'return': 0, 'hit': 0, 'count': 0},
        }
        total = {'bet': 0, 'return': 0, 'hit': 0, 'count': 0}

        for race_id, race_entries in races.items():
            if len(race_entries) < 6 or race_id not in payouts:
                continue

            # スコア計算・ソート
            scores = [(e['pit_number'], calc_score(e)) for e in race_entries]
            scores.sort(key=lambda x: -x[1])

            if len(scores) < 4:
                continue

            s1, s2, s3, s4 = scores[0][1], scores[1][1], scores[2][1], scores[3][1]
            p1, p2, p3, p4 = scores[0][0], scores[1][0], scores[2][0], scores[3][0]
            gap_1_2 = s1 - s2
            gap_2_3 = s2 - s3

            # 戦略判定
            if gap_1_2 >= first_thresh:
                strategy = '1着固定(6点)'
                combos = []
                for second in [p2, p3, p4]:
                    for third in [p2, p3, p4]:
                        if second != third:
                            combos.append([p1, second, third])
            elif gap_1_2 < 5 and gap_2_3 >= second_thresh:
                strategy = '1-2着固定(2点)'
                combos = [[p1, p2, p3], [p1, p2, p4]]
            else:
                strategy = '1点買い'
                combos = [[p1, p2, p3]]

            # 実際の結果
            actual = [int(x) for x in payouts[race_id]['combination'].split('-')]
            payout_amount = payouts[race_id]['amount']
            bet_amount = len(combos) * 100

            stats[strategy]['bet'] += bet_amount
            stats[strategy]['count'] += 1
            total['bet'] += bet_amount
            total['count'] += 1

            # 的中判定
            for combo in combos:
                if combo == actual:
                    stats[strategy]['hit'] += 1
                    stats[strategy]['return'] += payout_amount
                    total['hit'] += 1
                    total['return'] += payout_amount
                    break

        # 結果集計
        results.append({
            'name': pattern['name'],
            'stats': stats,
            'total': total
        })

    # 結果表示
    print("=" * 90)
    print("閾値別シミュレーション結果")
    print("=" * 90)
    print()

    for res in results:
        print(f"【{res['name']}】")
        for strat_name, s in res['stats'].items():
            if s['count'] > 0:
                rate = s['hit'] / s['count'] * 100
                roi = s['return'] / s['bet'] * 100
                print(f"  {strat_name}: {s['count']:,}レース | 的中{s['hit']:,}({rate:.1f}%) | 回収率{roi:.1f}%")

        t = res['total']
        if t['count'] > 0:
            total_rate = t['hit'] / t['count'] * 100
            total_roi = t['return'] / t['bet'] * 100
            profit = t['return'] - t['bet']
            print(f"  合計: {t['count']:,}レース | 的中{t['hit']:,}({total_rate:.1f}%) | 回収率{total_roi:.1f}% | 収支{profit:+,}円")
        print()

    # 比較表
    print("=" * 90)
    print("比較サマリー")
    print("=" * 90)
    print(f"{'閾値設定':<20} {'総レース':>10} {'6点買い率':>12} {'的中率':>10} {'回収率':>10} {'収支':>15}")
    print("-" * 85)

    for res in results:
        t = res['total']
        six_count = res['stats']['1着固定(6点)']['count']
        six_ratio = six_count / t['count'] * 100 if t['count'] > 0 else 0
        rate = t['hit'] / t['count'] * 100 if t['count'] > 0 else 0
        roi = t['return'] / t['bet'] * 100 if t['bet'] > 0 else 0
        profit = t['return'] - t['bet']
        print(f"{res['name']:<20} {t['count']:>10,} {six_ratio:>10.1f}% {rate:>9.1f}% {roi:>9.1f}% {profit:>+14,}円")

    # 追加分析: 1号艇A1条件付きフォーメーション
    print()
    print("=" * 90)
    print("追加分析: 1号艇A1の場合のみフォーメーション買い")
    print("=" * 90)
    print("※1号艇がA1の場合のみ6点買い、それ以外は1点買い")
    print()

    stats = {
        '1号艇A1で6点': {'bet': 0, 'return': 0, 'hit': 0, 'count': 0},
        '通常1点': {'bet': 0, 'return': 0, 'hit': 0, 'count': 0},
    }
    total = {'bet': 0, 'return': 0, 'hit': 0, 'count': 0}

    for race_id, race_entries in races.items():
        if len(race_entries) < 6 or race_id not in payouts:
            continue

        # スコア計算・ソート
        scores = [(e['pit_number'], calc_score(e)) for e in race_entries]
        scores.sort(key=lambda x: -x[1])

        if len(scores) < 4:
            continue

        p1, p2, p3, p4 = scores[0][0], scores[1][0], scores[2][0], scores[3][0]

        # 1号艇がA1かチェック
        pit1_a1 = False
        for e in race_entries:
            if e['pit_number'] == 1 and e.get('racer_rank') == 'A1':
                pit1_a1 = True
                break

        # 予測1位が1号艇かつA1の場合のみフォーメーション
        if p1 == 1 and pit1_a1:
            strategy = '1号艇A1で6点'
            combos = []
            for second in [p2, p3, p4]:
                for third in [p2, p3, p4]:
                    if second != third:
                        combos.append([p1, second, third])
        else:
            strategy = '通常1点'
            combos = [[p1, p2, p3]]

        # 実際の結果
        actual = [int(x) for x in payouts[race_id]['combination'].split('-')]
        payout_amount = payouts[race_id]['amount']
        bet_amount = len(combos) * 100

        stats[strategy]['bet'] += bet_amount
        stats[strategy]['count'] += 1
        total['bet'] += bet_amount
        total['count'] += 1

        # 的中判定
        for combo in combos:
            if combo == actual:
                stats[strategy]['hit'] += 1
                stats[strategy]['return'] += payout_amount
                total['hit'] += 1
                total['return'] += payout_amount
                break

    for name, s in stats.items():
        if s['count'] > 0:
            rate = s['hit'] / s['count'] * 100
            roi = s['return'] / s['bet'] * 100
            profit = s['return'] - s['bet']
            print(f"  {name}: {s['count']:,}レース | 的中{s['hit']:,}({rate:.1f}%) | 回収率{roi:.1f}% | 収支{profit:+,}円")

    if total['count'] > 0:
        total_rate = total['hit'] / total['count'] * 100
        total_roi = total['return'] / total['bet'] * 100
        profit = total['return'] - total['bet']
        print(f"\n  【合計】 {total['count']:,}レース | 的中{total['hit']:,}({total_rate:.1f}%) | 回収率{total_roi:.1f}% | 収支{profit:+,}円")

    # 1号艇A1 + 勝率条件付き
    print()
    print("=" * 90)
    print("追加分析: 1号艇A1 + 勝率7.0以上の場合のみフォーメーション")
    print("=" * 90)

    stats2 = {
        '1号艇A1高勝率で6点': {'bet': 0, 'return': 0, 'hit': 0, 'count': 0},
        '通常1点': {'bet': 0, 'return': 0, 'hit': 0, 'count': 0},
    }
    total2 = {'bet': 0, 'return': 0, 'hit': 0, 'count': 0}

    for race_id, race_entries in races.items():
        if len(race_entries) < 6 or race_id not in payouts:
            continue

        scores = [(e['pit_number'], calc_score(e)) for e in race_entries]
        scores.sort(key=lambda x: -x[1])

        if len(scores) < 4:
            continue

        p1, p2, p3, p4 = scores[0][0], scores[1][0], scores[2][0], scores[3][0]

        # 1号艇がA1かつ勝率7.0以上かチェック
        pit1_condition = False
        for e in race_entries:
            if e['pit_number'] == 1 and e.get('racer_rank') == 'A1':
                if (e.get('win_rate') or 0) >= 7.0:
                    pit1_condition = True
                break

        if p1 == 1 and pit1_condition:
            strategy = '1号艇A1高勝率で6点'
            combos = []
            for second in [p2, p3, p4]:
                for third in [p2, p3, p4]:
                    if second != third:
                        combos.append([p1, second, third])
        else:
            strategy = '通常1点'
            combos = [[p1, p2, p3]]

        actual = [int(x) for x in payouts[race_id]['combination'].split('-')]
        payout_amount = payouts[race_id]['amount']
        bet_amount = len(combos) * 100

        stats2[strategy]['bet'] += bet_amount
        stats2[strategy]['count'] += 1
        total2['bet'] += bet_amount
        total2['count'] += 1

        for combo in combos:
            if combo == actual:
                stats2[strategy]['hit'] += 1
                stats2[strategy]['return'] += payout_amount
                total2['hit'] += 1
                total2['return'] += payout_amount
                break

    for name, s in stats2.items():
        if s['count'] > 0:
            rate = s['hit'] / s['count'] * 100
            roi = s['return'] / s['bet'] * 100
            profit = s['return'] - s['bet']
            print(f"  {name}: {s['count']:,}レース | 的中{s['hit']:,}({rate:.1f}%) | 回収率{roi:.1f}% | 収支{profit:+,}円")

    if total2['count'] > 0:
        total_rate = total2['hit'] / total2['count'] * 100
        total_roi = total2['return'] / total2['bet'] * 100
        profit = total2['return'] - total2['bet']
        print(f"\n  【合計】 {total2['count']:,}レース | 的中{total2['hit']:,}({total_rate:.1f}%) | 回収率{total_roi:.1f}% | 収支{profit:+,}円")


def simulate_default_betting():
    """
    デフォルト買い目シミュレーション
    基本: 3連単4点 + 3連複1点
    レースによっては3連単を最大10点まで許容
    """
    print("=" * 80)
    print("デフォルト買い目シミュレーション")
    print("=" * 80)
    print("基本買い目: 3連単4点 + 3連複1点")
    print("※レースによっては3連単を最大10点まで許容")
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    start_date = '2023-11-27'
    end_date = '2024-11-27'

    print(f"期間: {start_date} ～ {end_date}")
    print()

    # データ取得
    query = """
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            e.pit_number,
            e.racer_rank,
            e.win_rate,
            e.local_win_rate,
            e.motor_second_rate,
            COALESCE(res.rank, 99) as result_rank
        FROM races r
        INNER JOIN entries e ON r.id = e.race_id
        LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
        WHERE r.race_date BETWEEN ? AND ?
          AND res.rank IS NOT NULL
          AND res.is_invalid = 0
        ORDER BY r.id, e.pit_number
    """
    cursor.execute(query, (start_date, end_date))
    entry_rows = cursor.fetchall()

    # 払戻データ取得
    cursor.execute("""
        SELECT race_id, bet_type, combination, amount
        FROM payouts
        WHERE bet_type IN ('trio', 'trifecta')
    """)
    payout_rows = cursor.fetchall()
    conn.close()

    # 払戻をインデックス化
    payouts = {}
    for row in payout_rows:
        race_id = row[0]
        if race_id not in payouts:
            payouts[race_id] = {}
        payouts[race_id][row[1]] = {'combination': row[2], 'amount': row[3]}

    # レースごとにグループ化
    races = defaultdict(list)
    for row in entry_rows:
        races[row['race_id']].append(dict(row))

    print(f"総レース数: {len(races):,}件")
    print(f"払戻データあり: {len(payouts):,}件")
    print()

    # スコア計算
    def calc_score(entry):
        score = 0.0
        pit = entry['pit_number']
        course_base = {1: 55, 2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
        score += course_base.get(pit, 10) / 55 * 100 * 0.35
        win_rate = entry.get('win_rate') or 0
        local_win_rate = entry.get('local_win_rate') or 0
        score += (win_rate * 0.6 + local_win_rate * 0.4) * 10 * 0.35
        motor_rate = entry.get('motor_second_rate') or 30
        score += motor_rate * 0.20
        rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
        rank = entry.get('racer_rank') or 'B1'
        score += rank_scores.get(rank, 40) * 0.10
        return score

    def get_trifecta_combos(scores, max_points=4):
        """
        3連単買い目を生成
        max_points: 最大買い目数（4, 6, 10など）
        """
        if len(scores) < 4:
            return []

        p1, p2, p3, p4 = scores[0][0], scores[1][0], scores[2][0], scores[3][0]
        s1, s2, s3, s4 = scores[0][1], scores[1][1], scores[2][1], scores[3][1]

        gap_1_2 = s1 - s2
        gap_2_3 = s2 - s3

        combos = []

        if max_points == 4:
            # 基本4点: 1着固定、2-3着を2-4位で2パターンずつ
            # 1-2-3, 1-2-4, 1-3-2, 1-3-4
            combos = [
                [p1, p2, p3],
                [p1, p2, p4],
                [p1, p3, p2],
                [p1, p3, p4],
            ]
        elif max_points == 6:
            # 6点: 1着固定、2-3着を2-4位で全展開
            for second in [p2, p3, p4]:
                for third in [p2, p3, p4]:
                    if second != third:
                        combos.append([p1, second, third])
        elif max_points == 10:
            # 10点: 1-2着を1-2位で固定 + 1着固定で2-3着を2-5位で展開
            p5 = scores[4][0] if len(scores) > 4 else p4
            # 1-2着固定パターン（4点）
            combos = [
                [p1, p2, p3],
                [p1, p2, p4],
                [p1, p2, p5],
                [p2, p1, p3],
                [p2, p1, p4],
                [p2, p1, p5],
            ]
            # 1着固定で3着候補を広げる（追加4点）
            for third in [p3, p4]:
                if [p1, p3, third] not in combos and p3 != third:
                    combos.append([p1, p3, third])
                if [p1, p4, third] not in combos and p4 != third:
                    combos.append([p1, p4, third])
            combos = combos[:10]  # 10点まで

        return combos

    def determine_betting_pattern(scores, race_entries):
        """
        レース状況から買い目パターンを決定
        戻り値: (パターン名, 3連単買い目数)
        """
        if len(scores) < 4:
            return ('skip', 0)

        s1, s2, s3, s4 = scores[0][1], scores[1][1], scores[2][1], scores[3][1]
        p1 = scores[0][0]

        gap_1_2 = s1 - s2
        gap_2_3 = s2 - s3
        gap_1_4 = s1 - s4

        # 1号艇A1かつ予測1位なら堅いレース
        pit1_a1 = False
        for e in race_entries:
            if e['pit_number'] == 1 and e.get('racer_rank') == 'A1':
                pit1_a1 = True
                break

        # パターン判定
        # 1. 1着が圧倒的に強い（gap>=15）→ 6点
        if gap_1_2 >= 15:
            return ('1着圧倒(6点)', 6)

        # 2. 混戦（gap_1_4 < 10）→ 10点
        if gap_1_4 < 10:
            return ('混戦(10点)', 10)

        # 3. 通常 → 4点
        return ('通常(4点)', 4)

    # 戦略別シミュレーション
    strategies = [
        {'name': '固定4点', 'trifecta_points': 4, 'dynamic': False},
        {'name': '固定6点', 'trifecta_points': 6, 'dynamic': False},
        {'name': '動的(4-10点)', 'trifecta_points': 0, 'dynamic': True},
    ]

    for strategy in strategies:
        print(f"=" * 60)
        print(f"【{strategy['name']}】3連単 + 3連複1点")
        print(f"=" * 60)

        trifecta_stats = {'bet': 0, 'return': 0, 'hit': 0, 'count': 0}
        trio_stats = {'bet': 0, 'return': 0, 'hit': 0, 'count': 0}
        total_stats = {'bet': 0, 'return': 0, 'hit': 0, 'count': 0}

        pattern_counts = defaultdict(int)

        for race_id, race_entries in races.items():
            if len(race_entries) < 6 or race_id not in payouts:
                continue

            # スコア計算
            scores = [(e['pit_number'], calc_score(e)) for e in race_entries]
            scores.sort(key=lambda x: -x[1])

            # 買い目数決定
            if strategy['dynamic']:
                pattern_name, trifecta_points = determine_betting_pattern(scores, race_entries)
                if pattern_name == 'skip':
                    continue
                pattern_counts[pattern_name] += 1
            else:
                trifecta_points = strategy['trifecta_points']

            # 3連単買い目生成
            trifecta_combos = get_trifecta_combos(scores, trifecta_points)

            # 3連複買い目（1点）
            trio_combo = set([scores[0][0], scores[1][0], scores[2][0]])

            # 3連単の結果
            if 'trifecta' in payouts[race_id]:
                actual_str = payouts[race_id]['trifecta']['combination']
                actual = [int(x) for x in actual_str.split('-')]
                payout = payouts[race_id]['trifecta']['amount']

                bet = len(trifecta_combos) * 100
                trifecta_stats['bet'] += bet
                trifecta_stats['count'] += 1
                total_stats['bet'] += bet

                for combo in trifecta_combos:
                    if combo == actual:
                        trifecta_stats['hit'] += 1
                        trifecta_stats['return'] += payout
                        total_stats['return'] += payout
                        break

            # 3連複の結果
            if 'trio' in payouts[race_id]:
                actual_str = payouts[race_id]['trio']['combination']
                actual_trio = set(int(x) for x in actual_str.split('='))
                payout = payouts[race_id]['trio']['amount']

                trio_stats['bet'] += 100
                trio_stats['count'] += 1
                total_stats['bet'] += 100

                if trio_combo == actual_trio:
                    trio_stats['hit'] += 1
                    trio_stats['return'] += payout
                    total_stats['return'] += payout

            total_stats['count'] += 1

        # 結果表示
        if trifecta_stats['count'] > 0:
            tri_rate = trifecta_stats['hit'] / trifecta_stats['count'] * 100
            tri_roi = trifecta_stats['return'] / trifecta_stats['bet'] * 100
            avg_bet = trifecta_stats['bet'] / trifecta_stats['count']
            print(f"  3連単: {trifecta_stats['count']:,}レース | "
                  f"的中{trifecta_stats['hit']:,}({tri_rate:.1f}%) | "
                  f"回収率{tri_roi:.1f}% | "
                  f"平均賭け{avg_bet:.0f}円")

        if trio_stats['count'] > 0:
            trio_rate = trio_stats['hit'] / trio_stats['count'] * 100
            trio_roi = trio_stats['return'] / trio_stats['bet'] * 100
            print(f"  3連複: {trio_stats['count']:,}レース | "
                  f"的中{trio_stats['hit']:,}({trio_rate:.1f}%) | "
                  f"回収率{trio_roi:.1f}%")

        if total_stats['count'] > 0:
            total_roi = total_stats['return'] / total_stats['bet'] * 100
            profit = total_stats['return'] - total_stats['bet']
            avg_total_bet = total_stats['bet'] / total_stats['count']
            print(f"\n  【合計】回収率{total_roi:.1f}% | "
                  f"収支{profit:+,}円 | "
                  f"平均賭け{avg_total_bet:.0f}円/レース")

        if strategy['dynamic'] and pattern_counts:
            print(f"\n  パターン内訳:")
            for pattern, count in sorted(pattern_counts.items()):
                print(f"    {pattern}: {count:,}レース")

        print()


def simulate_expected_value():
    """
    期待値ベース（Bパターン）シミュレーション
    予測確率とオッズを比較して、期待値プラスの買い目のみ購入
    """
    print("=" * 80)
    print("期待値ベース（Bパターン）シミュレーション")
    print("=" * 80)
    print("※予測確率×オッズ > 1.0 の買い目のみ購入")
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    start_date = '2023-11-27'
    end_date = '2024-11-27'

    print(f"期間: {start_date} ～ {end_date}")
    print()

    # レースデータ取得
    query = """
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            e.pit_number,
            e.racer_rank,
            e.win_rate,
            e.local_win_rate,
            e.motor_second_rate,
            COALESCE(res.rank, 99) as result_rank
        FROM races r
        INNER JOIN entries e ON r.id = e.race_id
        LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
        WHERE r.race_date BETWEEN ? AND ?
          AND res.rank IS NOT NULL
          AND res.is_invalid = 0
        ORDER BY r.id, e.pit_number
    """
    cursor.execute(query, (start_date, end_date))
    entry_rows = cursor.fetchall()

    # 払戻データ取得（オッズの代わりに使用）
    cursor.execute("""
        SELECT race_id, bet_type, combination, amount
        FROM payouts
        WHERE bet_type IN ('trio', 'trifecta')
    """)
    payout_rows = cursor.fetchall()
    conn.close()

    # 払戻をインデックス化
    payouts = {}
    for row in payout_rows:
        race_id = row[0]
        if race_id not in payouts:
            payouts[race_id] = {}
        payouts[race_id][row[1]] = {'combination': row[2], 'amount': row[3]}

    # レースごとにグループ化
    races = defaultdict(list)
    for row in entry_rows:
        races[row['race_id']].append(dict(row))

    print(f"総レース数: {len(races):,}件")
    print(f"払戻データあり: {len(payouts):,}件")
    print()

    # スコア計算
    def calc_score(entry):
        score = 0.0
        pit = entry['pit_number']
        course_base = {1: 55, 2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
        score += course_base.get(pit, 10) / 55 * 100 * 0.35
        win_rate = entry.get('win_rate') or 0
        local_win_rate = entry.get('local_win_rate') or 0
        score += (win_rate * 0.6 + local_win_rate * 0.4) * 10 * 0.35
        motor_rate = entry.get('motor_second_rate') or 30
        score += motor_rate * 0.20
        rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
        rank = entry.get('racer_rank') or 'B1'
        score += rank_scores.get(rank, 40) * 0.10
        return score

    def estimate_probability(scores, combo_type='trifecta'):
        """
        スコアから確率を推定
        combo_type: 'trifecta' or 'trio'
        """
        if len(scores) < 3:
            return {}

        # スコアを正規化して確率に変換
        total_score = sum(s[1] for s in scores)
        if total_score <= 0:
            return {}

        # 1着確率
        first_probs = {s[0]: s[1] / total_score for s in scores}

        # 簡易的な3連単確率計算
        probs = {}
        for i, (p1, s1) in enumerate(scores):
            for j, (p2, s2) in enumerate(scores):
                if i == j:
                    continue
                for k, (p3, s3) in enumerate(scores):
                    if i == k or j == k:
                        continue

                    # 独立と仮定した簡易計算
                    remaining1 = total_score - s1
                    remaining2 = total_score - s1 - s2

                    if remaining1 <= 0 or remaining2 <= 0:
                        continue

                    prob = (s1 / total_score) * (s2 / remaining1) * (s3 / remaining2)
                    key = f"{p1}-{p2}-{p3}"
                    probs[key] = prob

        return probs

    # 予測確率の閾値でフィルター
    print("【予測確率閾値フィルター別結果】")
    print("※予測確率が閾値以上の買い目のみ購入")
    print()

    prob_thresholds = [0.03, 0.05, 0.08, 0.10, 0.15]

    for prob_threshold in prob_thresholds:
        trifecta_stats = {'bet': 0, 'return': 0, 'hit': 0, 'count': 0, 'bet_count': 0}

        for race_id, race_entries in races.items():
            if len(race_entries) < 6 or race_id not in payouts:
                continue
            if 'trifecta' not in payouts[race_id]:
                continue

            # スコア計算
            scores = [(e['pit_number'], calc_score(e)) for e in race_entries]
            scores.sort(key=lambda x: -x[1])

            # 確率推定
            probs = estimate_probability(scores)

            trifecta_stats['count'] += 1

            actual_str = payouts[race_id]['trifecta']['combination']
            actual_payout = payouts[race_id]['trifecta']['amount']

            # 確率が閾値以上の買い目のみ購入
            for combo_str, prob in probs.items():
                if prob >= prob_threshold:
                    trifecta_stats['bet'] += 100
                    trifecta_stats['bet_count'] += 1

                    if combo_str == actual_str:
                        trifecta_stats['hit'] += 1
                        trifecta_stats['return'] += actual_payout

        # 結果表示
        print(f"--- 確率 >= {prob_threshold*100:.0f}% ---")
        if trifecta_stats['bet'] > 0:
            avg_bets = trifecta_stats['bet_count'] / trifecta_stats['count']
            tri_rate = trifecta_stats['hit'] / trifecta_stats['count'] * 100
            tri_roi = trifecta_stats['return'] / trifecta_stats['bet'] * 100
            print(f"  3連単: {trifecta_stats['count']:,}レース | "
                  f"平均{avg_bets:.1f}点/レース | "
                  f"的中{trifecta_stats['hit']:,}({tri_rate:.1f}%) | "
                  f"回収率{tri_roi:.1f}% | "
                  f"収支{trifecta_stats['return']-trifecta_stats['bet']:+,}円")
        else:
            print(f"  3連単: 購入対象なし")

    # 通常買いとの比較
    print()
    print("=" * 60)
    print("【比較: 通常4点買い vs 期待値フィルター】")
    print("=" * 60)

    # 通常4点買い
    normal_stats = {'bet': 0, 'return': 0, 'hit': 0, 'count': 0}

    for race_id, race_entries in races.items():
        if len(race_entries) < 6 or race_id not in payouts:
            continue
        if 'trifecta' not in payouts[race_id]:
            continue

        scores = [(e['pit_number'], calc_score(e)) for e in race_entries]
        scores.sort(key=lambda x: -x[1])

        if len(scores) < 4:
            continue

        p1, p2, p3, p4 = scores[0][0], scores[1][0], scores[2][0], scores[3][0]
        combos = [
            f"{p1}-{p2}-{p3}",
            f"{p1}-{p2}-{p4}",
            f"{p1}-{p3}-{p2}",
            f"{p1}-{p3}-{p4}",
        ]

        actual = payouts[race_id]['trifecta']['combination']
        payout = payouts[race_id]['trifecta']['amount']

        normal_stats['bet'] += 400
        normal_stats['count'] += 1

        if actual in combos:
            normal_stats['hit'] += 1
            normal_stats['return'] += payout

    if normal_stats['count'] > 0:
        rate = normal_stats['hit'] / normal_stats['count'] * 100
        roi = normal_stats['return'] / normal_stats['bet'] * 100
        profit = normal_stats['return'] - normal_stats['bet']
        print(f"通常4点買い: {normal_stats['count']:,}レース | "
              f"的中{normal_stats['hit']:,}({rate:.1f}%) | "
              f"回収率{roi:.1f}% | "
              f"収支{profit:+,}円")


def simulate_roi():
    """回収率シミュレーション"""
    print("=" * 80)
    print("回収率シミュレーション（単勝）")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 単勝払戻データのあるレースを取得
    start_date = '2023-11-27'
    end_date = '2024-11-27'

    print(f"期間: {start_date} ～ {end_date}")
    print()

    # レースデータと払戻を結合して取得
    query = """
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            e.pit_number,
            e.racer_number,
            e.racer_rank,
            e.win_rate,
            e.local_win_rate,
            e.motor_second_rate,
            e.f_count,
            e.l_count,
            COALESCE(res.rank, 99) as result_rank,
            p.combination as win_pit,
            p.amount as win_payout
        FROM races r
        INNER JOIN entries e ON r.id = e.race_id
        LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
        LEFT JOIN payouts p ON r.id = p.race_id AND p.bet_type = 'win'
        WHERE r.race_date BETWEEN ? AND ?
          AND res.rank IS NOT NULL
          AND res.is_invalid = 0
          AND p.amount IS NOT NULL
        ORDER BY r.id, e.pit_number
    """

    cursor.execute(query, (start_date, end_date))
    rows = cursor.fetchall()
    conn.close()

    # レースごとにグループ化
    races = defaultdict(list)
    for row in rows:
        races[row['race_id']].append(dict(row))

    print(f"払戻データのあるレース: {len(races):,}件")
    print()

    # スコア計算関数（シンプル版）
    def calc_score(entry, weights):
        score = 0.0
        pit = entry['pit_number']

        # コース
        course_base = {1: 55, 2: 18, 3: 12, 4: 10, 5: 6, 6: 5}
        course_score = course_base.get(pit, 10) / 55 * 100
        score += course_score * weights.get('course', 35) / 100

        # 選手
        win_rate = entry.get('win_rate') or 0
        local_win_rate = entry.get('local_win_rate') or 0
        racer_score = (win_rate * 0.6 + local_win_rate * 0.4) * 10
        score += racer_score * weights.get('racer', 35) / 100

        # モーター
        motor_rate = entry.get('motor_second_rate') or 30
        score += motor_rate * weights.get('motor', 20) / 100

        # 級別
        rank_scores = {'A1': 100, 'A2': 70, 'B1': 40, 'B2': 10}
        rank = entry.get('racer_rank') or 'B1'
        score += rank_scores.get(rank, 40) * weights.get('rank', 10) / 100

        return score

    # シミュレーション設定
    configs = [
        {'name': '基本', 'weights': {'course': 35, 'racer': 35, 'motor': 20, 'rank': 10}},
        {'name': 'コース重視', 'weights': {'course': 50, 'racer': 25, 'motor': 15, 'rank': 10}},
    ]

    results = []

    for config in configs:
        weights = config['weights']
        total_bet = 0
        total_return = 0
        win_count = 0
        race_count = 0

        for race_entries in races.values():
            if len(race_entries) < 6:
                continue

            # 1着払戻情報を取得
            win_pit = race_entries[0].get('win_pit')
            win_payout = race_entries[0].get('win_payout')

            if not win_pit or not win_payout:
                continue

            try:
                actual_winner = int(win_pit)
            except:
                continue

            # 予測
            scores = [(e['pit_number'], calc_score(e, weights)) for e in race_entries]
            scores.sort(key=lambda x: -x[1])
            predicted_winner = scores[0][0]

            # 賭け（100円）
            total_bet += 100
            race_count += 1

            if predicted_winner == actual_winner:
                total_return += win_payout  # 払戻金
                win_count += 1

        roi = total_return / total_bet * 100 if total_bet > 0 else 0
        win_rate = win_count / race_count * 100 if race_count > 0 else 0

        results.append({
            'name': config['name'],
            'races': race_count,
            'win_count': win_count,
            'win_rate': win_rate,
            'total_bet': total_bet,
            'total_return': total_return,
            'profit': total_return - total_bet,
            'roi': roi
        })

        print(f"--- {config['name']} ---")
        print(f"  レース数: {race_count:,}")
        print(f"  的中: {win_count:,} ({win_rate:.2f}%)")
        print(f"  投資: {total_bet:,}円")
        print(f"  払戻: {total_return:,}円")
        print(f"  収支: {total_return - total_bet:+,}円")
        print(f"  回収率: {roi:.1f}%")
        print()

    # 比較表
    print("=" * 80)
    print("回収率シミュレーション結果")
    print("=" * 80)
    print(f"{'設定':<15} {'的中率':>10} {'回収率':>10} {'収支':>15}")
    print("-" * 55)

    for r in results:
        print(f"{r['name']:<15} {r['win_rate']:>9.2f}% {r['roi']:>9.1f}% {r['profit']:>+14,}円")


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='高速バックテスト')
    parser.add_argument('--start', default='2023-11-27', help='開始日')
    parser.add_argument('--end', default='2024-11-27', help='終了日')
    parser.add_argument('--compare', action='store_true', help='重み比較モード')
    parser.add_argument('--extended', action='store_true', help='拡張要素比較モード')
    parser.add_argument('--optimize-fl', action='store_true', help='F/Lペナルティ最適化')
    parser.add_argument('--roi', action='store_true', help='回収率シミュレーション（単勝）')
    parser.add_argument('--trio', action='store_true', help='3連複/3連単シミュレーション')
    parser.add_argument('--formation', action='store_true', help='フォーメーション閾値最適化')
    parser.add_argument('--default', action='store_true', help='デフォルト買い目シミュレーション')
    parser.add_argument('--ev', action='store_true', help='期待値ベースシミュレーション')
    parser.add_argument('--sample', type=float, default=1.0, help='サンプリング率')

    args = parser.parse_args()

    if args.ev:
        simulate_expected_value()
    elif args.default:
        simulate_default_betting()
    elif args.formation:
        simulate_formation_thresholds()
    elif args.compare:
        compare_weights()
    elif args.extended:
        compare_extended()
    elif args.optimize_fl:
        optimize_fl_penalty()
    elif args.roi:
        simulate_roi()
    elif args.trio:
        simulate_trio_trifecta()
    else:
        backtester = FastBacktester()
        result = backtester.run_backtest(args.start, args.end, sample_rate=args.sample)
        backtester.print_results(result)


if __name__ == "__main__":
    main()
