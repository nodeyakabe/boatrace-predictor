# 推奨スクリプト一覧

**最終更新**: 2025年11月18日
**整理前**: 233個のPythonファイル → **整理後**: 約60個（75%削減）

---

## データ収集スクリプト

### レース基本データ
| スクリプト | 用途 | 推奨度 |
|----------|------|--------|
| [fetch_historical_data.py](fetch_historical_data.py) | 過去データ一括取得（メイン） | ⭐⭐⭐ |
| [fetch_original_tenji_daily.py](fetch_original_tenji_daily.py) | オリジナル展示の日次収集 | ⭐⭐⭐ |
| [fetch_all_data_comprehensive.py](fetch_all_data_comprehensive.py) | 包括的データ収集 | ⭐⭐ |
| [fetch_improved_v3.py](fetch_improved_v3.py) | V3スクレイパー版 | ⭐⭐ |
| [fetch_parallel_v6.py](fetch_parallel_v6.py) | 並列処理版 | ⭐⭐ |

### オリジナル展示収集（重要）
| スクリプト | 用途 | 推奨度 |
|----------|------|--------|
| [収集_オリジナル展示_日付指定.py](収集_オリジナル展示_日付指定.py) | **UI向け・日付直接指定** | ⭐⭐⭐ **推奨** |
| [収集_オリジナル展示_手動実行.py](収集_オリジナル展示_手動実行.py) | 相対日付指定（-1, 0, +1） | ⭐⭐ |

### 補完スクリプト
| スクリプト | 用途 | 推奨度 |
|----------|------|--------|
| [補完_race_details_INSERT対応_高速版.py](補完_race_details_INSERT対応_高速版.py) | **race_details作成（並列6スレッド）** | ⭐⭐⭐ **推奨** |
| [補完_風向データ_改善版.py](補完_風向データ_改善版.py) | 風向データ補完 | ⭐⭐ |
| [補完_天候データ_改善版.py](補完_天候データ_改善版.py) | 天候データ補完 | ⭐⭐ |
| [補完_レース詳細データ_改善版v4.py](補完_レース詳細データ_改善版v4.py) | レース詳細補完 | ⭐⭐ |

### 統合スクリプト
| スクリプト | 用途 | 推奨度 |
|----------|------|--------|
| [過去データ一括取得_統合版.py](過去データ一括取得_統合版.py) | 過去データ一括取得 | ⭐⭐ |
| [過去データ収集_完全版.py](過去データ収集_完全版.py) | races → details → 展示の順で収集 | ⭐⭐ |
| [fix_st_times.py](fix_st_times.py) | STタイムデータ補充 | ⭐⭐ |

---

## モデル・予測スクリプト

### 学習・バックテスト
| スクリプト | 用途 | 推奨度 |
|----------|------|--------|
| [train_conditional_model.py](train_conditional_model.py) | 条件付きランクモデル学習 | ⭐⭐⭐ |
| [run_backtest.py](run_backtest.py) | バックテスト実行 | ⭐⭐⭐ |
| [backtest_prediction.py](backtest_prediction.py) | 予測バックテスト | ⭐⭐ |

### 予測
| スクリプト | 用途 | 推奨度 |
|----------|------|--------|
| [predict_today.py](predict_today.py) | 今日のレース予測 | ⭐⭐⭐ |

### 分析（最近作成）
| スクリプト | 用途 | 推奨度 |
|----------|------|--------|
| [analyze_model_bias.py](analyze_model_bias.py) | モデルバイアス分析 | ⭐⭐⭐ |
| [test_probability_adjustment.py](test_probability_adjustment.py) | 確率補正効果検証 | ⭐⭐⭐ |
| [test_full_prediction_yesterday.py](test_full_prediction_yesterday.py) | 統合予測テスト | ⭐⭐ |

---

## ユーティリティスクリプト

### データベース管理
| スクリプト | 用途 | 推奨度 |
|----------|------|--------|
| [init_database.py](init_database.py) | データベース初期化 | ⭐⭐⭐ |
| [update_database.py](update_database.py) | データベース更新 | ⭐⭐ |
| [check_db_status.py](check_db_status.py) | データベース状況確認 | ⭐⭐⭐ |

