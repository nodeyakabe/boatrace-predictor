# ボーターズ分析レポート

## 実施日: 2025-12-06（Opus深掘り分析追加）

## 概要

ボーターズ（https://boaters-boatrace.com）のデータ分析手法を調査し、本プロジェクトで未活用だった情報・分析を特定。効果的な特徴量を実装し、バックテストで検証を行った。

---

## 1. ボーターズで発見した未活用情報

### 1.1 ボーターズの主要指標

| 指標 | 説明 | 本プロジェクトでの状況 |
|------|------|----------------------|
| AI3連対率 | ボーターズ独自のAI予測指標 | 独自指標のため対象外 |
| モーター順位 | 会場内でのモーターランキング | **未活用** → 実装済み |
| モーター展示タイム平均 | モーターの平均展示タイム | **未活用** → 実装済み |
| 今節成績 | 現在の節での着順パターン | **未活用** → 実装済み |
| コース別連対率 | 特定コースからの連対率 | **未活用** → 実装済み |
| 予測ST | 過去STからの推定値 | **未活用** → 実装済み |
| モーター優出/優勝数 | モーターの実績 | **未活用** → 実装済み |

### 1.2 公式サイトで取得可能なデータ確認

- 全ての必要データは公式サイトから取得可能
- ボーターズはアーカイブを残さないため、データ取得は公式サイトを優先

---

## 2. 実装した新規特徴量

### 2.1 新規特徴量一覧（24個）

```python
# src/features/boaters_inspired_features.py に実装

# モーター関連
- motor_venue_rank      # 会場内モーターランキング
- motor_venue_2ren      # モーター会場2連率
- motor_tenji_avg       # モーター展示タイム平均
- motor_tenji_diff_from_venue  # 展示タイム会場平均との差
- motor_yushutsu_count  # 優出回数
- motor_yusho_count     # 優勝回数
- motor_sg_g1_rate      # SG/G1での2連率

# 今節成績
- node_race_count       # 今節出走数
- node_avg_rank         # 今節平均着順
- node_win_rate         # 今節勝率
- node_2ren_rate        # 今節2連率
- node_3ren_rate        # 今節3連率
- node_trend            # 調子トレンド

# コース別成績（最重要）
- course_race_count     # コース別出走数
- course_win_rate       # コース別勝率 ★Top1
- course_2ren_rate      # コース別2連率 ★Top2
- course_3ren_rate      # コース別3連率
- course_avg_rank       # コース別平均着順 ★Top3

# ST関連
- predicted_st          # 予測ST
- st_stability          # ST安定性（標準偏差）
- early_st_rate         # 早いST率（0.10秒以下）
- late_st_rate          # 遅いST率（0.20秒以上）
- st_variance           # STばらつき
- aggressive_index      # 攻め度
```

### 2.2 実装ファイル

- `src/features/boaters_inspired_features.py` - 新規特徴量計算モジュール
- `src/ml/dataset_builder.py` - DatasetBuilderへの統合

---

## 3. バックテスト結果

### 3.1 テスト条件

| 項目 | 値 |
|------|-----|
| データ期間 | 2024-10-01 〜 2024-11-30 |
| 分割日 | 2024-11-15 |
| サンプルサイズ | 17,730行 |
| Train | 14,902行 |
| Test | 2,828行 |

### 3.2 モデル性能比較

| 指標 | ベースライン | 新規特徴量追加 | 改善率 |
|------|------------|--------------|--------|
| **AUC** | 0.8374 | 0.8401 | **+0.33%** |
| Accuracy | 0.8589 | 0.8586 | -0.04% |
| Precision | 0.6294 | 0.6212 | -1.30% |
| Recall | 0.4104 | 0.4271 | **+4.07%** |
| Log Loss | 0.3372 | 0.3366 | **+0.18%** |

### 3.3 特徴量重要度ランキング

**Top 20 特徴量**（★は新規特徴量）:

