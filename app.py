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
        "event_id": None,           # Wenn nicht None, sind wir im Editier-Modus
        "datum": datetime.date.today(),
        "uhrzeit": datetime.time(19, 0),
        "ensemble": "Tutti",
        "location_selection": "Bitte wählen...", 
        "new_loc_data": {},         # Hier landen die Daten aus dem Formular
        "selected_songs": []
    }

if 'page' not in st.session_state:
    st.session_state.page = "speichern"

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
    st.error(f"Verbindungsfehler: {e}")
    st.stop()

# --- DB FUNKTIONEN ---

def check_and_fix_db():
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

def load_repertoire():
    ws = sh.worksheet("Repertoire")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    required = ['ID', 'Titel', 'Komponist_Nachname', 'Bearbeiter_Nachname']
    for col in required:
        if col not in df.columns: df[col] = ""
    return df

def load_locations():
    ws = sh.worksheet("Locations")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    if df.empty: return pd.DataFrame(columns=['ID', 'Name', 'Strasse', 'PLZ', 'Stadt'])
    return df

def load_events():
    ws = sh.worksheet("Events")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    if not df.empty and 'Datum' in df.columns:
        df['Datum_Obj'] = pd.to_datetime(df['Datum'], format="%d.%m.%Y", errors='coerce')
    return df

def save_song_direct(titel, kn, kv, bn, bv, dauer, verlag):
    try:
        ws = sh.worksheet("Repertoire")
        col_ids = ws.col_values(1)[1:] 
        ids = [int(x) for x in col_ids if str(x).isdigit()]
        new_id = max(ids) + 1 if ids else 1
        row = [new_id, titel, kn, kv, bn, bv, dauer, verlag, "U-Musik", ""]
        ws.append_row(row)
        return True
    except: return False

def save_location_direct(name, strasse, plz, stadt):
    ws = sh.worksheet("Locations")
    col_ids = ws.col_values(1)[1:]
    ids = [int(x) for x in col_ids if str(x).isdigit()]
    new_id = max(ids) + 1 if ids else 1
    ws.append_row([new_id, name, strasse, plz, stadt])
    return True

