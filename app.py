import streamlit as st
import dropbox
import json
import pandas as pd
import io
import os
import time
from PIL import Image as PILImage

# --- CONFIGURATION ---
DROPBOX_APP_KEY = os.environ.get("DROPBOX_APP_KEY")
DROPBOX_APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")
DROPBOX_REFRESH_TOKEN = os.environ.get("DROPBOX_REFRESH_TOKEN")
DROPBOX_TOKEN = os.environ.get("DROPBOX_TOKEN")

GLOBAL_ASSETS = "/_Global_Assets"
ACTIONS_FOLDER = f"{GLOBAL_ASSETS}/Actions"
HEALTH_FOLDER = f"{GLOBAL_ASSETS}/_Server_Health"

# Root action options (from Global_Root.atn)
ROOT_ACTION_OPTIONS = ["Portrait", "Portrait_AI", "Landscape", "Landscape_AI"]

# MASTER STATION LIST
KNOWN_STATIONS = sorted([
    "DC Standard", "Dell Laptop", "Dell XPS", "DellNew1", "DellNew2", 
    "DellNew3", "DellNew4", "HP_Envy", "HP1", "HP2", "HP3", "HP4", 
    "Laptop 3", "Lenovo 1", "Lenovo 2", "Mini1BackUp", "Mini1Standard", 
    "Mini2BackUp", "Mini2Standard", "Mini3", "Mini3BackUp", 
    "Mini4Standard", "TXStandard"
])

# --- CONNECT TO DROPBOX ---
try:
    if DROPBOX_APP_KEY and DROPBOX_APP_SECRET and DROPBOX_REFRESH_TOKEN:
        dbx = dropbox.Dropbox(
            app_key=DROPBOX_APP_KEY,
            app_secret=DROPBOX_APP_SECRET,
            oauth2_refresh_token=DROPBOX_REFRESH_TOKEN
        )
    elif DROPBOX_TOKEN:
        dbx = dropbox.Dropbox(DROPBOX_TOKEN)
    else:
        st.error("Missing Dropbox Credentials")
        st.stop()
        
    try:
        dbx.users_get_current_account()
    except Exception:
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

def get_station_subfolder_actions(station_id):
    """Check if station has subfolder actions file."""
    try:
        action_path = f"{ACTIONS_FOLDER}/{station_id}.atn"
        dbx.files_get_metadata(action_path)
        return True
    except:
        return False

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
        "assigned_server": "",
        "settings": {
            "remove_background": False,
            "remove_bg_api_key": "",
            "orientation_mode": "auto",
            "temperature": 0
        },
        "root_actions": {
            "portrait": "Portrait",
            "landscape": "Landscape"
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

def create_trigger_image():
    """Create a small trigger image as bytes."""
    img = PILImage.new('RGB', (10, 10), color='red')
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=50)
    buffer.seek(0)
    return buffer.getvalue()

def upload_subfolder_actions(uploaded_file, station_id):
    """
    Upload subfolder action file for a station.
    File will be renamed to {station_id}.atn
    """
    try:
        # Save to Global Actions folder with station name
        action_path = f"{ACTIONS_FOLDER}/{station_id}.atn"
        dbx.files_upload(
            uploaded_file.getvalue(), 
            action_path, 
            mode=dropbox.files.WriteMode.overwrite
        )
        
        # Create trigger file in station's incoming folder
        # (using subfolder 001 as trigger location)
        trigger_path = f"/{station_id}/incoming/001/_trigger_reload.jpg"
        
        # Ensure subfolder exists
        try:
            dbx.files_create_folder_v2(f"/{station_id}/incoming/001")
        except:
            pass
        
        dbx.files_upload(
            create_trigger_image(), 
            trigger_path, 
            mode=dropbox.files.WriteMode.overwrite
        )
        
        return True, f"✅ Uploaded {station_id}.atn and triggered reload!"
        
    except Exception as e:
        return False, f"❌ Upload failed: {str(e)}"

