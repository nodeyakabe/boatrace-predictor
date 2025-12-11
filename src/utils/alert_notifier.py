#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
アラート通知モジュール

Phase 2.5: Email/Slack通知機能
- しきい値を超えた場合にアラート送信
- Email（SMTP）またはSlack Webhook対応
"""

import smtplib
import json
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional
from datetime import datetime


class AlertNotifier:
    """アラート通知クラス"""

    def __init__(self, config: Dict):
        """
        初期化

        Args:
            config: 通知設定辞書
        """
        self.config = config

    def send_alert(self, alerts: List[Dict], context: Optional[Dict] = None) -> bool:
        """
        アラート送信

        Args:
            alerts: アラートリスト
            context: コンテキスト情報

        Returns:
            送信成功ならTrue
        """
        if not alerts:
            return True

        success = True

        # Email通知
        if self.config.get('email', {}).get('enabled'):
            try:
                self._send_email(alerts, context)
            except Exception as e:
                print(f"Email送信エラー: {e}")
                success = False

        # Slack通知
        if self.config.get('slack', {}).get('enabled'):
            try:
                self._send_slack(alerts, context)
            except Exception as e:
                print(f"Slack送信エラー: {e}")
                success = False

        return success

    def _send_email(self, alerts: List[Dict], context: Optional[Dict] = None):
        """
        Email送信

        Args:
            alerts: アラートリスト
            context: コンテキスト情報
        """
        email_config = self.config['email']

        # メッセージ作成
        subject = f"[BoatRace Alert] パターンシステム監視アラート ({len(alerts)}件)"
        body = self._format_email_body(alerts, context)

        msg = MIMEMultipart()
        msg['From'] = email_config.get('from', 'noreply@boatrace.local')
        msg['To'] = ', '.join(email_config['to'])
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        # SMTP送信
        with smtplib.SMTP(email_config['smtp_host'], email_config['smtp_port']) as server:
            if email_config.get('use_tls', True):
                server.starttls()

            if email_config.get('username') and email_config.get('password'):
                server.login(email_config['username'], email_config['password'])

            server.send_message(msg)

        print(f"✓ Email送信完了: {', '.join(email_config['to'])}")

    def _send_slack(self, alerts: List[Dict], context: Optional[Dict] = None):
        """
        Slack Webhook送信

        Args:
            alerts: アラートリスト
            context: コンテキスト情報
        """
        slack_config = self.config['slack']
        webhook_url = slack_config['webhook_url']

        # メッセージ作成
        message = self._format_slack_message(alerts, context)

        payload = {
            'text': f"BoatRace パターンシステム監視アラート ({len(alerts)}件)",
            'blocks': [
                {
                    'type': 'header',
                    'text': {
                        'type': 'plain_text',
                        'text': f'🚨 監視アラート ({len(alerts)}件)'
                    }
                },
                {
                    'type': 'section',
                    'text': {
                        'type': 'mrkdwn',
                        'text': message
                    }
                }
            ]
        }

        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()

        print(f"✓ Slack送信完了: {webhook_url[:50]}...")

    def _format_email_body(self, alerts: List[Dict], context: Optional[Dict] = None) -> str:
        """Email本文フォーマット"""

        body = []
        body.append("=" * 60)
        body.append("BoatRace パターンシステム 監視アラート")
        body.append("=" * 60)
        body.append("")
        body.append(f"通知時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        if context:
            body.append(f"監視期間: {context.get('monitoring_period', 'N/A')}")
            body.append(f"レース数: {context.get('race_count', 'N/A')}")

        body.append("")
        body.append("【検出されたアラート】")
        body.append("")

        for i, alert in enumerate(alerts, 1):
            level_icon = {
                'critical': '🚨',
                'high': '⚠️',
                'medium': '⚙️',
                'low': 'ℹ️'
            }.get(alert['level'], 'ℹ️')

            body.append(f"{i}. {level_icon} [{alert['type'].upper()}] {alert['message']}")
            if alert.get('details'):
                body.append(f"   詳細: {alert['details']}")
            body.append("")

        body.append("")
        body.append("=" * 60)
        body.append("対応が必要な場合は、以下を確認してください:")
        body.append("  - パターンパフォーマンス: python scripts/monitor_pattern_performance.py")
        body.append("  - パターン更新: python scripts/auto_pattern_update.py")
        body.append("  - フィーチャーフラグ: config/feature_flags.py")
        body.append("=" * 60)

        return '\n'.join(body)

    def _format_slack_message(self, alerts: List[Dict], context: Optional[Dict] = None) -> str:
        """Slackメッセージフォーマット"""

        lines = []

        if context:
            lines.append(f"*監視期間*: {context.get('monitoring_period', 'N/A')}")
            lines.append(f"*レース数*: {context.get('race_count', 'N/A')}")
            lines.append("")

        lines.append("*検出されたアラート*:")
        lines.append("")

        for alert in alerts:
            level_icon = {
                'critical': ':rotating_light:',
                'high': ':warning:',
                'medium': ':gear:',
                'low': ':information_source:'
            }.get(alert['level'], ':information_source:')

            lines.append(f"{level_icon} *[{alert['type'].upper()}]* {alert['message']}")

            if alert.get('details'):
                lines.append(f"  └ {alert['details']}")

        return '\n'.join(lines)


def test_notification():
    """通知テスト"""

    print("=" * 60)
    print("アラート通知テスト")
    print("=" * 60)
    print()

    # テスト用設定（実際の設定ファイルから読み込むことを推奨）
    config = {
        'email': {
            'enabled': False,  # Trueにして設定を記入
            'smtp_host': 'smtp.gmail.com',
            'smtp_port': 587,
            'use_tls': True,
            'username': 'your_email@gmail.com',
            'password': 'your_app_password',
            'from': 'noreply@boatrace.local',
            'to': ['recipient@example.com']
        },
        'slack': {
            'enabled': False,  # Trueにして設定を記入
            'webhook_url': 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
        }
    }

    # テストアラート
    test_alerts = [
        {
            'type': 'warning',
            'level': 'medium',
            'message': 'パターン適用率が低下しています: 45%',
            'details': '通常は80%以上が推奨されます'
        },
        {
            'type': 'info',
            'level': 'low',
            'message': 'レース数: 150レース（正常範囲）'
        }
    ]

    context = {
        'monitoring_period': '2025-12-04 ～ 2025-12-11 (7日間)',
        'race_count': 150
    }

    notifier = AlertNotifier(config)

    if config['email']['enabled'] or config['slack']['enabled']:
        print("通知送信中...")
        success = notifier.send_alert(test_alerts, context)

        if success:
            print("✓ 通知送信成功")
        else:
            print("⚠️ 通知送信失敗（一部）")
    else:
        print("ℹ️ 通知が無効です（config内のenabledをTrueに設定してください）")
        print()
        print("Emailメッセージプレビュー:")
        print(notifier._format_email_body(test_alerts, context))

    print()
    print("=" * 60)


if __name__ == "__main__":
    test_notification()
