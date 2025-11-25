# 🎯 システム改善計画書

## アドバイス分析結果

### 目標
- **的中率**: 40〜55%（AI選定レース内）
- **回収率**: 110〜130%
- **手法**: 2段階モデル + Kelly基準投資戦略

---

## 📊 現状評価

### ✅ 既に実装済み
1. **データ基盤**
   - SQLiteデータベース
   - 選手・モーター・レース結果データ
   - 天候・展示タイムデータ
   - 潮汐データ

2. **特徴量（基本）**
   - 選手勝率、級別
   - モーター・ボート連対率
   - 展示タイム、STタイミング
   - コース別成績
   - 場所別成績

3. **モデル基盤**
   - XGBoostモデル
   - SHAP説明可能性
   - モデル保存・読み込み機能

4. **UI**
   - Streamlit UI
   - データ収集・管理機能
   - 選手詳細分析
   - 場攻略分析

### ⚠️ 未実装・改善必要

1. **2段階モデル（最重要！）**
   - ❌ Stage1: レース選別モデル
   - ❌ Stage2: 着順予測モデル

2. **投資戦略**
   - ❌ 期待値ベースの購入判定
   - ❌ Kelly基準での資金配分
   - ❌ リスク調整機能

3. **特徴量強化**
   - ❌ レース内展示順位（exh_rank_in_race）
   - ❌ Target Encoding
   - ❌ Frequency Encoding
   - ❌ 潮汐の相対的影響（tide_rel）

4. **モデル改善**
   - ❌ 確率校正（Calibration）
   - ❌ 時系列K-fold CV
   - ❌ LightGBM対応

5. **評価指標**
   - ❌ Precision@K, Recall@K
   - ❌ 月次ROI
   - ❌ 最大ドローダウン

6. **運用機能**
   - ❌ 週次自動再学習
   - ❌ A/Bテスト機能
   - ❌ パフォーマンスモニタリング

---

## 🎯 実装優先順位

### 【Phase 1】最優先（2週間）

#### 1.1 Stage1: レース選別モデル（1週間）
**目的**: 予想しやすいレースを選ぶ

**実装内容**:
```python
# src/ml/race_selector.py
class RaceSelector:
    """
    レース選別モデル（Stage1）

    出力: buy_score（0〜1の確率）
    - 1に近い = 予想しやすいレース
    - 0に近い = 予想困難なレース
    """

    def calculate_predictability_features(self, race_data):
        """
        予想しやすさを判定する特徴量

        1. データ充足率
           - 展示タイムデータの有無
           - 選手成績データの充実度
           - モーター成績データの充実度

        2. レースの安定性
           - コース別勝率の分散（小さいほど安定）
           - 選手実力差（大きいほど予想しやすい）
           - モーター性能差

        3. 過去の予測精度
           - 同条件レースでの的中率
           - 同会場での的中率

        4. 荒れにくさ指標
           - 1号艇逃げ率
           - インコース勝率
           - 万舟率（低いほど安定）
        """
        features = {
            # データ充足率
            'exh_data_completeness': ...,
            'racer_data_quality': ...,
            'motor_data_quality': ...,

            # レース安定性
            'course_winrate_variance': ...,
            'racer_skill_gap': ...,
            'motor_perf_gap': ...,

            # 過去精度
            'venue_accuracy': ...,
            'similar_race_accuracy': ...,

            # 荒れにくさ
            'escape_rate': ...,
            'inside_winrate': ...,
            'upset_rate': ...
        }
        return features
```

**学習データラベル**:
```python
# 過去レースで実際に的中したか（1）、外れたか（0）
# または、予測確率と実際の結果の乖離度
```

**評価指標**:
- Stage1スコア > 0.6 のレースだけを選定
- そのレースの的中率が目標（40-55%）達成

---

#### 1.2 期待値ベースの投資戦略（1週間）
**目的**: 期待値プラスの買い目のみ購入

