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

if 'page' not in st.session_state:
    st.session_state.page = "speichern" # Startseite geändert

@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
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

# --- DATENBANK FUNKTIONEN ---

def check_and_fix_db():
    # 1. Repertoire
    try:
        ws_rep = sh.worksheet("Repertoire")
    except:
        ws_rep = sh.add_worksheet(title="Repertoire", rows=100, cols=15)
    
    rep_headers = ['ID', 'Titel', 'Komponist_Nachname', 'Komponist_Vorname', 
                   'Bearbeiter_Nachname', 'Bearbeiter_Vorname', 'Dauer', 'Verlag', 'Werkeart', 'ISWC']
    curr_rep = ws_rep.row_values(1)
    if not curr_rep or curr_rep[0] != 'ID':
        ws_rep.update('A1:J1', [rep_headers])

    # 2. Events (JETZT MIT ADRESSE & UHRZEIT)
    try:
        ws_ev = sh.worksheet("Events")
    except:
        ws_ev = sh.add_worksheet(title="Events", rows=100, cols=15)
        
    # Neue Struktur für Events
    event_headers = ['Event_ID', 'Datum', 'Uhrzeit', 'Ensemble', 'Location_Name', 
                     'Strasse', 'PLZ', 'Stadt', 'Setlist_Name', 'Songs_IDs']
    curr_ev = ws_ev.row_values(1)
    # Checken ob "Uhrzeit" schon da ist, sonst updaten
    if not curr_ev or 'Uhrzeit' not in curr_ev:
        ws_ev.clear() # Sicherheitshalber clearen bei Strukturänderung
        ws_ev.update('A1:J1', [event_headers])

    # 3. Locations (NEU!)
    try:
        ws_loc = sh.worksheet("Locations")
    except:
        ws_loc = sh.add_worksheet(title="Locations", rows=50, cols=5)
    
    loc_headers = ['ID', 'Name', 'Strasse', 'PLZ', 'Stadt']
    curr_loc = ws_loc.row_values(1)
    if not curr_loc or curr_loc[0] != 'ID':
        ws_loc.update('A1:E1', [loc_headers])

def load_repertoire():
    ws = sh.worksheet("Repertoire")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    required = ['ID', 'Titel', 'Komponist_Nachname', 'Bearbeiter_Nachname']
    for col in required:
        if col not in df.columns:
            df[col] = ""
    return df

def load_locations():
    ws = sh.worksheet("Locations")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame(columns=['ID', 'Name', 'Strasse', 'PLZ', 'Stadt'])
    return df

def load_events():
    ws = sh.worksheet("Events")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    if not df.empty and 'Datum' in df.columns:
        df['Datum_Obj'] = pd.to_datetime(df['Datum'], format="%d.%m.%Y", errors='coerce')
    return df

def save_song(mode, song_id, titel, kn, kv, bn, bv, dauer, verlag):
    ws = sh.worksheet("Repertoire")
    if mode == "Neu":
        col_ids = ws.col_values(1)[1:] 
        ids = [int(x) for x in col_ids if str(x).isdigit()]
        new_id = max(ids) + 1 if ids else 1
        row = [new_id, titel, kn, kv, bn, bv, dauer, verlag, "U-Musik", ""]
        ws.append_row(row)
        return True, f"'{titel}' angelegt!"
    elif mode == "Edit":
        try:
            cell = ws.find(str(song_id), in_column=1)
            row_num = cell.row
            ws.update(f"B{row_num}:H{row_num}", [[titel, kn, kv, bn, bv, dauer, verlag]])
            return True, f"'{titel}' aktualisiert!"
        except Exception as e:
            return False, f"Fehler: {e}"

def save_location(name, strasse, plz, stadt):
    ws = sh.worksheet("Locations")
    col_ids = ws.col_values(1)[1:]
    ids = [int(x) for x in col_ids if str(x).isdigit()]
    new_id = max(ids) + 1 if ids else 1
    
    ws.append_row([new_id, name, strasse, plz, stadt])

# --- NAVIGATION ---

def navigation_bar():
    st.markdown("---")
    # 4 Buttons für die Bereiche
    c1, c2, c3, c4 = st.columns(4)
    
    if c1.button("💾 Speichern", use_container_width=True):
        st.session_state.page = "speichern"
        st.rerun()
        
    if c2.button("🎵 Repertoire", use_container_width=True):
        st.session_state.page = "repertoire"
        st.rerun()

    if c3.button("📍 Orte", use_container_width=True):
        st.session_state.page = "orte"
        st.rerun()
        
    if c4.button("📂 Archiv", use_container_width=True):
        st.session_state.page = "archiv"
        st.rerun()
    st.markdown("---")

