from datetime import datetime, timezone, timedelta


def get_pst_now():
    try:
        from zoneinfo import ZoneInfo
        pst_tz = ZoneInfo("Asia/Manila")
        return datetime.now(pst_tz)
    except Exception:
        local_tz = timezone(timedelta(hours=8))
        return datetime.now(local_tz)
