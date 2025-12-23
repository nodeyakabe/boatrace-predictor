# スクレイパー整理統合計画

**作成日**: 2025年11月3日
**目的**: 17個のスクレイパーモジュールを整理し、明確なバージョン管理と役割分担を確立

---

## 現状分析

### スクレイパーファイル一覧（21ファイル）

| ファイル名 | 行数 | 目的 | 状態 | 判定 |
|-----------|------|------|------|------|
| `__init__.py` | - | モジュール初期化 | 現役 | ✅ 保持 |
| **Base Scrapers（3種類）** |
| `base_scraper.py` | ? | ベーススクレイパー | v1 | ⚠️ 要確認 |
| `base_scraper_fast.py` | ? | 高速版ベース | v2? | ⚠️ 要確認 |
| `base_scraper_v2.py` | ? | ベーススクレイパーv2 | v2 | ⚠️ 要確認 |
| `safe_scraper_base.py` | ? | 安全版ベース | 現役 | ✅ 保持 |
| **Race Scrapers（2バージョン）** |
| `race_scraper.py` | 275行 | レーススクレイパー | v1 | ⚠️ 要確認 |
| `race_scraper_v2.py` | 532行 | レーススクレイパーv2 | v2 | ✅ 保持 |
| **Historical Scrapers（2種類）** |
| `historical_scraper.py` | ? | 過去データ取得 | v1 | ⚠️ 要確認 |
| `safe_historical_scraper.py` | ? | 安全版過去データ | v2 | ✅ 保持 |
| **Odds Scrapers（2種類）** |
| `odds_scraper.py` | 71行 | オッズ取得 | 現役 | ✅ 保持 |
| `odds_fetcher.py` | ? | オッズフェッチャー | 代替? | ⚠️ 要確認 |
| **Tenji Scrapers（2種類）** |
| `original_tenji_scraper.py` | ? | オリジナル展示 | v1 | ⚠️ 要確認 |
| `original_tenji_browser.py` | 217行 | オリジナル展示（ブラウザ版） | v2 | ✅ 保持 |
| **Tide Scrapers（2種類+1パーサー）** |
| `tide_scraper.py` | 179行 | 潮位スクレイパー | v1 | ✅ 保持 |
| `tide_browser_scraper.py` | 242行 | 潮位（ブラウザ版） | v2 | ✅ 保持 |
| `rdmdb_tide_parser.py` | 385行 | RDMDB潮位パーサー | 現役 | ✅ 保持 |
| **Other Scrapers** |
| `weather_scraper.py` | 65行 | 天候スクレイパー | 現役 | ✅ 保持 |
| `schedule_scraper.py` | 92行 | スケジュール取得 | 現役 | ✅ 保持 |
| `beforeinfo_scraper.py` | ? | 事前情報スクレイパー | 現役? | ⚠️ 要確認 |
| `result_scraper.py` | ? | 結果スクレイパー | 現役? | ⚠️ 要確認 |
| `bulk_scraper.py` | ? | 一括スクレイパー | ユーティリティ | ✅ 保持 |

---

## 問題点

### 1. バージョン管理の曖昧さ

**問題**:
- `race_scraper.py` と `race_scraper_v2.py` のどちらが現役？
- `base_scraper.py`, `base_scraper_fast.py`, `base_scraper_v2.py` の関係は？
- `historical_scraper.py` vs `safe_historical_scraper.py` の使い分けは？

**影響**:
- 開発者が選択に迷う
- 古いバージョンの保守コストが無駄
- バグ修正が一部にしか適用されない可能性

### 2. 命名規則の不統一

**問題**:
- `scraper` vs `fetcher` vs `parser` の使い分けが不明確
- `safe_` プレフィックスの意味が不明
- `_browser` サフィックスの位置づけが不明

**影響**:
- ファイルの目的が推測しにくい
- 可読性の低下

### 3. 機能重複の可能性

**問題**:
- 同じ機能を異なるファイルで実装している可能性
- v1とv2で同じコードが重複

**影響**:
- メンテナンスコストの増加
- バグ修正の漏れ

---

## 整理戦略

### Step 1: 使用状況の調査

各スクレイパーのインポート状況を確認:

```bash
# 使用状況を調査
grep -r "from src.scraper.base_scraper " . --include="*.py"
grep -r "from src.scraper.race_scraper " . --include="*.py"
grep -r "from src.scraper.historical_scraper " . --include="*.py"
# ... 各ファイルについて実施
```

