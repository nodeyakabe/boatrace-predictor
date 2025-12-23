#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ExtendedScorerの主要メソッドをキャッシュ対応にパッチ

最も頻繁に呼ばれる5つのメソッドをキャッシュ対応に変更
"""
import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def patch_calculate_exhibition_time_score():
    """calculate_exhibition_time_scoreをキャッシュ対応に"""
    filepath = 'src/analysis/extended_scorer.py'

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # race_detailsからの取得部分を修正
    old_code = '''    def calculate_exhibition_time_score(
        self,
        race_id: int,
        pit_number: int,
        max_score: float = 8.0
    ) -> Dict:
        """
        展示タイムに基づくスコアを計算

        展示タイムはレース当日のモーター調子を反映する重要な指標。
        他艇との相対比較でスコアを算出。

        Args:
            race_id: レースID
            pit_number: 枠番
            max_score: 最大スコア

        Returns:
            {'score': float, 'exhibition_time': float, 'rank': int, 'description': str}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 該当レースの全艇の展示タイムを取得
            cursor.execute('''
                SELECT pit_number, exhibition_time
                FROM race_details
                WHERE race_id = ? AND exhibition_time IS NOT NULL
                ORDER BY exhibition_time ASC
            ''', (race_id,))

            rows = cursor.fetchall()'''

    new_code = '''    def calculate_exhibition_time_score(
        self,
        race_id: int,
        pit_number: int,
        max_score: float = 8.0
    ) -> Dict:
        """
        展示タイムに基づくスコアを計算

        展示タイムはレース当日のモーター調子を反映する重要な指標。
        他艇との相対比較でスコアを算出。

        Args:
            race_id: レースID
            pit_number: 枠番
            max_score: 最大スコア

        Returns:
            {'score': float, 'exhibition_time': float, 'rank': int, 'description': str}
        """
        # キャッシュからの取得を試みる
        if self.batch_loader and self.batch_loader.is_loaded():
            # 全艇の展示タイムをキャッシュから取得
            times_data = []
            for pit in range(1, 7):
                details = self.batch_loader.get_race_details(race_id, pit)
                if details and details.get('exhibition_time') is not None:
                    times_data.append((pit, details['exhibition_time']))

            if times_data:
                # タイムでソート
                times_data.sort(key=lambda x: x[1])
                rows = times_data
            else:
                rows = []
        else:
            # キャッシュなし：DB直接アクセス
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            try:
                cursor.execute('''
                    SELECT pit_number, exhibition_time
                    FROM race_details
                    WHERE race_id = ? AND exhibition_time IS NOT NULL
                    ORDER BY exhibition_time ASC
                ''', (race_id,))

                rows = cursor.fetchall()
            finally:
                conn.close()'''

    content = content.replace(old_code, new_code)

    # 最後のconn.close()を削除（既にキャッシュ分岐で処理済み）
    # この部分は残す必要があるため、修正なし

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print("✓ calculate_exhibition_time_score をキャッシュ対応に修正")


def patch_calculate_tilt_angle_score():
    """calculate_tilt_angle_scoreをキャッシュ対応に"""
    filepath = 'src/analysis/extended_scorer.py'

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    old_code = '''    def calculate_tilt_angle_score(
        self,
        race_id: int,
        pit_number: int,
        racer_number: str,
        max_score: float = 3.0
    ) -> Dict:
        """
        チルト角度に基づくスコアを計算

        チルト角度は選手のセッティング傾向を示す。
        - マイナス（跳ね）: 出足重視、まくり向き
        - プラス（伏せ）: 伸び重視、逃げ・差し向き
        コース特性との相性を評価。

        Args:
            race_id: レースID
            pit_number: 枠番
            racer_number: 選手番号
            max_score: 最大スコア

        Returns:
            {'score': float, 'tilt_angle': float, 'setting_type': str, 'description': str}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 該当レースのチルト角度を取得
            cursor.execute('''
                SELECT tilt_angle
                FROM race_details
                WHERE race_id = ? AND pit_number = ?
            ''', (race_id, pit_number))

            row = cursor.fetchone()

            if not row or row[0] is None:'''

    new_code = '''    def calculate_tilt_angle_score(
        self,
        race_id: int,
        pit_number: int,
        racer_number: str,
        max_score: float = 3.0
    ) -> Dict:
        """
        チルト角度に基づくスコアを計算

        チルト角度は選手のセッティング傾向を示す。
        - マイナス（跳ね）: 出足重視、まくり向き
        - プラス（伏せ）: 伸び重視、逃げ・差し向き
        コース特性との相性を評価。

        Args:
            race_id: レースID
            pit_number: 枠番
            racer_number: 選手番号
            max_score: 最大スコア

        Returns:
            {'score': float, 'tilt_angle': float, 'setting_type': str, 'description': str}
        """
        # キャッシュからの取得を試みる
        tilt = None
        if self.batch_loader and self.batch_loader.is_loaded():
            details = self.batch_loader.get_race_details(race_id, pit_number)
            if details:
                tilt = details.get('tilt_angle')
        else:
            # キャッシュなし：DB直接アクセス
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    SELECT tilt_angle
                    FROM race_details
                    WHERE race_id = ? AND pit_number = ?
                ''', (race_id, pit_number))
                row = cursor.fetchone()
                if row:
                    tilt = row[0]
            finally:
                conn.close()

        if tilt is None:'''

    content = content.replace(old_code, new_code)

    # 元のコードのconn.close()を削除する必要があるため、該当箇所を修正
    # まず、tilt_angle_scoreメソッドの最後のconn.close()を探して削除
    lines = content.split('\n')
    new_lines = []
    in_tilt_method = False
    skip_next_finally = False

    for i, line in enumerate(lines):
        if 'def calculate_tilt_angle_score(' in line:
            in_tilt_method = True
        elif in_tilt_method and line.strip().startswith('def ') and 'calculate_tilt_angle_score' not in line:
            in_tilt_method = False

        # tilt_angle_scoreメソッド内の古いfinally:conn.close()を削除
        if in_tilt_method and 'finally:' in line and i > 0 and 'try:' in lines[i-5:i]:
            # 旧コードのfinallyブロックをスキップ
            if i + 1 < len(lines) and 'conn.close()' in lines[i + 1]:
                skip_next_finally = True
                continue

        if skip_next_finally and 'conn.close()' in line:
            skip_next_finally = False
            continue

        new_lines.append(line)

    content = '\n'.join(new_lines)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print("✓ calculate_tilt_angle_score をキャッシュ対応に修正")


def main():
    print("="*70)
    print("ExtendedScorer キャッシュ対応パッチ")
    print("="*70)

    print("\n主要メソッドをキャッシュ対応に修正中...")

    try:
        patch_calculate_exhibition_time_score()
        patch_calculate_tilt_angle_score()

        print("\n" + "="*70)
        print("パッチ適用完了")
        print("="*70)
        print("\n修正済みメソッド:")
        print("  1. calculate_exhibition_time_score")
        print("  2. calculate_tilt_angle_score")
        print("\n※ 他のメソッドも必要に応じて順次対応します")

    except Exception as e:
        print(f"\n✗ エラー: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
