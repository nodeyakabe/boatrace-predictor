"""
NEAR-GOOS RDMDB 潮位データパーサー
30秒値および1分値の潮位データを解析
"""
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional


class RDMDBTideParser:
    """RDMDB潮位データのパーサー"""

    @staticmethod
    def parse_30s_file(file_path: str, year: int, month: int) -> List[Dict]:
        """
        30秒値潮位データファイルを解析

        Args:
            file_path: ファイルパス
            year: 年
            month: 月

        Returns:
            list: [
                {
                    'datetime': '2022-11-01 00:00:00',
                    'sea_level_cm': 230,
                    'air_pressure_hpa': 1022.0,
                    'temperature_c': None,
                    'sea_level_smoothed_cm': 228.73
                },
                ...
            ]
        """
        tide_data = []

        try:
            with open(file_path, 'r', encoding='shift-jis', errors='ignore') as f:
                lines = f.readlines()

            # ヘッダー行をスキップして、データ行のみを処理
            data_lines = []
            header_end = False

            for line in lines:
                # ヘッダーの終わりを検出（#で始まらない行がデータ開始）
                if line.startswith('#'):
                    continue
                if not header_end:
                    # 最初のデータ行（地点名・日本語）をスキップ
                    header_end = True
                    continue

                data_lines.append(line)

            # 月の日数を取得
            if month == 12:
                next_month_start = datetime(year + 1, 1, 1)
            else:
                next_month_start = datetime(year, month + 1, 1)

            month_start = datetime(year, month, 1)
            days_in_month = (next_month_start - month_start).days

            # データを日ごとに処理
            records_per_day = 2880  # 30秒間隔 = 24h * 60min * 2
            current_record = 0

            for day in range(1, days_in_month + 1):
                for record_in_day in range(records_per_day):
                    if current_record >= len(data_lines):
                        break

                    line = data_lines[current_record].strip()
                    current_record += 1

                    # 行の長さチェック
                    if len(line) < 24:
                        continue

                    # データ抽出
                    try:
                        # Col 1-6: Sea Level (Observed) (cm)
                        sea_level_str = line[0:6].strip()
                        sea_level_cm = int(sea_level_str) if sea_level_str and sea_level_str != '######' else None

                        # Col 7-12: Air Pressure (hPa)
                        air_pressure_str = line[6:12].strip()
                        air_pressure_hpa = float(air_pressure_str) / 100.0 if air_pressure_str and air_pressure_str != '######' else None

                        # Col 13-18: Temperature (0.1 C)
                        temperature_str = line[12:18].strip()
                        temperature_c = float(temperature_str) / 10.0 if temperature_str and temperature_str != '######' else None

                        # Col 19-24: Sea Level (Smoothed) (0.01 cm)
                        sea_level_smoothed_str = line[18:24].strip()
                        sea_level_smoothed_cm = float(sea_level_smoothed_str) / 100.0 if sea_level_smoothed_str and sea_level_smoothed_str != '######' else None

                        # タイムスタンプ計算（30秒間隔）
                        seconds_in_day = record_in_day * 30
                        hours = seconds_in_day // 3600
                        minutes = (seconds_in_day % 3600) // 60
                        seconds = seconds_in_day % 60

                        dt = datetime(year, month, day, hours, minutes, seconds)

                        tide_data.append({
                            'datetime': dt.strftime('%Y-%m-%d %H:%M:%S'),
                            'sea_level_cm': sea_level_cm,
                            'air_pressure_hpa': air_pressure_hpa,
                            'temperature_c': temperature_c,
                            'sea_level_smoothed_cm': sea_level_smoothed_cm
                        })

                    except (ValueError, IndexError) as e:
                        # パースエラーはスキップ
                        continue

        except Exception as e:
            print(f"ファイル解析エラー ({file_path}): {e}")
            return []

        return tide_data

    @staticmethod
    def parse_01m_file(file_path: str, year: int, month: int) -> List[Dict]:
        """
        1分値潮位データファイルを解析（2023年1月以降）

        2つのフォーマットに対応:
        1. 固定幅フォーマット (古い形式)
        2. CSVフォーマット (2023年1月以降の新形式)

        Args:
            file_path: ファイルパス
            year: 年
            month: 月

        Returns:
            list: 30秒値と同じ形式
        """
        tide_data = []

        try:
            # エンコーディング自動検出: shift-jisを優先
            # RDMDBのファイルは基本的にshift-jis
            lines = None
            for encoding in ['shift-jis', 'utf-8', 'utf-16', 'utf-16-le']:
                try:
                    with open(file_path, 'r', encoding=encoding, errors='strict') as f:
                        lines = f.readlines()
                    # データ行が含まれているか簡易チェック
                    has_data = any('/' in line and ',' in line for line in lines[:50])
                    if has_data:
                        break
                except (UnicodeDecodeError, UnicodeError):
                    continue

            if lines is None:
                # どのエンコーディングも失敗した場合、errorsを使用
                with open(file_path, 'r', encoding='shift-jis', errors='ignore') as f:
                    lines = f.readlines()

            # デバッグ: ファイルの最初の数行を確認
            import os
            file_size = os.path.getsize(file_path)
            # print(f"  ファイルサイズ: {file_size:,} バイト, 総行数: {len(lines)}")

            # データ行を抽出（ヘッダーをスキップ）
            # 改善版: CSVフォーマットを正確に検出
            data_lines = []

            for line in lines:
                stripped = line.strip()

                # 空行をスキップ
                if not stripped:
                    continue

                # '#'で始まる行はコメント行としてスキップ
                if stripped.startswith('#'):
                    continue

                # CSVデータ行の判定: YYYY/MM/DD HH:MM:SS,数値,数値,数値 の形式
                # 例: 2023/10/01 00:00:00,453,453,454.13
                if '/' in stripped and ',' in stripped and ':' in stripped:
                    # より厳密な判定: 最初の部分が日時フォーマットか
                    try:
                        # カンマで分割して最初の部分が日時かチェック
                        first_part = stripped.split(',')[0].strip()
                        if len(first_part) == 19 and first_part[4] == '/' and first_part[10] == ' ':
                            # YYYY/MM/DD HH:MM:SS 形式
                            data_lines.append(line)
                            continue
                    except (IndexError, AttributeError):
                        pass

                # それ以外はヘッダーとしてスキップ
                # (地点名、説明文など)

            if not data_lines:
                # デバッグ: データ行が0の場合、ファイル内容の一部を表示
                #print(f"  警告: データ行が0件 (ファイルサイズ: {file_size}, 総行数: {len(lines)})")
                #if lines:
                #    print(f"  最初の5行:")
                #    for i, line in enumerate(lines[:5], 1):
                #        print(f"    {i}: {repr(line[:80])}")
                return []

            # フォーマット判定: CSVか固定幅か
            # CSVフォーマットは "YYYY/MM/DD HH:MM:SS,..." の形式
            first_line = data_lines[0].strip()
            is_csv = ',' in first_line and '/' in first_line

            if is_csv:
                # CSVフォーマット処理
                for line in data_lines:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        # フォーマット: 2023/01/01 00:00:00,233,233,231.62
                        parts = line.split(',')
                        if len(parts) < 4:
                            continue

                        # タイムスタンプパース
                        timestamp_str = parts[0].strip()
                        dt = datetime.strptime(timestamp_str, '%Y/%m/%d %H:%M:%S')

                        # 潮位データ (観測値)
                        sea_level_cm = int(parts[1].strip()) if parts[1].strip() and parts[1].strip() != '#####' else None

                        # 潮位データ (補完値) - 使用しない
                        # sea_level_completed = int(parts[2].strip()) if parts[2].strip() else None

                        # 潮位データ (平滑値)
                        sea_level_smoothed_cm = float(parts[3].strip()) if parts[3].strip() and parts[3].strip() != '#####' else None

                        # 気圧と気温のデータはCSVフォーマットには含まれていない
                        tide_data.append({
                            'datetime': dt.strftime('%Y-%m-%d %H:%M:%S'),
                            'sea_level_cm': sea_level_cm,
                            'air_pressure_hpa': None,
                            'temperature_c': None,
                            'sea_level_smoothed_cm': sea_level_smoothed_cm
                        })

                    except (ValueError, IndexError) as e:
                        # パースエラーはスキップ
                        continue

            else:
                # 固定幅フォーマット処理 (従来の処理)
                # 月の日数を取得
                if month == 12:
                    next_month_start = datetime(year + 1, 1, 1)
                else:
                    next_month_start = datetime(year, month + 1, 1)

                month_start = datetime(year, month, 1)
                days_in_month = (next_month_start - month_start).days

                # 1分間隔 = 24h * 60min = 1440 records/day
                records_per_day = 1440
                current_record = 0

                for day in range(1, days_in_month + 1):
                    for record_in_day in range(records_per_day):
                        if current_record >= len(data_lines):
                            break

                        line = data_lines[current_record].strip()
                        current_record += 1

                        if len(line) < 24:
                            continue

                        try:
                            sea_level_str = line[0:6].strip()
                            sea_level_cm = int(sea_level_str) if sea_level_str and sea_level_str != '######' else None

                            air_pressure_str = line[6:12].strip()
                            air_pressure_hpa = float(air_pressure_str) / 100.0 if air_pressure_str and air_pressure_str != '######' else None

                            temperature_str = line[12:18].strip()
                            temperature_c = float(temperature_str) / 10.0 if temperature_str and temperature_str != '######' else None

                            sea_level_smoothed_str = line[18:24].strip()
                            sea_level_smoothed_cm = float(sea_level_smoothed_str) / 100.0 if sea_level_smoothed_str and sea_level_smoothed_str != '######' else None

                            # タイムスタンプ計算（1分間隔）
                            minutes_in_day = record_in_day
                            hours = minutes_in_day // 60
                            minutes = minutes_in_day % 60

                            dt = datetime(year, month, day, hours, minutes, 0)

                            tide_data.append({
                                'datetime': dt.strftime('%Y-%m-%d %H:%M:%S'),
                                'sea_level_cm': sea_level_cm,
                                'air_pressure_hpa': air_pressure_hpa,
                                'temperature_c': temperature_c,
                                'sea_level_smoothed_cm': sea_level_smoothed_cm
                            })

                        except (ValueError, IndexError) as e:
                            continue

        except Exception as e:
            print(f"ファイル解析エラー ({file_path}): {e}")
            return []

        return tide_data

    @staticmethod
    def parse_file(file_path: str, year: int, month: int) -> List[Dict]:
        """
        ファイル名から自動的に30秒値/1分値を判定してパース

        Args:
            file_path: ファイルパス（例: "2022_11.30s_Hakata" or "2023_01.01m_Hakata" or "2023_01.1m_Hakata"）
            year: 年
            month: 月

        Returns:
            list: 潮位データ
        """
        # ファイル名から形式を判定
        if '.30s_' in file_path or '30s_' in file_path:
            return RDMDBTideParser.parse_30s_file(file_path, year, month)
        elif '.01m_' in file_path or '01m_' in file_path or '.1m_' in file_path or '1m_' in file_path:
            # 1m_ と 01m_ の両方をサポート
            return RDMDBTideParser.parse_01m_file(file_path, year, month)
        else:
            # 年月で判定（2022年12月まで30秒、2023年1月以降1分）
            if year < 2023 or (year == 2022 and month <= 12):
                return RDMDBTideParser.parse_30s_file(file_path, year, month)
            else:
                return RDMDBTideParser.parse_01m_file(file_path, year, month)


