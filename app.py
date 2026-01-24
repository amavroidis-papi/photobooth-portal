import streamlit as st
import dropbox
import json
import pandas as pd
from datetime import datetime
import io

# --- CONFIGURATION ---
# We fetch the secret token from the cloud server's environment variables for security
DROPBOX_TOKEN = st.secrets["DROPBOX_TOKEN"]
GLOBAL_ASSETS = "/_Global_Assets"
HEALTH_FOLDER = f"{GLOBAL_ASSETS}/_Server_Health"

# --- CONNECT TO DROPBOX ---
try:
    dbx = dropbox.Dropbox(DROPBOX_TOKEN)
    # Check connection
    dbx.users_get_current_account()
except Exception as e:
    st.error(f"Failed to connect to Dropbox: {e}")
    st.stop()

# --- HELPER FUNCTIONS ---
def get_fleet_status():
    """Reads all JSON files in _Server_Health to find active servers."""
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

def load_config(station_id):
    """Downloads config.json for a specific station."""
    path = f"/{station_id}/config.json"
    try:
        _, res = dbx.files_download(path)
        return json.load(io.BytesIO(res.content)), path
    except:
        return None, path

def save_config(config_data, path):
    """Uploads the modified config back to Dropbox."""
    data_str = json.dumps(config_data, indent=2)
    dbx.files_upload(data_str.encode('utf-8'), path, mode=dropbox.files.WriteMode.overwrite)
    return True

def upload_asset(uploaded_file, station_id, target_filename):
    """Uploads a background or overlay to the templates folder."""
    path = f"/{station_id}/templates/{target_filename}"
    dbx.files_upload(uploaded_file.getvalue(), path, mode=dropbox.files.WriteMode.overwrite)

# --- UI LAYOUT ---
st.set_page_config(page_title="Photobooth Command Center", layout="wide")
st.title("📷 Photobooth Fleet Command")

# 1. FLEET OVERVIEW
st.sidebar.header("Fleet Status")
servers = get_fleet_status()

if not servers:
    st.sidebar.warning("No active servers found.")
else:
    df = pd.DataFrame(servers)
    # Simple logic to determine Online/Offline (Active in last 5 mins)
    now = datetime.now()
    # Note: In a real app, parse the timestamps correctly depending on server timezone
    st.sidebar.table(df[['server_id', 'watching_station', 'status']])

# 2. SELECTOR
server_options = [s['server_id'] for s in servers]
selected_server_id = st.sidebar.selectbox("Select Server to Manage", server_options)

# Find the Station ID associated with this Server
active_station = next((s['watching_station'] for s in servers if s['server_id'] == selected_server_id), None)

if active_station:
    st.header(f"Managing: {selected_server_id} ➝ {active_station}")
    
    # LOAD CONFIG
    config, config_path = load_config(active_station)
    
    if config:
        # --- TAB INTERFACE ---
        tab1, tab2, tab3 = st.tabs(["⚙️ Settings", "🎨 Assets", "🎬 Profiles"])
        
        with tab1:
            st.subheader("Live Controls")
            col1, col2 = st.columns(2)
            
            with col1:
                # Toggle: Remove Background
                current_bg = config['settings'].get('remove_background', False)
                new_bg = st.toggle("Remove Background (API)", value=current_bg)
                if new_bg != current_bg:
                    config['settings']['remove_background'] = new_bg
                    save_config(config, config_path)
                    st.toast("Settings Updated!")

                # Slider: Temperature
                current_temp = config['settings'].get('temperature', 0)
                new_temp = st.slider("Color Temperature", -100, 100, current_temp)
                if new_temp != current_temp:
                    config['settings']['temperature'] = new_temp
                    save_config(config, config_path)
                    st.toast("Temperature Updated!")

            with col2:
                # Mode Selector
                modes = ["auto", "force_portrait", "force_landscape"]
                curr_mode = config['settings'].get('orientation_mode', 'auto')
                new_mode = st.selectbox("Orientation Mode", modes, index=modes.index(curr_mode))
                if new_mode != curr_mode:
                    config['settings']['orientation_mode'] = new_mode
                    save_config(config, config_path)
                    st.toast("Orientation Updated!")

        with tab2:
            st.subheader("Asset Manager")
            st.info(f"Uploading to: /{active_station}/templates/")
            
            # Sub-Profile Selector (e.g., 001, 002)
            profile_suffix = st.text_input("Sub-Profile Suffix (Leave empty for default)", placeholder="e.g., 001")
            
            c1, c2 = st.columns(2)
            with c1:
                bg_file = st.file_uploader("Upload New Background", type=['jpg', 'jpeg'])
                if bg_file and st.button("Update Background"):
                    fname = f"background{profile_suffix}.jpg" if profile_suffix else "background.jpg"
                    upload_asset(bg_file, active_station, fname)
                    st.success(f"Uploaded {fname}")

            with c2:
                ol_file = st.file_uploader("Upload New Overlay", type=['png'])
                if ol_file and st.button("Update Overlay"):
                    fname = f"overlay{profile_suffix}.png" if profile_suffix else "overlay.png"
                    upload_asset(ol_file, active_station, fname)
                    st.success(f"Uploaded {fname}")

        with tab3:
            st.subheader("Active Profile (Photoshop Actions)")
            # In a full version, we would list .atn files from _Global_Assets
            # For now, simple text editing or dropdown logic based on config structure
            
            current_portrait = config['active_profile']['portrait']['action_name']
            new_portrait = st.text_input("Portrait Action Name", current_portrait)
            
            if new_portrait != current_portrait:
                config['active_profile']['portrait']['action_name'] = new_portrait
                if st.button("Save Profile Change"):
                    save_config(config, config_path)
                    st.success("Profile Updated")

    else:
        st.error(f"Config file not found at {config_path}. Is the station folder setup?")
else:
    st.info("Select a server to begin.")