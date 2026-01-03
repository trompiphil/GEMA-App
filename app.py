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

# Session State für Navigation initialisieren
if 'page' not in st.session_state:
    st.session_state.page = "repertoire"

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
    
    required_headers = ['ID', 'Titel', 'Komponist_Nachname', 'Komponist_Vorname', 
                        'Bearbeiter_Nachname', 'Bearbeiter_Vorname', 'Dauer', 'Verlag', 'Werkeart', 'ISWC']
    
    current_headers = ws_rep.row_values(1)
    if not current_headers or current_headers[0] != 'ID':
        ws_rep.update('A1:J1', [required_headers])

    # 2. Events
    try:
        ws_ev = sh.worksheet("Events")
    except:
        ws_ev = sh.add_worksheet(title="Events", rows=100, cols=10)
        
    event_headers = ['Event_ID', 'Datum', 'Ensemble', 'Ort', 'Setlist_Name', 'Songs_IDs']
    if not ws_ev.row_values(1):
        ws_ev.update('A1:F1', [event_headers])

def load_repertoire():
    ws = sh.worksheet("Repertoire")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    required = ['ID', 'Titel', 'Komponist_Nachname', 'Bearbeiter_Nachname']
    for col in required:
        if col not in df.columns:
            df[col] = ""
    return df

def load_events():
    ws = sh.worksheet("Events")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    # Datumsformat sicherstellen
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
        return True, f"'{titel}' neu angelegt!"
    elif mode == "Edit":
        try:
            cell = ws.find(str(song_id), in_column=1)
            row_num = cell.row
            ws.update(f"B{row_num}:H{row_num}", [[titel, kn, kv, bn, bv, dauer, verlag]])
            return True, f"'{titel}' aktualisiert!"
        except Exception as e:
            return False, f"Fehler: {e}"

# --- NAVIGATION ---

def navigation_bar():
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    
    if c1.button("🎵 Repertoire", use_container_width=True):
        st.session_state.page = "repertoire"
        st.rerun()
        
    if c2.button("📅 Planer", use_container_width=True):
        st.session_state.page = "planer"
        st.rerun()
        
    if c3.button("📂 Archiv", use_container_width=True):
        st.session_state.page = "archiv"
        st.rerun()
    st.markdown("---")

# --- HAUPTPROGRAMM ---

# DB Check im Hintergrund
check_and_fix_db()

st.title("Orchester Manager 🎻")

# Menü anzeigen
navigation_bar()

# SEITE: REPERTOIRE
if st.session_state.page == "repertoire":
    st.subheader("Repertoire verwalten")
    
    mode = st.radio("Modus:", ["Neu anlegen", "Bearbeiten"], horizontal=True, label_visibility="collapsed")
    
    f_id = None
    default_vals = {"titel": "", "kn": "", "kv": "", "bn": "", "bv": "", "dauer": "03:00", "verlag": ""}
    
    # --- LOGIK FÜR BEARBEITEN MIT SUCHE ---
    if mode == "Bearbeiten":
        df_rep = load_repertoire()
        if not df_rep.empty:
            df_rep['Label'] = df_rep.apply(lambda x: f"{x['Titel']} ({x['Komponist_Nachname']})", axis=1)
            
            # 1. Suchfilter
            search_term = st.text_input("🔍 Titel suchen:", placeholder="Tippe zum Filtern...")
            
            # 2. Liste filtern
            if search_term:
                filtered_df = df_rep[df_rep['Label'].str.contains(search_term, case=False)]
            else:
                filtered_df = df_rep

            if not filtered_df.empty:
                selected_label = st.selectbox("Stück auswählen:", filtered_df['Label'].tolist())
                song_data = df_rep[df_rep['Label'] == selected_label].iloc[0]
                
                f_id = int(song_data['ID'])
                default_vals["titel"] = song_data['Titel']
                default_vals["kn"] = song_data['Komponist_Nachname']
                default_vals["kv"] = song_data['Komponist_Vorname']
                default_vals["bn"] = song_data['Bearbeiter_Nachname']
                default_vals["bv"] = song_data['Bearbeiter_Vorname']
                default_vals["dauer"] = str(song_data['Dauer'])
                default_vals["verlag"] = song_data['Verlag']
            else:
                st.warning("Kein Titel gefunden.")
                st.stop()
        else:
            st.warning("Datenbank leer.")
            st.stop()

    # --- FORMULAR ---
    with st.form("song_form", clear_on_submit=(mode=="Neu anlegen")):
        st.caption(f"Modus: {mode}")
        c1, c2 = st.columns([3, 1])
        titel = c1.text_input("Titel", value=default_vals["titel"])
        dauer = c2.text_input("Dauer", value=default_vals["dauer"])
        
        c3, c4 = st.columns(2)
        kn = c3.text_input("Komponist Nachname", value=default_vals["kn"])
        kv = c4.text_input("Komponist Vorname", value=default_vals["kv"])
        
        c5, c6 = st.columns(2)
        bn = c5.text_input("Bearbeiter Nachname", value=default_vals["bn"])
        bv = c6.text_input("Bearbeiter Vorname", value=default_vals["bv"])
        
        verlag = st.text_input("Verlag", value=default_vals["verlag"])
        
        submitted = st.form_submit_button("💾 Speichern", use_container_width=True)
        
        if submitted:
            if not titel or not kn:
                st.error("Pflichtfelder fehlen!")
            else:
                action_mode = "Edit" if mode == "Bearbeiten" else "Neu"
                success, msg = save_song(action_mode, f_id, titel, kn, kv, bn, bv, dauer, verlag)
                if success:
                    st.toast(msg, icon="✅")
                    time.sleep(1)
                    st.rerun()

