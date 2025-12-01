"""
ボートレーサー名鑑から選手マスタデータを取得

https://br-racers.jp/ から全選手の詳細情報を取得してDBに保存
"""

import os
import sys
import time
import re
from datetime import datetime
from typing import Dict, List, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from src.database.models import Database


class RacerMasterScraper:
    """ボートレーサー名鑑スクレイパー"""

    BASE_URL = "https://br-racers.jp"

    def __init__(self, db_path="data/boatrace.db", headless=True):
        """
        初期化

        Args:
            db_path: データベースファイルのパス
            headless: ヘッドレスモードで実行するか
        """
        self.db = Database(db_path)
        self.driver = None
        self.headless = headless

    def _init_driver(self):
        """Selenium WebDriverを初期化"""
        if self.driver:
            return

        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 10)

    def close(self):
        """ドライバーを閉じる"""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def fetch_all_racers_from_list(self, limit=None, female_only=False) -> List[Dict]:
        """
        全選手の詳細情報を一覧ページから直接取得

        Args:
            limit: 取得件数制限（テスト用、Noneで全件）
            female_only: 女性選手のみ取得するか

        Returns:
            選手詳細情報のリスト
        """
        self._init_driver()
        racers = []
        page = 1

        print(f"選手一覧ページから詳細情報を取得中...")
        if female_only:
            print("  女性選手のみを取得します")

        try:
            while True:
                # 女性選手のみの場合はフィルターを追加
                if female_only:
                    url = f"{self.BASE_URL}/?gender=female&page={page}"
                else:
                    url = f"{self.BASE_URL}/?page={page}"

                print(f"  ページ {page} を取得中...")

                self.driver.get(url)
                time.sleep(2)  # ページ読み込み待機

                # ページをスクロールしてバッジ画像の遅延読み込みをトリガー
                self.driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
                time.sleep(1)
                self.driver.execute_script('window.scrollTo(0, 0);')
                time.sleep(0.5)

                # 選手カードのリンクを取得
                try:
                    racer_elements = self.driver.find_elements(By.CSS_SELECTOR, 'a.c-result-item[href*="/racers/"]')

                    if not racer_elements:
                        print(f"  ページ {page} に選手データがありません。終了します。")
                        break

                    print(f"    {len(racer_elements)}人の選手を発見")

                    for i, elem in enumerate(racer_elements):
                        try:
                            # 10要素ごとにスクロールしてバッジ画像を読み込む（パフォーマンス対策）
                            if i % 10 == 0:
                                self.driver.execute_script('arguments[0].scrollIntoView({block: "center"});', elem)
                                time.sleep(0.2)

                            # 登録番号
                            racer_number = elem.find_element(By.CSS_SELECTOR, 'div.registration-number-cell').text.strip()

                            # 名前（カナと漢字）
                            name_kana_elements = elem.find_elements(By.CSS_SELECTOR, 'div.name-item-kana')
                            name_main_elements = elem.find_elements(By.CSS_SELECTOR, 'div.name-item-main')

                            name_kana = ' '.join([e.text.strip() for e in name_kana_elements])
                            name = ' '.join([e.text.strip() for e in name_main_elements])

                            # ランク
                            rank_elem = elem.find_element(By.CSS_SELECTOR, 'div.rank')
                            rank = rank_elem.text.strip()

                            # 支部・出身
                            branch = elem.find_element(By.CSS_SELECTOR, 'div.branch-name').text.strip()
                            hometown = elem.find_element(By.CSS_SELECTOR, 'div.prefecture-name').text.strip()

                            # 勝率、2連率、能力指数などの情報を取得（ラベルと値のペア）
                            info_labels = elem.find_elements(By.CSS_SELECTOR, 'dt.info-item-label')
                            info_values = elem.find_elements(By.CSS_SELECTOR, 'dd.info-item-value')

                            win_rate = None
                            second_rate = None
                            ability_index = None
                            wins = None

                            for label, value in zip(info_labels, info_values):
                                label_text = label.text.strip()
                                value_text = value.text.strip()

                                try:
                                    if '勝率' in label_text:
                                        win_rate = float(value_text)
                                    elif '連対' in label_text or '2連' in label_text:
                                        # 「4回」のような表記は数値のみ抽出（回数として保存）
                                        match = re.search(r'(\d+)', value_text)
                                        if match:
                                            # 2連対回数としてwinsに保存（DBスキーマにはwinsフィールドがある）
                                            wins = int(match.group(1))
                                    elif '能力指数' in label_text or '指数' in label_text:
                                        ability_index = float(value_text)
                                except ValueError:
                                    # 数値変換に失敗した場合はスキップ
                                    pass

                            # 性別（女性選手のみフィルターしている場合はfemale、そうでない場合は画像のバッジで判定）
                            gender = 'female' if female_only else None
                            if not female_only:
                                # バッジ画像があれば女性
                                badges = elem.find_elements(By.CSS_SELECTOR, 'img.badge')
                                gender = 'female' if badges else 'male'

                            racer_data = {
                                'racer_number': racer_number,
                                'name': name,
                                'name_kana': name_kana,
                                'gender': gender,
                                'rank': rank,
                                'branch': branch,
                                'hometown': hometown,
                                'win_rate': win_rate,
                                'second_rate': second_rate,
                                'ability_index': ability_index,
                                'wins': wins,
                            }

                            racers.append(racer_data)

                            if limit and len(racers) >= limit:
                                print(f"  制限数 {limit} に達しました")
                                return racers

                        except Exception as e:
                            print(f"    選手データ取得エラー: {str(e)}")
                            continue

                    page += 1

                except Exception as e:
                    print(f"  ページ取得エラー: {str(e)}")
                    break

        except Exception as e:
            print(f"エラーが発生しました: {str(e)}")
            import traceback
            traceback.print_exc()

        print(f"合計 {len(racers)}人の選手情報を取得しました")
        return racers

    def fetch_all_racers_basic(self, limit=None) -> List[Dict]:
        """
        全選手の基本情報を取得（一覧ページから）

        注: この関数は後方互換性のために残していますが、
        fetch_all_racers_from_list()を使用することを推奨します。

        Args:
            limit: 取得件数制限（テスト用、Noneで全件）

        Returns:
            選手基本情報のリスト
        """
        self._init_driver()
        racers = []
        page = 1

        print(f"選手一覧ページから基本情報を取得中...")

        try:
            while True:
                url = f"{self.BASE_URL}/racers?page={page}"
                print(f"  ページ {page} を取得中: {url}")

                self.driver.get(url)
                time.sleep(2)  # ページ読み込み待機

                # 選手カードのリンクを取得
                try:
                    # 登録番号が表示される要素を含むリンクを探す
                    racer_elements = self.driver.find_elements(By.CSS_SELECTOR, 'a[href*="/racers/"]')

                    if not racer_elements:
                        print(f"  ページ {page} に選手データがありません。終了します。")
                        break

                    page_racers = []
                    for elem in racer_elements:
                        href = elem.get_attribute('href')
                        if not href or '/racers/' not in href:
                            continue

                        # UUIDを抽出
                        uuid = href.split('/racers/')[-1].split('?')[0]

                        # 登録番号を取得（要素内のテキストから）
                        try:
                            text = elem.text
                            # 4桁の数字を探す（登録番号）
                            number_match = re.search(r'\b(\d{4})\b', text)
                            racer_number = number_match.group(1) if number_match else None

                            racer_info = {
                                'uuid': uuid,
                                'detail_url': href,
                                'racer_number': racer_number
                            }

                            # 重複チェック
                            if uuid not in [r['uuid'] for r in page_racers]:
                                page_racers.append(racer_info)

                        except Exception as e:
                            continue

                    print(f"  ページ {page}: {len(page_racers)} 人分のリンクを取得")
                    racers.extend(page_racers)

                    if limit and len(racers) >= limit:
                        print(f"  制限件数 {limit} に達しました")
                        racers = racers[:limit]
                        break

                    # データが取得できなかった、または少なかった場合は終了
                    if len(page_racers) == 0:
                        print(f"  データがなくなりました。終了します。")
                        break

                    # 次のページへ
                    page += 1
                    time.sleep(1)  # ページ間の待機

                except TimeoutException:
                    print(f"  ページ {page} のロードがタイムアウトしました")
                    break

        except Exception as e:
            print(f"エラーが発生しました: {e}")
            import traceback
            traceback.print_exc()

        print(f"合計 {len(racers)} 人分のリンクを取得しました")
        return racers

    def fetch_female_racers(self) -> List[Dict]:
        """
        女性選手のみを取得（性別フィルタ使用）

        Returns:
            女性選手の基本情報リスト（UUID or racer_numberのリスト）
        """
        self._init_driver()
        female_identifiers = set()
        page = 1

        print(f"女性選手一覧を取得中...")

        try:
            while True:
                url = f"{self.BASE_URL}/racers?gender=female&page={page}"
                print(f"  ページ {page} を取得中: {url}")

                self.driver.get(url)
                time.sleep(2)

                # 選手カードのリンクを取得
                racer_elements = self.driver.find_elements(By.CSS_SELECTOR, 'a[href*="/racers/"]')

                if not racer_elements:
                    print(f"  ページ {page} に選手データがありません。終了します。")
                    break

                page_count = 0
                for elem in racer_elements:
                    href = elem.get_attribute('href')
                    if not href or '/racers/' not in href:
                        continue

                    uuid = href.split('/racers/')[-1].split('?')[0]

                    # 登録番号も取得
                    try:
                        text = elem.text
                        number_match = re.search(r'\b(\d{4})\b', text)
                        if number_match:
                            female_identifiers.add(number_match.group(1))  # 登録番号で管理
                    except:
                        pass

                    female_identifiers.add(uuid)  # UUIDでも管理
                    page_count += 1

                print(f"  ページ {page}: {page_count} 人取得")

                # データがなくなったら終了
                if page_count == 0:
                    print(f"  データがなくなりました。終了します。")
                    break

                # 次のページへ
                page += 1
                time.sleep(1)

        except Exception as e:
            print(f"エラーが発生しました: {e}")
            import traceback
            traceback.print_exc()

        print(f"女性選手 {len(female_identifiers)} 人を取得しました")
        return female_identifiers

    def fetch_racer_detail(self, detail_url: str) -> Optional[Dict]:
        """
        個別選手ページから詳細情報を取得

        Args:
            detail_url: 選手詳細ページのURL

        Returns:
            選手詳細情報の辞書
        """
        self._init_driver()

        try:
            self.driver.get(detail_url)
            time.sleep(2)  # ページ読み込み待機

            racer_data = {}

            # ページ全体のテキストを取得
            page_text = self.driver.find_element(By.TAG_NAME, 'body').text

            # 登録番号（4桁）を抽出
            number_match = re.search(r'\b(\d{4})\b', page_text)
            if number_match:
                racer_data['racer_number'] = number_match.group(1)

            # 名前（漢字とカナ）
            name_match = re.search(r'([^\d\s]+\s*[^\d\s]+)[(（]([^\)）]+)[)）]', page_text)
            if name_match:
                racer_data['name'] = name_match.group(1).strip()
                racer_data['name_kana'] = name_match.group(2).strip()

            # 生年月日
            birth_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', page_text)
            if birth_match:
                racer_data['birth_date'] = f"{birth_match.group(1)}-{birth_match.group(2).zfill(2)}-{birth_match.group(3).zfill(2)}"

            # 身長
            height_match = re.search(r'身長[：:\s]*(\d+(?:\.\d+)?)\s*cm', page_text)
            if height_match:
                racer_data['height'] = float(height_match.group(1))

            # 体重
            weight_match = re.search(r'体重[：:\s]*(\d+(?:\.\d+)?)\s*kg', page_text)
            if weight_match:
                racer_data['weight'] = float(weight_match.group(1))

            # 血液型
            blood_match = re.search(r'血液型[：:\s]*([ABO]B?型)', page_text)
            if blood_match:
                racer_data['blood_type'] = blood_match.group(1)

            # 支部
            branch_match = re.search(r'([^都道府県\n]+(?:都|道|府|県))?([^支部\n]+)支部', page_text)
            if branch_match:
                racer_data['branch'] = branch_match.group(2).strip() + '支部'

            # 出身地
            hometown_match = re.search(r'出身[：:\s]*([^都道府県\n]+(?:都|道|府|県))', page_text)
            if hometown_match:
                racer_data['hometown'] = hometown_match.group(1).strip()

            # 登録期
            period_match = re.search(r'登録期[：:\s]*(\d+)期', page_text)
            if period_match:
                racer_data['registration_period'] = int(period_match.group(1))

            # 級別
            rank_match = re.search(r'([AB][12])級', page_text)
            if rank_match:
                racer_data['rank'] = rank_match.group(1)

            # 勝率
            win_rate_match = re.search(r'勝率[：:\s]*(\d+\.\d+)', page_text)
            if win_rate_match:
                racer_data['win_rate'] = float(win_rate_match.group(1))

            # 2連率
            second_rate_match = re.search(r'2連率[：:\s]*(\d+\.\d+)', page_text)
            if second_rate_match:
                racer_data['second_rate'] = float(second_rate_match.group(1))

            # 3連率
            third_rate_match = re.search(r'3連率[：:\s]*(\d+\.\d+)', page_text)
            if third_rate_match:
                racer_data['third_rate'] = float(third_rate_match.group(1))

            # 能力指数
            ability_match = re.search(r'能力指数[：:\s]*(\d+(?:\.\d+)?)', page_text)
            if ability_match:
                racer_data['ability_index'] = float(ability_match.group(1))

            # 平均ST
            st_match = re.search(r'平均ST[：:\s]*(\d+\.\d+)', page_text)
            if st_match:
                racer_data['average_st'] = float(st_match.group(1))

            # 優勝回数
            wins_match = re.search(r'優勝回数[：:\s]*(\d+)回', page_text)
            if wins_match:
                racer_data['wins'] = int(wins_match.group(1))

            return racer_data if racer_data else None

        except Exception as e:
            print(f"  詳細情報の抽出エラー: {e}")
            import traceback
            traceback.print_exc()
            return None

    def save_racer_to_db(self, racer_data: Dict):
        """
        選手データをDBに保存

        Args:
            racer_data: 選手データの辞書
        """
        if 'racer_number' not in racer_data:
            print(f"  警告: 登録番号がないためスキップ")
            return

        conn = self.db.connect()
        cursor = conn.cursor()

        try:
            # UPSERT（存在すれば更新、なければ挿入）
            cursor.execute("""
                INSERT INTO racers (
                    racer_number, name, name_kana, gender, birth_date,
                    height, weight, blood_type, branch, hometown,
                    registration_period, rank, win_rate, second_rate, third_rate,
                    ability_index, average_st, wins, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(racer_number) DO UPDATE SET
                    name = excluded.name,
                    name_kana = excluded.name_kana,
                    gender = excluded.gender,
                    birth_date = excluded.birth_date,
                    height = excluded.height,
                    weight = excluded.weight,
                    blood_type = excluded.blood_type,
                    branch = excluded.branch,
                    hometown = excluded.hometown,
                    registration_period = excluded.registration_period,
                    rank = excluded.rank,
                    win_rate = excluded.win_rate,
                    second_rate = excluded.second_rate,
                    third_rate = excluded.third_rate,
                    ability_index = excluded.ability_index,
                    average_st = excluded.average_st,
                    wins = excluded.wins,
                    updated_at = excluded.updated_at
            """, (
                racer_data.get('racer_number'),
                racer_data.get('name'),
                racer_data.get('name_kana'),
                racer_data.get('gender'),
                racer_data.get('birth_date'),
                racer_data.get('height'),
                racer_data.get('weight'),
                racer_data.get('blood_type'),
                racer_data.get('branch'),
                racer_data.get('hometown'),
                racer_data.get('registration_period'),
                racer_data.get('rank'),
                racer_data.get('win_rate'),
                racer_data.get('second_rate'),
                racer_data.get('third_rate'),
                racer_data.get('ability_index'),
                racer_data.get('average_st'),
                racer_data.get('wins'),
                datetime.now().isoformat()
            ))

            conn.commit()

        except Exception as e:
            print(f"  DB保存エラー: {e}")
            conn.rollback()
        finally:
            self.db.close()

    def update_racers_basic_only(self, limit=None):
        """
        一覧ページから基本情報を取得してDBに保存（簡易版）
        スクロール対応により、バッジ画像で女性選手を正確に判定

        Args:
            limit: 取得件数制限（テスト用）
        """
        try:
            # 全選手の一覧を取得（スクロール対応により女性も正確に検出）
            print("=" * 60)
            print("全選手の基本情報を取得")
            print("=" * 60)

            all_racers = self.fetch_all_racers_from_list(limit=limit, female_only=False)

            success_count = 0
            error_count = 0

            print("\n" + "=" * 60)
            print("データベースに保存")
            print("=" * 60)

            for i, racer in enumerate(all_racers, 1):
                try:
                    racer_number = racer.get('racer_number')

                    if not racer_number:
                        error_count += 1
                        print(f"[{i}/{len(all_racers)}] NG 登録番号なし")
                        continue

                    # DBに保存（fetch_all_racers_from_listが返すデータをそのまま使用）
                    self.save_racer_to_db(racer)
                    success_count += 1

                    # 進捗表示
                    gender_mark = '♀' if racer.get('gender') == 'female' else '♂'
                    if i % 100 == 0 or racer.get('gender') == 'female':
                        name = racer.get('name', '不明')
                        print(f"[{i}/{len(all_racers)}] OK {name} ({racer_number}) {gender_mark}")

                except Exception as e:
                    error_count += 1
                    print(f"[{i}/{len(all_racers)}] NG {str(e)}")

            print("\n" + "=" * 60)
            print("完了")
            print(f"成功: {success_count} 人")
            print(f"失敗: {error_count} 人")
            print("=" * 60)

        finally:
            self.close()

    def update_all_racers(self, limit=None):
        """
        全選手のデータを更新（一覧ページから直接取得）

        Args:
            limit: 取得件数制限（テスト用）
        """
        try:
            print("=" * 60)
            print("全選手詳細データの取得（一覧ページから）")
            print("=" * 60)

            # 一覧ページから全選手の詳細情報を取得
            all_racers = self.fetch_all_racers_from_list(limit=limit, female_only=False)

            success_count = 0
            error_count = 0

            print("\n" + "=" * 60)
            print("データベースへの保存")
            print("=" * 60)

            for i, racer in enumerate(all_racers, 1):
                try:
                    # DBに保存
                    self.save_racer_to_db(racer)
                    success_count += 1
                    gender_mark = '♀' if racer.get('gender') == 'female' else '♂'
                    print(f"[{i}/{len(all_racers)}] OK {racer.get('name', '不明')} ({racer.get('racer_number', '????')}) {gender_mark}")
                except Exception as e:
                    error_count += 1
                    print(f"[{i}/{len(all_racers)}] NG 保存失敗: {str(e)}")

            print("\n" + "=" * 60)
            print("完了")
            print(f"成功: {success_count} 人")
            print(f"失敗: {error_count} 人")
            print("=" * 60)

        finally:
            # ドライバーを確実に閉じる
            self.close()