### Step 2: バージョン判定

| ファイルペア | 判定基準 | 決定 |
|------------|---------|------|
| `race_scraper.py` vs `race_scraper_v2.py` | インポート数、行数、更新日時 | v2を採用、v1を削除 or アーカイブ |
| `base_scraper.py` vs `base_scraper_v2.py` | 使用状況、機能充実度 | 要調査 |
| `historical_scraper.py` vs `safe_historical_scraper.py` | エラー処理の充実度 | safe版を採用 |
| `original_tenji_scraper.py` vs `original_tenji_browser.py` | 動作確認、信頼性 | browser版を採用 |

### Step 3: 統合・削除

#### 削除候補

1. **古いバージョン**
   - `race_scraper.py` → v2があるため削除
   - `historical_scraper.py` → safe版があるため削除
   - `original_tenji_scraper.py` → browser版があるため削除
   - `base_scraper.py` → v2または safe版に統一

2. **未使用ファイル**
   - インポートされていないファイルを特定
   - 削除前にバックアップ

#### 統合候補

1. **Base Scrapers の統合**
   ```
   現状: base_scraper.py, base_scraper_fast.py, base_scraper_v2.py, safe_scraper_base.py

   統合案:
   - safe_scraper_base.py を唯一のベースクラスとして採用
   - 他は削除

   または:
   - base_scraper_v2.py をメインに
   - safe機能を統合
   - base_scraper.py と base_scraper_fast.py は削除
   ```

2. **Odds Scrapers の統合**
   ```
   現状: odds_scraper.py, odds_fetcher.py

   統合案:
   - 機能が重複していれば、どちらか一方に統合
   - 異なる役割であれば、明確に命名変更
   ```

---

## 推奨ファイル構成（整理後）

### 理想的な構成

```
src/scraper/
├── __init__.py                    # モジュール初期化
├── base.py                        # ベーススクレイパー（safe_scraper_base.py から改名）
│
├── race.py                        # レーススクレイパー（race_scraper_v2.py から改名）
├── result.py                      # 結果スクレイパー
├── beforeinfo.py                  # 事前情報スクレイパー
│
├── odds.py                        # オッズ取得（odds_scraper.py から改名）
│
├── tenji.py                       # オリジナル展示（original_tenji_browser.py から改名）
│
├── tide.py                        # 潮位スクレイパー（tide_scraper.py から改名）
├── tide_browser.py                # 潮位ブラウザ版（tide_browser_scraper.py から改名）
├── tide_parser.py                 # RDMDB潮位パーサー（rdmdb_tide_parser.py から改名）
│
├── weather.py                     # 天候スクレイパー（weather_scraper.py から改名）
├── schedule.py                    # スケジュール取得（schedule_scraper.py から改名）
│
├── bulk.py                        # 一括スクレイパー（bulk_scraper.py から改名）
└── historical.py                  # 過去データ取得（safe_historical_scraper.py から改名）
```

**メリット**:
- ✅ シンプルで明快
- ✅ `_scraper` サフィックスを削除（フォルダ名で明確）
- ✅ バージョン番号なし（常に最新版のみ保持）
- ✅ 一目で目的がわかる

---

## 段階的実行計画

### Phase 1: 調査（1日）

1. **使用状況の完全調査**
   ```bash
   # すべてのスクレイパーのインポート状況を調査
   for file in src/scraper/*.py; do
       filename=$(basename "$file" .py)
       echo "=== $filename ==="
       grep -r "from src.scraper.$filename import" . --include="*.py"
       grep -r "import src.scraper.$filename" . --include="*.py"
   done > scraper_usage_report.txt
   ```

2. **各ファイルの内容確認**
   - ファイルサイズ
   - 最終更新日
   - 主要クラス・関数
   - ドキュメント文字列

3. **バージョン比較**
   - `race_scraper.py` vs `race_scraper_v2.py`
   - `base_scraper.py` vs `base_scraper_v2.py` vs `safe_scraper_base.py`
   - etc.

### Phase 2: バックアップ（15分）

```bash
# バックアップディレクトリ作成
mkdir -p backup/scraper_backup_20251103

# 全スクレイパーをバックアップ
cp -r src/scraper/* backup/scraper_backup_20251103/

# Git コミット
git add .
git commit -m "Backup: スクレイパー整理前のバックアップ"
```