# --- HAUPTPROGRAMM ---

check_and_fix_db()

st.title("Orchester Manager 🎻")

navigation_bar()

# --- SEITE: AUFTRITT SPEICHERN ---
if st.session_state.page == "speichern":
    st.subheader("Vergangenen Auftritt erfassen")
    
    # DATEN LADEN
    df_loc = load_locations()
    df_rep = load_repertoire()

    # FORMULAR FÜR RAHMENDATEN (Verhindert Neuladen beim Tippen!)
    # Wir benutzen jetzt eine Form für die Metadaten
    with st.form("metadata_form"):
        c_date, c_time = st.columns(2)
        inp_date = c_date.date_input("Datum", datetime.date.today())
        inp_time = c_time.time_input("Uhrzeit", datetime.time(19, 0)) # Standard 19 Uhr
        
        c_ens, c_loc = st.columns(2)
        inp_ens = c_ens.selectbox("Ensemble", ["Tutti", "BQ", "Quartett", "Duo"])
        
        # Location Dropdown
        loc_options = ["Bitte wählen..."] + df_loc['Name'].tolist() if not df_loc.empty else ["Bitte wählen..."]
        inp_loc_name = c_loc.selectbox("Spielort", loc_options)
        
        st.caption("Erst Rahmendaten bestätigen, dann Stücke wählen:")
        meta_submitted = st.form_submit_button("1. Daten bestätigen & Stücke wählen")
    
    # Logik: Zeige Song-Auswahl erst, wenn Location gewählt ist (oder User Button drückt)
    if inp_loc_name != "Bitte wählen...":
        
        # Location Details holen
        loc_data = df_loc[df_loc['Name'] == inp_loc_name].iloc[0]
        st.info(f"📍 Gewählt: {loc_data['Name']}, {loc_data['Strasse']}, {loc_data['PLZ']} {loc_data['Stadt']}")
        
        st.markdown("### 2. Programmwahl")
        
        if not df_rep.empty and 'Titel' in df_rep.columns:
            df_rep['Label'] = df_rep.apply(
                lambda x: f"{x['Titel']} ({x['Komponist_Nachname']})" + (f" / Arr: {x['Bearbeiter_Nachname']}" if x['Bearbeiter_Nachname'] else ""), 
                axis=1
            )
            
            # Suche (Außerhalb Formular, damit dynamisch)
            search_filter = st.text_input("🔎 Repertoire filtern:", placeholder="Tippe Titel...")
            
            options = df_rep['Label'].tolist()
            if search_filter:
                options = [opt for opt in options if search_filter.lower() in opt.lower()]
                
            selected_labels = st.multiselect("Gespielte Stücke (in Reihenfolge):", options)
            
            # ABSCHLUSS BUTTON
            if st.button("✅ Auftritt final speichern", type="primary", use_container_width=True):
                if not selected_labels:
                    st.error("Bitte mindestens ein Stück auswählen.")
                else:
                    datum_str = inp_date.strftime("%d.%m.%Y")
                    time_str = inp_time.strftime("%H:%M")
                    dateiname = f"{inp_ens}{datum_str}{loc_data['Stadt']}Setlist.xlsx" # Ort aus DB nutzen!
                    
                    song_ids = []
                    for label in selected_labels:
                        row = df_rep[df_rep['Label'] == label].iloc[0]
                        song_ids.append(str(row['ID']))
                    
                    ws_ev = sh.worksheet("Events")
                    ws_ev.append_row([
                        str(datetime.datetime.now()), 
                        datum_str,
                        time_str,
                        inp_ens,
                        loc_data['Name'], # Location Name
                        loc_data['Strasse'],
                        str(loc_data['PLZ']),
                        loc_data['Stadt'],
                        dateiname, 
                        ",".join(song_ids)
                    ])
                    
                    st.balloons()
                    st.success(f"Gespeichert! Setlist: {dateiname}")
                    time.sleep(2)
                    st.rerun()
        else:
            st.warning("Repertoire leer.")
    else:
        st.info("Bitte wähle oben einen Spielort aus (oder lege unter 'Orte' einen neuen an).")

