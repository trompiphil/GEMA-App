import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import datetime
import time

# --- KONFIGURATION ---
DB_NAME = "GEMA_Datenbank"

# --- SETUP & VERBINDUNG ---
st.set_page_config(page_title="GEMA Manager", page_icon="xj", layout="centered")

# INITIALISIERUNG DES GEDÄCHTNISSES
if 'gig_draft' not in st.session_state:
    st.session_state.gig_draft = {
        "event_id": None,
        "datum": datetime.date.today(),
        "uhrzeit": datetime.time(19, 0),
        "ensemble": "Tutti",
        "location_selection": "Bitte wählen...", 
        "new_loc_data": {},
        "selected_songs": []
    }

if 'page' not in st.session_state:
    st.session_state.page = "speichern"

# Nur einmal ausführen pro Session!
if 'db_checked' not in st.session_state:
    st.session_state.db_checked = False

@st.cache_resource
def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    s_info = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(s_info, scopes=scopes)
    client = gspread.authorize(creds)
    drive_service = build('drive', 'v3', credentials=creds)
    return client, drive_service

try:
    client, drive_service = get_gspread_client()
    sh = client.open(DB_NAME)
except Exception as e:
    st.error(f"Verbindungsfehler (Bitte Seite neu laden in 1 min): {e}")
    st.stop()

# --- DB FUNKTIONEN (CACHED) ---

def check_and_fix_db():
    """Prüft Struktur nur 1x pro Sitzung, um Quota zu sparen"""
    if st.session_state.db_checked:
        return

    try: ws_rep = sh.worksheet("Repertoire")
    except: ws_rep = sh.add_worksheet(title="Repertoire", rows=100, cols=15)
    rep_headers = ['ID', 'Titel', 'Komponist_Nachname', 'Komponist_Vorname', 
                   'Bearbeiter_Nachname', 'Bearbeiter_Vorname', 'Dauer', 'Verlag', 'Werkeart', 'ISWC']
    curr_rep = ws_rep.row_values(1)
    if not curr_rep or curr_rep[0] != 'ID': ws_rep.update('A1:J1', [rep_headers])

    try: ws_ev = sh.worksheet("Events")
    except: ws_ev = sh.add_worksheet(title="Events", rows=100, cols=15)
    event_headers = ['Event_ID', 'Datum', 'Uhrzeit', 'Ensemble', 'Location_Name', 
                     'Strasse', 'PLZ', 'Stadt', 'Setlist_Name', 'Songs_IDs']
    curr_ev = ws_ev.row_values(1)
    if not curr_ev or 'Uhrzeit' not in curr_ev:
        ws_ev.clear(); ws_ev.update('A1:J1', [event_headers])

    try: ws_loc = sh.worksheet("Locations")
    except: ws_loc = sh.add_worksheet(title="Locations", rows=50, cols=5)
    loc_headers = ['ID', 'Name', 'Strasse', 'PLZ', 'Stadt']
    if not ws_loc.row_values(1): ws_loc.update('A1:E1', [loc_headers])
    
    st.session_state.db_checked = True

# --- CACHING DECORATORS ---
# Das hier ist die Magie: Daten werden im RAM gehalten und nicht jedes Mal neu geladen!

@st.cache_data(ttl=600) # Hält Daten für 10 Minuten im Speicher
def get_data_repertoire():
    ws = sh.worksheet("Repertoire")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    required = ['ID', 'Titel', 'Komponist_Nachname', 'Bearbeiter_Nachname']
    for col in required:
        if col not in df.columns: df[col] = ""
    return df

@st.cache_data(ttl=600)
def get_data_locations():
    ws = sh.worksheet("Locations")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    if df.empty: return pd.DataFrame(columns=['ID', 'Name', 'Strasse', 'PLZ', 'Stadt'])
    return df

@st.cache_data(ttl=600)
def get_data_events():
    ws = sh.worksheet("Events")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    if not df.empty and 'Datum' in df.columns:
        df['Datum_Obj'] = pd.to_datetime(df['Datum'], format="%d.%m.%Y", errors='coerce')
    return df

def clear_all_caches():
    """Löscht den Cache, damit nach dem Speichern die neuen Daten geladen werden"""
    get_data_repertoire.clear()
    get_data_locations.clear()
    get_data_events.clear()

