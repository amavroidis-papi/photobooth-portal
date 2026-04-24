import streamlit as st
import dropbox
import json
import pandas as pd
import io
import os
import time

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

# MASTER STATION LIST
KNOWN_STATIONS = sorted([
    "DC Standard", "Dell Laptop", "Dell XPS", "DellNew1", "DellNew2", 
    "DellNew3", "DellNew4", "HP_Envy", "HP1", "HP2", "HP3", "HP4", 
    "Laptop 3", "Lenovo 1", "Lenovo 2", "Mini1BackUp", "Mini1Standard", 
    "Mini2BackUp", "Mini2Standard", "Mini3", "Mini3BackUp", 
    "Mini4Standard", "TXStandard"
])

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
            "portrait": {"action_set": "Global_Actions", "action_name": "Portrait"},
            "landscape": {"action_set": "Global_Actions", "action_name": "Landscape"}
        },
        "subfolder_action_set": "Event_Subfolders"
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

def upload_action_file(uploaded_file, target_folder):
    ensure_dropbox_folder(target_folder)
    target_path = f"{target_folder}/{uploaded_file.name}"
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

def action_name_input(label, current_value, available_actions, key):
    if available_actions:
        options = available_actions
        if current_value and current_value not in options:
            options = [current_value] + options
        index = options.index(current_value) if current_value in options else 0
        return st.selectbox(label, options, index=index, key=key)
    return st.text_input(label, current_value, key=key)

# --- UI LAYOUT ---
st.set_page_config(page_title="Photobooth Command", layout="wide", page_icon="📷")
st.title("📷 Photobooth Fleet Command")

# 1. SIDEBAR - FLEET VIEW
st.sidebar.header("📡 Live Status")
fleet_data = get_fleet_data()
if fleet_data:
    df = pd.DataFrame(fleet_data)
    st.sidebar.dataframe(
        df[['server_id', 'status']], 
        hide_index=True, use_container_width=True
    )
    
    # Optional Filter
    online_servers = sorted(list(set([s['server_id'] for s in fleet_data])))
    filter_server = st.sidebar.selectbox("Filter by Server (Optional)", ["All Stations"] + online_servers)
else:
    st.sidebar.warning("No servers online.")
    filter_server = "All Stations"

st.sidebar.divider()

# 2. STATION SELECTOR
st.sidebar.header("🎮 Station Manager")

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

selected_station = st.sidebar.selectbox("Select Station to Configure", display_list)

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