**実装内容**:
```python
# src/betting/kelly_strategy.py
class KellyBettingStrategy:
    """
    Kelly基準での投資戦略
    """

    def calculate_expected_value(self, pred_prob, odds):
        """
        期待値 = pred_prob × odds - 1

        Args:
            pred_prob: モデル予測確率（校正済み）
            odds: オッズ

        Returns:
            expected_value: 期待値
        """
        return pred_prob * odds - 1

    def kelly_criterion(self, pred_prob, odds, bankroll, fraction=0.25):
        """
        Kelly基準での賭け金計算

        Args:
            pred_prob: 勝率予測
            odds: オッズ
            bankroll: 資金
            fraction: リスク調整（0.25 = 1/4 Kelly）

        Returns:
            bet_size: 賭け金
        """
        p = pred_prob
        b = odds - 1  # 純利益倍率
        q = 1 - p

        # Kelly formula: (bp - q) / b
        kelly_fraction = (b * p - q) / b

        # フラクショナルKelly（リスク削減）
        bet_fraction = max(0, kelly_fraction * fraction)

        return bankroll * bet_fraction

    def select_bets(self, race_predictions, odds_data, min_ev=0.05):
        """
        購入すべき買い目を選定

        Args:
            race_predictions: 予測結果
            odds_data: オッズデータ
            min_ev: 最小期待値（5%以上）

        Returns:
            selected_bets: 購入推奨買い目リスト
        """
        bets = []

        for pred in race_predictions:
            ev = self.calculate_expected_value(pred['prob'], pred['odds'])

            if ev > min_ev:
                bet_size = self.kelly_criterion(
                    pred['prob'],
                    pred['odds'],
                    bankroll=10000,
                    fraction=0.25
                )

                bets.append({
                    'combination': pred['combination'],
                    'pred_prob': pred['prob'],
                    'odds': pred['odds'],
                    'expected_value': ev,
                    'recommended_bet': bet_size
                })

        return sorted(bets, key=lambda x: x['expected_value'], reverse=True)
```

**UIへの統合**:
```python
# リアルタイム予想画面に追加
st.subheader("💰 推奨購入戦略")

for bet in recommended_bets:
    st.markdown(f"""
    **{bet['combination']}**
    - 予測確率: {bet['pred_prob']:.1%}
    - オッズ: {bet['odds']:.0f}倍
    - 期待値: {bet['expected_value']:.1%}
    - 推奨購入額: ¥{bet['recommended_bet']:.0f}
    """)
```

---

### 【Phase 2】高優先（2週間）

#### 2.1 特徴量強化（1週間）

**追加特徴量**:
```python
# 1. レース内展示順位
def calc_exhibition_rank_in_race(race_data):
    """展示タイムのレース内順位"""
    race_data['exh_rank_in_race'] = race_data.groupby('race_id')['exhibition_time'].rank()
    return race_data

# 2. Target Encoding
from category_encoders import TargetEncoder

def apply_target_encoding(X_train, y_train, X_test, categorical_cols):
    """
    カテゴリ変数をTarget Encodingで数値化

    例: 選手ID → その選手の平均勝率
    """
    encoder = TargetEncoder(cols=categorical_cols)
    X_train_encoded = encoder.fit_transform(X_train, y_train)
    X_test_encoded = encoder.transform(X_test)
    return X_train_encoded, X_test_encoded

# 3. 潮汐の相対的影響
def calc_tide_relative(race_data):
    """
    潮汐の影響を相対化

    - 満潮時を+1、干潮時を-1
    - 場所ごとの潮汐影響度を考慮
    """
    tide_mapping = {'満潮': 1.0, '上げ': 0.5, '下げ': -0.5, '干潮': -1.0}
    race_data['tide_rel'] = race_data['tide_type'].map(tide_mapping)

    # 場所ごとの潮汐影響度で重み付け
    venue_tide_impact = {...}  # DBから取得
    race_data['tide_rel_weighted'] = race_data['tide_rel'] * race_data['venue_code'].map(venue_tide_impact)

    return race_data
```

---

#### 2.2 確率校正（3日）

**実装内容**:
```python
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression

class ProbabilityCalibrator:
    """
    予測確率の校正

    生のモデル出力確率を、実際の的中確率に近づける
    """

    def calibrate_platt(self, model, X_val, y_val):
        """
        Platt Scaling

        ロジスティック回帰で確率を校正
        """
        calibrated = CalibratedClassifierCV(
            model,
            method='sigmoid',
            cv='prefit'
        )
        calibrated.fit(X_val, y_val)
        return calibrated

    def calibrate_isotonic(self, y_true, y_pred):
        """
        Isotonic Regression

        より柔軟な校正（単調増加制約のみ）
        """
        calibrator = IsotonicRegression(out_of_bounds='clip')
        calibrator.fit(y_pred, y_true)
        return calibrator
```

**効果**:
- 予測確率 50% → 実際の的中率も約50%
- Kelly基準での賭け金計算の精度向上

---

#### 2.3 時系列K-fold CV（3日）

**実装内容**:
```python
from sklearn.model_selection import TimeSeriesSplit

def time_series_cross_validation(data, n_splits=5):
    """
    時系列を考慮したクロスバリデーション

    訓練データに未来情報が混入しないように分割
    """
    tscv = TimeSeriesSplit(n_splits=n_splits)

    scores = []
    for train_idx, val_idx in tscv.split(data):
        train_data = data.iloc[train_idx]
        val_data = data.iloc[val_idx]

        # モデル学習
        model = train_model(train_data)

        # 評価
        score = evaluate_model(model, val_data)
        scores.append(score)

    return np.mean(scores), np.std(scores)
```

---

### 【Phase 3】中優先（2週間）