1. is_inner: 0.5205
2. pit_number: 0.1368
3. ★ **course_win_rate: 0.0457** (Top1新規)
4. is_outer: 0.0186
5. win_rate_rank: 0.0178
6. ★ **course_2ren_rate: 0.0149** (Top2新規)
7. win_rate: 0.0109
8. ★ **course_avg_rank: 0.0100** (Top3新規)
9. st_time: 0.0085
10. exhibition_time_rank: 0.0078
11. ★ node_avg_rank: 0.0077
12. third_rate: 0.0072
13. ★ course_3ren_rate: 0.0068
14. local_second_rate: 0.0068
15. ★ late_st_rate: 0.0068
16. ★ motor_venue_2ren: 0.0067
17. local_win_rate: 0.0063
18. ★ predicted_st: 0.0062
19. ★ motor_tenji_diff_from_venue: 0.0061
20. ★ node_3ren_rate: 0.0061

### 3.4 新規特徴量の重要度合計

**全体の18.71%** を新規特徴量が占める

---

## 4. 効果分析

### 4.1 有効だった特徴量

| 特徴量 | 重要度 | 効果 |
|--------|--------|------|
| course_win_rate | 0.0457 | コース適性を直接反映。最も効果的 |
| course_2ren_rate | 0.0149 | 2着以内に入る能力を評価 |
| course_avg_rank | 0.0100 | 安定した着順傾向を捉える |
| node_avg_rank | 0.0077 | 今節の調子を反映 |
| motor_venue_2ren | 0.0067 | モーター性能の会場内相対評価 |
| predicted_st | 0.0062 | STの予測に有効 |

### 4.2 効果が限定的だった特徴量

| 特徴量 | 重要度 | 理由 |
|--------|--------|------|
| motor_sg_g1_rate | 0.0000 | SG/G1データが少ない会場が多い |
| motor_yusho_count | 0.0046 | 優勝データが少ない |
| node_race_count | 0.0048 | 今節の出走数自体は予測に寄与しにくい |

### 4.3 結論

- **AUCは0.33%改善**（0.8374 → 0.8401）
- **Recallは4.07%改善**（的中を逃さない能力が向上）
- 新規特徴量は全体の約19%の重要度を持つ
- **コース別成績（course_win_rate）が最も効果的**

---

## 5. 今後の改善提案

### 5.1 さらなる改善の可能性

1. **コース別成績の細分化**
   - 会場×コース別の成績
   - 天候×コース別の成績

2. **今節成績の拡張**
   - 今節のモーター成績
   - 今節のST平均

3. **時系列特徴量の追加**
   - 直近N節のトレンド
   - 季節性の考慮

### 5.2 推奨する使用方法

```python
from src.ml.dataset_builder import DatasetBuilder

builder = DatasetBuilder()

# 全特徴量を含むデータセット構築
df = builder.build_training_dataset(start_date, end_date)
df = builder.add_all_derived_features(df, include_boaters=True)
```

---

## 6. バックアップ情報

変更を元に戻す場合:
```
models_backup_20251206_143221/
```
にバックアップが保存されています。

---

## 7. 実装ファイル一覧

| ファイル | 説明 |
|---------|------|
| `src/features/boaters_inspired_features.py` | 新規特徴量計算モジュール |
| `src/ml/dataset_builder.py` | DatasetBuilder統合（更新） |
| `tests/test_boaters_features_backtest.py` | バックテストスクリプト |
| `temp/boaters_features_backtest_result.json` | バックテスト結果 |
| `docs/BOATERS_ANALYSIS_REPORT.md` | 本レポート |

---

## 8. まとめ

ボーターズの分析手法を参考に、24個の新規特徴量を実装した。バックテストの結果、AUCが0.33%改善し、Recallが4.07%向上した。

特に**コース別成績（course_win_rate, course_2ren_rate, course_avg_rank）**が効果的であり、選手のコース適性を正確に捉えることで予測精度が向上した。