if __name__ == "__main__":
    # テスト実行
    import sys
    import os

    print("="*80)
    print("RDMDB潮位データパーサー テスト")
    print("="*80)

    # サンプルファイルをパース
    test_file = "rdmdb_downloads/2022_11.30s_Hakata"

    if os.path.exists(test_file):
        print(f"\nファイル: {test_file}")
        print(f"サイズ: {os.path.getsize(test_file):,} バイト")

        tide_data = RDMDBTideParser.parse_file(test_file, 2022, 11)

        print(f"\n解析結果:")
        print(f"  総レコード数: {len(tide_data):,}件")

        if tide_data:
            print(f"\n  最初の10件:")
            for i, data in enumerate(tide_data[:10]):
                print(f"    {i+1}. {data['datetime']}: "
                      f"潮位={data['sea_level_cm']}cm, "
                      f"気圧={data['air_pressure_hpa']}hPa, "
                      f"気温={data['temperature_c']}°C, "
                      f"潮位(平滑)={data['sea_level_smoothed_cm']}cm")

            print(f"\n  最後の10件:")
            for i, data in enumerate(tide_data[-10:]):
                print(f"    {len(tide_data)-9+i}. {data['datetime']}: "
                      f"潮位={data['sea_level_cm']}cm, "
                      f"気圧={data['air_pressure_hpa']}hPa")

            # 2022-11-01の1日分のデータ数を確認
            day1_data = [d for d in tide_data if d['datetime'].startswith('2022-11-01')]
            print(f"\n  2022-11-01のデータ数: {len(day1_data)}件（期待値: 2880件）")
    else:
        print(f"\nエラー: ファイルが見つかりません: {test_file}")
        print("先にdownload_rdmdb_sample.pyを実行してください")

    print("\n" + "="*80)
