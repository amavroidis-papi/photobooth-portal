import streamlit as st
import dropbox
import json
import pandas as pd
import io
import os
import time
from PIL import Image as PILImage

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

# MASTER STATION LIST
KNOWN_STATIONS = sorted([
    "DC Standard", "Dell Laptop", "Dell XPS", "DellNew1", "DellNew2", 
    "DellNew3", "DellNew4", "HP_Envy", "HP1", "HP2", "HP3", "HP4", 
    "Laptop 3", "Lenovo 1", "Lenovo 2", "Mini1BackUp", "Mini1Standard", 
    "Mini2BackUp", "Mini2Standard", "Mini3", "Mini3BackUp", 
    "Mini4Standard", "TXStandard"
])

# Subfolder options for events
SUBFOLDER_OPTIONS = ["001", "002", "003", "004", "005", "006", "007", "008", "009"]

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

def get_available_actions():
    """Get actions from Global folder (legacy)."""
    actions = []
    try:
        res = dbx.files_list_folder(ACTIONS_FOLDER)
        for entry in res.entries:
            if entry.name.endswith('.atn'):
                actions.append(entry.name.replace(".atn", ""))
    except: pass
    return sorted(actions)

def get_station_actions(station_id):
    """Get actions from station's local folder."""
    actions = []
    try:
        station_actions_path = f"/{station_id}/actions"
        res = dbx.files_list_folder(station_actions_path)
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

def upload_action_to_station(uploaded_file, station_id, target_type, subfolder=None):
    """
    Upload action file to station's /actions/ folder with proper naming.
    
    Args:
        uploaded_file: The uploaded .atn file
        station_id: Target station (e.g., "HP1")
        target_type: "root" or "subfolder"
        subfolder: Subfolder number (e.g., "001") if target_type is "subfolder"
    
    Returns:
        (success: bool, message: str)
    """
    try:
        # Determine target filename
        if target_type == "root":
            target_filename = f"{station_id}_Root.atn"
            trigger_path = f"/{station_id}/incoming/_trigger_reload.jpg"
        else:
            target_filename = f"{station_id}_{subfolder}.atn"
            trigger_path = f"/{station_id}/incoming/{subfolder}/_trigger_reload.jpg"
        
        # Ensure actions folder exists (upload will create it)
        action_path = f"/{station_id}/actions/{target_filename}"
        
        # Upload the action file
        dbx.files_upload(
            uploaded_file.getvalue(), 
            action_path, 
            mode=dropbox.files.WriteMode.overwrite
        )
        
        # Create and upload trigger file (small red image)
        trigger_image = create_trigger_image()
        dbx.files_upload(
            trigger_image, 
            trigger_path, 
            mode=dropbox.files.WriteMode.overwrite
        )
        
        return True, f"✅ Uploaded as {target_filename} and triggered reload!"
        
    except Exception as e:
        return False, f"❌ Upload failed: {str(e)}"

def create_trigger_image():
    """Create a small trigger image (1x1 red pixel) as bytes."""
    img = PILImage.new('RGB', (10, 10), color='red')
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=50)
    buffer.seek(0)
    return buffer.getvalue()

def ensure_station_folders(station_id):
    """Ensure station has required folders."""
    folders = [
        f"/{station_id}/actions",
        f"/{station_id}/incoming",
        f"/{station_id}/processed",
        f"/{station_id}/final"
    ]
    for folder in folders:
        try:
            dbx.files_create_folder_v2(folder)
        except:
            pass  # Folder already exists

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

# --- FLEET DASHBOARD ---
if fleet_data:
    with st.expander("🌐 Global Fleet Dashboard", expanded=False):
        for data in fleet_data:
            sid = data.get('server_id')
            version = data.get('version', 'Unknown')
            st.subheader(f"🖥️ {sid} ({data.get('status')}) - {version}")
            
            active = data.get('active_stations', [])
            standby = data.get('standby_stations', [])
            ghosts = data.get('unconfigured_stations', [])

            t1, t2, t3 = st.tabs([
                f"🟢 Active ({len(active)})", 
                f"🟡 Standby ({len(standby)})", 
                f"🔴 Unconfigured ({len(ghosts)})"
            ])
            
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

