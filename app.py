import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import datetime

# --- KONFIGURATION ---
DB_NAME = "GEMA_Datenbank"
FOLDER_NAME_TEMPLATES = "Templates"
TEMPLATE_FILENAME = "Setlist_Template.xlsx" # Wie du die Datei im Drive genannt hast
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
    try:
        ws_rep = sh.worksheet("Repertoire")
    except:
        ws_rep = sh.add_worksheet(title="Repertoire", rows=100, cols=10)
    
    # Prüfen ob Header da sind, sonst schreiben
    if not ws_rep.row_values(1):
        ws_rep.update('A1:H1', [['ID', 'Titel', 'Komponist_Nachname', 'Komponist_Vorname', 'Bearbeiter', 'Dauer', 'Verlag', 'Werkeart']])

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

def add_song(titel, komp_nach, komp_vor, bearbeiter, dauer, verlag):
    ws = sh.worksheet("Repertoire")
    # Neue ID berechnen (Max ID + 1)
    col_ids = ws.col_values(1)[1:] # ohne Header
    if not col_ids:
        new_id = 1
    else:
        new_id = max([int(x) for x in col_ids if str(x).isdigit()]) + 1
        
    row = [new_id, titel, komp_nach, komp_vor, bearbeiter, dauer, verlag, "U-Musik"]
    ws.append_row(row)

# --- APP UI ---

st.title("Orchester Manager 🎻")

# Datenbank initialisieren (passiert lautlos im Hintergrund)
init_db()

# Tabs für Navigation
tab1, tab2, tab3 = st.tabs(["➕ Repertoire", "📅 Neuer Auftritt", "⚙️ Einstellungen"])

# --- TAB 1: REPERTOIRE PFLEGEN ---
with tab1:
    st.header("Neues Stück erfassen")
    with st.form("new_song_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        f_titel = col1.text_input("Titel")
        f_dauer = col2.text_input("Dauer (MM:SS)", value="03:00")
        
        col3, col4 = st.columns(2)
        f_komp_n = col3.text_input("Komponist Nachname")
        f_komp_v = col4.text_input("Komponist Vorname")
        
        f_verlag = st.text_input("Verlag")
        
        submitted = st.form_submit_button("Speichern")
        if submitted and f_titel and f_komp_n:
            add_song(f_titel, f_komp_n, f_komp_v, "", f_dauer, f_verlag)
            st.success(f"'{f_titel}' gespeichert!")
            st.rerun() # Seite neu laden um Tabelle zu aktualisieren

    st.divider()
    st.subheader("Aktuelles Repertoire")
    df_rep = load_repertoire()
    if not df_rep.empty:
        # Suche
        search = st.text_input("Suche im Repertoire", "")
        if search:
            mask = df_rep.apply(lambda x: x.astype(str).str.contains(search, case=False).any(), axis=1)
            df_rep = df_rep[mask]
        
        st.dataframe(df_rep, use_container_width=True)
    else:
        st.info("Noch keine Stücke in der Datenbank.")

# --- TAB 2: GIG ERSTELLEN ---
with tab2:
    st.header("Setliste erstellen")
    
    col_a, col_b = st.columns(2)
    inp_date = col_a.date_input("Datum", datetime.date.today())
    inp_ens = col_b.selectbox("Ensemble", ["Tutti", "BQ", "Quartett", "Duo"])
    
    inp_ort = st.text_input("Ort (für Dateiname)", "Eschwege")
    
    # Song Auswahl
    df_rep = load_repertoire()
    if not df_rep.empty:
        df_rep['Anzeige'] = df_rep['Titel'] + " (" + df_rep['Komponist_Nachname'] + ")"
        selected_songs = st.multiselect("Stücke auswählen (Reihenfolge beachten!)", df_rep['Anzeige'].tolist())
        
        if st.button("Setliste generieren"):
            # 1. Dateinamen bauen
            datum_str = inp_date.strftime("%d.%m.%Y")
            dateiname = f"{inp_ens}{datum_str}{inp_ort}Setlist.xlsx"
            
            st.info(f"Erstelle Datei: {dateiname} ... (Funktion folgt im nächsten Schritt)")
            
            # HIER KOMMT GLEICH DIE EXCEL-LOGIK HIN
            # Wir speichern erstmal nur das Event in die Datenbank
            ws_ev = sh.worksheet("Events")
            # IDs der Songs finden
            song_ids = []
            for s in selected_songs:
                # Einfache Suche nach ID (könnte man eleganter lösen)
                row = df_rep[df_rep['Anzeige'] == s].iloc[0]
                song_ids.append(str(row['ID']))
            
            ws_ev.append_row([
                str(datetime.datetime.now()), 
                datum_str, 
                inp_ens, 
                inp_ort, 
                dateiname, 
                ",".join(song_ids)
            ])
            st.success("Veranstaltung in Datenbank gespeichert!")
            
    else:
        st.warning("Bitte erst Stücke im Repertoire erfassen.")

# --- TAB 3: SETTINGS ---
with tab3:
    st.write("Verbindung zur Datenbank: OK ✅")
    st.write(f"Datenbank-Datei: {DB_NAME}")