# --- SEITE: ORTE VERWALTEN ---
elif st.session_state.page == "orte":
    st.subheader("📍 Locations verwalten")
    
    with st.form("new_location"):
        st.write("Neuen Spielort anlegen")
        l_name = st.text_input("Name (z.B. Stadthalle Eschwege)")
        l_str = st.text_input("Straße & Hausnummer")
        c1, c2 = st.columns([1, 2])
        l_plz = c1.text_input("PLZ")
        l_stadt = c2.text_input("Stadt")
        
        if st.form_submit_button("Ort speichern"):
            if l_name and l_stadt:
                save_location(l_name, l_str, l_plz, l_stadt)
                st.success(f"Ort '{l_name}' gespeichert!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Name und Stadt sind Pflicht.")
                
    st.divider()
    st.write("Gespeicherte Orte:")
    st.dataframe(load_locations(), use_container_width=True, hide_index=True)

# --- SEITE: REPERTOIRE (Gleich geblieben) ---
elif st.session_state.page == "repertoire":
    st.subheader("Repertoire verwalten")
    mode = st.radio("Modus:", ["Neu anlegen", "Bearbeiten"], horizontal=True, label_visibility="collapsed")
    f_id = None
    default_vals = {"titel": "", "kn": "", "kv": "", "bn": "", "bv": "", "dauer": "03:00", "verlag": ""}
    
    if mode == "Bearbeiten":
        df_rep = load_repertoire()
        if not df_rep.empty:
            df_rep['Label'] = df_rep.apply(lambda x: f"{x['Titel']} ({x['Komponist_Nachname']})", axis=1)
            search_term = st.text_input("🔍 Suchen:", placeholder="Titel...")
            if search_term:
                filtered_df = df_rep[df_rep['Label'].str.contains(search_term, case=False)]
            else:
                filtered_df = df_rep

            if not filtered_df.empty:
                selected_label = st.selectbox("Auswahl:", filtered_df['Label'].tolist())
                song_data = df_rep[df_rep['Label'] == selected_label].iloc[0]
                f_id = int(song_data['ID'])
                default_vals = {"titel": song_data['Titel'], "kn": song_data['Komponist_Nachname'], 
                                "kv": song_data['Komponist_Vorname'], "bn": song_data['Bearbeiter_Nachname'],
                                "bv": song_data['Bearbeiter_Vorname'], "dauer": str(song_data['Dauer']),
                                "verlag": song_data['Verlag']}
            else:
                st.warning("Nichts gefunden.")
                st.stop()
        else: 
            st.stop()

    with st.form("song_form", clear_on_submit=(mode=="Neu anlegen")):
        c1, c2 = st.columns([3, 1])
        titel = c1.text_input("Titel", value=default_vals["titel"])
        dauer = c2.text_input("Dauer", value=default_vals["dauer"])
        c3, c4 = st.columns(2)
        kn = c3.text_input("Komponist NN", value=default_vals["kn"])
        kv = c4.text_input("Komponist VN", value=default_vals["kv"])
        c5, c6 = st.columns(2)
        bn = c5.text_input("Bearb. NN", value=default_vals["bn"])
        bv = c6.text_input("Bearb. VN", value=default_vals["bv"])
        verlag = st.text_input("Verlag", value=default_vals["verlag"])
        
        if st.form_submit_button("💾 Speichern", use_container_width=True):
            if not titel or not kn:
                st.error("Pflichtfelder fehlen!")
            else:
                action = "Edit" if mode == "Bearbeiten" else "Neu"
                success, msg = save_song(action, f_id, titel, kn, kv, bn, bv, dauer, verlag)
                if success:
                    st.toast(msg, icon="✅"); time.sleep(1); st.rerun()

# --- SEITE: ARCHIV ---
elif st.session_state.page == "archiv":
    st.subheader("📂 Setlist Archiv")
    df_events = load_events()
    if not df_events.empty and 'Datum_Obj' in df_events.columns:
        df_events = df_events.sort_values(by='Datum_Obj', ascending=False)
        for year in df_events['Datum_Obj'].dt.year.unique():
            st.markdown(f"### {year}")
            df_year = df_events[df_events['Datum_Obj'].dt.year == year]
            for month in df_year['Datum_Obj'].dt.month.unique():
                m_name = datetime.date(2000, int(month), 1).strftime('%B')
                with st.expander(f"{m_name} ({len(df_year[df_year['Datum_Obj'].dt.month == month])})"):
                    for _, row in df_year[df_year['Datum_Obj'].dt.month == month].iterrows():
                        st.write(f"**{row['Datum']}** | {row['Location_Name']}")
                        st.caption(f"{row['Ensemble']} | {row['Uhrzeit']} Uhr | {row['Setlist_Name']}")
                        st.divider()
    else:
        st.info("Keine Einträge.")