# --- SPEICHER FUNKTIONEN ---

def save_song_direct(titel, kn, kv, bn, bv, dauer, verlag):
    try:
        ws = sh.worksheet("Repertoire")
        col_ids = ws.col_values(1)[1:] 
        ids = [int(x) for x in col_ids if str(x).isdigit()]
        new_id = max(ids) + 1 if ids else 1
        row = [new_id, titel, kn, kv, bn, bv, dauer, verlag, "U-Musik", ""]
        ws.append_row(row)
        clear_all_caches() # Cache leeren!
        return True
    except: return False

def save_location_direct(name, strasse, plz, stadt):
    ws = sh.worksheet("Locations")
    col_ids = ws.col_values(1)[1:]
    ids = [int(x) for x in col_ids if str(x).isdigit()]
    new_id = max(ids) + 1 if ids else 1
    ws.append_row([new_id, name, strasse, plz, stadt])
    clear_all_caches() # Cache leeren!
    return True

def update_event_in_db(event_id, row_data):
    ws = sh.worksheet("Events")
    try:
        cell = ws.find(str(event_id), in_column=1)
        row_num = cell.row
        ws.update(f"A{row_num}:J{row_num}", [[event_id] + row_data])
        clear_all_caches() # Cache leeren!
        return True
    except Exception as e:
        st.error(f"Fehler: {e}")
        return False

# --- NAVIGATION ---

def navigation_bar():
    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("💾 Speichern / Edit", use_container_width=True, type="primary" if st.session_state.page == "speichern" else "secondary"):
        st.session_state.page = "speichern"; st.rerun()
    if c2.button("🎵 Repertoire", use_container_width=True, type="primary" if st.session_state.page == "repertoire" else "secondary"):
        st.session_state.page = "repertoire"; st.rerun()
    if c3.button("📍 Orte", use_container_width=True, type="primary" if st.session_state.page == "orte" else "secondary"):
        st.session_state.page = "orte"; st.rerun()
    if c4.button("📂 Archiv", use_container_width=True, type="primary" if st.session_state.page == "archiv" else "secondary"):
        st.session_state.page = "archiv"; st.rerun()
    st.markdown("---")

# --- HAUPTPROGRAMM ---

check_and_fix_db()
st.title("Orchester Manager 🎻")
navigation_bar()

