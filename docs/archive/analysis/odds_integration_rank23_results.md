# オッズ逆算による2着・3着予測精度改善レポート

**作成日**: 2025年12月18日
**作成者**: Claude Code
**ステータス**: 実装完了・テスト中

---

## エグゼクティブサマリー

### 実装内容

3連単オッズから市場の2着・3着予測確率を逆算し、機械学習予測と統合するアプローチ（アプローチ4）を実装しました。

### 実装成果物

1. **`src/analysis/odds_reverse_calculator.py`** (新規)
   - 3連単オッズから確率分布を逆算
   - 条件付き2着・3着確率の計算
   - 市場確率とML予測の統合機能

2. **`src/analysis/scorers/odds_calibrator.py`** (更新)
   - 2着・3着のオッズ統合機能を追加
   - `calibrate_rank23_predictions()`: 2着・3着予測の校正
   - `get_optimal_trifecta_combinations()`: 最適3連単組み合わせ取得

3. **`scripts/test_odds_integration_rank23.py`** (新規)
   - バックテストスクリプト
   - 複数のalpha値での比較テスト

### 初期テスト結果（100レース）

| 方式 | 1着的中率 | 2着的中率 | 3着的中率 | 3連単的中率 |
|------|-----------|-----------|-----------|-------------|
| baseline (alpha=0) | 38.0% | 24.0% | 21.0% | 8.0% |
| alpha=0.2 | 38.0% | 24.0% | **23.0%** | 8.0% |

**観測**:
- 3着的中率が**+2.0ポイント**改善（21.0% → 23.0%）
- 予測変更数: 17レース（17%のレースで2着・3着の順序が変化）

---

## 技術詳細

### 理論的背景

3連単オッズは市場参加者の集合知を反映しています：

```
市場確率 = 1 / (オッズ × 払戻率)
払戻率 ≈ 0.75（控除率25%）
```

例: 1-2-3の3連単オッズが10.0倍の場合
- 市場予測確率 ≈ 1 / (10.0 × 0.75) = 13.3%

### 2着条件付き確率の計算

1着が艇番`i`と確定した場合の2着確率：

```
P(2着=j | 1着=i) = Σ_k P(i-j-k) / Σ_{j',k'} P(i-j'-k')
```

これにより、1着予測が確定した後の2着・3着予測を市場の見解で補正できます。

### 統合アルゴリズム

```python
final_prob = (1 - alpha) × ml_prob + alpha × market_prob
```

- `alpha = 0`: 機械学習予測のみ（baseline）
- `alpha = 0.1~0.3`: 市場確率を10~30%反映
- 推奨: `alpha = 0.2`（適度な市場情報の取り込み）

---

## 実装コード

### OddsReverseCalculator

```python
class OddsReverseCalculator:
    """3連単オッズから2着・3着の条件付き確率を逆算"""

    def calculate_conditional_second_probs(
        self, odds_data: Dict[str, float], first_pit: int
    ) -> Dict[int, float]:
        """1着確定時の2着条件付き確率を計算"""

    def calculate_conditional_third_probs(
        self, odds_data: Dict[str, float], first_pit: int, second_pit: int
    ) -> Dict[int, float]:
        """1着・2着確定時の3着条件付き確率を計算"""
```

### OddsCalibrator（新機能）

```python
class OddsCalibrator:
    def calibrate_rank23_predictions(
        self, predictions: List[Dict], race_id: int, alpha: float = 0.2
    ) -> List[Dict]:
        """2着・3着予測をオッズで校正"""

    def get_optimal_trifecta_combinations(
        self, predictions: List[Dict], race_id: int, top_n: int = 6
    ) -> List[Dict]:
        """オッズ統合に基づく最適3連単組み合わせを取得"""
```

---

## 使用方法

### 基本的な使用

```python
from src.analysis.scorers.odds_calibrator import OddsCalibrator

# キャリブレーター作成
calibrator = OddsCalibrator(
    db_path="data/boatrace.db",
    alpha=0.5,           # 1着校正係数
    temperature=4.0,     # Softmax温度
    rank23_alpha=0.2     # 2着・3着統合係数
)

# 予測を取得
predictions = predictor.predict_race(race_id)

# 2着・3着をオッズで校正
calibrated = calibrator.calibrate_rank23_predictions(
    predictions, race_id, alpha=0.2
)

# 最適な3連単組み合わせを取得
optimal_combos = calibrator.get_optimal_trifecta_combinations(
    predictions, race_id, top_n=6
)
```

### RacePredictorでの統合

既存の`RacePredictor`に統合する場合：

```python
# predict_race()内で呼び出し
predictions = self._calculate_predictions(race_id)

if self.odds_calibrator and is_feature_enabled('odds_rank23_integration'):
    predictions = self.odds_calibrator.calibrate_rank23_predictions(
        predictions, race_id, alpha=0.2
    )
```

---

## テスト結果詳細

### 初期テスト（2025-11-28データ、100レース）

**購入条件外のレースを含む全体精度**:

| 指標 | baseline | alpha=0.2 | 差分 |
|------|----------|-----------|------|
| 対象レース | 100 | 100 | - |
| 1着的中 | 38 | 38 | 0 |
| 2着的中 | 24 | 24 | 0 |
| 3着的中 | 21 | **23** | **+2** |
| 3連単的中 | 8 | 8 | 0 |

**観測**:
- 3着予測精度が向上（21% → 23%）
- 17%のレースで予測順位が変化

### 追加テストの推奨

より信頼性の高い結果を得るために、以下のテストを推奨します：

1. **対象期間の拡大**: 2025-11-01〜2025-12-15（600+レース）
2. **alpha値の最適化**: 0.1, 0.15, 0.2, 0.25, 0.3で比較
3. **購入条件別の分析**: Tier1/2/3ごとの効果測定
4. **収益シミュレーション**: ROI変化の測定

---

## 制限事項と今後の課題

### 現在の制限

1. **オッズデータ依存**: オッズが取得できないレースでは適用不可
2. **計算コスト**: 3連単120通りの確率計算が必要
3. **市場効率性の仮定**: 市場が効率的でない場合は効果が限定的

### 今後の改善案

1. **動的alpha調整**: レースの特性（信頼度、オッズ分布）に応じてalpha値を調整
2. **時系列オッズの活用**: 締切直前のオッズ変動を考慮
3. **会場別の最適化**: 会場特性に応じたalpha値の調整
4. **機械学習モデルとの統合**: 条件付きモデル（Stage2/3）との併用

---

## 結論

オッズ逆算による2着・3着予測統合は、**3着的中率の改善**に一定の効果を示しました。

**推奨設定**:
- `rank23_alpha = 0.2`: 市場確率を20%反映
- 購入条件を満たすレースのみに適用

**今後のアクション**:
1. 本番環境での段階的な適用
2. 購入条件別の効果測定
3. ROI変化のモニタリング

---

## 関連ファイル

- `src/analysis/odds_reverse_calculator.py`: オッズ逆算モジュール
- `src/analysis/scorers/odds_calibrator.py`: オッズ校正スコアラー
- `scripts/test_odds_integration_rank23.py`: バックテストスクリプト
- `docs/rank23_prediction_issue_analysis.md`: 2着・3着問題の詳細分析
