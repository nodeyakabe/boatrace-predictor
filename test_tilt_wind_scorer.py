"""チルト・風スコアラーのテスト"""
import sys
sys.path.append('.')

from src.scoring.tilt_wind_scorer import TiltWindScorer

scorer = TiltWindScorer()

print("=== チルト・風スコアラー テスト ===")

test_race_id = 133159

for pit in range(1, 7):
    course = pit  # 枠なりと仮定
    result = scorer.calculate_tilt_wind_score(test_race_id, pit, course)
    score = result.get('tilt_wind_score', 0)
    tilt = result.get('tilt_angle', '?')
    wind_dir = result.get('wind_direction', '?')
    wind_spd = result.get('wind_speed', '?')
    print(f"艇{pit}（{course}コース）: チルト={tilt}°、風向={wind_dir}時、風速={wind_spd}m/s → スコア={score:.1f}点")
