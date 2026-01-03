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

# Session State initialisieren (Das Gedächtnis der App)
if 'page' not in st.session_state:
    st.session_state.page = "planer" # Startseite

# Cache für den Planer initialisieren (falls noch nicht da)
if 'planer_cache' not in st.session_state:
    st.session_state.planer_cache = {
        "datum": datetime.date.today(),
        "ensemble": "Tutti",
        "ort": "Eschwege",
        "selected_songs": [], # Hier merken wir uns die Lieder
        "search_term": ""
    }

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
    
    # Wir speichern NICHT hier, sondern direkt bei Eingabe im Widget (on_change ist nicht nötig, wir lesen session_state)
    
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

check_and_fix_db()

st.title("Orchester Manager 🎻")

navigation_bar()

# SEITE: REPERTOIRE
if st.session_state.page == "repertoire":
    st.subheader("Repertoire verwalten")
    
    mode = st.radio("Modus:", ["Neu anlegen", "Bearbeiten"], horizontal=True, label_visibility="collapsed")
    
    f_id = None
    default_vals = {"titel": "", "kn": "", "kv": "", "bn": "", "bv": "", "dauer": "03:00", "verlag": ""}
    
    if mode == "Bearbeiten":
        df_rep = load_repertoire()
        if not df_rep.empty:
            df_rep['Label'] = df_rep.apply(lambda x: f"{x['Titel']} ({x['Komponist_Nachname']})", axis=1)
            
            search_term = st.text_input("🔍 Titel suchen:", placeholder="Tippe zum Filtern...")
            
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
    
    # 1. DATEN LADEN / CACHE UPDATEN
    # Wir benutzen den Cache als 'value', schreiben aber Änderungen sofort zurück
    
    col_a, col_b = st.columns(2)
    
    # Datum
    new_date = col_a.date_input("Datum", value=st.session_state.planer_cache["datum"])
    st.session_state.planer_cache["datum"] = new_date
    
    # Ensemble
    ens_options = ["Tutti", "BQ", "Quartett", "Duo"]
    # Sicherstellen, dass der gecachte Wert noch gültig ist (falls man Optionen ändert)
    default_ens = st.session_state.planer_cache["ensemble"]
    if default_ens not in ens_options: default_ens = "Tutti"
    
    new_ens = col_b.selectbox("Ensemble", ens_options, index=ens_options.index(default_ens))
    st.session_state.planer_cache["ensemble"] = new_ens
    
    # Ort
    new_ort = st.text_input("Ort", value=st.session_state.planer_cache["ort"])
    st.session_state.planer_cache["ort"] = new_ort
    
    # 2. SONG AUSWAHL
    df_rep = load_repertoire()
    
    if not df_rep.empty and 'Titel' in df_rep.columns:
        df_rep['Label'] = df_rep.apply(
            lambda x: f"{x['Titel']} ({x['Komponist_Nachname']})" + (f" / Arr: {x['Bearbeiter_Nachname']}" if x['Bearbeiter_Nachname'] else ""), 
            axis=1
        )
        
        st.write("Programm zusammenstellen:")
        
        # Suche im Cache speichern
        search_filter = st.text_input("🔎 Repertoire durchsuchen:", 
                                      value=st.session_state.planer_cache["search_term"],
                                      placeholder="Suchbegriff eingeben...")
        st.session_state.planer_cache["search_term"] = search_filter
        
        all_options = df_rep['Label'].tolist()
        
        # Validierung: Prüfen, ob die im Cache gespeicherten Songs noch in der DB existieren
        # (Falls du im Repertoire was umbenannt hast)
        valid_cached_songs = [s for s in st.session_state.planer_cache["selected_songs"] if s in all_options]
        
        # Filterlogik für die Anzeige
        if search_filter:
            filtered_options = [opt for opt in all_options if search_filter.lower() in opt.lower()]
        else:
            filtered_options = all_options
            
        # Multiselect
        # Wichtig: "default" sind die bereits gewählten (validen) Songs
        # Wir müssen sicherstellen, dass die 'default' Werte auch in den 'options' enthalten sind
        # Trick: Wir kombinieren gefilterte Optionen mit den bereits gewählten, damit nichts abstürzt
        display_options = list(set(filtered_options + valid_cached_songs))
        
        # Sortieren für bessere Optik
        display_options.sort()
        
        new_selection = st.multiselect(
            "Auswahl (Reihenfolge!):", 
            options=display_options,
            default=valid_cached_songs
        )
        
        # SOFORT im Cache speichern
        st.session_state.planer_cache["selected_songs"] = new_selection
        
        st.markdown("---")
        
        if st.button("🚀 Setliste speichern", use_container_width=True):
            datum_str = new_date.strftime("%d.%m.%Y")
            dateiname = f"{new_ens}{datum_str}{new_ort}Setlist.xlsx"
            
            song_ids = []
            for label in new_selection:
                row = df_rep[df_rep['Label'] == label].iloc[0]
                song_ids.append(str(row['ID']))
            
            ws_ev = sh.worksheet("Events")
            ws_ev.append_row([
                str(datetime.datetime.now()), 
                datum_str, 
                new_ens, 
                new_ort, 
                dateiname, 
                ",".join(song_ids)
            ])
            
            # Cache leeren nach erfolgreichem Speichern?
            # Macht Sinn, damit man den nächsten Gig planen kann
            st.session_state.planer_cache["selected_songs"] = []
            # Ort lassen wir stehen, ist oft gleich
            
            st.toast(f"Gespeichert!", icon="🎉")
            st.success(f"Auftritt **{new_ort}** angelegt.")
            st.info("ℹ️ Excel-Generierung folgt im nächsten Schritt.")
            time.sleep(2)
            st.rerun() # Reload um Formular zu leeren
    else:
        st.info("Repertoire leer.")

# SEITE: ARCHIV
elif st.session_state.page == "archiv":
    st.subheader("📂 Setlist Archiv")
    
    df_events = load_events()
    
    if not df_events.empty and 'Datum_Obj' in df_events.columns:
        df_events = df_events.sort_values(by='Datum_Obj', ascending=False)
        years = df_events['Datum_Obj'].dt.year.unique()
        
        for year in years:
            st.markdown(f"### {year}")
            df_year = df_events[df_events['Datum_Obj'].dt.year == year]
            months = df_year['Datum_Obj'].dt.month.unique()
            for month in months:
                month_name = datetime.date(2000, int(month), 1).strftime('%B')
                with st.expander(f"{month_name} ({len(df_year[df_year['Datum_Obj'].dt.month == month])} Auftritte)"):
                    events_month = df_year[df_year['Datum_Obj'].dt.month == month]
                    for idx, row in events_month.iterrows():
                        c_info, c_link = st.columns([3, 1])
                        with c_info:
                            st.write(f"**{row['Datum']} - {row['Ort']}**")
                            st.caption(f"{row['Ensemble']} | {row['Setlist_Name']}")
                        with c_link:
                            search_url = f"https://drive.google.com/drive/search?q={row['Setlist_Name']}"
                            st.link_button("Öffnen", search_url)
                        st.divider()
    else:
        st.info("Noch keine Auftritte gespeichert.")
