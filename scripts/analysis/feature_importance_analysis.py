"""
特徴量重要度分析スクリプト
conditional_rank_v3 モデルの各サブモデル（1着/2着/3着）の特徴量重要度を計測・出力する
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import xgboost as xgb

MODEL_NAME = "conditional_rank_v3_20251216_134119"
MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models")


def load_meta(model_name):
    meta_path = os.path.join(MODELS_DIR, f"{model_name}.meta.json")
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_importance(model_name, rank_type, feature_names, importance_type="gain"):
    model_path = os.path.join(MODELS_DIR, f"{model_name}_{rank_type}.json")
    booster = xgb.Booster()
    booster.load_model(model_path)

    scores = booster.get_score(importance_type=importance_type)
    # XGBoost はインデックス名 f0,f1... を使う場合があるので両方対応
    result = []
    for i, fname in enumerate(feature_names):
        key_by_name = fname
        key_by_index = f"f{i}"
        score = scores.get(key_by_name, scores.get(key_by_index, 0.0))
        result.append((fname, score))

    result.sort(key=lambda x: x[1], reverse=True)
    return result


def print_importance(rank_type, importance_list, top_n=20):
    total = sum(v for _, v in importance_list) or 1
    print(f"\n{'='*60}")
    print(f"  {rank_type}着予測モデル  特徴量重要度 Top {top_n}  (importance_type=gain)")
    print(f"  特徴量数: {len(importance_list)}")
    print(f"{'='*60}")
    print(f"  {'順位':<4} {'特徴量名':<45} {'スコア':>10}  {'割合':>6}")
    print(f"  {'-'*70}")
    for rank, (fname, score) in enumerate(importance_list[:top_n], 1):
        pct = score / total * 100
        print(f"  {rank:<4} {fname:<45} {score:>10.1f}  {pct:>5.1f}%")

    # 未使用特徴量（スコア=0）
    unused = [f for f, s in importance_list if s == 0.0]
    if unused:
        print(f"\n  [!] 未使用(score=0): {len(unused)}個")
        for f in unused:
            print(f"    - {f}")


def categorize_features(importance_list):
    """特徴量をカテゴリ別に集計"""
    categories = {
        "選手成績": ["win_rate", "second_rate", "third_rate", "local_win_rate", "local_second_rate"],
        "機材": ["motor_second_rate", "boat_second_rate"],
        "直前情報": ["avg_st", "exhibition_time", "exhibition_st", "exhibition_course", "tilt_angle"],
        "環境": ["wind_speed", "wave_height", "temperature", "water_temperature"],
        "統合スコア": ["total_score"],
        "相対特徴量(1着比)": [],
        "相対特徴量(2着比)": [],
        "コース相対": [],
    }

    total = sum(v for _, v in importance_list) or 1
    cat_scores = {k: 0.0 for k in categories}

    for fname, score in importance_list:
        matched = False
        for cat, keys in categories.items():
            if fname in keys:
                cat_scores[cat] += score
                matched = True
                break
        if not matched:
            if "diff_pred_first" in fname or "pred_first" in fname:
                cat_scores["相対特徴量(1着比)"] += score
            elif "diff_pred_second" in fname or "pred_second" in fname or "gap_pred" in fname:
                cat_scores["相対特徴量(2着比)"] += score
            elif "course" in fname or "inner" in fname or "outer" in fname or "between" in fname:
                cat_scores["コース相対"] += score

    return {k: (v, v / total * 100) for k, v in cat_scores.items() if v > 0}


def print_category_summary(rank_type, importance_list):
    cat = categorize_features(importance_list)
    print(f"\n  --- カテゴリ別集計 ({rank_type}着) ---")
    for cname, (score, pct) in sorted(cat.items(), key=lambda x: x[1][0], reverse=True):
        bar = "#" * int(pct / 2)
        print(f"  {cname:<22} {pct:>5.1f}%  {bar}")


def main():
    meta = load_meta(MODEL_NAME)

    feature_map = {
        "first":  meta["feature_names"],
        "second": meta["second_feature_names"],
        "third":  meta["third_feature_names"],
    }

    all_results = {}
    for rank_type, feature_names in feature_map.items():
        imp = get_importance(MODEL_NAME, rank_type, feature_names, importance_type="gain")
        all_results[rank_type] = imp

    # 各モデルの重要度を出力
    for rank_type in ["first", "second", "third"]:
        imp = all_results[rank_type]
        print_importance(rank_type, imp, top_n=20)
        print_category_summary(rank_type, imp)

    # 1着モデルに絞った環境データの詳細
    print(f"\n{'='*60}")
    print("  環境データ（風速・波高・気温・水温）の詳細")
    print(f"{'='*60}")
    env_features = ["wind_speed", "wave_height", "temperature", "water_temperature"]
    for rank_type in ["first", "second", "third"]:
        imp = all_results[rank_type]
        total = sum(v for _, v in imp) or 1
        print(f"\n  [{rank_type}着モデル]")
        env_total = 0.0
        for fname, score in imp:
            if fname in env_features:
                pct = score / total * 100
                print(f"    {fname:<25} {score:>10.1f}  ({pct:.2f}%)")
                env_total += score
        print(f"    {'環境データ合計':<25} {env_total:>10.1f}  ({env_total/total*100:.2f}%)")

    # total_score の重要度確認
    print(f"\n{'='*60}")
    print("  total_score（ルールベース統合スコア）の重要度")
    print(f"{'='*60}")
    for rank_type in ["first", "second", "third"]:
        imp_dict = dict(all_results[rank_type])
        total = sum(imp_dict.values()) or 1
        ts = imp_dict.get("total_score", 0.0)
        print(f"  [{rank_type}着]  total_score: {ts:.1f}  ({ts/total*100:.2f}%)")


if __name__ == "__main__":
    main()