if selected_station:
    st.header(f"🔧 Managing: {selected_station}")
    
    config, config_path = load_config(selected_station)
    
    if not config:
        st.warning(f"Config missing for {selected_station}")
        if st.button("Initialize Config Now"):
            config, config_path = create_default_config(selected_station)
            st.rerun()
            
    if config:
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
            tab1, tab2, tab3 = st.tabs(["⚙️ Settings", "🎨 Assets", "🎬 Profiles & Actions"])
            
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
                # 1. Fetch Lists
                station_actions_folder = f"/{selected_station}/actions"
                global_action_sets = get_available_actions(ACTIONS_FOLDER)
                station_action_sets = get_available_actions(station_actions_folder)
                if not global_action_sets: global_action_sets = ["Default"]
                if not station_action_sets: station_action_sets = ["Event_Subfolders"]

                # 2. Root Actions
                st.markdown("### Root Folder Actions (Single Photos)")
                st.caption(f"Action files are loaded from {ACTIONS_FOLDER}")
                col_p, col_l = st.columns(2)
                
                with col_p:
                    st.caption("Portrait")
                    cur_p_set = config['active_profile']['portrait'].get('action_set', '')
                    cur_p_name = config['active_profile']['portrait'].get('action_name', 'Portrait')
                    
                    idx_p = global_action_sets.index(cur_p_set) if cur_p_set in global_action_sets else 0
                    new_p_set = st.selectbox("Global Action Set", global_action_sets, index=idx_p, key="p_set")
                    p_actions = load_action_metadata(ACTIONS_FOLDER, new_p_set)
                    new_p_name = action_name_input("Action Name", cur_p_name, p_actions, "p_name")

                    if new_p_set != cur_p_set or new_p_name != cur_p_name:
                        if st.button("Save Portrait"):
                            config['active_profile']['portrait']['action_set'] = new_p_set
                            config['active_profile']['portrait']['action_name'] = new_p_name
                            save_config(config, config_path)
                            st.success("Saved!")

                with col_l:
                    st.caption("Landscape")
                    cur_l_set = config['active_profile']['landscape'].get('action_set', '')
                    cur_l_name = config['active_profile']['landscape'].get('action_name', 'Landscape')
                    
                    idx_l = global_action_sets.index(cur_l_set) if cur_l_set in global_action_sets else 0
                    new_l_set = st.selectbox("Global Action Set", global_action_sets, index=idx_l, key="l_set")
                    l_actions = load_action_metadata(ACTIONS_FOLDER, new_l_set)
                    new_l_name = action_name_input("Action Name", cur_l_name, l_actions, "l_name")

                    if new_l_set != cur_l_set or new_l_name != cur_l_name:
                        if st.button("Save Landscape"):
                            config['active_profile']['landscape']['action_set'] = new_l_set
                            config['active_profile']['landscape']['action_name'] = new_l_name
                            save_config(config, config_path)
                            st.success("Saved!")

                st.divider()

                # 3. Subfolder Actions
                st.markdown("### Event Subfolder Actions (001...)")
                st.caption(f"Action files are loaded from {station_actions_folder}")
                cur_sub_set = config.get('subfolder_action_set', 'Event_Subfolders')
                idx_sub = station_action_sets.index(cur_sub_set) if cur_sub_set in station_action_sets else 0
                
                new_sub_set = st.selectbox("Station Action Set", station_action_sets, index=idx_sub, key="sub_set")
                sub_actions = load_action_metadata(station_actions_folder, new_sub_set)
                if sub_actions:
                    st.caption("Actions in this set: " + ", ".join(sub_actions[:8]) + ("..." if len(sub_actions) > 8 else ""))
                else:
                    st.caption("No metadata found yet. Upload or update metadata below to enable dropdowns.")
                
                if new_sub_set != cur_sub_set:
                    if st.button("Update Subfolder Set"):
                        config['subfolder_action_set'] = new_sub_set
                        save_config(config, config_path)
                        st.success("Updated!")

                st.divider()
                
                # 4. Uploader
                st.subheader("Upload New .atn File")
                col_global_up, col_station_up = st.columns(2)

                with col_global_up:
                    st.caption("Global root-photo action sets")
                    up_global_atn = st.file_uploader("Upload global .atn", type=['atn'], key="global_atn")
                    global_meta_set = st.text_input("Global action set name", value=(up_global_atn.name.replace(".atn", "") if up_global_atn else "Photobooth_Actions"), key="global_meta_set")
                    existing_global_actions = load_action_metadata(ACTIONS_FOLDER, global_meta_set)
                    if existing_global_actions:
                        st.caption("Existing actions: " + ", ".join(existing_global_actions[:8]) + ("..." if len(existing_global_actions) > 8 else ""))
                    global_action_text = st.text_area(
                        "Add action names to global set",
                        value="",
                        key="global_action_text",
                        placeholder="2x6_Strip\n4x6_Postcard"
                    )
                    if up_global_atn and st.button("Upload Global Action"):
                        upload_action_file(up_global_atn, ACTIONS_FOLDER)
                        save_action_metadata(ACTIONS_FOLDER, global_meta_set, global_action_text)
                        st.success(f"Uploaded to {ACTIONS_FOLDER}")
                        time.sleep(1)
                        st.rerun()
                    elif st.button("Save Global Metadata"):
                        save_action_metadata(ACTIONS_FOLDER, global_meta_set, global_action_text)
                        st.success(f"Saved metadata for {global_meta_set}")
                        time.sleep(1)
                        st.rerun()

                with col_station_up:
                    st.caption("Station event-subfolder action sets")
                    up_station_atn = st.file_uploader("Upload station .atn", type=['atn'], key="station_atn")
                    station_meta_set = st.text_input("Station action set name", value=(up_station_atn.name.replace(".atn", "") if up_station_atn else cur_sub_set), key="station_meta_set")
                    existing_station_actions = load_action_metadata(station_actions_folder, station_meta_set)
                    if existing_station_actions:
                        st.caption("Existing actions: " + ", ".join(existing_station_actions[:8]) + ("..." if len(existing_station_actions) > 8 else ""))
                    station_action_text = st.text_area(
                        "Add action names to station set",
                        value="",
                        key="station_action_text",
                        placeholder=f"{selected_station}001\n{selected_station}002"
                    )
                    if up_station_atn and st.button("Upload Station Action"):
                        upload_action_file(up_station_atn, station_actions_folder)
                        save_action_metadata(station_actions_folder, station_meta_set, station_action_text)
                        st.success(f"Uploaded to {station_actions_folder}")
                        time.sleep(1)
                        st.rerun() # Auto-Refresh Dropdowns 
                    elif st.button("Save Station Metadata"):
                        save_action_metadata(station_actions_folder, station_meta_set, station_action_text)
                        st.success(f"Saved metadata for {station_meta_set}")
                        time.sleep(1)
                        st.rerun()
