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
    """Stellt sicher, dass die Header existieren."""
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
    # Pandas-Bug-Fix: Leere Strings erzwingen, wo Daten fehlen
    required = ['ID', 'Titel', 'Komponist_Nachname', 'Bearbeiter_Nachname']
    for col in required:
        if col not in df.columns:
            df[col] = ""
    return df

def save_song(mode, song_id, titel, kn, kv, bn, bv, dauer, verlag):
    ws = sh.worksheet("Repertoire")
    
    if mode == "Neu":
        # Neue ID generieren
        col_ids = ws.col_values(1)[1:] 
        ids = [int(x) for x in col_ids if str(x).isdigit()]
        new_id = max(ids) + 1 if ids else 1
        
        row = [new_id, titel, kn, kv, bn, bv, dauer, verlag, "U-Musik", ""]
        ws.append_row(row)
        return True, f"'{titel}' neu angelegt!"
        
    elif mode == "Edit":
        # Zeile finden anhand der ID
        try:
            cell = ws.find(str(song_id), in_column=1)
            row_num = cell.row
            # Update der Zellen (Spalte 2 bis 8)
            # Achtung: gspread update range ist etwas tricky, wir machen es einzeln oder per range
            # Range: B(row):H(row) -> Titel bis Verlag
            ws.update(f"B{row_num}:H{row_num}", [[titel, kn, kv, bn, bv, dauer, verlag]])
            return True, f"'{titel}' aktualisiert!"
        except Exception as e:
            return False, f"Fehler beim Update: {e}"

# --- APP UI ---

st.title("Orchester Manager 🎻")

# DB Check im Hintergrund
check_and_fix_db()

# Tabs
tab1, tab2, tab3 = st.tabs(["🎵 Repertoire", "📅 Neuer Auftritt", "⚙️ Einstellungen"])

# --- TAB 1: REPERTOIRE (NEU & EDIT) ---
with tab1:
    mode = st.radio("Modus:", ["Neu anlegen", "Bearbeiten"], horizontal=True)
    
    # Variablen für das Formular vor-initialisieren
    f_id = None
    default_titel = ""
    default_kn = ""
    default_kv = ""
    default_bn = ""
    default_bv = ""
    default_dauer = "03:00"
    default_verlag = ""
    
    # Wenn "Bearbeiten", dann Auswahlbox zeigen und Daten laden
    if mode == "Bearbeiten":
        df_rep = load_repertoire()
        if not df_rep.empty:
            df_rep['Label'] = df_rep.apply(lambda x: f"{x['Titel']} ({x['Komponist_Nachname']})", axis=1)
            # Auswahlbox
            selected_label = st.selectbox("Welches Stück bearbeiten?", df_rep['Label'].tolist())
            
            # Daten des gewählten Songs holen
            song_data = df_rep[df_rep['Label'] == selected_label].iloc[0]
            
            f_id = int(song_data['ID'])
            default_titel = song_data['Titel']
            default_kn = song_data['Komponist_Nachname']
            default_kv = song_data['Komponist_Vorname']
            default_bn = song_data['Bearbeiter_Nachname']
            default_bv = song_data['Bearbeiter_Vorname']
            default_dauer = str(song_data['Dauer'])
            default_verlag = song_data['Verlag']
        else:
            st.warning("Noch nichts zum Bearbeiten da.")
            st.stop()

    # Das Formular (wird für Neu UND Bearbeiten genutzt)
    with st.form("song_form", clear_on_submit=(mode=="Neu anlegen")):
        st.write(f"**{mode}**")
        
        c1, c2 = st.columns([3, 1])
        titel = c1.text_input("Titel", value=default_titel)
        dauer = c2.text_input("Dauer", value=default_dauer)
        
        c3, c4 = st.columns(2)
        kn = c3.text_input("Komponist Nachname", value=default_kn)
        kv = c4.text_input("Komponist Vorname", value=default_kv)
        
        c5, c6 = st.columns(2)
        bn = c5.text_input("Bearbeiter Nachname", value=default_bn)
        bv = c6.text_input("Bearbeiter Vorname", value=default_bv)
        
        verlag = st.text_input("Verlag", value=default_verlag)
        
        # Submit Button
        submitted = st.form_submit_button("💾 Speichern")
        
        if submitted:
            if not titel or not kn:
                st.error("Titel und Komponist fehlen!")
            else:
                # Speichern Logik aufrufen
                action_mode = "Edit" if mode == "Bearbeiten" else "Neu"
                success, msg = save_song(action_mode, f_id, titel, kn, kv, bn, bv, dauer, verlag)
                
                if success:
                    st.toast(msg, icon="✅")
                    time.sleep(1) # Kurz warten damit man Toast sieht
                    st.rerun()
                else:
                    st.error(msg)

    # Tabelle unten zur Kontrolle
    st.divider()
    with st.expander("Ganze Liste ansehen"):
        df_show = load_repertoire()
        if not df_show.empty:
            st.dataframe(df_show, hide_index=True, use_container_width=True)

# --- TAB 2: GIG PLANEN ---
with tab2:
    st.header("Setliste planen")
    
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
        
        selected_labels = st.multiselect("Programm (in richtiger Reihenfolge)", df_rep['Label'].tolist())
        
        if st.button("🚀 Setliste generieren"):
            datum_str = inp_date.strftime("%d.%m.%Y")
            dateiname = f"{inp_ens}{datum_str}{inp_ort}Setlist.xlsx"
            
            # IDs sammeln
            song_ids = []
            for label in selected_labels:
                row = df_rep[df_rep['Label'] == label].iloc[0]
                song_ids.append(str(row['ID']))
            
            # Speichern in DB
            ws_ev = sh.worksheet("Events")
            ws_ev.append_row([
                str(datetime.datetime.now()), 
                datum_str, 
                inp_ens, 
                inp_ort, 
                dateiname, 
                ",".join(song_ids)
            ])
            
            st.toast(f"Auftritt gespeichert!", icon="🎉")
            st.success(f"Daten für **{dateiname}** wurden erfasst.")
            st.info("⚠️ Excel-Generierung wird im nächsten Schritt aktiviert!")
            
    else:
        st.warning("Repertoire ist leer.")

# --- TAB 3: SETTINGS ---
with tab3:
    st.write(f"Verbunden mit: {DB_NAME}")
