# 予測ロジック改善の効率化ガイド v2

**作成日**: 2025-12-22
**目的**: 「たまたま」を排除し、長期的な効果を重視した効率化

---

## 📌 前提認識

### ❌ 避けるべきアプローチ

**短期サンプルでの損切り判断**
- 200件のサンプル検証 → 運要素が大きい
- 1ヶ月（1,500件）検証 → まだ「たまたま」のリスクあり
- **問題**: 本当は良い施策を見逃す可能性

### ✅ 目指すべき方向

**長期的な効果の確実な測定**
- 複数年（2022-2025年、約78,000レース）でのバックテスト
- 統計的に有意な差を確認
- 年度間で安定した効果を確認

---

## 🚀 効率化の本質：処理時間の削減

「短期で見切る」のではなく、「全期間検証を高速化する」アプローチ

### 現状の問題

| 年度 | レース数 | 現在の処理時間（推定） |
|------|---------|---------------------|
| 2022 | 35,883 | 約3-4時間 |
| 2023 | 9,084 | 約1時間 |
| 2024 | 14,014 | 約1.5時間 |
| 2025 | 18,980 | 約2時間 |
| **合計** | **77,961** | **約7-8時間** ❌ |

**問題**: 1つのロジック変更を検証するのに半日以上かかる

---

## ✅ 解決策：処理の最適化

### 【戦略1】予測ロジック自体の高速化（最重要）

#### 現状のボトルネック調査

```python
# どの処理が遅いかプロファイリング
python scripts/profile_prediction_performance.py --race-id 12345
```

予想されるボトルネック：
1. **DB読み込み** - 同じデータを何度も取得
2. **特徴量計算** - 毎回ゼロから計算
3. **モデル推論** - 複数モデルを逐次実行
4. **階層的予測** - Stage1→2→3の依存関係

#### 最適化案

**A. 日次一括ロード（既に実装済み）**
```python
# BatchDataLoaderを使用
predictor = RacePredictor(use_cache=True)
predictor.batch_loader.load_daily_data('2025-06-15')
```

**効果**: 1レース 11秒 → 3秒（約70%削減）

**B. 特徴量の事前計算・キャッシュ**

現在：レースごとに選手の直近成績を毎回計算
↓
改善：全選手×全日付の特徴量を事前計算してテーブル化

```sql
-- racer_features テーブル（既存）
-- racer_venue_features テーブル（既存）
-- motor_features テーブル（未使用 → 活用）
```

**効果**: さらに30-50%削減の可能性

**C. 並列処理の最大化**

現在：1プロセスで1日分を処理
↓
改善：日ごとに完全独立して並列処理

```python
# 8コア並列で処理
# 2022年: 3時間 → 30-40分（75%削減）
```

---

### 【戦略2】差分予測の活用

全レースを再生成するのではなく、**変更の影響を受ける部分のみ再計算**

#### ロジック変更の種類別対応

| 変更種類 | 影響範囲 | 再計算の必要性 |
|---------|---------|--------------|
| **スコアリング重み変更** | 全レース | ✅ 全再計算必要 |
| **新特徴量追加** | 全レース | ✅ 全再計算必要 |
| **フィルター条件変更** | 購入判定のみ | ❌ 予測は再利用可能 |
| **買い目パターン変更** | 買い目生成のみ | ❌ 予測は再利用可能 |

#### 実装例

```python
# 予測データは既存を使い、フィルターだけ変更して検証
from src.betting.bet_target_evaluator import BetTargetEvaluator

evaluator = BetTargetEvaluator()

# 既存の予測データを読み込み
conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

for race in races:
    # 予測データを取得（再生成不要）
    predictions = get_existing_predictions(race_id)

    # 新しいフィルターで購入判定
    should_buy, reason = evaluator.evaluate_race(race_id, predictions)

    # バックテスト
    # ...
```

**効果**: 予測再生成（7-8時間）→ フィルター検証（10-30分）= **95%削減**

---

### 【戦略3】段階的な全期間検証

全年度を一気に処理せず、順次確認しながら進める

#### ワークフロー

```
Step 1: 2025年のみ再生成（40分）
  ↓
  効果確認（ROI、的中率）
  ↓
  ✅ プラス → Step 2へ
  ❌ マイナス → 中止（40分で判断）

Step 2: 2024年も再生成（1時間）
  ↓
  2年間の効果確認
  ↓
  ✅ 両年でプラス → Step 3へ
  ❌ 片方マイナス → 検討（要因分析）

Step 3: 2022-2023年も再生成（2時間）
  ↓
  4年間の効果確認
  ↓
  ✅ 全年度でプラス → 本採用
```