### Phase 3: 削除（1日）

1. **明らかに古いバージョンを削除**
   ```bash
   # 例: race_scraper.py を削除（v2があるため）
   git rm src/scraper/race_scraper.py

   # インポート文を修正
   find . -name "*.py" -type f -exec sed -i 's/from src.scraper.race_scraper/from src.scraper.race_scraper_v2/g' {} +
   ```

2. **未使用ファイルを削除**
   - 使用状況レポートで0件のファイルを削除

3. **動作確認**
   ```bash
   # Streamlit UI起動確認
   streamlit run ui/app.py

   # 各タブの動作確認
   # - データ収集機能
   # - 予想機能
   ```

### Phase 4: 改名（半日）

**注意**: この段階は破壊的変更が大きいため、慎重に実施

```bash
# 例: race_scraper_v2.py → race.py
git mv src/scraper/race_scraper_v2.py src/scraper/race.py

# インポート文を一括変更
find . -name "*.py" -type f -exec sed -i 's/from src.scraper.race_scraper_v2/from src.scraper.race/g' {} +
```

### Phase 5: ドキュメント更新（半日）

1. **HANDOVER.md 更新**
2. **SYSTEM_SPECIFICATION.md 更新**
3. **README.md 更新**
4. **本ファイル（SCRAPER_CONSOLIDATION_PLAN.md）を最終版に更新**

---

## 最小限アプローチ（推奨）

大規模な改名は避け、**削除のみ**を実施:

### 削除候補（確実）

1. **古いバージョン**
   - `race_scraper.py` （v2があるため）
   - `historical_scraper.py` （safe版があるため）
   - `original_tenji_scraper.py` （browser版があるため）

2. **重複ベースクラス**
   - `base_scraper.py` と `base_scraper_fast.py` のどちらか（使用状況次第）

### 実行手順

```bash
# 1. 使用状況確認（必須）
grep -r "from src.scraper.race_scraper import" . --include="*.py"

# 2. 結果が0件であれば削除
git rm src/scraper/race_scraper.py

# 3. 動作確認
streamlit run ui/app.py

# 4. コミット
git commit -m "削除: 未使用のrace_scraper.py（v2に統合済み）"
```

---

## リスク管理

### リスク1: 隠れた依存関係

**対策**:
- 削除前に必ず grep でインポート検索
- バックアップを必ず作成
- 段階的に削除（一度に1ファイルずつ）

### リスク2: 動作不良

**対策**:
- 各削除後に Streamlit UI を起動確認
- データ収集機能をテスト実行
- エラーが出たら即座にバックアップから復元

### リスク3: 開発履歴の喪失

**対策**:
- Git で履歴を保持
- バックアップディレクトリを長期保管
- 削除理由をドキュメント化

---

## 期待される成果

### 短期的成果

- ✅ ファイル数の削減（21 → 15程度）
- ✅ バージョン管理の明確化
- ✅ 選択の迷いがなくなる

### 長期的成果

- ✅ メンテナンスコストの削減
- ✅ 新規開発者のオンボーディング改善
- ✅ バグ修正の効率化

---

## 次のステップ

### 即座に実行可能

1. **使用状況調査スクリプト実行** - 1時間
2. **調査結果の分析** - 30分
3. **削除候補リストの確定** - 30分

### 承認後に実行

4. **バックアップ作成** - 5分
5. **古いバージョンの削除** - 1時間
6. **動作確認** - 1時間
7. **ドキュメント更新** - 30分

---

## まとめ

### 推奨アクション

**最小限アプローチを採用**: 古いバージョンの削除のみ

**理由**:
1. リスクが低い
2. 即座に実行可能
3. 効果が明確（ファイル数削減）
4. 改名は将来的に検討

### 判断が必要な項目

❓ 以下のファイルペアのどちらを残すべきか？
- `base_scraper.py` vs `base_scraper_v2.py` vs `safe_scraper_base.py`
- `odds_scraper.py` vs `odds_fetcher.py`
- `beforeinfo_scraper.py` の使用状況

→ **次のステップ**: 使用状況調査スクリプトを実行し、判断材料を収集

---

**作成者**: Claude
**バージョン**: 1.0
**最終更新**: 2025年11月3日
