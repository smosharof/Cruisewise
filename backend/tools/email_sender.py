"""Resend-backed transactional email for reprice alerts.

The send is fire-and-forget from the watch-agent's perspective: failures are
logged but do not propagate, so a Resend outage can't poison the reprice
flow. ``send_reprice_email`` returns a bool only so callers can record
delivery status if they want; current callers ignore it.
"""

from __future__ import annotations

import logging

import resend

from backend.config import get_settings

logger = logging.getLogger(__name__)


def send_reprice_email(
    to_email: str,
    ship_name: str,
    cruise_line: str,
    departure_date: str,
    cabin_category: str,
    price_paid: int,
    current_price: int,
    savings: int,
    email_subject: str,
    email_body: str,
) -> bool:
    """Send a price-drop alert email via Resend. Returns True on success."""
    settings = get_settings()
    if not settings.resend_api_key:
        logger.warning("Resend API key not configured — skipping email")
        return False

    try:
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #1a73e8; padding: 24px; border-radius: 8px 8px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 20px;">
                    🎉 Price Drop Alert — {ship_name}
                </h1>
            </div>

            <div style="background: #f8f9fa; padding: 24px; border-radius: 0 0 8px 8px; border: 1px solid #e0e0e0;">
                <p style="font-size: 16px; color: #333;">
                    Good news! The fare for your upcoming cruise has dropped.
                </p>

                <div style="background: white; border-radius: 8px; padding: 16px; margin: 16px 0; border: 1px solid #e0e0e0;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px; color: #666;">Ship</td>
                            <td style="padding: 8px; font-weight: bold;">{ship_name} ({cruise_line})</td>
                        </tr>
                        <tr style="background: #f8f9fa;">
                            <td style="padding: 8px; color: #666;">Departure</td>
                            <td style="padding: 8px; font-weight: bold;">{departure_date}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; color: #666;">Cabin</td>
                            <td style="padding: 8px; font-weight: bold;">{cabin_category.title()}</td>
                        </tr>
                        <tr style="background: #f8f9fa;">
                            <td style="padding: 8px; color: #666;">You paid</td>
                            <td style="padding: 8px; font-weight: bold;">${price_paid:,}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; color: #666;">Current price</td>
                            <td style="padding: 8px; font-weight: bold; color: #34a853;">${current_price:,}</td>
                        </tr>
                        <tr style="background: #e8f5e9;">
                            <td style="padding: 8px; color: #1b5e20; font-weight: bold;">Potential savings</td>
                            <td style="padding: 8px; font-weight: bold; color: #1b5e20; font-size: 18px;">${savings:,}</td>
                        </tr>
                    </table>
                </div>

                <p style="font-size: 14px; color: #333; margin-top: 24px;">
                    <strong>Forward this email to your travel agent:</strong>
                </p>

                <div style="background: white; border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px; font-family: monospace; font-size: 13px; white-space: pre-wrap; color: #333;">
Subject: {email_subject}

{email_body}
                </div>

                <p style="font-size: 12px; color: #999; margin-top: 24px;">
                    Sent by Cruisewise · Price monitoring for cruise travelers
                </p>
            </div>
        </div>
        """

        params = {
            "from": "Cruisewise <noreply@moeshamim.com>",
            "to": [to_email],
            "subject": f"Price Drop Alert: {ship_name} — Save ${savings:,}",
            "html": html_body,
        }

        resend.Emails.send(params)
        logger.info(
            "Reprice email sent to %s for %s savings=$%d",
            to_email,
            ship_name,
            savings,
        )
        return True

    except Exception as e:
        logger.error("Failed to send reprice email to %s: %s", to_email, e)
        return False