**効果**:
- 2025年でマイナスなら40分で中止（従来: 7-8時間）
- 段階的に確認→リスク低減

**注意**: これも「たまたま」のリスクはあるが、複数年で確認することで軽減

---

### 【戦略4】インクリメンタル検証

ロジック変更を小さく分割して、1つずつ検証

#### 例：「決まり手別展開予測」の実装

**従来のアプローチ（一気に実装）**:
```python
# 一度に全部実装
- 決まり手確率計算
- 展開予測ロジック
- 2着・3着スコア調整
- まくりリスク調整

↓
全期間再生成（7-8時間）
↓
効果測定
```

**改善アプローチ（段階的実装）**:
```python
# Step 1: 決まり手確率計算のみ
kimarite_flow_prediction: True
makuri_risk_adjustment: False
↓
2025年のみ再生成（40分）
↓
効果: +2.0pt確認

# Step 2: まくりリスク調整を追加
makuri_risk_adjustment: True
↓
2025年のみ再生成（40分）
↓
効果: +4.1pt（さらに改善）

# Step 3: 全期間で確認
↓
全年度再生成（2-3時間）
```

**効果**:
- 各段階で効果を確認→無駄な実装を減らせる
- 問題が起きたときの切り分けが容易

---

## 🔧 具体的な実装

### 【実装1】予測処理のプロファイリングツール

```python
# scripts/profile_prediction_performance.py
import cProfile
import pstats
from src.analysis.race_predictor import RacePredictor

def profile_prediction():
    predictor = RacePredictor(use_cache=True)

    # 100レース分の処理をプロファイル
    profiler = cProfile.Profile()
    profiler.enable()

    for race_id in range(100000, 100100):
        try:
            predictor.predict_race(race_id)
        except:
            pass

    profiler.disable()

    # 結果を表示
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(20)  # 上位20個の遅い処理を表示

profile_prediction()
```

**効果**: どこが遅いか特定→ピンポイントで最適化

---

### 【実装2】差分バックテストツール

予測データを再利用して、フィルター条件だけ変更して高速検証

```python
# scripts/fast_filter_backtest.py
"""
既存の予測データを使い、フィルター条件だけ変更して高速バックテスト

処理時間: 10-30分（予測再生成: 7-8時間 → 95%削減）
"""
import sqlite3
from src.betting.bet_target_evaluator import BetTargetEvaluator
from config.settings import DATABASE_PATH

def fast_filter_backtest(year: str):
    evaluator = BetTargetEvaluator()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # その年の全レースを取得
    cursor.execute("""
        SELECT r.id
        FROM races r
        WHERE r.race_date LIKE ? || '%'
        ORDER BY r.race_date
    """, (year,))

    race_ids = [row[0] for row in cursor.fetchall()]

    stats = {
        'purchase_count': 0,
        'total_investment': 0,
        'total_return': 0
    }

    for race_id in race_ids:
        # 既存の予測データを読み込み（再生成不要）
        cursor.execute("""
            SELECT pit_number, rank_prediction, total_score, confidence
            FROM race_predictions
            WHERE race_id = ?
            AND prediction_type = 'advance'
            ORDER BY rank_prediction
        """, (race_id,))

        predictions = []
        for row in cursor.fetchall():
            predictions.append({
                'pit_number': row[0],
                'rank_prediction': row[1],
                'total_score': row[2],
                'confidence': row[3]
            })

        if not predictions:
            continue

        # 新しいフィルターで購入判定
        should_buy, reason = evaluator.evaluate_race(race_id, predictions)

        if should_buy:
            stats['purchase_count'] += 1
            stats['total_investment'] += 400

            # 払戻を計算
            top3 = predictions[:3]
            combination = f"{top3[0]['pit_number']}-{top3[1]['pit_number']}-{top3[2]['pit_number']}"

            cursor.execute("""
                SELECT amount
                FROM payouts
                WHERE race_id = ?
                AND bet_type = 'trifecta'
                AND combination = ?
            """, (race_id, combination))

            payout_row = cursor.fetchone()
            if payout_row:
                stats['total_return'] += payout_row[0]

    conn.close()

    # 結果表示
    if stats['total_investment'] > 0:
        roi = stats['total_return'] / stats['total_investment'] * 100
        profit = stats['total_return'] - stats['total_investment']

        print(f"購入レース数: {stats['purchase_count']}")
        print(f"投資額: {stats['total_investment']:,}円")
        print(f"払戻額: {stats['total_return']:,}円")
        print(f"収支: {profit:+,}円")
        print(f"ROI: {roi:.1f}%")

# 使い方
fast_filter_backtest('2025')
```