# --- MAIN STATION CONFIGURATION ---
if selected_station:
    st.header(f"🔧 Managing: {selected_station}")
    
    config, config_path = load_config(selected_station)
    
    if not config:
        st.warning(f"Config missing for {selected_station}")
        if st.button("Initialize Config Now"):
            config, config_path = create_default_config(selected_station)
            ensure_station_folders(selected_station)
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
            tab1, tab2, tab3, tab4 = st.tabs([
                "🎬 Upload Actions", 
                "⚙️ Settings", 
                "🎨 Assets", 
                "📋 Current Actions"
            ])
            
            # --- TAB 1: UPLOAD ACTIONS (NEW - Primary Tab) ---
            with tab1:
                st.subheader("📤 Upload Action to Station")
                
                # Instructions Box
                st.info("""
                **📋 ACTION NAMING RULES**
                
                When creating actions in Photoshop, name them exactly as follows:
                
                **For ROOT uploads** (photos in main incoming folder):
                - Create action named **"Portrait"** (for portrait photos)
                - Create action named **"Landscape"** (for landscape photos)
                
                **For SUBFOLDER uploads** (photos in incoming/001, 002, etc.):
                - Create action named **"Main"**
                
                The action SET name can be anything you want (e.g., "Wedding_Template.atn")
                """)
                
                st.divider()
                
                # Target Selection
                col1, col2 = st.columns(2)
                
                with col1:
                    target_type = st.radio(
                        "Upload Target",
                        ["Root (incoming folder)", "Subfolder (001, 002, etc.)"],
                        key="upload_target"
                    )
                
                with col2:
                    if "Subfolder" in target_type:
                        subfolder = st.selectbox(
                            "Select Subfolder",
                            SUBFOLDER_OPTIONS,
                            key="subfolder_select"
                        )
                    else:
                        subfolder = None
                        st.caption("Root actions handle Portrait & Landscape automatically")
                
                st.divider()
                
                # File Uploader
                uploaded_action = st.file_uploader(
                    "Select .atn file to upload",
                    type=['atn'],
                    key="action_uploader"
                )
                
                if uploaded_action:
                    # Show what will happen
                    if "Root" in target_type:
                        target_name = f"{selected_station}_Root.atn"
                        st.caption(f"📁 Will be saved as: `/{selected_station}/actions/{target_name}`")
                        st.caption(f"🎯 Trigger file will be placed in: `/{selected_station}/incoming/`")
                    else:
                        target_name = f"{selected_station}_{subfolder}.atn"
                        st.caption(f"📁 Will be saved as: `/{selected_station}/actions/{target_name}`")
                        st.caption(f"🎯 Trigger file will be placed in: `/{selected_station}/incoming/{subfolder}/`")
                    
                    # Upload Button
                    if st.button("🚀 Upload & Apply", type="primary"):
                        with st.spinner("Uploading and triggering reload..."):
                            # Ensure folders exist
                            ensure_station_folders(selected_station)
                            if subfolder:
                                try:
                                    dbx.files_create_folder_v2(f"/{selected_station}/incoming/{subfolder}")
                                except: pass
                            
                            # Upload
                            target = "root" if "Root" in target_type else "subfolder"
                            success, message = upload_action_to_station(
                                uploaded_action, 
                                selected_station, 
                                target, 
                                subfolder
                            )
                            
                            if success:
                                st.success(message)
                                st.balloons()
                            else:
                                st.error(message)
                
                st.divider()
                
                # Show current station actions
                st.subheader(f"📂 Current Actions for {selected_station}")
                station_actions = get_station_actions(selected_station)
                if station_actions:
                    for action in station_actions:
                        st.caption(f"✅ {action}.atn")
                else:
                    st.caption("No actions uploaded yet for this station.")
            
            # --- TAB 2: SETTINGS ---
            with tab2:
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

            # --- TAB 3: ASSETS ---
            with tab3:
                st.subheader("Upload Assets")
                st.caption(f"Target: /{selected_station}/templates/")
                suffix = st.text_input("Sub-Profile (e.g., 001)", placeholder="Default", key="asset_suffix")
                
                c1, c2 = st.columns(2)
                with c1:
                    bg = st.file_uploader("Background (.jpg)", type=['jpg', 'jpeg'], key="bg_upload")
                    if bg and st.button("Upload BG"):
                        name = f"background{suffix}.jpg" if suffix else "background.jpg"
                        upload_asset(bg, f"/{selected_station}/templates/{name}")
                        st.success(f"Saved {name}")
                        time.sleep(1)
                        st.rerun()
                with c2:
                    ol = st.file_uploader("Overlay (.png)", type=['png'], key="overlay_upload")
                    if ol and st.button("Upload Overlay"):
                        name = f"overlay{suffix}.png" if suffix else "overlay.png"
                        upload_asset(ol, f"/{selected_station}/templates/{name}")
                        st.success(f"Saved {name}")
                        time.sleep(1)
                        st.rerun()

            # --- TAB 4: CURRENT ACTIONS (View Only) ---
            with tab4:
                st.subheader("📋 Current Action Configuration")
                
                st.markdown("### Station Actions")
                station_actions = get_station_actions(selected_station)
                if station_actions:
                    for action in station_actions:
                        if "_Root" in action:
                            st.success(f"🏠 **Root:** {action}.atn → Uses actions 'Portrait' & 'Landscape'")
                        elif "_" in action:
                            parts = action.split("_")
                            if len(parts) >= 2:
                                subfolder = parts[-1]
                                st.info(f"📁 **Subfolder {subfolder}:** {action}.atn → Uses action 'Main'")
                        else:
                            st.caption(f"📄 {action}.atn")
                else:
                    st.warning("No actions uploaded for this station yet.")
                
                st.divider()
                
                st.markdown("### Legacy Global Actions")
                st.caption("These are in the old /_Global_Assets/Actions/ folder:")
                global_actions = get_available_actions()
                if global_actions:
                    st.caption(", ".join(global_actions))
                else:
                    st.caption("None")
                
                st.divider()
                
                # Legacy uploader (for backwards compatibility)
                with st.expander("⚠️ Legacy: Upload to Global Actions (Old System)"):
                    st.warning("This uploads to the shared Global folder. Use 'Upload Actions' tab for the new per-station system.")
                    up_atn = st.file_uploader("Select .atn file", type=['atn'], key="legacy_upload")
                    if up_atn and st.button("Upload to Global"):
                        upload_asset(up_atn, f"{ACTIONS_FOLDER}/{up_atn.name}")
                        st.success("Uploaded to Global!")
                        time.sleep(1)
                        st.rerun()
