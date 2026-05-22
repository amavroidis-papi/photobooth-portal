"""Database boundary for the Operations Portal.

The existing Fleet Management app stores station/event automation state in
Dropbox JSON files. Operations data stays separate and uses Supabase/Postgres.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request


OPERATIONS_SCHEMA = os.environ.get("OPERATIONS_SCHEMA", "operations")
RAW_SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_URL = RAW_SUPABASE_URL
for suffix in ("/auth/v1", "/rest/v1", "/storage/v1"):
    if suffix in SUPABASE_URL:
        SUPABASE_URL = SUPABASE_URL.split(suffix)[0]
        break
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")


class OperationsDatabaseError(RuntimeError):
    pass


class OperationsDatabaseNotConfigured(OperationsDatabaseError):
    pass


def is_configured():
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY)


def _require_config():
    if not is_configured():
        raise OperationsDatabaseNotConfigured(
            "Missing SUPABASE_URL or SUPABASE_ANON_KEY. Add them to Heroku Config Vars."
        )


def _build_url(table_name, query=None):
    base = f"{SUPABASE_URL}/rest/v1/{table_name}"
    if not query:
        return base
    return f"{base}?{query.lstrip('?')}"


def _headers(access_token=None, prefer=None):
    token = access_token or SUPABASE_ANON_KEY
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Accept-Profile": OPERATIONS_SCHEMA,
        "Content-Profile": OPERATIONS_SCHEMA,
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _request(method, table_name, query=None, payload=None, access_token=None, prefer=None):
    _require_config()
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        _build_url(table_name, query),
        data=data,
        headers=_headers(access_token=access_token, prefer=prefer),
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            details = json.loads(raw)
            message = details.get("message") or details.get("hint") or raw
        except Exception:
            message = raw or str(e)
        raise OperationsDatabaseError(message) from e
    except Exception as e:
        raise OperationsDatabaseError(str(e)) from e


def check_connection(access_token=None):
    query = "select=id&limit=1"
    return _request("GET", "events", query=query, access_token=access_token)


def list_clients(access_token=None):
    query = urllib.parse.urlencode({
        "select": "id,client_name,status",
        "order": "client_name.asc",
    })
    return _request("GET", "clients", query=query, access_token=access_token) or []


def list_venues(access_token=None):
    query = urllib.parse.urlencode({
        "select": "id,venue_name,address,google_maps_url",
        "order": "venue_name.asc",
    })
    return _request("GET", "venues", query=query, access_token=access_token) or []


def list_staff(access_token=None):
    query = urllib.parse.urlencode({
        "select": "id,full_name,email,phone,status",
        "order": "full_name.asc",
    })
    return _request("GET", "staff", query=query, access_token=access_token) or []


def list_operations_events(start_date=None, end_date=None, access_token=None):
    filters = {
        "select": (
            "id,event_date,event_name,status,solution_type,event_start_at,"
            "event_end_at,setup_start_at,takedown_start_at,clients(client_name),"
            "venues(venue_name,google_maps_url)"
        ),
        "order": "event_date.asc,event_start_at.asc",
    }
    query_parts = [urllib.parse.urlencode(filters)]
    if start_date:
        query_parts.append(f"event_date=gte.{urllib.parse.quote(str(start_date))}")
    if end_date:
        query_parts.append(f"event_date=lte.{urllib.parse.quote(str(end_date))}")
    return _request("GET", "events", query="&".join(query_parts), access_token=access_token) or []


def list_logistics_tasks(start_at=None, end_at=None, access_token=None):
    filters = {
        "select": (
            "id,event_id,task_type,title,scheduled_start_at,scheduled_end_at,"
            "location_text,assigned_team_text,assigned_vehicle_text,status,priority"
        ),
        "order": "scheduled_start_at.asc",
    }
    query_parts = [urllib.parse.urlencode(filters)]
    if start_at:
        query_parts.append(f"scheduled_start_at=gte.{urllib.parse.quote(str(start_at))}")
    if end_at:
        query_parts.append(f"scheduled_start_at=lte.{urllib.parse.quote(str(end_at))}")
    return _request("GET", "logistics_tasks", query="&".join(query_parts), access_token=access_token) or []


def list_staff_jobs(user_email, access_token=None):
    query = urllib.parse.urlencode({
        "select": (
            "id,role,start_at,end_at,status,confirmation_note,"
            "events(id,event_date,event_name,solution_type,dress_code,staff_notes,"
            "event_start_at,event_end_at,clients(client_name),venues(venue_name,google_maps_url)),"
            "staff!inner(email,full_name)"
        ),
        "staff.email": f"eq.{user_email}",
        "order": "start_at.asc",
    })
    return _request("GET", "event_staff_assignments", query=query, access_token=access_token) or []
