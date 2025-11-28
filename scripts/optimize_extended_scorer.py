#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ExtendedScorerをBatchDataLoader対応に最適化

各メソッドでキャッシュが利用可能な場合はキャッシュから取得、
なければDB直接アクセスという後方互換性のある設計に変更
"""
import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def modify_extended_scorer():
    """ExtendedScorerを修正"""
    filepath = 'src/analysis/extended_scorer.py'

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. __init__にbatch_loaderパラメータを追加
    content = content.replace(
        '    def __init__(self, db_path: str = None):\n        self.db_path = db_path or DATABASE_PATH',
        '''    def __init__(self, db_path: str = None, batch_loader=None):
        """
        初期化

        Args:
            db_path: データベースパス
            batch_loader: BatchDataLoaderインスタンス（キャッシュ使用時）
        """
        self.db_path = db_path or DATABASE_PATH
        self.batch_loader = batch_loader'''
    )

    # 2. calculate_session_performanceをキャッシュ対応に
    old_session = '''    def calculate_session_performance(
        self,
        racer_number: str,
        venue_code: str,
        target_date: str,
        max_score: float = 5.0
    ) -> Dict:
        """
        節間成績スコアを計算

        同一会場での直近成績（同じ開催期間内）を評価

        Args:
            racer_number: 選手番号
            venue_code: 会場コード
            target_date: 対象日付（YYYY-MM-DD）
            max_score: 最大スコア

        Returns:
            {'score': float, 'races': int, 'avg_rank': float, 'trend': str}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 同一会場で直近7日以内（≒同一開催）のレース
            cursor.execute('''
                SELECT res.rank, r.race_date, r.race_number
                FROM entries e
                JOIN races r ON e.race_id = r.id
                LEFT JOIN results res ON res.race_id = r.id AND res.pit_number = e.pit_number
                WHERE e.racer_number = ?
                  AND r.venue_code = ?
                  AND r.race_date < ?
                  AND r.race_date >= date(?, '-7 days')
                  AND res.rank IS NOT NULL
                  AND res.rank NOT IN ('F', 'L', '欠', '失')
                ORDER BY r.race_date DESC, r.race_number DESC
                LIMIT 12
            ''', (racer_number, venue_code, target_date, target_date))

            results = cursor.fetchall()

            if not results:
                return {
                    'score': max_score * 0.5,  # データなしは中間
                    'races': 0,
                    'avg_rank': None,
                    'trend': 'unknown',
                    'description': '節間データなし'
                }

            # 着順を数値化
            ranks = []
            for row in results:
                try:
                    rank = int(row[0])
                    if 1 <= rank <= 6:
                        ranks.append(rank)
                except (ValueError, TypeError):
                    pass

            if not ranks:
                return {
                    'score': max_score * 0.5,
                    'races': len(results),
                    'avg_rank': None,
                    'trend': 'unknown',
                    'description': '有効データなし'
                }

            avg_rank = sum(ranks) / len(ranks)

            # スコア計算（平均着順が低いほど高スコア）
            # 1着=max_score, 6着=0
            score = max(0, (6 - avg_rank) / 5 * max_score)

            # トレンド判定（前半vs後半）
            if len(ranks) >= 4:
                first_half = sum(ranks[:len(ranks)//2]) / (len(ranks)//2)
                second_half = sum(ranks[len(ranks)//2:]) / (len(ranks) - len(ranks)//2)
                if second_half < first_half - 0.5:
                    trend = 'improving'
                elif second_half > first_half + 0.5:
                    trend = 'declining'
                else:
                    trend = 'stable'
            else:
                trend = 'insufficient'

            return {
                'score': score,
                'races': len(ranks),
                'avg_rank': round(avg_rank, 2),
                'trend': trend,
                'description': f'節間{len(ranks)}走 平均{avg_rank:.1f}着'
            }

        finally:
            conn.close()'''

    new_session = '''    def calculate_session_performance(
        self,
        racer_number: str,
        venue_code: str,
        target_date: str,
        max_score: float = 5.0
    ) -> Dict:
        """
        節間成績スコアを計算

        同一会場での直近成績（同じ開催期間内）を評価

        Args:
            racer_number: 選手番号
            venue_code: 会場コード
            target_date: 対象日付（YYYY-MM-DD）
            max_score: 最大スコア

        Returns:
            {'score': float, 'races': int, 'avg_rank': float, 'trend': str}
        """
        # キャッシュからの取得を試みる
        if self.batch_loader and self.batch_loader.is_loaded():
            cached_results = self.batch_loader.get_session_performance(racer_number, venue_code)
            if cached_results is not None:
                # キャッシュデータを使用
                ranks = []
                for result in cached_results:
                    try:
                        rank = int(result['rank'])
                        if 1 <= rank <= 6:
                            ranks.append(rank)
                    except (ValueError, TypeError):
                        pass

                if not ranks:
                    return {
                        'score': max_score * 0.5,
                        'races': len(cached_results),
                        'avg_rank': None,
                        'trend': 'unknown',
                        'description': '有効データなし'
                    }

                avg_rank = sum(ranks) / len(ranks)
                score = max(0, (6 - avg_rank) / 5 * max_score)

                # トレンド判定
                if len(ranks) >= 4:
                    first_half = sum(ranks[:len(ranks)//2]) / (len(ranks)//2)
                    second_half = sum(ranks[len(ranks)//2:]) / (len(ranks) - len(ranks)//2)
                    if second_half < first_half - 0.5:
                        trend = 'improving'
                    elif second_half > first_half + 0.5:
                        trend = 'declining'
                    else:
                        trend = 'stable'
                else:
                    trend = 'insufficient'

                return {
                    'score': score,
                    'races': len(ranks),
                    'avg_rank': round(avg_rank, 2),
                    'trend': trend,
                    'description': f'節間{len(ranks)}走 平均{avg_rank:.1f}着'
                }

        # キャッシュがない場合はDB直接アクセス（従来通り）
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT res.rank, r.race_date, r.race_number
                FROM entries e
                JOIN races r ON e.race_id = r.id
                LEFT JOIN results res ON res.race_id = r.id AND res.pit_number = e.pit_number
                WHERE e.racer_number = ?
                  AND r.venue_code = ?
                  AND r.race_date < ?
                  AND r.race_date >= date(?, '-7 days')
                  AND res.rank IS NOT NULL
                  AND res.rank NOT IN ('F', 'L', '欠', '失')
                ORDER BY r.race_date DESC, r.race_number DESC
                LIMIT 12
            ''', (racer_number, venue_code, target_date, target_date))

            results = cursor.fetchall()

            if not results:
                return {
                    'score': max_score * 0.5,
                    'races': 0,
                    'avg_rank': None,
                    'trend': 'unknown',
                    'description': '節間データなし'
                }

            ranks = []
            for row in results:
                try:
                    rank = int(row[0])
                    if 1 <= rank <= 6:
                        ranks.append(rank)
                except (ValueError, TypeError):
                    pass

            if not ranks:
                return {
                    'score': max_score * 0.5,
                    'races': len(results),
                    'avg_rank': None,
                    'trend': 'unknown',
                    'description': '有効データなし'
                }

            avg_rank = sum(ranks) / len(ranks)
            score = max(0, (6 - avg_rank) / 5 * max_score)

            if len(ranks) >= 4:
                first_half = sum(ranks[:len(ranks)//2]) / (len(ranks)//2)
                second_half = sum(ranks[len(ranks)//2:]) / (len(ranks) - len(ranks)//2)
                if second_half < first_half - 0.5:
                    trend = 'improving'
                elif second_half > first_half + 0.5:
                    trend = 'declining'
                else:
                    trend = 'stable'
            else:
                trend = 'insufficient'

            return {
                'score': score,
                'races': len(ranks),
                'avg_rank': round(avg_rank, 2),
                'trend': trend,
                'description': f'節間{len(ranks)}走 平均{avg_rank:.1f}着'
            }

        finally:
            conn.close()'''

    content = content.replace(old_session, new_session)

    # 3. 他のメソッドも同様にキャッシュ対応に（簡略化のため、主要なもののみ実装）
    # ここでは主要なcalculate_previous_race_levelを修正

    old_prev_race = '''    def calculate_previous_race_level(
        self,
        racer_number: str,
        target_date: str,
        max_score: float = 5.0
    ) -> Dict:
        """
        前走レベル評価

        直前のレースがSG/G1だったか、一般戦だったかで調子を推定

        Args:
            racer_number: 選手番号
            target_date: 対象日付
            max_score: 最大スコア

        Returns:
            {'score': float, 'prev_grade': str, 'prev_result': int, 'description': str}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 直近のレース（対象日より前）
            cursor.execute('''
                SELECT r.race_grade, res.rank, r.race_date
                FROM entries e
                JOIN races r ON e.race_id = r.id
                LEFT JOIN results res ON res.race_id = r.id AND res.pit_number = e.pit_number
                WHERE e.racer_number = ?
                  AND r.race_date < ?
                ORDER BY r.race_date DESC, r.race_number DESC
                LIMIT 1
            ''', (racer_number, target_date))

            row = cursor.fetchone()

            if not row:
                return {
                    'score': max_score * 0.5,
                    'prev_grade': None,
                    'prev_result': None,
                    'description': '前走データなし'
                }

            prev_grade, prev_rank, prev_date = row

            # グレード評価
            grade_scores = {
                'SG': 1.0,
                'G1': 0.9,
                'G2': 0.8,
                'G3': 0.7,
                '一般': 0.5,
                'ルーキーシリーズ': 0.4,
            }
            grade_factor = grade_scores.get(prev_grade, 0.5)

            # 前走結果評価
            try:
                rank = int(prev_rank)
                if rank == 1:
                    result_factor = 1.0
                elif rank == 2:
                    result_factor = 0.8
                elif rank <= 3:
                    result_factor = 0.6
                else:
                    result_factor = 0.4
            except (ValueError, TypeError):
                result_factor = 0.3  # F/L等

            # 複合スコア
            score = max_score * (grade_factor * 0.4 + result_factor * 0.6)

            return {
                'score': score,
                'prev_grade': prev_grade,
                'prev_result': prev_rank,
                'description': f'前走{prev_grade or "不明"} {prev_rank or "-"}着'
            }

        finally:
            conn.close()'''

    new_prev_race = '''    def calculate_previous_race_level(
        self,
        racer_number: str,
        target_date: str,
        max_score: float = 5.0
    ) -> Dict:
        """
        前走レベル評価

        直前のレースがSG/G1だったか、一般戦だったかで調子を推定

        Args:
            racer_number: 選手番号
            target_date: 対象日付
            max_score: 最大スコア

        Returns:
            {'score': float, 'prev_grade': str, 'prev_result': int, 'description': str}
        """
        # キャッシュからの取得を試みる
        if self.batch_loader and self.batch_loader.is_loaded():
            cached_data = self.batch_loader.get_previous_race(racer_number)
            if cached_data:
                prev_grade = cached_data.get('prev_grade')
                prev_rank = cached_data.get('prev_rank')

                grade_scores = {
                    'SG': 1.0,
                    'G1': 0.9,
                    'G2': 0.8,
                    'G3': 0.7,
                    '一般': 0.5,
                    'ルーキーシリーズ': 0.4,
                }
                grade_factor = grade_scores.get(prev_grade, 0.5)

                try:
                    rank = int(prev_rank)
                    if rank == 1:
                        result_factor = 1.0
                    elif rank == 2:
                        result_factor = 0.8
                    elif rank <= 3:
                        result_factor = 0.6
                    else:
                        result_factor = 0.4
                except (ValueError, TypeError):
                    result_factor = 0.3

                score = max_score * (grade_factor * 0.4 + result_factor * 0.6)

                return {
                    'score': score,
                    'prev_grade': prev_grade,
                    'prev_result': prev_rank,
                    'description': f'前走{prev_grade or "不明"} {prev_rank or "-"}着'
                }

        # キャッシュがない場合はDB直接アクセス
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT r.race_grade, res.rank, r.race_date
                FROM entries e
                JOIN races r ON e.race_id = r.id
                LEFT JOIN results res ON res.race_id = r.id AND res.pit_number = e.pit_number
                WHERE e.racer_number = ?
                  AND r.race_date < ?
                ORDER BY r.race_date DESC, r.race_number DESC
                LIMIT 1
            ''', (racer_number, target_date))

            row = cursor.fetchone()

            if not row:
                return {
                    'score': max_score * 0.5,
                    'prev_grade': None,
                    'prev_result': None,
                    'description': '前走データなし'
                }

            prev_grade, prev_rank, prev_date = row

            grade_scores = {
                'SG': 1.0,
                'G1': 0.9,
                'G2': 0.8,
                'G3': 0.7,
                '一般': 0.5,
                'ルーキーシリーズ': 0.4,
            }
            grade_factor = grade_scores.get(prev_grade, 0.5)

            try:
                rank = int(prev_rank)
                if rank == 1:
                    result_factor = 1.0
                elif rank == 2:
                    result_factor = 0.8
                elif rank <= 3:
                    result_factor = 0.6
                else:
                    result_factor = 0.4
            except (ValueError, TypeError):
                result_factor = 0.3

            score = max_score * (grade_factor * 0.4 + result_factor * 0.6)

            return {
                'score': score,
                'prev_grade': prev_grade,
                'prev_result': prev_rank,
                'description': f'前走{prev_grade or "不明"} {prev_rank or "-"}着'
            }

        finally:
            conn.close()'''

    content = content.replace(old_prev_race, new_prev_race)

    # ファイルを保存
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print("✅ ExtendedScorer を修正しました")
    print("   - __init__にbatch_loaderパラメータを追加")
    print("   - calculate_session_performanceをキャッシュ対応に")
    print("   - calculate_previous_race_levelをキャッシュ対応に")


if __name__ == "__main__":
    modify_extended_scorer()