#### 3.1 評価指標の拡充（1週間）

**追加指標**:
```python
class AdvancedMetrics:
    """
    高度な評価指標
    """

    def precision_at_k(self, y_true, y_pred_proba, k=10):
        """
        上位K件の精度

        予測確率上位K件のうち、何件が的中したか
        """
        top_k_indices = np.argsort(y_pred_proba)[-k:]
        return y_true[top_k_indices].mean()

    def recall_at_k(self, y_true, y_pred_proba, k=10):
        """
        上位K件の再現率

        実際の的中のうち、何%を上位K件でカバーしたか
        """
        top_k_indices = np.argsort(y_pred_proba)[-k:]
        return y_true[top_k_indices].sum() / y_true.sum()

    def monthly_roi(self, bet_results):
        """
        月次ROI（投資収益率）

        (獲得金額 - 投資金額) / 投資金額
        """
        monthly_stats = bet_results.groupby(bet_results['date'].dt.to_period('M')).agg({
            'bet_amount': 'sum',
            'return_amount': 'sum'
        })

        monthly_stats['roi'] = (monthly_stats['return_amount'] - monthly_stats['bet_amount']) / monthly_stats['bet_amount']

        return monthly_stats

    def max_drawdown(self, balance_series):
        """
        最大ドローダウン

        資金の最大下落幅
        """
        cummax = balance_series.cummax()
        drawdown = (balance_series - cummax) / cummax
        return drawdown.min()
```

---

#### 3.2 運用機能（1週間）

**週次自動再学習**:
```python
# scripts/weekly_retrain.py
import schedule
import time

def weekly_retrain_job():
    """
    週次でモデルを再学習
    """
    print(f"[{datetime.now()}] 週次再学習を開始")

    # 1. 最新データを取得
    data = fetch_latest_data(days=180)

    # 2. モデル学習
    model = train_model(data)

    # 3. 評価
    metrics = evaluate_model(model)

    # 4. 性能が向上していれば保存
    if metrics['accuracy'] > current_best_accuracy:
        model.save('models/latest_model.pkl')
        log_model_update(metrics)

    print(f"[{datetime.now()}] 週次再学習が完了")

# スケジュール設定
schedule.every().sunday.at("02:00").do(weekly_retrain_job)

while True:
    schedule.run_pending()
    time.sleep(3600)  # 1時間ごとにチェック
```

**パフォーマンスモニタリング**:
```python
# ui/pages/performance_monitor.py
def render_performance_monitor():
    """
    モデルのパフォーマンスをモニタリング
    """
    st.header("📊 パフォーマンスモニタリング")

    # 1. 的中率の推移
    st.subheader("的中率の推移（週次）")
    fig_accuracy = plot_weekly_accuracy()
    st.plotly_chart(fig_accuracy)

    # 2. 回収率の推移
    st.subheader("回収率の推移（月次）")
    fig_roi = plot_monthly_roi()
    st.plotly_chart(fig_roi)

    # 3. 最大ドローダウン
    st.metric("最大ドローダウン", f"{max_dd:.1%}")

    # 4. アラート
    if current_accuracy < threshold:
        st.error("⚠️ 精度が低下しています！モデル再学習を検討してください")
```

---

## 🚀 実装スケジュール

### Week 1-2: Phase 1（最優先）
- [ ] Stage1: レース選別モデル実装
- [ ] Kelly基準投資戦略実装
- [ ] UIへの統合

### Week 3-4: Phase 2（高優先）
- [ ] 特徴量強化（展示順位、Target Encoding等）
- [ ] 確率校正実装
- [ ] 時系列K-fold CV実装

### Week 5-6: Phase 3（中優先）
- [ ] 評価指標拡充
- [ ] 週次自動再学習機能
- [ ] パフォーマンスモニタリングUI

---

## 📝 注意事項

### 必須ルール
1. **時系列厳守**
   - 訓練データに未来情報が混入しないこと
   - 日付順でデータを分割
   - オッズは予測時点で取得できるものに限定

2. **正規化**
   - player_id, motor_no は必ず正規化
   - 場所コード、レースタイプもエンコーディング

3. **検証**
   - SHAPで特徴量の寄与を確認
   - 未来情報が含まれていないかチェック
   - バックテストで実運用シミュレーション

---

## 🎯 目標達成基準

### 短期目標（2ヶ月）
- [ ] Stage1モデルの実装完了
- [ ] Kelly戦略の実装完了
- [ ] バックテストで的中率30%以上

### 中期目標（4ヶ月）
- [ ] 的中率40%達成（AI選定レース内）
- [ ] 回収率110%達成
- [ ] 自動運用機能の完成

### 長期目標（6ヶ月）
- [ ] 的中率50%以上
- [ ] 回収率120%以上
- [ ] 完全自動化運用