def update_event_in_db(event_id, row_data):
    """Aktualisiert eine existierende Zeile in Events"""
    ws = sh.worksheet("Events")
    try:
        cell = ws.find(str(event_id), in_column=1)
        row_num = cell.row
        # Wir überschreiben die ganze Zeile (außer ID an pos 0)
        # row_data kommt ohne ID, also Event_ID, Datum, Uhrzeit...
        # range ist B{row}:J{row}
        ws.update(f"A{row_num}:J{row_num}", [[event_id] + row_data])
        return True
    except Exception as e:
        st.error(f"Fehler beim Update: {e}")
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
# SEITE 1: AUFTRITT SPEICHERN & EDITIEREN
# ==========================================
if st.session_state.page == "speichern":
    
    # DATEN LADEN
    df_loc = load_locations()
    df_rep = load_repertoire()
    df_events = load_events()
    
    # --- EDITIER-FUNKTION ---
    with st.expander("🛠 Bereits gespeicherten Auftritt bearbeiten", expanded=False):
        if not df_events.empty:
            # Dropdown Label bauen
            df_events['Label'] = df_events.apply(lambda x: f"{x['Datum']} - {x['Location_Name']} ({x['Ensemble']})", axis=1)
            # Sortieren nach Datum neu -> alt
            df_events = df_events.sort_values(by='Datum_Obj', ascending=False)
            
            edit_options = ["Neuen Auftritt erfassen"] + df_events['Label'].tolist()
            edit_selection = st.selectbox("Wähle einen Auftritt zum Bearbeiten:", edit_options)
            
            if st.button("Diesen Auftritt laden"):
                if edit_selection != "Neuen Auftritt erfassen":
                    # Daten aus DB holen und in Session State schreiben
                    row = df_events[df_events['Label'] == edit_selection].iloc[0]
                    
                    st.session_state.gig_draft["event_id"] = row['Event_ID']
                    st.session_state.gig_draft["datum"] = datetime.datetime.strptime(row['Datum'], "%d.%m.%Y").date()
                    try:
                        st.session_state.gig_draft["uhrzeit"] = datetime.datetime.strptime(row['Uhrzeit'], "%H:%M").time()
                    except:
                        st.session_state.gig_draft["uhrzeit"] = datetime.time(19, 0)
                        
                    st.session_state.gig_draft["ensemble"] = row['Ensemble']
                    st.session_state.gig_draft["location_selection"] = row['Location_Name']
                    
                    # Song IDs wieder in Labels wandeln
                    saved_ids = str(row['Songs_IDs']).split(",")
                    restored_labels = []
                    if not df_rep.empty:
                        # Hilfs-Map ID -> Label
                        df_rep['Label'] = df_rep.apply(lambda x: f"{x['Titel']} ({x['Komponist_Nachname']})", axis=1)
                        id_to_label = dict(zip(df_rep['ID'].astype(str), df_rep['Label']))
                        
                        for sid in saved_ids:
                            if sid in id_to_label:
                                restored_labels.append(id_to_label[sid])
                                
                    st.session_state.gig_draft["selected_songs"] = restored_labels
                    st.toast("Auftritt geladen! Jetzt bearbeiten und speichern.", icon="✏️")
                    time.sleep(1)
                    st.rerun()
                else:
                    # Reset auf Leer
                    st.session_state.gig_draft["event_id"] = None
                    st.session_state.gig_draft["selected_songs"] = []
                    st.toast("Reset auf 'Neu'", icon="🆕")
                    time.sleep(0.5)
                    st.rerun()
        else:
            st.info("Keine gespeicherten Auftritte gefunden.")

    # --- ÜBERSCHRIFT ---
    if st.session_state.gig_draft["event_id"]:
        st.header(f"✏️ Auftritt bearbeiten (ID: {st.session_state.gig_draft['event_id']})")
    else:
        st.header("📝 Neuen Auftritt erfassen")

    # --- RAHMENDATEN ---
    c_date, c_time = st.columns(2)
    st.session_state.gig_draft["datum"] = c_date.date_input("Datum", value=st.session_state.gig_draft["datum"])
    st.session_state.gig_draft["uhrzeit"] = c_time.time_input("Uhrzeit", value=st.session_state.gig_draft["uhrzeit"])
    
    st.session_state.gig_draft["ensemble"] = st.selectbox("Ensemble", ["Tutti", "BQ", "Quartett", "Duo"], 
                                                          index=["Tutti", "BQ", "Quartett", "Duo"].index(st.session_state.gig_draft["ensemble"]))

    # --- LOCATION LOGIK ---
    st.write("📍 **Spielort**")
    loc_options = ["Bitte wählen..."] + df_loc['Name'].tolist() + ["➕ Neuer Ort..."]
    
    # Index finden
    try: sel_idx = loc_options.index(st.session_state.gig_draft["location_selection"])
    except: sel_idx = 0
        
    selected_loc = st.selectbox("Ort:", options=loc_options, index=sel_idx)
    st.session_state.gig_draft["location_selection"] = selected_loc

    final_loc_data = {}
    
    if selected_loc == "➕ Neuer Ort...":
        # FORMULAR GEGEN RELOADS
        st.info("Bitte Adresse eingeben und bestätigen:")
        with st.form("new_loc_form"):
            nl_name = st.text_input("Name der Location*")
            nl_str = st.text_input("Straße & Nr")
            c_plz, c_stadt = st.columns([1, 2])
            nl_plz = c_plz.text_input("PLZ")
            nl_stadt = c_stadt.text_input("Stadt*")
            
            if st.form_submit_button("Adresse bestätigen"):
                st.session_state.gig_draft["new_loc_data"] = {
                    "Name": nl_name, "Strasse": nl_str, "PLZ": nl_plz, "Stadt": nl_stadt
                }
                st.success("Adresse übernommen!")
                # KEIN Rerun hier nötig, User sieht den Erfolg und macht weiter
        
        # Prüfen ob Daten da sind
        if st.session_state.gig_draft["new_loc_data"]:
            d = st.session_state.gig_draft["new_loc_data"]
            st.caption(f"✅ Vorgemerkt: {d.get('Name')}, {d.get('Stadt')}")
            final_loc_data = d
            
    elif selected_loc != "Bitte wählen...":
        row = df_loc[df_loc['Name'] == selected_loc].iloc[0]
        final_loc_data = row.to_dict()
        st.caption(f"Adresse: {final_loc_data['Strasse']}, {final_loc_data['Stadt']}")

    st.markdown("---")

    # --- SONG AUSWAHL ---
    st.write("🎵 **Programm**")
    
    # SCHNELL-ANLAGE (Erweitert)
    with st.expander("➕ Titel fehlt? Hier sofort anlegen"):
        with st.form("quick_add_song"):
            qc1, qc2 = st.columns([3, 1])
            q_tit = qc1.text_input("Titel")
            q_dur = qc2.text_input("Dauer", value="03:00")
            qc3, qc4 = st.columns(2)
            q_kn = qc3.text_input("Komponist NN")
            q_kv = qc4.text_input("Komponist VN")
            
            # NEU: Bearbeiter
            qc5, qc6 = st.columns(2)
            q_bn = qc5.text_input("Bearbeiter NN")
            q_bv = qc6.text_input("Bearbeiter VN")
            
            q_ver = st.text_input("Verlag")
            
            if st.form_submit_button("Schnell speichern"):
                if q_tit and q_kn:
                    save_song_direct(q_tit, q_kn, q_kv, q_bn, q_bv, q_dur, q_ver)
                    st.toast(f"'{q_tit}' hinzugefügt!", icon="✅")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Titel & Komponist Pflicht.")

    # MULTISELECT
    if not df_rep.empty and 'Titel' in df_rep.columns:
        df_rep['Label'] = df_rep.apply(lambda x: f"{x['Titel']} ({x['Komponist_Nachname']})", axis=1)
        all_options = df_rep['Label'].tolist()
        valid_selected = [s for s in st.session_state.gig_draft["selected_songs"] if s in all_options]
        
        selection = st.multiselect("Suche (Titel/Komponist):", options=all_options, default=valid_selected)
        st.session_state.gig_draft["selected_songs"] = selection
        
        st.markdown("---")
        
        # --- SPEICHERN BUTTON ---
        btn_text = "🔄 Änderungen speichern" if st.session_state.gig_draft["event_id"] else "✅ Auftritt final speichern"
        
        if st.button(btn_text, type="primary", use_container_width=True):
            # Validierung
            errors = []
            if selected_loc == "Bitte wählen..." or (selected_loc == "➕ Neuer Ort..." and not final_loc_data.get("Name")):
                errors.append("Bitte Ort wählen oder eingeben.")
            if not selection:
                errors.append("Bitte mindestens ein Stück wählen.")
            
            if errors:
                for e in errors: st.error(e)
            else:
                # 1. Neuer Ort?
                if selected_loc == "➕ Neuer Ort...":
                    save_location_direct(final_loc_data["Name"], final_loc_data["Strasse"], 
                                         final_loc_data["PLZ"], final_loc_data["Stadt"])
                
                # 2. Daten vorbereiten
                datum_str = st.session_state.gig_draft["datum"].strftime("%d.%m.%Y")
                time_str = st.session_state.gig_draft["uhrzeit"].strftime("%H:%M")
                dateiname = f"{st.session_state.gig_draft['ensemble']}{datum_str}{final_loc_data['Stadt']}Setlist.xlsx"
                
                song_ids = []
                for label in selection:
                    row = df_rep[df_rep['Label'] == label].iloc[0]
                    song_ids.append(str(row['ID']))
                
                # Datensatz für DB (ohne ID am Anfang, das macht die Save/Update funktion)
                row_data_for_db = [
                    datum_str, time_str,
                    st.session_state.gig_draft["ensemble"],
                    final_loc_data["Name"], final_loc_data["Strasse"],
                    str(final_loc_data["PLZ"]), final_loc_data["Stadt"],
                    dateiname, ",".join(song_ids)
                ]
                
                # 3. Speichern oder Updaten
                if st.session_state.gig_draft["event_id"]:
                    # UPDATE
                    success = update_event_in_db(st.session_state.gig_draft["event_id"], row_data_for_db)
                    msg = "Auftritt aktualisiert!"
                else:
                    # NEU
                    # Neue Event ID berechnen
                    ws_ev = sh.worksheet("Events")
                    col_ids = ws_ev.col_values(1)[1:]
                    e_ids = [int(x) for x in col_ids if str(x).isdigit()]
                    new_ev_id = max(e_ids) + 1 if e_ids else 1
                    
                    ws_ev.append_row([new_ev_id] + row_data_for_db)
                    success = True
                    msg = "Auftritt neu gespeichert!"
                
                if success:
                    st.balloons()
                    st.success(f"{msg} Setlist: {dateiname}")
                    # Draft Reset
                    st.session_state.gig_draft = {
                        "event_id": None, "datum": datetime.date.today(), "uhrzeit": datetime.time(19, 0),
                        "ensemble": "Tutti", "location_selection": "Bitte wählen...", 
                        "new_loc_data": {}, "selected_songs": []
                    }
                    time.sleep(2)
                    st.rerun()

    else:
        st.warning("Repertoire leer.")