### プロジェクト管理
| スクリプト | 用途 | 推奨度 |
|----------|------|--------|
| [cleanup_project.py](cleanup_project.py) | プロジェクトクリーンアップ | ⭐⭐ |
| [cleanup_execute.py](cleanup_execute.py) | クリーンアップ実行（本スクリプト） | ⭐⭐⭐ |
| [backup_project.py](backup_project.py) | プロジェクトバックアップ | ⭐⭐⭐ |
| [create_zip_package.py](create_zip_package.py) | プロジェクトZIP作成 | ⭐⭐ |

### テスト（最近作成のみ残存）
| スクリプト | 用途 | 推奨度 |
|----------|------|--------|
| [test_original_tenji_data.py](test_original_tenji_data.py) | オリジナル展示データ取得テスト | ⭐⭐ |
| [test_beforeinfo_direct.py](test_beforeinfo_direct.py) | BeforeInfoスクレイパーテスト | ⭐⭐ |
| [debug_odds_fetch.py](debug_odds_fetch.py) | オッズ取得デバッグ | ⭐⭐ |
| [test_odds_yesterday.py](test_odds_yesterday.py) | オッズ取得テスト | ⭐⭐ |

---

## UI関連

### Streamlit UI
| スクリプト | 用途 | 推奨度 |
|----------|------|--------|
| [ui/app.py](ui/app.py) | メインUIアプリ | ⭐⭐⭐ |
| [ui/pages/*.py](ui/pages/) | 各ページUI | ⭐⭐⭐ |

---

## アーカイブ済みスクリプト

以下のスクリプトは [archive/scripts_old/](archive/scripts_old/) に移動されました：

### 移動されたカテゴリ
- **test_*.py** - 104個のテスト・デバッグスクリプト
- **check_*.py** - 古い確認スクリプト
- **analyze_*.py** - 古い分析スクリプト
- **補完_*.py** - 古いバージョンの補完スクリプト
- **収集_*.py** - 古いバージョンの収集スクリプト
- **fetch_*.py** - 古いバージョンのfetchスクリプト

必要に応じて `archive/scripts_old/` から復元可能です。

---

## 使用例

### 1. 昨日のデータ収集（UI向け）
```bash
python 収集_オリジナル展示_日付指定.py 2025-11-17
```

### 2. race_details作成（高速版）
```bash
python 補完_race_details_INSERT対応_高速版.py 2025-11-17 2025-11-17
```

### 3. モデル学習
```bash
python train_conditional_model.py
```

### 4. バックテスト
```bash
python run_backtest.py
```

### 5. 今日のレース予測
```bash
python predict_today.py
```

---

## 注意事項

### オリジナル展示データ
- **重要**: オリジナル展示データは「昨日」と「今日」のみ利用可能
- 2日前以前のデータは自動削除される
- 日次自動収集を設定すること（[DAILY_COLLECTION_SETUP.md](DAILY_COLLECTION_SETUP.md)参照）

### データ収集の推奨順序
1. `fetch_historical_data.py` - racesテーブル作成
2. `補完_race_details_INSERT対応_高速版.py` - race_details作成
3. `収集_オリジナル展示_日付指定.py` - オリジナル展示収集

---

## 関連ドキュメント

- [README.md](README.md) - プロジェクト概要
- [COMPREHENSIVE_DATA_COLLECTION_README.md](COMPREHENSIVE_DATA_COLLECTION_README.md) - データ収集システム
- [オリジナル展示収集_UI連携ガイド.md](オリジナル展示収集_UI連携ガイド.md) - UI連携ガイド
- [docs/プロジェクト全体レビュー_20251118.md](docs/プロジェクト全体レビュー_20251118.md) - プロジェクト全体レビュー
- [CLEANUP_PLAN_20251118.md](CLEANUP_PLAN_20251118.md) - クリーンアップ計画

---

**整理実施日**: 2025年11月18日
**整理者**: Claude Code