**効果**: フィルター調整だけなら予測再生成不要→ 10-30分で検証可能

---

### 【実装3】並列処理の改善版

年度ごとに完全独立して並列処理

```python
# scripts/regenerate_multi_year_parallel.py
from concurrent.futures import ProcessPoolExecutor
import subprocess

def regenerate_year(year):
    """1年分の予測を再生成（独立プロセス）"""
    subprocess.run([
        'python', 'scripts/regenerate_predictions_single_year.py',
        '--year', str(year)
    ])

def regenerate_all_years_parallel():
    years = [2022, 2023, 2024, 2025]

    # 4年分を並列処理（年ごとに独立）
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(regenerate_year, year) for year in years]

        for future in futures:
            future.result()

# 実行
regenerate_all_years_parallel()
```

**効果**: 4年分を並列処理 → 約2-3時間（逐次: 7-8時間 → 60-70%削減）

**注意**: メモリ使用量が増えるため、16GB以上推奨

---

## 📊 最適化の効果比較

| 手法 | 処理時間 | 削減率 | 適用条件 |
|------|---------|--------|---------|
| **現状（逐次処理）** | 7-8時間 | - | - |
| **並列処理（年度別）** | 2-3時間 | **60-70%削減** | メモリ16GB以上 |
| **並列処理（日別）** | 1-2時間 | **80-85%削減** | 既存スクリプト改善 |
| **特徴量事前計算** | 0.5-1時間 | **90%削減** | 実装に1-2日必要 |
| **差分検証（フィルターのみ）** | 10-30分 | **95%削減** | スコアリング変更には不可 |

---

## 🎯 推奨ワークフロー

### ケース1: スコアリングロジック変更

```bash
# Step 1: 最新年度のみ検証（40分）
python scripts/regenerate_predictions_2025_parallel.py

# Step 2: バックテストで効果確認
python scripts/backtest_single_year.py --year 2025

# → プラスなら次へ

# Step 3: 前年度も検証（1時間）
python scripts/regenerate_predictions_single_year.py --year 2024

# → 2年連続プラスなら次へ

# Step 4: 全年度検証（2-3時間、並列処理）
python scripts/regenerate_multi_year_parallel.py
```

**合計**: 約3-4時間（従来: 7-8時間 → 50%削減）

---

### ケース2: フィルター条件変更

```bash
# 予測データは再利用、フィルターのみ変更

# 全年度を一気に検証（10-30分）
python scripts/fast_filter_backtest.py --year 2025
python scripts/fast_filter_backtest.py --year 2024
python scripts/fast_filter_backtest.py --year 2023
python scripts/fast_filter_backtest.py --year 2022
```

**合計**: 10-30分（従来: 7-8時間 → **95%削減**）

---

## 💡 長期的な改善策

### 1. 特徴量の完全な事前計算

**現状**: レースごとに選手の直近成績を毎回計算

**改善**: 全選手×全日付の特徴量を事前計算

```sql
-- 実装すべきテーブル
CREATE TABLE racer_daily_features (
    racer_number TEXT,
    race_date TEXT,
    recent_avg_rank_10 REAL,
    recent_win_rate_10 REAL,
    -- その他の特徴量
    PRIMARY KEY (racer_number, race_date)
);

-- 1度だけ全期間を計算（1日かかる）
python scripts/precompute_all_features.py

-- 以降は高速に予測生成（10倍速）
```

**効果**: 1レース 3秒 → 0.3秒（90%削減）

**実装コスト**: 1-2日

---

### 2. GPU活用（将来的）

機械学習モデル（階層的予測）をGPUで高速化

**効果**: さらに5-10倍高速化の可能性

---

## ✅ まとめ

### 短期で効果を見極めるアプローチ（v1）

- ❌ 「たまたま」のリスクが高い
- ❌ 本当に良い施策を見逃す可能性

### 長期的な効果を確実に測定しつつ効率化（v2）

- ✅ **並列処理**: 7-8時間 → 2-3時間（60-70%削減）
- ✅ **段階的検証**: 最新年度から順次確認（無駄を減らす）
- ✅ **差分検証**: フィルター変更なら95%削減
- ✅ **特徴量事前計算**: 1-2日の実装で90%削減（長期的）

### 次にやるべきこと

1. **即効性**: 並列処理スクリプトの活用
2. **中期**: 差分バックテストツールの実装
3. **長期**: 特徴量の完全な事前計算

---

**作成者**: Claude Sonnet 4.5