# ==========================================
# SEITE 1: AUFTRITT SPEICHERN
# ==========================================
if st.session_state.page == "speichern":
    
    # DATEN LADEN (JETZT GECACHED UND SCHNELL!)
    df_loc = get_data_locations()
    df_rep = get_data_repertoire()
    df_events = get_data_events()
    
    # --- EDITIER-FUNKTION ---
    with st.expander("🛠 Bereits gespeicherten Auftritt bearbeiten", expanded=False):
        if not df_events.empty:
            df_events['Label'] = df_events.apply(lambda x: f"{x['Datum']} - {x['Location_Name']} ({x['Ensemble']})", axis=1)
            df_events = df_events.sort_values(by='Datum_Obj', ascending=False)
            
            edit_options = ["Neuen Auftritt erfassen"] + df_events['Label'].tolist()
            edit_selection = st.selectbox("Wähle einen Auftritt:", edit_options)
            
            if st.button("Laden"):
                if edit_selection != "Neuen Auftritt erfassen":
                    row = df_events[df_events['Label'] == edit_selection].iloc[0]
                    st.session_state.gig_draft["event_id"] = row['Event_ID']
                    st.session_state.gig_draft["datum"] = datetime.datetime.strptime(row['Datum'], "%d.%m.%Y").date()
                    try: st.session_state.gig_draft["uhrzeit"] = datetime.datetime.strptime(row['Uhrzeit'], "%H:%M").time()
                    except: st.session_state.gig_draft["uhrzeit"] = datetime.time(19, 0)
                    st.session_state.gig_draft["ensemble"] = row['Ensemble']
                    st.session_state.gig_draft["location_selection"] = row['Location_Name']
                    
                    saved_ids = str(row['Songs_IDs']).split(",")
                    restored_labels = []
                    if not df_rep.empty:
                        df_rep['Label'] = df_rep.apply(lambda x: f"{x['Titel']} ({x['Komponist_Nachname']})", axis=1)
                        id_to_label = dict(zip(df_rep['ID'].astype(str), df_rep['Label']))
                        for sid in saved_ids:
                            if sid in id_to_label: restored_labels.append(id_to_label[sid])
                                
                    st.session_state.gig_draft["selected_songs"] = restored_labels
                    st.toast("Geladen!", icon="✏️"); time.sleep(0.5); st.rerun()
                else:
                    st.session_state.gig_draft["event_id"] = None
                    st.session_state.gig_draft["selected_songs"] = []
                    st.toast("Reset", icon="🆕"); time.sleep(0.5); st.rerun()
        else:
            st.info("Keine gespeicherten Auftritte.")

    if st.session_state.gig_draft["event_id"]:
        st.header(f"✏️ Bearbeiten (ID: {st.session_state.gig_draft['event_id']})")
    else:
        st.header("📝 Neuen Auftritt erfassen")

    # --- RAHMENDATEN ---
    c_date, c_time = st.columns(2)
    st.session_state.gig_draft["datum"] = c_date.date_input("Datum", value=st.session_state.gig_draft["datum"])
    st.session_state.gig_draft["uhrzeit"] = c_time.time_input("Uhrzeit", value=st.session_state.gig_draft["uhrzeit"])
    
    st.session_state.gig_draft["ensemble"] = st.selectbox("Ensemble", ["Tutti", "BQ", "Quartett", "Duo"], 
                                                          index=["Tutti", "BQ", "Quartett", "Duo"].index(st.session_state.gig_draft["ensemble"]))

    # --- LOCATION ---
    st.write("📍 **Spielort**")
    loc_options = ["Bitte wählen..."] + df_loc['Name'].tolist() + ["➕ Neuer Ort..."]
    try: sel_idx = loc_options.index(st.session_state.gig_draft["location_selection"])
    except: sel_idx = 0
    selected_loc = st.selectbox("Ort:", options=loc_options, index=sel_idx)
    st.session_state.gig_draft["location_selection"] = selected_loc

    final_loc_data = {}
    if selected_loc == "➕ Neuer Ort...":
        st.info("Neue Adresse eingeben:")
        with st.form("new_loc_form"):
            nl_name = st.text_input("Name*"); nl_str = st.text_input("Straße & Nr")
            c_plz, c_stadt = st.columns([1, 2])
            nl_plz = c_plz.text_input("PLZ"); nl_stadt = c_stadt.text_input("Stadt*")
            if st.form_submit_button("Bestätigen"):
                st.session_state.gig_draft["new_loc_data"] = {"Name": nl_name, "Strasse": nl_str, "PLZ": nl_plz, "Stadt": nl_stadt}
                st.success("Übernommen!"); st.rerun()
        
        if st.session_state.gig_draft["new_loc_data"]:
            d = st.session_state.gig_draft["new_loc_data"]
            st.caption(f"✅ Vorgemerkt: {d.get('Name')}")
            final_loc_data = d
    elif selected_loc != "Bitte wählen...":
        row = df_loc[df_loc['Name'] == selected_loc].iloc[0]
        final_loc_data = row.to_dict()
        st.caption(f"Adresse: {final_loc_data['Strasse']}, {final_loc_data['Stadt']}")

    st.markdown("---")

    # --- SONGS ---
    st.write("🎵 **Programm**")
    with st.expander("➕ Titel fehlt? Hier sofort anlegen"):
        with st.form("quick_add_song"):
            qc1, qc2 = st.columns([3, 1])
            q_tit = qc1.text_input("Titel"); q_dur = qc2.text_input("Dauer", value="03:00")
            qc3, qc4 = st.columns(2)
            q_kn = qc3.text_input("Komponist NN"); q_kv = qc4.text_input("Komponist VN")
            qc5, qc6 = st.columns(2)
            q_bn = qc5.text_input("Bearbeiter NN"); q_bv = qc6.text_input("Bearbeiter VN")
            q_ver = st.text_input("Verlag")
            if st.form_submit_button("Schnell speichern"):
                if q_tit and q_kn:
                    save_song_direct(q_tit, q_kn, q_kv, q_bn, q_bv, q_dur, q_ver)
                    st.toast(f"'{q_tit}' hinzugefügt!", icon="✅"); time.sleep(1); st.rerun()
                else: st.error("Pflichtfelder fehlen.")

    if not df_rep.empty and 'Titel' in df_rep.columns:
        df_rep['Label'] = df_rep.apply(lambda x: f"{x['Titel']} ({x['Komponist_Nachname']})", axis=1)
        all_options = df_rep['Label'].tolist()
        valid_selected = [s for s in st.session_state.gig_draft["selected_songs"] if s in all_options]
        
        selection = st.multiselect("Suche:", options=all_options, default=valid_selected)
        st.session_state.gig_draft["selected_songs"] = selection
        
        st.markdown("---")
        
        btn_text = "🔄 Aktualisieren" if st.session_state.gig_draft["event_id"] else "✅ Final speichern"
        if st.button(btn_text, type="primary", use_container_width=True):
            errors = []
            if selected_loc == "Bitte wählen..." or (selected_loc == "➕ Neuer Ort..." and not final_loc_data.get("Name")):
                errors.append("Bitte Ort wählen.")
            if not selection: errors.append("Kein Stück gewählt.")
            
            if errors:
                for e in errors: st.error(e)
            else:
                if selected_loc == "➕ Neuer Ort...":
                    save_location_direct(final_loc_data["Name"], final_loc_data["Strasse"], final_loc_data["PLZ"], final_loc_data["Stadt"])
                
                datum_str = st.session_state.gig_draft["datum"].strftime("%d.%m.%Y")
                time_str = st.session_state.gig_draft["uhrzeit"].strftime("%H:%M")
                dateiname = f"{st.session_state.gig_draft['ensemble']}{datum_str}{final_loc_data['Stadt']}Setlist.xlsx"
                
                song_ids = []
                for label in selection:
                    row = df_rep[df_rep['Label'] == label].iloc[0]
                    song_ids.append(str(row['ID']))
                
                row_data = [
                    datum_str, time_str, st.session_state.gig_draft["ensemble"],
                    final_loc_data["Name"], final_loc_data["Strasse"], str(final_loc_data["PLZ"]), final_loc_data["Stadt"],
                    dateiname, ",".join(song_ids)
                ]
                
                if st.session_state.gig_draft["event_id"]:
                    success = update_event_in_db(st.session_state.gig_draft["event_id"], row_data)
                else:
                    ws_ev = sh.worksheet("Events"); col_ids = ws_ev.col_values(1)[1:]
                    e_ids = [int(x) for x in col_ids if str(x).isdigit()]
                    new_ev_id = max(e_ids) + 1 if e_ids else 1
                    ws_ev.append_row([new_ev_id] + row_data)
                    clear_all_caches() # Wichtig!
                    success = True
                
                if success:
                    st.balloons()
                    st.success(f"Gespeichert: {dateiname}")
                    st.session_state.gig_draft = {
                        "event_id": None, "datum": datetime.date.today(), "uhrzeit": datetime.time(19, 0),
                        "ensemble": "Tutti", "location_selection": "Bitte wählen...", 
                        "new_loc_data": {}, "selected_songs": []
                    }
                    time.sleep(2); st.rerun()

    else: st.warning("Repertoire leer.")

# ==========================================
# ANDERE SEITEN (Kurz)
# ==========================================
elif st.session_state.page == "repertoire":
    st.subheader("Repertoire")
    with st.form("simple_rep"):
        c1, c2 = st.columns([3,1])
        t = c1.text_input("Titel"); d = c2.text_input("Dauer", "03:00")
        k = st.text_input("Komponist NN")
        if st.form_submit_button("Speichern"):
            save_song_direct(t, k, "", "", "", d, "")
            st.success("OK"); time.sleep(1); st.rerun()
    st.dataframe(get_data_repertoire(), use_container_width=True)

elif st.session_state.page == "orte":
    st.subheader("Locations")
    with st.form("new_loc"):
        l_name = st.text_input("Name"); l_stadt = st.text_input("Stadt")
        if st.form_submit_button("Speichern"):
            save_location_direct(l_name, "", "", l_stadt)
            st.success("OK"); time.sleep(1); st.rerun()
    st.dataframe(get_data_locations(), use_container_width=True)

elif st.session_state.page == "archiv":
    st.subheader("Archiv")
    st.dataframe(get_data_events(), use_container_width=True)