# SEITE: PLANER
elif st.session_state.page == "planer":
    st.subheader("Auftritt planen")
    
    col_a, col_b = st.columns(2)
    inp_date = col_a.date_input("Datum", datetime.date.today())
    inp_ens = col_b.selectbox("Ensemble", ["Tutti", "BQ", "Quartett", "Duo"])
    inp_ort = st.text_input("Ort", "Eschwege")
    
    df_rep = load_repertoire()
    
    if not df_rep.empty and 'Titel' in df_rep.columns:
        df_rep['Label'] = df_rep.apply(
            lambda x: f"{x['Titel']} ({x['Komponist_Nachname']})" + (f" / Arr: {x['Bearbeiter_Nachname']}" if x['Bearbeiter_Nachname'] else ""), 
            axis=1
        )
        
        # Filter für die Setlist-Auswahl
        st.write("Programm zusammenstellen:")
        search_filter = st.text_input("🔎 Repertoire durchsuchen:", placeholder="Suchbegriff eingeben...", key="search_planner")
        
        options = df_rep['Label'].tolist()
        if search_filter:
            # Filtern der Optionen basierend auf Suche
            options = [opt for opt in options if search_filter.lower() in opt.lower()]
            
        selected_labels = st.multiselect("Auswahl (Reihenfolge!):", options)
        
        if st.button("🚀 Setliste speichern", use_container_width=True):
            datum_str = inp_date.strftime("%d.%m.%Y")
            dateiname = f"{inp_ens}{datum_str}{inp_ort}Setlist.xlsx"
            
            song_ids = []
            # Achtung: Wir müssen die IDs aus dem originalen DF holen
            for label in selected_labels:
                row = df_rep[df_rep['Label'] == label].iloc[0]
                song_ids.append(str(row['ID']))
            
            ws_ev = sh.worksheet("Events")
            ws_ev.append_row([
                str(datetime.datetime.now()), 
                datum_str, 
                inp_ens, 
                inp_ort, 
                dateiname, 
                ",".join(song_ids)
            ])
            
            st.toast(f"Gespeichert!", icon="🎉")
            st.success(f"Auftritt **{inp_ort}** angelegt.")
            st.info("ℹ️ Excel-Generierung folgt im nächsten Schritt.")
    else:
        st.info("Repertoire leer.")

# SEITE: ARCHIV
elif st.session_state.page == "archiv":
    st.subheader("📂 Setlist Archiv")
    
    df_events = load_events()
    
    if not df_events.empty and 'Datum_Obj' in df_events.columns:
        # Sortieren: Neueste zuerst
        df_events = df_events.sort_values(by='Datum_Obj', ascending=False)
        
        # Gruppieren nach Jahr
        years = df_events['Datum_Obj'].dt.year.unique()
        
        for year in years:
            st.markdown(f"### {year}")
            df_year = df_events[df_events['Datum_Obj'].dt.year == year]
            
            # Gruppieren nach Monat
            months = df_year['Datum_Obj'].dt.month.unique()
            for month in months:
                month_name = datetime.date(2000, int(month), 1).strftime('%B') # Monat als Name
                with st.expander(f"{month_name} ({len(df_year[df_year['Datum_Obj'].dt.month == month])} Auftritte)"):
                    
                    # Einzelne Events anzeigen
                    events_month = df_year[df_year['Datum_Obj'].dt.month == month]
                    for idx, row in events_month.iterrows():
                        col_info, col_link = st.columns([3, 1])
                        
                        with col_info:
                            st.write(f"**{row['Datum']} - {row['Ort']}**")
                            st.caption(f"Ensemble: {row['Ensemble']} | Datei: {row['Setlist_Name']}")
                        
                        with col_link:
                            # Link zur Drive Suche (da wir keine direkte URL in der DB haben bisher)
                            search_url = f"https://drive.google.com/drive/search?q={row['Setlist_Name']}"
                            st.link_button("Öffnen", search_url)
                        
                        st.divider()
    else:
        st.info("Noch keine Auftritte gespeichert.")
