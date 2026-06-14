import streamlit as st
import dropbox
import json
import pandas as pd
import io
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

try:
    from operations_app import render_operations_app
except ModuleNotFoundError:
    render_operations_app = None

# --- CONFIGURATION ---
# V2 AUTHENTICATION VARS
DROPBOX_APP_KEY = os.environ.get("DROPBOX_APP_KEY")
DROPBOX_APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")
DROPBOX_REFRESH_TOKEN = os.environ.get("DROPBOX_REFRESH_TOKEN")
# Fallback for old token
DROPBOX_TOKEN = os.environ.get("DROPBOX_TOKEN")

GLOBAL_ASSETS = "/_Global_Assets"
ACTIONS_FOLDER = f"{GLOBAL_ASSETS}/Actions"
HEALTH_FOLDER = f"{GLOBAL_ASSETS}/_Server_Health"
PHOTOSHOP_SCRIPTS_FOLDER = f"{GLOBAL_ASSETS}/PhotoshopScripts"
EVENTS_FOLDER = f"{GLOBAL_ASSETS}/Events"
LOGO_URL = "https://photos.smugmug.com/photos/i-JGmn4QZ/0/Kfbh3K2TsxsddC59CndM9vRx45XBzmXGDx4MfS5CV/O/i-JGmn4QZ.png"
APP_TIMEZONE = ZoneInfo("Europe/Athens")
RAW_SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_URL = RAW_SUPABASE_URL
for suffix in ("/auth/v1", "/rest/v1", "/storage/v1"):
    if suffix in SUPABASE_URL:
        SUPABASE_URL = SUPABASE_URL.split(suffix)[0]
        break
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
ALLOWED_EMAIL_DOMAIN = os.environ.get("ALLOWED_EMAIL_DOMAIN", "thephotobooth.gr").lower().lstrip("@")
PORTAL_ADMIN_EMAILS = {
    email.strip().lower()
    for email in os.environ.get("PORTAL_ADMIN_EMAILS", "").split(",")
    if email.strip()
}
PORTAL_FLEET_EMAILS = {
    email.strip().lower()
    for email in os.environ.get("PORTAL_FLEET_EMAILS", "").split(",")
    if email.strip()
}
PORTAL_OPERATIONS_EMAILS = {
    email.strip().lower()
    for email in os.environ.get("PORTAL_OPERATIONS_EMAILS", "").split(",")
    if email.strip()
}

st.set_page_config(page_title="Photobooth Command", layout="wide", page_icon="📷")

# MASTER STATION LIST
KNOWN_STATIONS = sorted([
    "DC Standard", "Dell Laptop", "Dell XPS", "DellNew1", "DellNew2", 
    "DellNew3", "DellNew4", "HP_Envy", "HP1", "HP2", "HP3", "HP4", 
    "Laptop 3", "Lenovo 1", "Lenovo 2", "Mini1BackUp", "Mini1Standard", 
    "Mini2BackUp", "Mini2Standard", "Mini3", "Mini3BackUp", 
    "Mini4Standard", "TXStandard"
])

# --- PORTAL AUTHENTICATION ---
def normalize_email(email):
    return (email or "").strip().lower()

def is_allowed_staff_email(email):
    return normalize_email(email).endswith(f"@{ALLOWED_EMAIL_DOMAIN}")

def validate_password_strength(password):
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if not any(char.islower() for char in password):
        return "Password must include at least one lowercase letter."
    if not any(char.isupper() for char in password):
        return "Password must include at least one uppercase letter."
    if not any(char.isdigit() for char in password):
        return "Password must include at least one number."
    if not any(not char.isalnum() for char in password):
        return "Password must include at least one special character."
    return None

def get_user_role(email):
    email = normalize_email(email)
    if email in PORTAL_ADMIN_EMAILS:
        return "admin"
    return "staff"

def has_fleet_access(email):
    email = normalize_email(email)
    return email in PORTAL_ADMIN_EMAILS or email in PORTAL_FLEET_EMAILS

def has_operations_access(email):
    email = normalize_email(email)
    if email in PORTAL_ADMIN_EMAILS:
        return True
    if PORTAL_OPERATIONS_EMAILS:
        return email in PORTAL_OPERATIONS_EMAILS
    return True

def get_allowed_portals(email):
    portals = []
    if has_fleet_access(email):
        portals.append("Fleet Management")
    if has_operations_access(email):
        portals.append("Operations")
    return portals

def supabase_auth_request(endpoint, payload=None, access_token=None):
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None, "Missing SUPABASE_URL or SUPABASE_ANON_KEY."

    url = f"{SUPABASE_URL}/auth/v1/{endpoint.lstrip('/')}"
    body = json.dumps(payload or {}).encode("utf-8")
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {access_token or SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
    }
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            content = response.read().decode("utf-8")
            return json.loads(content) if content else {}, None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            data = json.loads(raw)
            message = data.get("msg") or data.get("message") or data.get("error_description") or raw
        except Exception:
            message = raw or str(e)
        return None, message
    except Exception as e:
        return None, str(e)

