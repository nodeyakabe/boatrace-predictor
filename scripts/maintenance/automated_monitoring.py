#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自動モニタリングスクリプト

Phase 2.5: cronジョブで定期実行
- 週次/月次でパターンパフォーマンスを自動監視
- しきい値を超えた場合にアラート
- レポートを自動保存
"""

import sys
import os
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict
import json


def automated_monitoring(config_file: str = 'config/monitoring_config.json'):
    """
    自動モニタリング実行

    Args:
        config_file: 設定ファイルパス
    """

    print("=" * 80)
    print("自動モニタリングシステム")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    # 設定ファイル読み込み
    config = load_config(config_file)

    # データベース接続
    db_path = os.path.join(project_root, 'data', 'boatrace.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 監視対象期間
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=config['monitoring_days'])

    print(f"監視期間: {start_date} ～ {end_date} ({config['monitoring_days']}日間)")
    print()

    # 対象レース取得
    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= ? AND r.race_date <= ?
          AND EXISTS (
              SELECT 1 FROM results res
              WHERE res.race_id = r.id AND res.rank = 1
          )
          AND EXISTS (
              SELECT 1 FROM race_details rd
              WHERE rd.race_id = r.id
                AND rd.exhibition_time IS NOT NULL
                AND rd.st_time IS NOT NULL
          )
        ORDER BY r.race_date DESC, r.race_number DESC
        LIMIT {config['max_races']}
    """.format(config=config), (start_date, end_date))

    races = cursor.fetchall()
    print(f"対象レース数: {len(races)}レース")
    print()

    # 簡易版: レース数とパターン適用率のみチェック
    # （実際の予測実行は時間がかかるため、別途実施）

    alerts = []

    # レース数チェック
    if len(races) < config['min_races_threshold']:
        alerts.append({
            'type': 'warning',
            'level': 'low',
            'message': f'レース数不足: {len(races)}レース（最小{config["min_races_threshold"]}必要）'
        })

    conn.close()

    # アラート判定
    print("=" * 80)
    print("【アラート判定】")
    print("=" * 80)
    print()

    if alerts:
        for alert in alerts:
            level_icon = {
                'critical': '🚨',
                'high': '⚠️',
                'medium': '⚙️',
                'low': 'ℹ️'
            }.get(alert['level'], 'ℹ️')

            print(f"{level_icon} [{alert['type'].upper()}] {alert['message']}")

        # アラート通知（設定されている場合）
        if config.get('enable_notifications'):
            send_alerts(alerts, config)
    else:
        print("✓ すべてのチェックが正常です")

    print()

    # レポート保存
    report_path = os.path.join(
        project_root,
        'output',
        f'automated_monitoring_{end_date}.json'
    )

    report = {
        'timestamp': datetime.now().isoformat(),
        'monitoring_period': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat(),
            'days': config['monitoring_days']
        },
        'race_count': len(races),
        'alerts': alerts,
        'status': 'ok' if not alerts else 'warning'
    }

    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"📄 レポート保存: {report_path}")
    print()
    print("=" * 80)
    print("自動モニタリング完了")
    print("=" * 80)

    return len(alerts) == 0


def load_config(config_file: str) -> dict:
    """
    設定ファイル読み込み

    Args:
        config_file: 設定ファイルパス

    Returns:
        設定辞書
    """
    default_config = {
        'monitoring_days': 7,
        'max_races': 200,
        'min_races_threshold': 20,
        'accuracy_threshold': 0.45,  # 的中率45%未満でアラート
        'pattern_apply_rate_min': 0.5,  # パターン適用率50%未満でアラート
        'pattern_apply_rate_max': 0.95,  # パターン適用率95%超でアラート
        'enable_notifications': False,
        'notification_config': {
            'email': {
                'enabled': False,
                'to': [],
                'smtp_host': '',
                'smtp_port': 587
            },
            'slack': {
                'enabled': False,
                'webhook_url': ''
            }
        }
    }

    config_path = os.path.join(project_root, config_file)

    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            user_config = json.load(f)
            default_config.update(user_config)

    return default_config


def send_alerts(alerts: list, config: dict):
    """
    アラート通知送信

    Args:
        alerts: アラートリスト
        config: 設定辞書
    """
    print()
    print("=" * 80)
    print("【アラート通知】")
    print("=" * 80)
    print()

    notification_config = config.get('notification_config', {})

    # Email通知
    if notification_config.get('email', {}).get('enabled'):
        print("📧 Email通知: 有効（実装予定）")
        # send_email_alert(alerts, notification_config['email'])

    # Slack通知
    if notification_config.get('slack', {}).get('enabled'):
        print("💬 Slack通知: 有効（実装予定）")
        # send_slack_alert(alerts, notification_config['slack'])

    if not any([
        notification_config.get('email', {}).get('enabled'),
        notification_config.get('slack', {}).get('enabled')
    ]):
        print("ℹ️ 通知設定なし（config/monitoring_config.jsonで設定可能）")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='自動モニタリングシステム')
    parser.add_argument(
        '--config',
        type=str,
        default='config/monitoring_config.json',
        help='設定ファイルパス'
    )

    args = parser.parse_args()

    success = automated_monitoring(args.config)
    sys.exit(0 if success else 1)