# ==========================================
# ANDERE SEITEN (Kurzfassungen)
# ==========================================
elif st.session_state.page == "repertoire":
    st.subheader("Repertoire verwalten")
    # Code für Repertoire (Copy Paste from previous versions if needed or stick to basic form)
    with st.form("simple_rep_add", clear_on_submit=True):
        st.write("Neues Stück anlegen")
        c1, c2 = st.columns([3,1])
        t = c1.text_input("Titel"); d = c2.text_input("Dauer", "03:00")
        k = st.text_input("Komponist NN")
        if st.form_submit_button("Speichern"):
            save_song_direct(t, k, "", "", "", d, "")
            st.success("Gespeichert"); st.rerun()
    st.divider()
    df_rep = load_repertoire()
    st.dataframe(df_rep, use_container_width=True)

elif st.session_state.page == "orte":
    st.subheader("📍 Locations verwalten")
    # Code für Orte
    with st.form("new_location"):
        l_name = st.text_input("Name"); l_str = st.text_input("Straße")
        c1, c2 = st.columns([1, 2])
        l_plz = c1.text_input("PLZ"); l_stadt = c2.text_input("Stadt")
        if st.form_submit_button("Speichern"):
            save_location_direct(l_name, l_str, l_plz, l_stadt)
            st.success("Ort gespeichert!"); st.rerun()
    st.dataframe(load_locations(), use_container_width=True)

elif st.session_state.page == "archiv":
    st.subheader("📂 Setlist Archiv")
    df_events = load_events()
    if not df_events.empty:
        st.dataframe(df_events, use_container_width=True)