def supabase_get_user(access_token):
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None, "Missing SUPABASE_URL or SUPABASE_ANON_KEY."

    url = f"{SUPABASE_URL}/auth/v1/user"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {access_token}",
    }
    request = urllib.request.Request(url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            data = json.loads(raw)
            message = data.get("msg") or data.get("message") or data.get("error_description") or raw
        except Exception:
            message = raw or str(e)
        return None, message
    except Exception as e:
        return None, str(e)

def is_email_confirmed(user):
    return bool(user.get("email_confirmed_at") or user.get("confirmed_at"))

def set_auth_session(session_data):
    access_token = session_data.get("access_token")
    user = session_data.get("user")
    if access_token and not user:
        user, _ = supabase_get_user(access_token)
    if not access_token or not user:
        return "Login succeeded but no valid user session was returned."

    email = normalize_email(user.get("email"))
    if not is_allowed_staff_email(email):
        return f"Only @{ALLOWED_EMAIL_DOMAIN} accounts can access this portal."
    if not is_email_confirmed(user):
        return "Please confirm your email before logging in. Check your inbox."

    st.session_state.auth_access_token = access_token
    st.session_state.auth_user = user
    st.session_state.auth_email = email
    st.session_state.auth_role = get_user_role(email)
    return None

def logout_user():
    token = st.session_state.get("auth_access_token")
    if token:
        supabase_auth_request("logout", {}, access_token=token)
    for key in ["auth_access_token", "auth_user", "auth_email", "auth_role", "selected_portal"]:
        st.session_state.pop(key, None)

def render_account_sidebar():
    st.sidebar.image(LOGO_URL, width=100)
    if st.session_state.get("auth_email"):
        st.sidebar.caption(f"Signed in: {st.session_state.auth_email}")
        st.sidebar.caption(f"Role: {st.session_state.get('auth_role', 'staff')}")
    if st.sidebar.button("Switch Portal"):
        st.session_state.pop("selected_portal", None)
        st.session_state.pop("portal_view", None)
        st.rerun()
    if st.sidebar.button("Logout"):
        logout_user()
        st.rerun()

def render_portal_selector():
    email = st.session_state.get("auth_email")
    allowed_portals = get_allowed_portals(email)
    selected_portal = st.session_state.get("selected_portal")

    if selected_portal in allowed_portals:
        return selected_portal
    st.session_state.pop("selected_portal", None)

    st.title("📷 Photobooth Command")
    st.image(LOGO_URL, width=120)
    st.subheader("Choose Portal")
    st.caption(f"Signed in as {email}")

    if not allowed_portals:
        st.error("Your account does not have access to any portal yet. Ask an admin to add your email to a portal access list.")
        if st.button("Logout"):
            logout_user()
            st.rerun()
        st.stop()

    cols = st.columns(len(allowed_portals))
    for col, portal in zip(cols, allowed_portals):
        with col:
            st.markdown(f"### {portal}")
            if portal == "Fleet Management":
                st.caption("Station configuration, fleet health, and technical event automation.")
            else:
                st.caption("Operations planning, staff jobs, logistics tasks, and weekly scheduling.")
            if st.button(f"Open {portal}", key=f"open_{portal}"):
                st.session_state.selected_portal = portal
                st.rerun()

    st.stop()

def render_auth_gate():
    token = st.session_state.get("auth_access_token")
    if token and st.session_state.get("auth_user"):
        return True
    if token:
        user, error = supabase_get_user(token)
        if user:
            email = normalize_email(user.get("email"))
            if is_allowed_staff_email(email) and is_email_confirmed(user):
                st.session_state.auth_user = user
                st.session_state.auth_email = email
                st.session_state.auth_role = get_user_role(email)
                return True
        logout_user()

    st.title("📷 Photobooth Fleet Command")
    st.image(LOGO_URL, width=120)
    st.subheader("Portal Login")
    st.caption(f"Access is limited to verified @{ALLOWED_EMAIL_DOMAIN} staff accounts.")

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        st.error("Supabase is not configured. Add SUPABASE_URL and SUPABASE_ANON_KEY in Heroku Config Vars.")
        return False

    login_tab, signup_tab = st.tabs(["Login", "Sign up"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email").strip()
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Login")

        if submitted:
            email = normalize_email(email)
            if not is_allowed_staff_email(email):
                st.error(f"Use your @{ALLOWED_EMAIL_DOMAIN} email address.")
            elif not password:
                st.error("Enter your password.")
            else:
                data, error = supabase_auth_request(
                    "token?grant_type=password",
                    {"email": email, "password": password}
                )
                if error:
                    st.error(error)
                else:
                    session_error = set_auth_session(data)
                    if session_error:
                        st.error(session_error)
                    else:
                        st.rerun()

    with signup_tab:
        with st.form("signup_form"):
            email = st.text_input("Work email", key="signup_email").strip()
            password = st.text_input("Create password", type="password", key="signup_password")
            st.caption("Minimum 8 characters with uppercase, lowercase, number, and special character.")
            password_confirm = st.text_input("Confirm password", type="password", key="signup_password_confirm")
            submitted = st.form_submit_button("Create account")

        if submitted:
            email = normalize_email(email)
            if not is_allowed_staff_email(email):
                st.error(f"Signup is only available for @{ALLOWED_EMAIL_DOMAIN} emails.")
            elif validate_password_strength(password):
                st.error(validate_password_strength(password))
            elif password != password_confirm:
                st.error("Passwords do not match.")
            else:
                data, error = supabase_auth_request(
                    "signup",
                    {"email": email, "password": password, "data": {"role": "staff"}}
                )
                if error:
                    st.error(error)
                else:
                    st.success("Account created. Check your email and confirm your account before logging in.")

    return False

if not render_auth_gate():
    st.stop()

selected_portal = render_portal_selector()

if selected_portal == "Operations":
    render_account_sidebar()
    if render_operations_app:
        render_operations_app(
            current_user=st.session_state.get("auth_email"),
            current_role=st.session_state.get("auth_role"),
            access_token=st.session_state.get("auth_access_token"),
        )
    else:
        st.error("Operations module is not deployed yet. Upload operations_app.py, operations_db.py, and operations_models.py alongside app.py.")
    st.stop()

# --- CONNECT TO DROPBOX (V2 AUTH LOGIC) ---
try:
    if DROPBOX_APP_KEY and DROPBOX_APP_SECRET and DROPBOX_REFRESH_TOKEN:
        # NEW: Long-lived connection using Refresh Token
        dbx = dropbox.Dropbox(
            app_key=DROPBOX_APP_KEY,
            app_secret=DROPBOX_APP_SECRET,
            oauth2_refresh_token=DROPBOX_REFRESH_TOKEN
        )
    elif DROPBOX_TOKEN:
        # OLD: Short-lived token fallback
        dbx = dropbox.Dropbox(DROPBOX_TOKEN)
    else:
        st.error("Missing Dropbox Credentials (APP_KEY/SECRET/REFRESH_TOKEN or DROPBOX_TOKEN)")
        st.stop()
        
    # Test Connection (Soft Check)
    try:
        dbx.users_get_current_account()
    except Exception:
        # Ignore scope errors if we can't read account info
        pass
        
except Exception as e:
    st.error(f"Dropbox Connection Failed: {e}")
    st.stop()

# --- HELPER FUNCTIONS ---
def get_fleet_data():
    """Reads health files to see who is ONLINE."""
    servers = []
    try:
        res = dbx.files_list_folder(HEALTH_FOLDER)
        for entry in res.entries:
            if entry.name.endswith('.json'):
                try:
                    _, res = dbx.files_download(entry.path_lower)
                    data = json.load(io.BytesIO(res.content))
                    servers.append(data)
                except: pass
    except: pass
    return servers

def get_available_actions(folder_path=ACTIONS_FOLDER):
    actions = []
    try:
        res = dbx.files_list_folder(folder_path)
        for entry in res.entries:
            if entry.name.endswith('.atn'):
                actions.append(entry.name.replace(".atn", ""))
    except: pass
    return sorted(actions)

def load_config(station_id):
    path = f"/{station_id}/config.json"
    try:
        _, res = dbx.files_download(path)
        return json.load(io.BytesIO(res.content)), path
    except:
        return None, path

def create_default_config(station_id):
    default_data = {
        "server_id": "Unassigned",
        "station_id": station_id,
        "station_enabled": True, 
        "settings": {
            "remove_background": False,
            "remove_bg_api_key": "",
            "orientation_mode": "auto",
            "temperature": 0
        },
        "active_profile": {
            "portrait": {"action_set": station_id, "action_name": "Portrait"},
            "landscape": {"action_set": station_id, "action_name": "Landscape"}
        }
    }
    path = f"/{station_id}/config.json"
    save_config(default_data, path)
    return default_data, path

def save_config(config_data, path):
    data_str = json.dumps(config_data, indent=2)
    dbx.files_upload(data_str.encode('utf-8'), path, mode=dropbox.files.WriteMode.overwrite)
    return True

def upload_asset(uploaded_file, target_path):
    dbx.files_upload(uploaded_file.getvalue(), target_path, mode=dropbox.files.WriteMode.overwrite)

def dropbox_user_path(dropbox_path):
    return f"~/Library/CloudStorage/Dropbox{dropbox_path}"

def dropbox_file_exists(path):
    try:
        dbx.files_get_metadata(path)
        return True
    except:
        return False

def resolve_authoring_template_path(station_id, kind, suffix):
    extensions = [".png"] if kind == "overlay" else [".jpg", ".jpeg", ".png"]
    base = f"/{station_id}/templates/authoring"
    names = []
    if suffix:
        for ext in extensions:
            names.append(f"{kind}{suffix}{ext}")
    for ext in extensions:
        names.append(f"{kind}{ext}")

    for name in names:
        path = f"{base}/{name}"
        if dropbox_file_exists(path):
            return dropbox_user_path(path)
    return ""

def update_authoring_context(station_id, suffix):
    context = {
        "station_id": station_id,
        "subfolder": suffix,
        "background": resolve_authoring_template_path(station_id, "background", suffix),
        "overlay": resolve_authoring_template_path(station_id, "overlay", suffix),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    ensure_dropbox_folder(PHOTOSHOP_SCRIPTS_FOLDER)
    dbx.files_upload(
        json.dumps(context, indent=2).encode("utf-8"),
        f"{PHOTOSHOP_SCRIPTS_FOLDER}/authoring_context.json",
        mode=dropbox.files.WriteMode.overwrite
    )
    return context

def upload_template_asset(uploaded_file, station_id, name, suffix):
    target_path = f"/{station_id}/templates/{name}"
    authoring_path = f"/{station_id}/templates/authoring/{name}"
    ensure_dropbox_folder(f"/{station_id}/templates")
    ensure_dropbox_folder(f"/{station_id}/templates/authoring")
    data = uploaded_file.getvalue()
    dbx.files_upload(data, target_path, mode=dropbox.files.WriteMode.overwrite)
    dbx.files_upload(data, authoring_path, mode=dropbox.files.WriteMode.overwrite)
    update_authoring_context(station_id, suffix)

def ensure_dropbox_folder(folder_path):
    try:
        dbx.files_create_folder_v2(folder_path)
    except:
        pass

def upload_action_file(uploaded_file, target_folder, target_filename=None):
    ensure_dropbox_folder(target_folder)
    filename = target_filename or uploaded_file.name
    target_path = f"{target_folder}/{filename}"
    dbx.files_upload(uploaded_file.getvalue(), target_path, mode=dropbox.files.WriteMode.overwrite)
    return target_path

def load_action_metadata(folder_path, action_set):
    candidate_names = [
        action_set,
        action_set.strip(),
        action_set.replace(" ", "_"),
        action_set.replace("_", " ")
    ]
    seen_paths = set()
    for name in candidate_names:
        path = f"{folder_path}/{name}.json"
        if path in seen_paths:
            continue
        seen_paths.add(path)
        try:
            _, res = dbx.files_download(path)
            data = json.load(io.BytesIO(res.content))
            actions = data.get("actions", [])
            return [a.strip() for a in actions if isinstance(a, str) and a.strip()]
        except:
            pass
    return []

def parse_action_lines(action_text):
    actions = []
    for line in action_text.splitlines():
        action = line.strip()
        if action and action not in actions:
            actions.append(action)
    return actions

def save_action_metadata(folder_path, action_set, action_text, append_only=True):
    existing_actions = load_action_metadata(folder_path, action_set) if append_only else []
    actions = existing_actions[:]
    for action in parse_action_lines(action_text):
        if action not in actions:
            actions.append(action)

    metadata = {
        "action_set": action_set,
        "actions": actions,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    ensure_dropbox_folder(folder_path)
    path = f"{folder_path}/{action_set}.json"
    dbx.files_upload(
        json.dumps(metadata, indent=2).encode("utf-8"),
        path,
        mode=dropbox.files.WriteMode.overwrite
    )
    return actions

def clear_action_metadata(folder_path, action_set):
    metadata = {
        "action_set": action_set,
        "actions": [],
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    ensure_dropbox_folder(folder_path)
    path = f"{folder_path}/{action_set}.json"
    dbx.files_upload(
        json.dumps(metadata, indent=2).encode("utf-8"),
        path,
        mode=dropbox.files.WriteMode.overwrite
    )
    return path

def action_name_input(label, current_value, available_actions, key):
    if available_actions:
        options = available_actions
        if current_value and current_value not in options:
            options = [current_value] + options
        index = options.index(current_value) if current_value in options else 0
        return st.selectbox(label, options, index=index, key=key)
    return st.text_input(label, current_value, key=key)

def unique_test_filename(original_name):
    name, ext = os.path.splitext(original_name)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)
    return f"portal_test_{timestamp}_{safe_name}{ext.lower()}"

def upload_test_photo(uploaded_file, station_id, subfolder):
    filename = unique_test_filename(uploaded_file.name)
    incoming_folder = f"/{station_id}/incoming"
    if subfolder:
        incoming_folder = f"{incoming_folder}/{subfolder}"
    ensure_dropbox_folder(incoming_folder)
    target_path = f"{incoming_folder}/{filename}"
    dbx.files_upload(uploaded_file.getvalue(), target_path, mode=dropbox.files.WriteMode.overwrite)
    return filename, target_path

def find_final_output(station_id, subfolder, filename):
    name, _ = os.path.splitext(filename)
    final_folder = f"/{station_id}/final"
    if subfolder:
        final_folder = f"{final_folder}/{subfolder}"
    final_path = f"{final_folder}/{name}.jpg"
    try:
        dbx.files_get_metadata(final_path)
        return final_path
    except:
        return None

def wait_for_final_output(station_id, subfolder, filename, timeout_seconds=45):
    start = time.time()
    while time.time() - start < timeout_seconds:
        final_path = find_final_output(station_id, subfolder, filename)
        if final_path:
            return final_path
        time.sleep(3)
    return None

def download_dropbox_file(path):
    _, res = dbx.files_download(path)
    return res.content

def app_now():
    return datetime.now(APP_TIMEZONE)

def app_timestamp():
    return app_now().strftime("%Y-%m-%d %H:%M:%S")

def slugify(value):
    cleaned = "".join(c.lower() if c.isalnum() else "_" for c in value.strip())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "event"

def build_event_id(event_name, station_id, start_dt):
    return f"{start_dt.strftime('%Y%m%d_%H%M')}_{slugify(station_id)}_{slugify(event_name)}"

def save_event(event_data):
    ensure_dropbox_folder(EVENTS_FOLDER)
    path = f"{EVENTS_FOLDER}/{event_data['event_id']}.json"
    event_data["updated_at"] = app_timestamp()
    dbx.files_upload(
        json.dumps(event_data, indent=2).encode("utf-8"),
        path,
        mode=dropbox.files.WriteMode.overwrite
    )
    return path

def list_events():
    events = []
    try:
        res = dbx.files_list_folder(EVENTS_FOLDER)
        for entry in res.entries:
            if entry.name.endswith(".json"):
                try:
                    _, file_res = dbx.files_download(entry.path_lower)
                    event = json.load(io.BytesIO(file_res.content))
                    events.append(event)
                except:
                    pass
    except:
        pass
    return sorted(events, key=lambda e: e.get("start_at", ""), reverse=True)

def create_event(event_name, station_id, assigned_server, start_date, start_time, end_date, end_time):
    start_dt = datetime.combine(start_date, start_time)
    end_dt = datetime.combine(end_date, end_time)
    if end_dt <= start_dt:
        raise ValueError("End date/time must be after start date/time.")

    event_id = build_event_id(event_name, station_id, start_dt)
    event = {
        "event_id": event_id,
        "event_name": event_name,
        "station_id": station_id,
        "assigned_server": assigned_server,
        "status": "scheduled",
        "start_at": start_dt.strftime("%Y-%m-%d %H:%M"),
        "end_at": end_dt.strftime("%Y-%m-%d %H:%M"),
        "timezone": "Europe/Athens",
        "created_at": app_timestamp(),
        "updated_at": app_timestamp()
    }
    save_event(event)
    return event

def activate_event(event):
    for existing_event in list_events():
        if (
            existing_event.get("station_id") == event["station_id"]
            and existing_event.get("status") == "active"
            and existing_event.get("event_id") != event["event_id"]
        ):
            existing_event["status"] = "completed"
            existing_event["deactivated_at"] = app_timestamp()
            save_event(existing_event)

    config, config_path = load_config(event["station_id"])
    if not config:
        config, config_path = create_default_config(event["station_id"])

    config["station_enabled"] = True
    config["assigned_server"] = event.get("assigned_server", config.get("assigned_server", "Unassigned"))
    config["active_event_id"] = event["event_id"]
    config["active_event_name"] = event["event_name"]
    save_config(config, config_path)

    event["status"] = "active"
    event["activated_at"] = app_timestamp()
    save_event(event)
    return event

def deactivate_event(event):
    config, config_path = load_config(event["station_id"])
    if config and config.get("active_event_id") == event["event_id"]:
        config["station_enabled"] = False
        config["last_event_id"] = event["event_id"]
        config.pop("active_event_id", None)
        config.pop("active_event_name", None)
        save_config(config, config_path)

    event["status"] = "completed"
    event["deactivated_at"] = app_timestamp()
    save_event(event)
    return event

def parse_event_datetime(value):
    return datetime.strptime(value, "%Y-%m-%d %H:%M")

def sync_events_now():
    now = app_now().replace(tzinfo=None)
    events = list_events()
    changes = []

    active_by_station = {}
    for event in events:
        try:
            start_at = parse_event_datetime(event.get("start_at", ""))
            end_at = parse_event_datetime(event.get("end_at", ""))
        except:
            continue

        if now >= end_at and event.get("status") != "completed":
            deactivate_event(event)
            changes.append(f"Completed {event.get('event_name')}")
        elif start_at <= now < end_at:
            station_id = event.get("station_id")
            current = active_by_station.get(station_id)
            if not current or parse_event_datetime(event.get("start_at")) > parse_event_datetime(current.get("start_at")):
                active_by_station[station_id] = event
        elif now < start_at and event.get("status") == "active":
            event["status"] = "scheduled"
            save_event(event)
            config, config_path = load_config(event.get("station_id"))
            if config and config.get("active_event_id") == event.get("event_id"):
                config["station_enabled"] = False
                config.pop("active_event_id", None)
                config.pop("active_event_name", None)
                save_config(config, config_path)
            changes.append(f"Scheduled {event.get('event_name')}")

    for event in active_by_station.values():
        if event.get("status") != "active":
            activate_event(event)
            changes.append(f"Activated {event.get('event_name')}")

    return changes

# --- UI LAYOUT ---
st.title("📷 Photobooth Fleet Command")

# 1. SIDEBAR - FLEET VIEW
st.sidebar.image(LOGO_URL, width=100)
if st.session_state.get("auth_email"):
    st.sidebar.caption(f"Signed in: {st.session_state.auth_email}")
    st.sidebar.caption(f"Role: {st.session_state.get('auth_role', 'staff')}")
    if st.sidebar.button("Switch Portal"):
        st.session_state.pop("selected_portal", None)
        st.session_state.pop("portal_view", None)
        st.rerun()
    if st.sidebar.button("Logout"):
        logout_user()
        st.rerun()
st.sidebar.header("📡 Live Status")
fleet_data = get_fleet_data()
if fleet_data:
    df = pd.DataFrame(fleet_data)
    if 'disk_used_percent' in df.columns:
        df['disk_used_%'] = df['disk_used_percent'].astype(str) + "%"
    else:
        df['disk_used_%'] = "n/a"
    st.sidebar.dataframe(
        df[['server_id', 'disk_used_%', 'status']], 
        hide_index=True, use_container_width=True
    )
    
    # Optional Filter
    online_servers = sorted(list(set([s['server_id'] for s in fleet_data])))
    filter_server = st.sidebar.selectbox("Filter by Server (Optional)", ["All Stations"] + online_servers)
else:
    st.sidebar.warning("No servers online.")
    filter_server = "All Stations"

st.sidebar.divider()

# 2. PORTAL VIEW
st.sidebar.header("🧭 Portal View")
if "portal_view" not in st.session_state:
    st.session_state.portal_view = "Station Manager"
if "pending_portal_view" in st.session_state:
    st.session_state.portal_view = st.session_state.pop("pending_portal_view")
if "pending_sidebar_station" in st.session_state:
    st.session_state.sidebar_station = st.session_state.pop("pending_sidebar_station")
portal_view = st.sidebar.radio("Select View", ["Station Manager", "Events"], key="portal_view", label_visibility="collapsed")

st.sidebar.divider()

# 3. STATION SELECTOR

# Logic: If a server is filtered, show only its stations. Otherwise, show ALL.
if filter_server != "All Stations":
    # Filter using v52 lists
    filtered_list = []
    for s in fleet_data:
        if s['server_id'] == filter_server:
            # Safely get lists, default to empty
            filtered_list.extend(s.get('active_stations', []))
            filtered_list.extend(s.get('standby_stations', []))
    display_list = sorted(list(set(filtered_list)))
else:
    display_list = KNOWN_STATIONS

selected_station = None
if portal_view == "Station Manager":
    st.sidebar.header("🎮 Station Manager")
    if "sidebar_station" in st.session_state and st.session_state.sidebar_station not in display_list:
        display_list = sorted(display_list + [st.session_state.sidebar_station])
    selected_station = st.sidebar.selectbox("Select Station to Configure", display_list, key="sidebar_station")

# --- PAGE 1: FLEET DASHBOARD (IF NO STATION SELECTED OR DASHBOARD MODE) ---
# NOTE: Your requested code keeps it simple, but let's fix the Dashboard Crash here
# We display the Dashboard if users select "All Stations" in filter context, 
# but Streamlit runs top-to-bottom. We will inject the Dashboard view here 
# if the sidebar filter is active, OR just show it at the top.
# Let's keep your structure: Title -> Sidebar -> Main Area.

# FIX: We render the Fleet Dashboard at the top if data exists
if fleet_data:
    with st.expander("🌍 Global Fleet Dashboard", expanded=True):
        for data in fleet_data:
            sid = data.get('server_id')
            st.subheader(f"🖥️ {sid} ({data.get('status')})")
            
            active = data.get('active_stations', [])
            standby = data.get('standby_stations', [])
            ghosts = data.get('unconfigured_stations', [])

            t1, t2, t3 = st.tabs([
                f"🟢 Active ({len(active)})", 
                f"🟡 Standby ({len(standby)})", 
                f"🔴 Unconfigured ({len(ghosts)})"
            ])
            
            # FIXED: Standard if/else blocks to prevent 'With' object errors
            with t1:
                if active:
                    st.success(", ".join(active))
                else:
                    st.caption("None")
            
            with t2:
                if standby:
                    st.warning(", ".join(standby))
                else:
                    st.caption("None")
                    
            with t3:
                if ghosts:
                    st.error(", ".join(ghosts))
                else:
                    st.caption("None")
            st.divider()

if portal_view == "Events":
    st.header("📅 Events")
    st.caption("Create events and manually activate/deactivate station processing.")

    all_events = list_events()
    online_servers = sorted(list(set([s.get('server_id') for s in fleet_data if s.get('server_id')]))) if fleet_data else []
    server_options = sorted(list(set(online_servers + ["71946", "73780"])))

    if st.button("Sync Events Now", key="sync_events_now"):
        changes = sync_events_now()
        if changes:
            st.success("Updated: " + ", ".join(changes))
        else:
            st.info("No event status changes needed.")
        time.sleep(1)
        st.rerun()

    st.markdown("### Create Event")
    c_name, c_station, c_server = st.columns([2, 1, 1])
    with c_name:
        event_name = st.text_input("Event name", key="global_event_name")
    with c_station:
        event_station = st.selectbox("Station", KNOWN_STATIONS, key="global_event_station")
    with c_server:
        default_server_idx = server_options.index("71946") if "71946" in server_options else 0
        event_server = st.selectbox("Assigned server", server_options, index=default_server_idx, key="global_event_server")

    c_start_date, c_start_time, c_end_date, c_end_time = st.columns(4)
    current_app_time = app_now()
    with c_start_date:
        event_start_date = st.date_input("Start date", value=current_app_time.date(), key="global_event_start_date")
    with c_start_time:
        event_start_time = st.time_input("Start time", value=current_app_time.replace(minute=0, second=0, microsecond=0).time(), key="global_event_start_time")
    with c_end_date:
        event_end_date = st.date_input("End date", value=current_app_time.date(), key="global_event_end_date")
    with c_end_time:
        event_end_time = st.time_input("End time", value=current_app_time.replace(hour=min(current_app_time.hour + 4, 23), minute=0, second=0, microsecond=0).time(), key="global_event_end_time")

    if st.button("Create Event", key="global_create_event"):
        if not event_name.strip():
            st.error("Enter an event name.")
        else:
            try:
                event = create_event(
                    event_name.strip(),
                    event_station,
                    event_server,
                    event_start_date,
                    event_start_time,
                    event_end_date,
                    event_end_time
                )
                st.success(f"Created event: {event['event_name']}")
                time.sleep(1)
                st.rerun()
            except ValueError as e:
                st.error(str(e))

    st.divider()

    active_events = [e for e in all_events if e.get("status") == "active"]
    upcoming_events = [e for e in all_events if e.get("status") == "scheduled"]
    completed_events = [e for e in all_events if e.get("status") == "completed"]

    event_bucket = st.selectbox("Show events", ["Active", "Upcoming", "Completed", "All"], key="event_bucket")
    if event_bucket == "Active":
        visible_events = active_events
    elif event_bucket == "Upcoming":
        visible_events = upcoming_events
    elif event_bucket == "Completed":
        visible_events = completed_events
    else:
        visible_events = all_events

    st.markdown("### Event List")
    if visible_events:
        event_rows = [
            {
                "event_name": e.get("event_name"),
                "station_id": e.get("station_id"),
                "status": e.get("status"),
                "start_at": e.get("start_at"),
                "end_at": e.get("end_at"),
                "assigned_server": e.get("assigned_server")
            }
            for e in visible_events
        ]
        st.dataframe(pd.DataFrame(event_rows), hide_index=True, use_container_width=True)

        event_labels = [
            f"{e.get('event_name')} | {e.get('station_id')} | {e.get('start_at')} | {e.get('status')}"
            for e in visible_events
        ]
        selected_event_label = st.selectbox("Select event", event_labels, key="global_selected_event")
        selected_event_obj = visible_events[event_labels.index(selected_event_label)]

        c_activate, c_deactivate = st.columns(2)
        with c_activate:
            if st.button("Activate Selected Event", key="global_activate_event"):
                activate_event(selected_event_obj)
                st.success("Event activated and station enabled.")
                time.sleep(1)
                st.rerun()
        with c_deactivate:
            if st.button("Deactivate Selected Event", key="global_deactivate_event"):
                deactivate_event(selected_event_obj)
                st.success("Event completed and station disabled.")
                time.sleep(1)
                st.rerun()
        if st.button("Customize Event", key="global_customize_event"):
            st.session_state.customizing_event_id = selected_event_obj.get("event_id")
            st.session_state.pending_portal_view = "Station Manager"
            st.session_state.pending_sidebar_station = selected_event_obj.get("station_id")
            st.rerun()
    else:
        st.info("No events found for this view.")

elif selected_station:
    st.header(f"🔧 Managing: {selected_station}")
    
    config, config_path = load_config(selected_station)
    
    if not config:
        st.warning(f"Config missing for {selected_station}")
        if st.button("Initialize Config Now"):
            config, config_path = create_default_config(selected_station)
            st.rerun()
            
    if config:
        customizing_event_id = st.session_state.get("customizing_event_id")
        if customizing_event_id:
            matching_events = [e for e in list_events() if e.get("event_id") == customizing_event_id]
            if matching_events:
                event = matching_events[0]
                st.info(f"Customizing event: {event.get('event_name')} ({event.get('start_at')} - {event.get('end_at')})")
            if st.button("Clear Event Context"):
                st.session_state.pop("customizing_event_id", None)
                st.rerun()

        # --- MASTER SWITCH ---
        is_enabled = config.get("station_enabled", True)
        
        # UI Styling for the Switch
        col_sw, col_st = st.columns([1, 5])
        with col_sw:
            new_enabled = st.toggle("Station ON/OFF", value=is_enabled)
        with col_st:
            if new_enabled:
                st.markdown("### 🟢 Active")
            else:
                st.markdown("### 🔴 Disabled (Ignoring Photos)")
        
        if new_enabled != is_enabled:
            config["station_enabled"] = new_enabled
            save_config(config, config_path)
            st.rerun()

        st.divider()

        if is_enabled:
            tab1, tab2, tab3, tab4 = st.tabs(["⚙️ Settings", "🎨 Assets", "🎬 Profiles & Actions", "🧪 Test Output"])
            
            # --- TAB 1: SETTINGS ---
            with tab1:
                c1, c2 = st.columns(2)
                with c1:
                    curr_bg = config['settings'].get('remove_background', False)
                    new_bg = st.toggle("Remove Background (API)", value=curr_bg)
                    if new_bg != curr_bg:
                        config['settings']['remove_background'] = new_bg
                        save_config(config, config_path)
                        st.toast("Updated BG")
                    
                    curr_temp = config['settings'].get('temperature', 0)
                    new_temp = st.slider("Temperature", -100, 100, curr_temp)
                    if new_temp != curr_temp:
                        config['settings']['temperature'] = new_temp
                        save_config(config, config_path)
                        st.toast("Updated Temp")

                with c2:
                    modes = ["auto", "force_portrait", "force_landscape"]
                    curr_mode = config['settings'].get('orientation_mode', 'auto')
                    new_mode = st.selectbox("Orientation", modes, index=modes.index(curr_mode))
                    if new_mode != curr_mode:
                        config['settings']['orientation_mode'] = new_mode
                        save_config(config, config_path)
                        st.toast("Updated Orientation")

            # --- TAB 2: ASSETS ---
            with tab2:
                st.subheader("Upload Assets")
                st.caption(f"Target: /{selected_station}/templates/")
                suffix = st.text_input("Sub-Profile (e.g., 001)", placeholder="Default")
                
                c1, c2 = st.columns(2)
                with c1:
                    bg = st.file_uploader("Background (.jpg)", type=['jpg', 'jpeg'])
                    if bg and st.button("Upload BG"):
                        name = f"background{suffix}.jpg" if suffix else "background.jpg"
                        upload_template_asset(bg, selected_station, name, suffix)
                        st.success(f"Saved {name}")
                        time.sleep(1)
                        st.rerun() # Auto-Refresh
                with c2:
                    ol = st.file_uploader("Overlay (.png)", type=['png'])
                    if ol and st.button("Upload Overlay"):
                        name = f"overlay{suffix}.png" if suffix else "overlay.png"
                        upload_template_asset(ol, selected_station, name, suffix)
                        st.success(f"Saved {name}")
                        time.sleep(1)
                        st.rerun() # Auto-Refresh

            # --- TAB 3: ACTIONS ---
            with tab3:
                station_actions_folder = f"/{selected_station}/actions"
                station_action_set = selected_station
                station_action_filename = f"{station_action_set}.atn"
                station_action_path = f"{station_actions_folder}/{station_action_filename}"
                station_actions = load_action_metadata(station_actions_folder, station_action_set)

                st.markdown("### Station Photoshop Action Set")
                st.caption(f"Live action file: {station_action_path}")
                st.caption(f"Photoshop set name must be exactly: {station_action_set}")

                legacy_sets = []
                for orientation in ("portrait", "landscape"):
                    current_set = config.get('active_profile', {}).get(orientation, {}).get('action_set')
                    if current_set and current_set != station_action_set:
                        legacy_sets.append(f"{orientation}: {current_set}")
                if config.get('subfolder_action_set'):
                    legacy_sets.append(f"subfolders: {config.get('subfolder_action_set')}")

                if legacy_sets:
                    st.info("Legacy action-set config detected: " + ", ".join(legacy_sets))
                    if st.button("Clean Legacy Action Config"):
                        config.pop('subfolder_action_set', None)
                        config['active_profile']['portrait']['action_set'] = station_action_set
                        config['active_profile']['landscape']['action_set'] = station_action_set
                        save_config(config, config_path)
                        st.success("Config now uses the station action set only.")
                        time.sleep(1)
                        st.rerun()

                if station_actions:
                    st.caption("Actions in station set: " + ", ".join(station_actions[:12]) + ("..." if len(station_actions) > 12 else ""))
                else:
                    st.caption("No metadata found yet. Upload the station .atn and add action names below to enable dropdowns.")

                # 1. Root Actions
                st.markdown("### Root Folder Actions (Single Photos)")
                col_p, col_l = st.columns(2)

                with col_p:
                    st.caption("Portrait")
                    cur_p_name = config['active_profile']['portrait'].get('action_name', 'Portrait')
                    new_p_name = action_name_input("Action Name", cur_p_name, station_actions, "p_name")

                    if new_p_name != cur_p_name or config['active_profile']['portrait'].get('action_set') != station_action_set:
                        if st.button("Save Portrait"):
                            config['active_profile']['portrait']['action_set'] = station_action_set
                            config['active_profile']['portrait']['action_name'] = new_p_name
                            config.pop('subfolder_action_set', None)
                            save_config(config, config_path)
                            st.success("Saved portrait action.")

                with col_l:
                    st.caption("Landscape")
                    cur_l_name = config['active_profile']['landscape'].get('action_name', 'Landscape')
                    new_l_name = action_name_input("Action Name", cur_l_name, station_actions, "l_name")

                    if new_l_name != cur_l_name or config['active_profile']['landscape'].get('action_set') != station_action_set:
                        if st.button("Save Landscape"):
                            config['active_profile']['landscape']['action_set'] = station_action_set
                            config['active_profile']['landscape']['action_name'] = new_l_name
                            config.pop('subfolder_action_set', None)
                            save_config(config, config_path)
                            st.success("Saved landscape action.")

                st.divider()

                # 2. Subfolder Actions
                st.markdown("### Event Subfolder Actions (001...099)")
                st.caption(f"Subfolder photos use the same Photoshop set: {station_action_set}")
                st.info(
                    f"Automatic rule: /{selected_station}/incoming/001 runs action {selected_station}001, "
                    f"/{selected_station}/incoming/002 runs {selected_station}002, up to 099. "
                    "These subfolder action names do not need to be added to portal metadata."
                )

                st.divider()

                # 3. Uploader and Metadata
                st.subheader(f"Upload {station_action_filename}")
                st.caption("Upload one .atn file per station. Metadata is only for portal dropdowns; subfolder actions follow the automatic naming rule.")
                up_station_atn = st.file_uploader("Upload station .atn", type=['atn'], key="station_atn")
                existing_station_actions = load_action_metadata(station_actions_folder, station_action_set)
                if existing_station_actions:
                    st.caption("Existing metadata actions: " + ", ".join(existing_station_actions[:12]) + ("..." if len(existing_station_actions) > 12 else ""))

                station_action_text = st.text_area(
                    f"Add root/dropdown action names to {station_action_set}",
                    value="",
                    key="station_action_text",
                    placeholder=f"{selected_station}_Portrait\n{selected_station}_Landscape\n{selected_station}_Strip_AI"
                )

                col_upload, col_metadata, col_clear = st.columns(3)
                with col_upload:
                    if up_station_atn and st.button("Upload Station Action Set"):
                        upload_action_file(up_station_atn, station_actions_folder, target_filename=station_action_filename)
                        save_action_metadata(station_actions_folder, station_action_set, station_action_text)
                        st.success(f"Uploaded to {station_action_path}")
                        time.sleep(1)
                        st.rerun()
                with col_metadata:
                    if st.button("Save Station Metadata"):
                        save_action_metadata(station_actions_folder, station_action_set, station_action_text)
                        st.success(f"Saved metadata for {station_action_set}")
                        time.sleep(1)
                        st.rerun()
                with col_clear:
                    clear_confirm = st.checkbox("Confirm clear", key="clear_station_metadata_confirm")
                    if st.button("Clear Metadata", disabled=not clear_confirm):
                        clear_action_metadata(station_actions_folder, station_action_set)
                        st.success(f"Cleared metadata for {station_action_set}. The .atn file was not deleted.")
                        time.sleep(1)
                        st.rerun()

            # --- TAB 4: TEST OUTPUT ---
            with tab4:
                st.subheader("Test Station Output")
                st.caption("Uploads one test photo into the selected station queue and waits briefly for the final JPG.")

                test_photo = st.file_uploader("Test photo", type=['jpg', 'jpeg', 'png'], key="test_photo")
                test_route = st.selectbox("Test route", ["Root incoming", "Event subfolder"], key="test_route")
                test_subfolder = ""
                if test_route == "Event subfolder":
                    test_subfolder = st.text_input("Subfolder", value="001", max_chars=3, key="test_subfolder").strip()

                if test_photo and st.button("Run Test Photo"):
                    if test_route == "Event subfolder" and not test_subfolder:
                        st.error("Enter a subfolder such as 001.")
                    else:
                        filename, incoming_path = upload_test_photo(test_photo, selected_station, test_subfolder)
                        st.info(f"Uploaded to {incoming_path}")

                        with st.spinner("Waiting for final output..."):
                            final_path = wait_for_final_output(selected_station, test_subfolder, filename)

                        if final_path:
                            final_bytes = download_dropbox_file(final_path)
                            st.success(f"Final output ready: {final_path}")
                            st.image(final_bytes, caption=os.path.basename(final_path), use_container_width=True)
                            st.download_button(
                                "Download Final JPG",
                                data=final_bytes,
                                file_name=os.path.basename(final_path),
                                mime="image/jpeg"
                            )
                        else:
                            st.warning("Final output was not found within 45 seconds. Check the station failed folder or email alerts.")
