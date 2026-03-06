"""
AirAware – Email alert notifications via Supabase + Resend.

Supabase stores subscriber preferences.
Resend sends the actual alert emails.
A background thread checks AQI periodically and fires alerts.

Required env vars:
    SUPABASE_URL      – Your Supabase project URL
    SUPABASE_KEY      – Your Supabase anon/service key
    RESEND_API_KEY    – Your Resend API key
    ALERT_FROM_EMAIL  – Sender email (verified domain in Resend), default: onboarding@resend.dev
"""

import os
import time
import threading
from datetime import datetime, timedelta, timezone

import resend
from supabase import create_client

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
ALERT_FROM_EMAIL = os.environ.get("ALERT_FROM_EMAIL", "onboarding@resend.dev")

CHECK_INTERVAL = 1800  # 30 minutes
COOLDOWN_HOURS = 6     # don't re-alert same subscriber within 6 hours

TABLE = "alert_subscribers"


def _get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def is_configured():
    """Return True if all required services are configured."""
    return bool(SUPABASE_URL and SUPABASE_KEY and RESEND_API_KEY)


# ---------------------------------------------------------------------------
# Subscriber CRUD
# ---------------------------------------------------------------------------
def add_subscriber(email, city="Delhi", aqi_threshold=150):
    """Add or reactivate a subscriber."""
    sb = _get_supabase()
    if sb is None:
        return {"error": "Supabase not configured"}

    # Check if already exists
    existing = (
        sb.table(TABLE)
        .select("id, is_active")
        .eq("email", email)
        .eq("city", city)
        .execute()
    )

    if existing.data:
        # Reactivate + update threshold
        row = existing.data[0]
        sb.table(TABLE).update({
            "is_active": True,
            "aqi_threshold": aqi_threshold,
        }).eq("id", row["id"]).execute()
        return {"status": "reactivated", "email": email, "city": city}

    sb.table(TABLE).insert({
        "email": email,
        "city": city,
        "aqi_threshold": aqi_threshold,
        "is_active": True,
    }).execute()
    return {"status": "subscribed", "email": email, "city": city}


def remove_subscriber(email, city=None):
    """Deactivate a subscriber (soft delete)."""
    sb = _get_supabase()
    if sb is None:
        return {"error": "Supabase not configured"}

    query = sb.table(TABLE).update({"is_active": False}).eq("email", email)
    if city:
        query = query.eq("city", city)
    query.execute()
    return {"status": "unsubscribed", "email": email}


def list_subscribers(city=None):
    """List active subscribers, optionally filtered by city."""
    sb = _get_supabase()
    if sb is None:
        return []
    query = sb.table(TABLE).select("*").eq("is_active", True)
    if city:
        query = query.eq("city", city)
    result = query.execute()
    return result.data or []


# ---------------------------------------------------------------------------
# Email sending via Resend
# ---------------------------------------------------------------------------
def _send_alert_email(to_email, city, aqi_value, status, advice_list):
    """Send a single AQI alert email via Resend."""
    if not RESEND_API_KEY:
        print(f"[Notify] Resend not configured – skipping email to {to_email}")
        return False

    resend.api_key = RESEND_API_KEY

    advice_html = "".join(f"<li>{a}</li>" for a in advice_list)

    html_body = f"""
    <div style="font-family:Arial,sans-serif; max-width:500px; margin:auto; padding:20px;">
        <h2 style="color:#e74c3c;">⚠️ AirAware AQI Alert</h2>
        <p>The air quality in <strong>{city}</strong> has exceeded your alert threshold.</p>
        <div style="background:#f8f9fa; border-radius:8px; padding:16px; text-align:center; margin:16px 0;">
            <div style="font-size:48px; font-weight:bold; color:#e74c3c;">{aqi_value}</div>
            <div style="font-size:14px; color:#666;">Current AQI – {status}</div>
        </div>
        <h3>Health Advisory:</h3>
        <ul>{advice_html}</ul>
        <hr style="margin:20px 0;">
        <p style="font-size:12px; color:#999;">
            You received this because you subscribed to AirAware alerts for {city}.<br>
            <a href="#">Unsubscribe</a>
        </p>
    </div>
    """

    try:
        resend.Emails.send({
            "from": ALERT_FROM_EMAIL,
            "to": [to_email],
            "subject": f"🚨 AQI Alert: {city} at {aqi_value} ({status})",
            "html": html_body,
        })
        print(f"[Notify] Alert email sent to {to_email} for {city} (AQI={aqi_value})")
        return True
    except Exception as e:
        print(f"[Notify] Failed to send email to {to_email}: {e}")
        return False


# ---------------------------------------------------------------------------
# Background checker
# ---------------------------------------------------------------------------
def _check_and_alert(get_city_data_fn, get_aqi_category_fn):
    """Check AQI for all cities with subscribers and send alerts."""
    sb = _get_supabase()
    if sb is None:
        return

    subscribers = list_subscribers()
    if not subscribers:
        return

    # Group subscribers by city
    city_subs = {}
    for sub in subscribers:
        city_subs.setdefault(sub["city"], []).append(sub)

    now = datetime.now(timezone.utc)

    for city, subs in city_subs.items():
        data = get_city_data_fn(city)
        if data is None:
            continue

        aqi_value = float(data["aqi"])
        cat = get_aqi_category_fn(aqi_value)

        for sub in subs:
            if aqi_value < sub["aqi_threshold"]:
                continue

            # Check cooldown
            last_alerted = sub.get("last_alerted_at")
            if last_alerted:
                try:
                    last_dt = datetime.fromisoformat(last_alerted.replace("Z", "+00:00"))
                    if (now - last_dt) < timedelta(hours=COOLDOWN_HOURS):
                        continue
                except (ValueError, TypeError):
                    pass

            sent = _send_alert_email(
                sub["email"], city, aqi_value,
                cat["label"], cat["advice"],
            )

            if sent:
                sb.table(TABLE).update({
                    "last_alerted_at": now.isoformat(),
                }).eq("id", sub["id"]).execute()


def start_alert_checker(get_city_data_fn, get_aqi_category_fn):
    """Start a background thread that checks AQI and sends alerts periodically."""
    if not is_configured():
        print("[Notify] Supabase/Resend not configured – alert checker disabled.")
        return

    def _loop():
        print(f"[Notify] Alert checker started (interval={CHECK_INTERVAL}s, cooldown={COOLDOWN_HOURS}h)")
        while True:
            try:
                _check_and_alert(get_city_data_fn, get_aqi_category_fn)
            except Exception as e:
                print(f"[Notify] Alert check error: {e}")
            time.sleep(CHECK_INTERVAL)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
