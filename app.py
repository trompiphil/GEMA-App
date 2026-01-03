import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import datetime

# --- KONFIGURATION ---
DB_NAME = "GEMA_Datenbank"
FOLDER_NAME_TEMPLATES = "Templates"
TEMPLATE_FILENAME = "Setlist_Template.xlsx" 
OUTPUT_FOLDER_NAME = "Output"

# --- SETUP & VERBINDUNG ---
st.set_page_config(page_title="GEMA Manager", page_icon="xj", layout="centered")

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

# --- HILFSFUNKTIONEN ---

def init_db():
    """Erstellt die Tabellenblätter und Spalten, falls die DB leer ist."""
    # 1. Repertoire
    try:
        ws_rep = sh.worksheet("Repertoire")
    except:
        ws_rep = sh.add_worksheet(title="Repertoire", rows=100, cols=15)
    
    # Header schreiben (nur wenn Zeile 1 leer ist)
    if not ws_rep.row_values(1):
        headers = [
            'ID', 'Titel', 
            'Komponist_Nachname', 'Komponist_Vorname', 
            'Bearbeiter_Nachname', 'Bearbeiter_Vorname', 
            'Dauer', 'Verlag', 'Werkeart', 'ISWC'
        ]
        ws_rep.update('A1:J1', [headers])

    # 2. Events
    try:
        ws_ev = sh.worksheet("Events")
    except:
        ws_ev = sh.add_worksheet(title="Events", rows=100, cols=10)
        
    if not ws_ev.row_values(1):
        ws_ev.update('A1:F1', [['Event_ID', 'Datum', 'Ensemble', 'Ort', 'Setlist_Name', 'Songs_IDs']])

def load_repertoire():
    ws = sh.worksheet("Repertoire")
    data = ws.get_all_records()
    return pd.DataFrame(data)

def add_song(titel, k_nach, k_vor, b_nach, b_vor, dauer, verlag):
    ws = sh.worksheet("Repertoire")
    # Neue ID berechnen
    col_ids = ws.col_values(1)[1:] 
    if not col_ids:
        new_id = 1
    else:
        # Sicherstellen, dass wir nur Zahlen nehmen
        ids = [int(x) for x in col_ids if str(x).isdigit()]
        new_id = max(ids) + 1 if ids else 1
        
    row = [
        new_id, titel, 
        k_nach, k_vor, 
        b_nach, b_vor, 
        dauer, verlag, 
        "U-Musik", "" # ISWC erst mal leer
    ]
    ws.append_row(row)

# --- APP UI ---

st.title("Orchester Manager 🎻")

# DB Check
init_db()

tab1, tab2, tab3 = st.tabs(["➕ Repertoire", "📅 Neuer Auftritt", "⚙️ Einstellungen"])

# --- TAB 1: REPERTOIRE ---
with tab1:
    st.header("Neues Stück erfassen")
    
    with st.form("new_song_form", clear_on_submit=True):
        st.caption("Pflichtfelder sind fett markiert")
        
        # Zeile 1: Titel & Dauer
        c1, c2 = st.columns([3, 1])
        f_titel = c1.text_input("**Titel**")
        f_dauer = c2.text_input("**Dauer (MM:SS)**", value="03:00")
        
        st.markdown("---")
        
        # Zeile 2: Komponist
        c3, c4 = st.columns(2)
        f_komp_n = c3.text_input("**Komponist Nachname**")
        f_komp_v = c4.text_input("Komponist Vorname")
        
        # Zeile 3: Bearbeiter
        c5, c6 = st.columns(2)
        f_bearb_n = c5.text_input("Bearbeiter Nachname (optional)")
        f_bearb_v = c6.text_input("Bearbeiter Vorname (optional)")
        
        st.markdown("---")
        
        f_verlag = st.text_input("Verlag")
        
        submitted = st.form_submit_button("Speichern")
        
        if submitted:
            if not f_titel or not f_komp_n:
                st.error("Bitte mindestens Titel und Komponist Nachname angeben.")
            else:
                add_song(f_titel, f_komp_n, f_komp_v, f_bearb_n, f_bearb_v, f_dauer, f_verlag)
                st.success(f"'{f_titel}' wurde gespeichert!")
                st.rerun()

    st.divider()
    
    # Anzeige Repertoire
    df_rep = load_repertoire()
    if not df_rep.empty:
        search = st.text_input("Suche im Repertoire", "", placeholder="Titel oder Komponist...")
        if search:
            mask = df_rep.apply(lambda x: x.astype(str).str.contains(search, case=False).any(), axis=1)
            df_rep = df_rep[mask]
        
        # Schöne Tabelle anzeigen
        st.dataframe(
            df_rep, 
            column_config={
                "ID": None, # ID verstecken
                "Komponist_Nachname": "Komponist",
                "Bearbeiter_Nachname": "Bearbeiter"
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("Datenbank ist noch leer.")

# --- TAB 2: GIG ---
with tab2:
    st.header("Setliste planen")
    
    col_a, col_b = st.columns(2)
    inp_date = col_a.date_input("Datum", datetime.date.today())
    inp_ens = col_b.selectbox("Ensemble", ["Tutti", "BQ", "Quartett", "Duo"])
    inp_ort = st.text_input("Ort", "Eschwege")
    
    df_rep = load_repertoire()
    
    if not df_rep.empty:
        # Anzeige für Dropdown zusammenbauen
        df_rep['Label'] = df_rep.apply(
            lambda x: f"{x['Titel']} ({x['Komponist_Nachname']})" + (f" / Arr: {x['Bearbeiter_Nachname']}" if x['Bearbeiter_Nachname'] else ""), 
            axis=1
        )
        
        selected_labels = st.multiselect("Programm wählen", df_rep['Label'].tolist())
        
        if st.button("Setliste generieren"):
            datum_str = inp_date.strftime("%d.%m.%Y")
            dateiname = f"{inp_ens}{datum_str}{inp_ort}Setlist.xlsx"
            
            # IDs holen
            song_ids = []
            for label in selected_labels:
                row = df_rep[df_rep['Label'] == label].iloc[0]
                song_ids.append(str(row['ID']))
            
            # Event speichern
            ws_ev = sh.worksheet("Events")
            ws_ev.append_row([
                str(datetime.datetime.now()), 
                datum_str, 
                inp_ens, 
                inp_ort, 
                dateiname, 
                ",".join(song_ids)
            ])
            
            st.success(f"Auftritt gespeichert! (Datei-Generierung folgt)")
            st.json({"Datei": dateiname, "Songs": selected_labels})

# --- TAB 3: SETTINGS ---
with tab3:
    st.write(f"Datenbank: {DB_NAME}")
    st.write("Hier kommen später Dropdown-Einstellungen hin.")