これらの特徴量は既存のDatasetBuilderに統合済みであり、`add_all_derived_features(df, include_boaters=True)`で使用可能。

---

## 追加分析: Opus深掘り（会場×コース特徴量）

### 9. Opus分析による発見

#### 9.1 会場間のコース勝率差（最大25%の差）

| 会場タイプ | 1コース勝率 | 代表的な会場 |
|-----------|-----------|-------------|
| **イン有利** | 65-70% | 徳山(69.8%), 大村(68.8%), 下関(67.4%) |
| **荒れやすい** | 45-49% | 江戸川(45.1%), 平和島(46.7%), 戸田(45.7%) |

#### 9.2 条件別の影響

| 条件 | 1コース勝率への影響 |
|-----|-------------------|
| 強風(5m+) | **-5.8%** |
| 荒水(6cm+) | **-9.8%** |

#### 9.3 サンプルサイズ問題と解決策

| 問題 | 解決策 |
|------|--------|
| 選手×会場×コースは平均2.8走しかない | ベイズ推定でスムージング |
| 60%の組み合わせが1-2走のみ | 全国コース成績との加重平均 |

---

### 10. 会場×コース特徴量の実装

**ファイル**: [src/features/venue_course_features.py](../src/features/venue_course_features.py)

```python
# 実装された新規特徴量（11個）
- venue_course_advantage      # 会場コース有利度（静的、最大25%差）
- recent_course_win_rate      # 直近10走のコース別勝率
- recent_course_2ren_rate     # 直近10走のコース別2連率
- recent_course_avg_rank      # 直近10走のコース別平均着順
- wind_course_factor          # 風条件×コース調整係数
- wave_course_factor          # 波高×コース調整係数
- condition_course_factor     # 条件×コース調整係数（統合）
- racer_venue_skill           # 選手の会場適性（ベイズ推定）
- racer_course_skill          # 選手のコース適性（ベイズ推定）
- racer_venue_course_skill    # 選手×会場×コース適性（ベイズ推定）★最重要
- racer_venue_course_combined # 統合スコア★Top2
```

---

### 11. 会場×コース特徴量のバックテスト結果

| 指標 | ベースライン | 新規特徴量追加 | 改善率 |
|------|------------|--------------|--------|
| **AUC** | 0.8345 | 0.8357 | **+0.14%** |
| **Accuracy** | 0.8309 | 0.8587 | **+3.34%** |
| **Recall** | 0.0021 | 0.4538 | **大幅改善** |
| **Log Loss** | 0.3666 | 0.3381 | **+7.8%** |

#### 特徴量重要度ランキング

| 順位 | 特徴量 | 重要度 |
|------|--------|--------|
| **1** | racer_venue_course_skill | **0.1620** |
| **2** | racer_venue_course_combined | **0.1421** |
| 3 | is_outer | 0.0808 |
| **4** | racer_course_skill | **0.0751** |
| 5 | win_rate_rank | 0.0566 |

**会場×コース特徴量の重要度合計: 49.63%**（全体の約半分）

---

### 12. 最終的な使用方法

```python
from src.ml.dataset_builder import DatasetBuilder

builder = DatasetBuilder()

# データセット構築
df = builder.build_training_dataset(start_date, end_date)

# 全特徴量追加（ボーターズ + 会場×コース）
df = builder.add_all_derived_features(
    df,
    include_boaters=True,        # ボーターズ特徴量
    include_venue_course=True    # 会場×コース特徴量（推奨）
)
```

---

### 13. 追加ファイル一覧

| ファイル | 説明 |
|---------|------|
| `src/features/venue_course_features.py` | 会場×コース特徴量モジュール |
| `tests/test_venue_course_features_backtest.py` | バックテストスクリプト |
| `temp/venue_course_features_backtest_result.json` | バックテスト結果 |