def ensure_station_folders(station_id):
    """Ensure station has required folders."""
    folders = [
        f"/{station_id}/incoming",
        f"/{station_id}/processed",
        f"/{station_id}/final"
    ]
    for folder in folders:
        try:
            dbx.files_create_folder_v2(folder)
        except:
            pass

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
    
    online_servers = sorted(list(set([s['server_id'] for s in fleet_data])))
    filter_server = st.sidebar.selectbox("Filter by Server", ["All Stations"] + online_servers)
else:
    st.sidebar.warning("No servers online.")
    filter_server = "All Stations"

st.sidebar.divider()

# 2. STATION SELECTOR
st.sidebar.header("🎮 Station Manager")

if filter_server != "All Stations":
    filtered_list = []
    for s in fleet_data:
        if s['server_id'] == filter_server:
            filtered_list.extend(s.get('active_stations', []))
            filtered_list.extend(s.get('standby_stations', []))
    display_list = sorted(list(set(filtered_list)))
else:
    display_list = KNOWN_STATIONS

selected_station = st.sidebar.selectbox("Select Station", display_list)

# --- FLEET DASHBOARD ---
if fleet_data:
    with st.expander("🌐 Fleet Dashboard", expanded=False):
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
        
        col_sw, col_st = st.columns([1, 5])
        with col_sw:
            new_enabled = st.toggle("Station ON/OFF", value=is_enabled)
        with col_st:
            if new_enabled:
                st.markdown("### 🟢 Active")
            else:
                st.markdown("### 🔴 Disabled")
        
        if new_enabled != is_enabled:
            config["station_enabled"] = new_enabled
            save_config(config, config_path)
            st.rerun()

        st.divider()

        if is_enabled:
            tab1, tab2, tab3 = st.tabs([
                "🎬 Actions", 
                "⚙️ Settings", 
                "🎨 Assets"
            ])
            
            # --- TAB 1: ACTIONS ---
            with tab1:
                # Ensure root_actions exists in config
                if 'root_actions' not in config:
                    config['root_actions'] = {
                        'portrait': 'Portrait',
                        'landscape': 'Landscape'
                    }
                    save_config(config, config_path)
                
                # === ROOT ACTIONS SECTION ===
                st.subheader("📸 Root Actions (incoming folder)")
                st.caption("Photos dropped directly in the incoming folder use these actions from Global_Root.atn")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    current_portrait = config['root_actions'].get('portrait', 'Portrait')
                    portrait_options = ["Portrait", "Portrait_AI"]
                    portrait_idx = portrait_options.index(current_portrait) if current_portrait in portrait_options else 0
                    
                    new_portrait = st.selectbox(
                        "Portrait Action",
                        portrait_options,
                        index=portrait_idx,
                        key="portrait_select"
                    )
                
                with col2:
                    current_landscape = config['root_actions'].get('landscape', 'Landscape')
                    landscape_options = ["Landscape", "Landscape_AI"]
                    landscape_idx = landscape_options.index(current_landscape) if current_landscape in landscape_options else 0
                    
                    new_landscape = st.selectbox(
                        "Landscape Action",
                        landscape_options,
                        index=landscape_idx,
                        key="landscape_select"
                    )
                
                # Save if changed
                if new_portrait != current_portrait or new_landscape != current_landscape:
                    if st.button("💾 Save Root Action Selection"):
                        config['root_actions']['portrait'] = new_portrait
                        config['root_actions']['landscape'] = new_landscape
                        save_config(config, config_path)
                        st.success("Root actions updated!")
                        st.rerun()
                
                st.divider()
                
                # === SUBFOLDER ACTIONS SECTION ===
                st.subheader("📁 Subfolder Actions (001, 002, etc.)")
                st.caption(f"Photos in subfolders use actions from {selected_station}.atn")
                
                # Check if station has subfolder actions
                has_subfolder_actions = get_station_subfolder_actions(selected_station)
                
                if has_subfolder_actions:
                    st.success(f"✅ {selected_station}.atn exists in Global Actions")
                else:
                    st.warning(f"⚠️ {selected_station}.atn not found - upload below")
                
                st.markdown("---")
                
                # Upload section
                st.markdown("**Upload New Subfolder Actions**")
                
                # Instructions
                with st.expander("📋 How to Create Subfolder Actions", expanded=not has_subfolder_actions):
                    st.markdown(f"""
                    **Step-by-step guide:**
                    
                    1. Open Photoshop
                    2. Open Actions Panel (Window → Actions)
                    3. Create a new Action Set named exactly: **`{selected_station}`**
                    4. Inside this set, create actions named:
                       - `001` (for incoming/001 folder)
                       - `002` (for incoming/002 folder)
                       - `003`, `004`, etc. as needed
                    5. Each action should include **Save** and **Close** steps
                    6. Select the set **`{selected_station}`** in the Actions panel
                    7. Click ☰ menu → **Save Actions**
                    8. Save the file (any filename is fine)
                    9. Upload here!
                    
                    **Important:** The set name MUST be exactly `{selected_station}`
                    """)
                
                # File uploader
                uploaded_action = st.file_uploader(
                    "Select .atn file",
                    type=['atn'],
                    key="subfolder_action_upload"
                )
                
                if uploaded_action:
                    st.caption(f"📁 Will be saved as: `/_Global_Assets/Actions/{selected_station}.atn`")
                    
                    if st.button("🚀 Upload & Apply", type="primary"):
                        with st.spinner("Uploading..."):
                            success, message = upload_subfolder_actions(uploaded_action, selected_station)
                            if success:
                                st.success(message)
                                st.balloons()
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.error(message)
            
            # --- TAB 2: SETTINGS ---
            with tab2:
                st.subheader("⚙️ Processing Settings")
                
                c1, c2 = st.columns(2)
                with c1:
                    # Server Assignment
                    current_server = config.get('assigned_server', '')
                    server_options = [""] + [s['server_id'] for s in fleet_data] if fleet_data else [""]
                    server_idx = server_options.index(current_server) if current_server in server_options else 0
                    new_server = st.selectbox("Assigned Server", server_options, index=server_idx)
                    if new_server != current_server:
                        config['assigned_server'] = new_server
                        save_config(config, config_path)
                        st.toast("Server updated!")
                    
                    # Background Removal
                    curr_bg = config['settings'].get('remove_background', False)
                    new_bg = st.toggle("Remove Background (API)", value=curr_bg)
                    if new_bg != curr_bg:
                        config['settings']['remove_background'] = new_bg
                        save_config(config, config_path)
                        st.toast("Updated!")
                    
                    if new_bg:
                        curr_key = config['settings'].get('remove_bg_api_key', '')
                        new_key = st.text_input("Remove.bg API Key", value=curr_key, type="password")
                        if new_key != curr_key:
                            config['settings']['remove_bg_api_key'] = new_key
                            save_config(config, config_path)
                            st.toast("API Key saved!")

                with c2:
                    # Orientation Mode
                    modes = ["auto", "force_portrait", "force_landscape"]
                    curr_mode = config['settings'].get('orientation_mode', 'auto')
                    new_mode = st.selectbox("Orientation Mode", modes, index=modes.index(curr_mode))
                    if new_mode != curr_mode:
                        config['settings']['orientation_mode'] = new_mode
                        save_config(config, config_path)
                        st.toast("Updated!")
                    
                    # Temperature
                    curr_temp = config['settings'].get('temperature', 0)
                    new_temp = st.slider("Temperature Adjustment", -100, 100, curr_temp)
                    if new_temp != curr_temp:
                        config['settings']['temperature'] = new_temp
                        save_config(config, config_path)
                        st.toast("Updated!")

            # --- TAB 3: ASSETS ---
            with tab3:
                st.subheader("🎨 Upload Assets")
                st.caption(f"Target: /{selected_station}/templates/")
                
                suffix = st.text_input("Sub-Profile (e.g., 001)", placeholder="Leave empty for default", key="asset_suffix")
                
                c1, c2 = st.columns(2)
                with c1:
                    bg = st.file_uploader("Background (.jpg)", type=['jpg', 'jpeg'], key="bg_upload")
                    if bg and st.button("Upload Background"):
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
