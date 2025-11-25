# BoatRaceプロジェクト コード解析レポート

**解析日**: 2025年11月3日
**解析対象**: 全プロジェクトコード（src/, ui/, ルートディレクトリ）
**総コード行数**: 約26,000行以上
**ファイル数**: 140+ファイル

---

## 目次

1. [プロジェクト概要](#プロジェクト概要)
2. [重大なエラー（即座修正必要）](#重大なエラー即座修正必要)
3. [機能的な問題（未実装機能）](#機能的な問題未実装機能)
4. [設計上の問題](#設計上の問題)
5. [その他の問題点](#その他の問題点)
6. [エラー統計サマリー](#エラー統計サマリー)
7. [優先度別修正推奨順序](#優先度別修正推奨順序)
8. [詳細解析結果](#詳細解析結果)

---

## プロジェクト概要

### 目的
日本の競艇（ボートレース）の統計分析に基づく期待値プラス買い目推奨システム

### プロジェクト構成

```
BoatRace/
├── src/               # コアロジック（21,366行）
│   ├── analysis/      # データ分析・統計（19ファイル）
│   ├── analyzer/      # 分析エンジン（8ファイル）
│   ├── betting/       # ベッティング戦略（1ファイル）
│   ├── database/      # DB管理（5ファイル）
│   ├── ml/            # 機械学習（5ファイル）
│   ├── models/        # MLモデル実装（1ファイル）
│   ├── prediction/    # 予測ルール（1ファイル）
│   ├── scraper/       # スクレイパー（17ファイル）
│   └── utils/         # ユーティリティ（6ファイル）
├── ui/                # Streamlit UI（4,782行）
│   ├── app.py         # メインアプリ（2,233行）
│   └── components/    # UIコンポーネント（8ファイル）
├── data/              # データベース・ログ
├── config/            # 設定ファイル
└── *.py               # 70+個のスクリプト
```

### 技術スタック
- Python 3.8+
- Streamlit（UI）
- SQLite（データベース）
- XGBoost, LightGBM（機械学習）
- BeautifulSoup4, requests（スクレイピング）
- pandas, numpy（データ処理）

---

## 重大なエラー（即座修正必要）

### 1. SQL構文エラー（12箇所）

**ファイル**: `src/analysis/data_coverage_checker.py`
**重大度**: 🔴 高
**影響**: データカバレッジチェック機能が完全に動作不能

#### 問題内容
テーブルエイリアスと列名の間に不要なスペースが挿入されている

#### エラー箇所一覧

| 行番号 | 誤った記述 | 正しい記述 |
|--------|-----------|-----------|
| 136 | `e. racer_number` | `e.racer_number` |
| 148 | `e. racer_rank` | `e.racer_rank` |
| 178 | `res. rank` | `res.rank` |
| 192 | `rd. tilt_angle` | `rd.tilt_angle` |
| 217 | `e. motor_number` | `e.motor_number` |
| 234 | `res. rank` | `res.rank` |
| 248 | `e. boat_number` | `e.boat_number` |
| 265 | `res. rank` | `res.rank` |
| 430 | `rd. actual_course` | `rd.actual_course` |
| 442 | `rd. exhibition_time` | `rd.exhibition_time` |
| 454 | `rd. st_time` | `rd.st_time` |
| 529 | `res. rank` | `res.rank` |

#### 修正方法
```python
# 修正前
"SELECT COUNT(*) FROM entries e WHERE e. racer_number IS NOT NULL"

# 修正後
"SELECT COUNT(*) FROM entries e WHERE e.racer_number IS NOT NULL"
```

#### 修正スクリプト
既に `fix_data_coverage_checker.py` が存在するが、スペース問題には対応していない。
新たに修正スクリプトを作成する必要あり。

---

### 2. モジュールインポートエラー

**ファイル**: `ui/app.py:28`
**重大度**: 🔴 高
**影響**: アプリケーション全体が起動できない

#### 問題内容
```python
from src.ml.shap_explainer import SHAPExplainer
```

`shap` ライブラリが requirements.txt に含まれているが、正しくインポートされない可能性

#### 修正方法

**オプション1**: shap を確実にインストール
```bash
pip install shap
```

**オプション2**: 使用していない場合はインポートを削除またはコメントアウト
```python
# from src.ml.shap_explainer import SHAPExplainer  # 未使用のためコメントアウト
```

#### 確認方法
```bash
python -c "import shap; print(shap.__version__)"
```

---

### 3. SQLインジェクション脆弱性

**ファイル**:
- `ui/components/venue_strategy.py:87`
- `backtest_prediction.py:38`

**重大度**: 🔴 高
**影響**: セキュリティリスク

#### 問題内容
文字列フォーマットで SQL クエリを組み立てている

```python
# 危険な実装
venue_filter = f"AND r.venue_code = '{venue_code}'" if venue_code else ""
query = f"""
    SELECT * FROM races r
    WHERE r.race_date BETWEEN ? AND ?
    {venue_filter}
"""
```

#### 修正方法
パラメータ化クエリを使用

```python
# 安全な実装
if venue_code:
    query = """
        SELECT * FROM races r
        WHERE r.race_date BETWEEN ? AND ?
        AND r.venue_code = ?
    """
    params = (start_date, end_date, venue_code)
else:
    query = """
        SELECT * FROM races r
        WHERE r.race_date BETWEEN ? AND ?
    """
    params = (start_date, end_date,)

df = pd.read_sql_query(query, conn, params=params)
```

---

## 機能的な問題（未実装機能）

### 4. Stage2 モデル学習機能が未実装

**ファイル**: `ui/components/model_training.py:299-301`
**重大度**: 🟡 中
**影響**: ユーザーがモデル学習タブで実際に学習を実行できない

#### 問題内容
```python
def run_training():
    # TODO: 実装
    st.error("❌ データ読み込みが未実装です")
    return
```

#### 必要な実装
1. データセットの読み込み
2. 特徴量エンジニアリング
3. XGBoostモデルの学習
4. モデルの保存
5. 評価指標の表示

---

### 5. モデル評価機能が未実装

**ファイル**: `ui/components/model_training.py:339-340`
**重大度**: 🟡 中

```python
def render_model_evaluation_tab():
    st.info("💡 モデル評価機能は実装中です")
```

#### 必要な実装
1. 学習済みモデルの読み込み
2. テストデータでの評価
3. 混同行列の表示
4. ROC曲線・PR曲線
5. 特徴量重要度の表示

---

### 6. 予想シミュレーション機能が未実装

**ファイル**: `ui/components/model_training.py:356-357`
**重大度**: 🟡 中

```python
def render_prediction_simulation_tab():
    st.info("💡 予想シミュレーション機能は実装中です")
```

---

### 7. Phase 3.3 特徴量生成が未実装

**ファイル**: `src/analysis/feature_generator.py:137-140`
**重大度**: 🟡 中
**影響**: 高度な特徴量が使用できず、予測精度が低下する可能性

```python
def generate_advanced_features(self, df, historical_results=None):
    # TODO: Phase 3.3で実装
    # 1. 直近成績（過去10レースの平均着順）
    # 2. 当地相性（venue_codeごとの成績）
    # 3. 天候・水面条件（別途取得が必要）
    return result_df  # 何もしない
```

#### 必要な実装
- 選手の直近成績（過去N戦の平均着順、勝率等）
- 当地相性スコア（会場別の成績）
- 天候・風速・波高との相関特徴量
- 時間帯別の成績特徴量

---

## 設計上の問題

### 8. モジュールの重複設計

**重大度**: 🟠 中
**影響**: メンテナンス負荷増加、ロジックの不一致リスク

#### 重複しているモジュール
1. `src/analysis/race_predictor.py` ⇔ `src/analyzer/race_predictor.py`
2. `src/analysis/statistics_calculator.py` ⇔ `src/analyzer/statistics_analyzer.py`
3. 他複数のモジュールが analysis/ と analyzer/ で重複

#### 推奨対応
- analysis/ と analyzer/ の役割を明確に分離
- または一方に統合してもう一方を削除
- インターフェースの統一

---

### 9. スクレイパーモジュールの管理不足

**重大度**: 🟠 中
**影響**: 保守性の低下

#### 問題点
- 17個のスクレイパーファイルが存在
- バージョン管理が曖昧（base, fast, v2 など混在）
- 責任分担が不明確
- 古いバージョンが削除されていない

#### スクレイパーファイル一覧
```
src/scraper/
├── abstract_scraper.py          # 抽象基底クラス
├── beforeinfo_scraper.py        # 事前情報
├── beforeinfo_scraper_fast.py   # 高速版
├── kimarite_fetcher.py          # 決まり手
├── odds_fetcher.py              # オッズ
├── odds_scraper.py              # オッズ（別版）
├── race_detail_fetcher.py       # レース詳細
├── race_scraper_base.py         # 基底版
├── race_scraper_v2.py           # V2版
├── result_scraper.py            # 結果
├── results_fetcher.py           # 結果（別版）
├── schedule_fetcher.py          # スケジュール
├── schedule_scraper.py          # スケジュール（別版）
├── tide_browser_scraper.py      # 潮位（ブラウザ版）
├── tide_fetcher.py              # 潮位
├── weather_fetcher.py           # 天気
└── weather_scraper.py           # 天気（別版）
```

#### 推奨対応
1. 共通インターフェース（AbstractScraper）を強化
2. 使用されていない古いバージョンを削除
3. ファイル名の命名規則を統一（*_scraper.py または *_fetcher.py）
4. ドキュメントで各スクレイパーの役割を明記

---

### 10. 例外処理の不足

**重大度**: 🟢 低〜中
**影響**: デバッグが困難

#### 問題のあるパターン
```python
try:
    # 処理
except Exception:
    pass  # エラーを無視
```

#### 該当ファイル
- `src/scraper/result_scraper.py`
- `src/scraper/odds_scraper.py`
- `src/scraper/tide_browser_scraper.py`
- 他多数

#### 推奨対応
```python
import logging

logger = logging.getLogger(__name__)

try:
    # 処理
except Exception as e:
    logger.error(f"エラー発生: {e}", exc_info=True)
    # 必要に応じてリトライや代替処理
```

---

## その他の問題点

### 11. Windowsパス依存

**ファイル**: ui/app.py, ui/components/bulk_data_collector.py 他
**重大度**: 🟢 低

#### 問題内容
```python
python_exe = os.path.join(PROJECT_ROOT, 'venv', 'Scripts', 'python.exe')
```

Windows固有のパス（`Scripts/python.exe`）を使用
Linux/Macでは `bin/python`

#### 推奨対応
```python
# クロスプラットフォーム対応
import sys
python_exe = sys.executable  # 現在のPythonインタープリタを使用
```

---

### 12. SessionState管理の不十分

**ファイル**: `ui/components/model_training.py:218, 235`
**重大度**: 🟢 低

#### 問題内容
タブ切り替え時にセッション状態が失われる可能性

#### 推奨対応
```python
# セッション状態の初期化
if 'selected_features' not in st.session_state:
    st.session_state['selected_features'] = []

# ウィジェットのkeyとsession_stateを連携
st.multiselect(
    "特徴量を選択",
    options=all_features,
    default=st.session_state['selected_features'],
    key='feature_selector'
)
```

---

### 13. ハードコーディングされた値

**ファイル**: `ui/app.py:317`
**重大度**: 🟢 低

```python
st.write("• 1号艇の基本勝率: 48.65% (データから抽出)")
```

#### 問題点
実際のデータと不整合の可能性

#### 推奨対応
```python
# データベースから動的に計算
conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()
cursor.execute("""
    SELECT
        COUNT(CASE WHEN res.rank = 1 THEN 1 END) * 100.0 / COUNT(*) as win_rate
    FROM results res
    JOIN entries e ON res.race_id = e.race_id AND res.boat_number = e.boat_number
    WHERE e.pit_number = 1
""")
win_rate = cursor.fetchone()[0]
st.write(f"• 1号艇の基本勝率: {win_rate:.2f}% (データから算出)")
```

---

### 14. 型ヒント不足

**重大度**: 🟢 低
**影響**: 可読性・保守性の低下

#### 推奨対応
```python
# 型ヒントの追加
from typing import List, Dict, Optional

def get_race_data(
    race_id: int,
    db_path: str = "data/boatrace.db"
) -> Optional[Dict[str, any]]:
    """
    レースデータを取得

    Args:
        race_id: レースID
        db_path: データベースパス

    Returns:
        レースデータ辞書、存在しない場合はNone
    """
    # 実装
```

---

### 15. テストコード不足

**重大度**: 🟢 低
**現状**: ユニットテストがほとんど存在しない

#### 推奨対応
```python
# tests/ ディレクトリを作成
tests/
├── test_database.py
├── test_scrapers.py
├── test_analysis.py
├── test_ml.py
└── conftest.py  # pytest設定

# 例: tests/test_database.py
import pytest
from src.database.data_manager import DataManager

def test_save_race_result():
    dm = DataManager(db_path=":memory:")  # インメモリDB
    race_data = {...}
    result = dm.save_race_result(race_data)
    assert result is True
```

---

## エラー統計サマリー

| カテゴリ | 件数 | 重大度 | 修正優先度 |
|---------|------|--------|-----------|
| SQL構文エラー | 12 | 🔴 高 | 1 |
| モジュールインポートエラー | 1 | 🔴 高 | 1 |
| SQLインジェクション脆弱性 | 2+ | 🔴 高 | 1 |
| 未実装機能 | 4 | 🟡 中 | 2 |
| 設計問題 | 5 | 🟠 中 | 2 |
| 例外処理不足 | 20+ | 🟢 低〜中 | 3 |
| プラットフォーム依存 | 5+ | 🟢 低 | 3 |
| 型ヒント不足 | 多数 | 🟢 低 | 4 |
| テストコード不足 | 全般 | 🟢 低 | 4 |
| **合計** | **49+** | - | - |

---

## 優先度別修正推奨順序

### 最優先（即座に実施）

#### 1. SQL構文エラーの修正
- **ファイル**: `src/analysis/data_coverage_checker.py`
- **作業時間**: 10分
- **方法**: 全12箇所の `エイリアス. カラム名` を `エイリアス.カラム名` に置換

```bash
# 一括置換スクリプトの作成・実行
python fix_sql_syntax_errors.py
```

#### 2. shap ライブラリの確認
- **作業時間**: 5分
- **方法**: インストール確認、または未使用なら削除

```bash
pip install shap
# または
# ui/app.py の該当行をコメントアウト
```

#### 3. SQLインジェクション脆弱性の修正
- **ファイル**:
  - `ui/components/venue_strategy.py`
  - `backtest_prediction.py`
- **作業時間**: 20分
- **方法**: パラメータ化クエリへ書き換え

---

### 高優先度（1週間以内）

#### 4. Stage2 モデル学習機能の実装
- **ファイル**: `ui/components/model_training.py`
- **作業時間**: 2〜3時間
- **内容**: データ読み込み → 特徴量生成 → モデル学習 → 評価

#### 5. モデル評価タブの実装
- **作業時間**: 1〜2時間
- **内容**: 混同行列、ROC曲線、特徴量重要度の表示

#### 6. 予想シミュレーション機能の実装
- **作業時間**: 2〜3時間
- **内容**: 過去データでのシミュレーション実行・結果表示

#### 7. Phase 3.3 特徴量生成の実装
- **ファイル**: `src/analysis/feature_generator.py`
- **作業時間**: 3〜4時間
- **内容**: 直近成績、当地相性、天候相関の特徴量追加

#### 8. 例外処理の強化
- **対象**: 全スクレイパーファイル
- **作業時間**: 2時間
- **内容**: `pass` を `logger.error()` に置換

---

### 中優先度（1ヶ月以内）

#### 9. モジュール重複設計の解消
- **対象**: analysis/ と analyzer/
- **作業時間**: 半日
- **内容**: 役割分担の明確化、または統合

#### 10. スクレイパーの整理・統合
- **対象**: src/scraper/
- **作業時間**: 半日
- **内容**: 古いバージョン削除、命名規則統一、ドキュメント作成

#### 11. Windowsパス依存の解消
- **作業時間**: 30分
- **内容**: `sys.executable` の使用

#### 12. SessionState管理の改善
- **作業時間**: 1時間

#### 13. ハードコーディング値の動的計算化
- **作業時間**: 1時間

---

### 低優先度（将来的に）

#### 14. 型ヒントの追加
- **作業時間**: 数日
- **内容**: 全関数に型ヒント追加

#### 15. テストコードの追加
- **作業時間**: 1週間
- **内容**: pytest を使ったユニットテスト作成

#### 16. ドキュメント整備
- **作業時間**: 数日
- **内容**: API ドキュメント、アーキテクチャ図

#### 17. パフォーマンス最適化
- **作業時間**: 継続的
- **内容**: クエリ最適化、キャッシング導入

---

## 詳細解析結果

### src/ ディレクトリ構造

```
src/
├── analysis/ (19ファイル, 約8,000行)
│   ├── backtest.py                  # バックテスト実行
│   ├── data_coverage_checker.py     # ⚠️ SQL構文エラー12箇所
│   ├── data_explorer.py             # データ探索
│   ├── data_preprocessor.py         # 前処理パイプライン
│   ├── data_quality.py              # データ品質監視
│   ├── feature_calculator.py        # 特徴量計算
│   ├── feature_generator.py         # ⚠️ Phase 3.3未実装
│   ├── grade_analyzer.py            # グレード分析
│   ├── grade_scorer.py              # グレードスコア
│   ├── kimarite_analyzer.py         # 決まり手分析
│   ├── kimarite_scorer.py           # 決まり手スコア
│   ├── motor_analyzer.py            # モーター分析
│   ├── pattern_analyzer.py          # パターン分析
│   ├── race_predictor.py            # 🔄 重複モジュール
│   ├── racer_analyzer.py            # 選手分析
│   ├── realtime_predictor.py        # リアルタイム予想
│   ├── rule_validator.py            # ルール検証
│   └── statistics_calculator.py     # 🔄 重複モジュール
│
├── analyzer/ (8ファイル, 約3,000行)
│   ├── grade_analyzer.py            # 🔄 重複
│   ├── kimarite_analyzer.py         # 🔄 重複
│   ├── motor_analyzer.py            # 🔄 重複
│   ├── pattern_analyzer.py          # 🔄 重複
│   ├── race_predictor.py            # 🔄 重複
│   ├── racer_analyzer.py            # 🔄 重複
│   └── statistics_analyzer.py       # 🔄 重複
│
├── betting/ (1ファイル)
│   └── kelly_strategy.py            # ケリー戦略
│
├── database/ (5ファイル, 約2,000行)
│   ├── models.py                    # テーブル定義
│   ├── data_manager.py              # データ管理
│   ├── fast_data_manager.py         # 高速データ管理
│   ├── views.py                     # ビュー定義
│   └── __init__.py
│
├── ml/ (5ファイル, 約2,500行)
│   ├── model_trainer.py             # XGBoost学習
│   ├── dataset_builder.py           # データセット構築
│   ├── probability_calibration.py   # 確率校正
│   ├── race_selector.py             # レース選定
│   └── shap_explainer.py            # SHAP説明
│
├── prediction/ (1ファイル)
│   └── rule_based_engine.py         # ルールベース予測
│
├── scraper/ (17ファイル, 約5,000行)
│   ├── abstract_scraper.py
│   ├── beforeinfo_scraper.py
│   ├── beforeinfo_scraper_fast.py   # 🔄 重複バージョン
│   ├── kimarite_fetcher.py
│   ├── odds_fetcher.py
│   ├── odds_scraper.py              # 🔄 重複
│   ├── race_detail_fetcher.py
│   ├── race_scraper_base.py         # 🔄 重複バージョン
│   ├── race_scraper_v2.py
│   ├── result_scraper.py            # ⚠️ 例外処理不足
│   ├── results_fetcher.py           # 🔄 重複
│   ├── schedule_fetcher.py
│   ├── schedule_scraper.py          # 🔄 重複
│   ├── tide_browser_scraper.py      # ⚠️ 例外処理不足
│   ├── tide_fetcher.py
│   ├── weather_fetcher.py
│   └── weather_scraper.py           # 🔄 重複
│
└── utils/ (6ファイル, 約1,500行)
    ├── logger.py
    ├── data_validator.py
    ├── date_utils.py
    ├── math_utils.py
    ├── result_manager.py
    └── scoring_config.py
```

### ui/ ディレクトリ構造

```
ui/
├── app.py (2,233行)
│   ├── ⚠️ shap インポートエラー可能性
│   ├── ⚠️ ハードコーディング値
│   └── ⚠️ Windows パス依存
│
└── components/
    ├── backtest.py (281行)
    │   └── バックテスト実行UI
    │
    ├── betting_recommendation.py (333行)
    │   └── Kelly基準購入推奨
    │
    ├── bulk_data_collector.py (248行)
    │   ├── 過去データ一括取得
    │   └── ⚠️ Windows パス依存
    │
    ├── data_export.py (289行)
    │   └── データエクスポート
    │
    ├── model_training.py (746行)
    │   ├── ⚠️ Stage2学習未実装
    │   ├── ⚠️ モデル評価未実装
    │   ├── ⚠️ シミュレーション未実装
    │   └── ⚠️ SessionState管理不足
    │
    ├── original_tenji_collector.py (109行)
    │   └── 展示データ収集
    │
    └── venue_strategy.py (543行)
        └── ⚠️ SQLインジェクション脆弱性
```

### ルートディレクトリ スクリプト（70+ファイル）

#### データ収集系
- `fetch_parallel_v6.py` - 並列データ取得（最新版）
- `fetch_missing_data.py` - 欠損データ補完
- `過去データ一括取得_統合版.py` - 一括取得

#### 補完系
- `補完_決まり手データ_改善版.py`
- `補完_天候データ_改善版.py`
- `補完_払戻金データ.py`
- `補完_風向データ_改善版.py`
- `補完_レース詳細データ_改善版v4.py`

#### 分析・確認系
- `backtest_prediction.py` - ⚠️ SQLインジェクション
- `analyze_collected_data.py`
- `check_db_status.py`
- `check_data_progress.py`

#### テスト系
- `test_odds_fetcher.py`
- `test_kimarite_fix.py`
- `run_tests.py`

#### ユーティリティ系
- `fix_data_coverage_checker.py` - ⚠️ スペースエラー未対応
- `backup_project.py`
- `delete_scripts.py`
- `reanalyze_all.py`

---

## 推奨される即座のアクション

```bash
# ステップ1: SQL構文エラーを修正
# 新しい修正スクリプトを作成・実行（後述）

# ステップ2: shap ライブラリを確認
python -c "import shap; print(shap.__version__)"
# エラーなら
pip install shap

# ステップ3: SQLインジェクション脆弱性を修正
# venue_strategy.py と backtest_prediction.py を手動修正

# ステップ4: requirements.txt を更新
pip freeze > requirements.txt

# ステップ5: 動作確認
streamlit run ui/app.py
```

---

## まとめ

### プロジェクトの強み
- 包括的なデータ収集機構
- 機械学習による予測機能
- 使いやすいStreamlit UI
- 詳細なドキュメント（HANDOVER.md等）

### 主な改善点
1. **SQL構文エラー12箇所** - データ分析機能が動作不能
2. **未実装機能が多い** - UIに表示されているが実際には動作しない
3. **セキュリティ脆弱性** - SQLインジェクションのリスク
4. **設計の重複** - analysis/ と analyzer/ の役割が不明確
5. **スクレイパーの乱立** - 17個のファイルが整理されていない

### 次のステップ
1. 最優先エラーを修正（SQL構文、shap、SQLインジェクション）
2. 未実装機能の実装（Stage2学習、モデル評価等）
3. 設計の見直し（モジュール統合、スクレイパー整理）
4. テストコードの追加
5. ドキュメント整備

---

**作成者**: Claude
**バージョン**: 1.0
**最終更新**: 2025年11月3日
