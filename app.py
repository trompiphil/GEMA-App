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

# INITIALISIERUNG DES GEDÄCHTNISSES (SESSION STATE)
# Wir legen Container an, die auch beim Neuladen bestehen bleiben
if 'gig_draft' not in st.session_state:
    st.session_state.gig_draft = {
        "datum": datetime.date.today(),
        "uhrzeit": datetime.time(19, 0),
        "ensemble": "Tutti",
        "location_selection": None, # Was im Dropdown gewählt wurde
        "new_loc_name": "",         # Falls neuer Ort: Name
        "new_loc_str": "",          # Falls neuer Ort: Straße
        "new_loc_plz": "",
        "new_loc_stadt": "",
        "selected_songs": []        # Die Liste der Lieder
    }

if 'page' not in st.session_state:
    st.session_state.page = "speichern"

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

# --- DB FUNKTIONEN ---

def check_and_fix_db():
    # 1. Repertoire
    try: ws_rep = sh.worksheet("Repertoire")
    except: ws_rep = sh.add_worksheet(title="Repertoire", rows=100, cols=15)
    
    rep_headers = ['ID', 'Titel', 'Komponist_Nachname', 'Komponist_Vorname', 
                   'Bearbeiter_Nachname', 'Bearbeiter_Vorname', 'Dauer', 'Verlag', 'Werkeart', 'ISWC']
    curr_rep = ws_rep.row_values(1)
    if not curr_rep or curr_rep[0] != 'ID': ws_rep.update('A1:J1', [rep_headers])

    # 2. Events
    try: ws_ev = sh.worksheet("Events")
    except: ws_ev = sh.add_worksheet(title="Events", rows=100, cols=15)
    event_headers = ['Event_ID', 'Datum', 'Uhrzeit', 'Ensemble', 'Location_Name', 
                     'Strasse', 'PLZ', 'Stadt', 'Setlist_Name', 'Songs_IDs']
    if not ws_ev.row_values(1) or 'Uhrzeit' not in ws_ev.row_values(1):
        ws_ev.clear(); ws_ev.update('A1:J1', [event_headers])

    # 3. Locations
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
    """Speichert Song und gibt True zurück, ohne Rerun zu erzwingen (macht die App)"""
    try:
        ws = sh.worksheet("Repertoire")
        col_ids = ws.col_values(1)[1:] 
        ids = [int(x) for x in col_ids if str(x).isdigit()]
        new_id = max(ids) + 1 if ids else 1
        row = [new_id, titel, kn, kv, bn, bv, dauer, verlag, "U-Musik", ""]
        ws.append_row(row)
        return True
    except Exception as e:
        return False

def save_location_direct(name, strasse, plz, stadt):
    ws = sh.worksheet("Locations")
    col_ids = ws.col_values(1)[1:]
    ids = [int(x) for x in col_ids if str(x).isdigit()]
    new_id = max(ids) + 1 if ids else 1
    ws.append_row([new_id, name, strasse, plz, stadt])
    return True

# --- NAVIGATION ---

def navigation_bar():
    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("💾 Auftritt speichern", use_container_width=True, type="primary" if st.session_state.page == "speichern" else "secondary"):
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
# SEITE 1: AUFTRITT SPEICHERN (OPTIMIERT)
# ==========================================
if st.session_state.page == "speichern":
    st.subheader("Vergangenen Auftritt erfassen")
    
    # Daten laden
    df_loc = load_locations()
    df_rep = load_repertoire()
    
    # --- RAHMENDATEN ---
    # Wir nutzen st.columns und speichern Änderungen SOFORT in session_state
    
    c_date, c_time = st.columns(2)
    st.session_state.gig_draft["datum"] = c_date.date_input("Datum", value=st.session_state.gig_draft["datum"])
    st.session_state.gig_draft["uhrzeit"] = c_time.time_input("Uhrzeit", value=st.session_state.gig_draft["uhrzeit"])
    
    st.session_state.gig_draft["ensemble"] = st.selectbox("Ensemble", ["Tutti", "BQ", "Quartett", "Duo"], 
                                                          index=["Tutti", "BQ", "Quartett", "Duo"].index(st.session_state.gig_draft["ensemble"]))

    # --- LOCATION LOGIK (Hybrid) ---
    st.write("📍 **Spielort**")
    
    # Liste bauen: Vorhandene Orte + Option "NEU"
    loc_options = ["Bitte wählen..."] + df_loc['Name'].tolist() + ["➕ Neuer Ort..."]
    
    # Versuchen, den alten Wert wiederzufinden (Index)
    try:
        sel_idx = loc_options.index(st.session_state.gig_draft["location_selection"])
    except:
        sel_idx = 0
        
    selected_loc = st.selectbox("Ort suchen (tippen zum Filtern) oder neu anlegen:", 
                                options=loc_options, 
                                index=sel_idx)
    
    # Auswahl ins Gedächtnis schreiben
    st.session_state.gig_draft["location_selection"] = selected_loc

    # Falls "Neuer Ort" gewählt wurde -> Eingabefelder zeigen
    final_loc_data = {} # Hier speichern wir am Ende die validen Daten für den Gig
    
    if selected_loc == "➕ Neuer Ort...":
        with st.container(border=True):
            st.info("Bitte Adresse für den neuen Ort eingeben (wird gespeichert):")
            st.session_state.gig_draft["new_loc_name"] = st.text_input("Name der Location*", value=st.session_state.gig_draft["new_loc_name"])
            st.session_state.gig_draft["new_loc_str"] = st.text_input("Straße & Nr", value=st.session_state.gig_draft["new_loc_str"])
            c_plz, c_stadt = st.columns([1, 2])
            st.session_state.gig_draft["new_loc_plz"] = c_plz.text_input("PLZ", value=st.session_state.gig_draft["new_loc_plz"])
            st.session_state.gig_draft["new_loc_stadt"] = c_stadt.text_input("Stadt*", value=st.session_state.gig_draft["new_loc_stadt"])
            
            # Daten für Speicherung vorbereiten
            final_loc_data = {
                "Name": st.session_state.gig_draft["new_loc_name"],
                "Strasse": st.session_state.gig_draft["new_loc_str"],
                "PLZ": st.session_state.gig_draft["new_loc_plz"],
                "Stadt": st.session_state.gig_draft["new_loc_stadt"]
            }
    elif selected_loc != "Bitte wählen...":
        # Bestehenden Ort nutzen
        row = df_loc[df_loc['Name'] == selected_loc].iloc[0]
        final_loc_data = row.to_dict()
        st.caption(f"Adresse: {final_loc_data['Strasse']}, {final_loc_data['PLZ']} {final_loc_data['Stadt']}")

    st.markdown("---")

    # --- SONG AUSWAHL & SCHNELL-ANLAGE ---
    
    st.write("🎵 **Programm**")
    
    # 1. INLINE SCHNELL-ANLAGE (Der Gamechanger)
    with st.expander("➕ Titel fehlt? Hier sofort anlegen (ohne Seitenwechsel)"):
        with st.form("quick_add_song"):
            qc1, qc2 = st.columns([3, 1])
            q_tit = qc1.text_input("Titel")
            q_dur = qc2.text_input("Dauer", value="03:00")
            qc3, qc4 = st.columns(2)
            q_kn = qc3.text_input("Komponist NN")
            q_kv = qc4.text_input("Komponist VN")
            q_ver = st.text_input("Verlag")
            
            if st.form_submit_button("Schnell speichern"):
                if q_tit and q_kn:
                    save_song_direct(q_tit, q_kn, q_kv, "", "", q_dur, q_ver)
                    st.toast(f"'{q_tit}' hinzugefügt! Ist jetzt unten verfügbar.", icon="✅")
                    time.sleep(1)
                    st.rerun() # Seite neu laden -> DB lädt neu -> Song ist da!
                else:
                    st.error("Titel & Komponist Pflicht.")

    # 2. SELEKTION
    if not df_rep.empty and 'Titel' in df_rep.columns:
        # Label bauen
        df_rep['Label'] = df_rep.apply(lambda x: f"{x['Titel']} ({x['Komponist_Nachname']})", axis=1)
        
        # Validierung der bereits gewählten Songs (falls DB sich geändert hat)
        all_options = df_rep['Label'].tolist()
        valid_selected = [s for s in st.session_state.gig_draft["selected_songs"] if s in all_options]
        
        # Das Multiselect Feld (Durchsuchbar!)
        # Wichtig: Wir schreiben das Ergebnis direkt wieder in session_state
        selection = st.multiselect(
            "Suche nach Titel oder Komponist (Tippen zum Filtern):",
            options=all_options,
            default=valid_selected
        )
        st.session_state.gig_draft["selected_songs"] = selection
        
        st.markdown("---")
        
        # --- SPEICHERN BUTTON ---
        if st.button("✅ Auftritt final speichern", type="primary", use_container_width=True):
            # Validierung
            errors = []
            if selected_loc == "Bitte wählen..." or (selected_loc == "➕ Neuer Ort..." and not final_loc_data["Name"]):
                errors.append("Bitte Ort wählen oder eingeben.")
            if not selection:
                errors.append("Bitte mindestens ein Stück wählen.")
            
            if errors:
                for e in errors: st.error(e)
            else:
                # 1. Falls neuer Ort -> Erst speichern
                if selected_loc == "➕ Neuer Ort...":
                    save_location_direct(final_loc_data["Name"], final_loc_data["Strasse"], 
                                         final_loc_data["PLZ"], final_loc_data["Stadt"])
                
                # 2. Event speichern
                datum_str = st.session_state.gig_draft["datum"].strftime("%d.%m.%Y")
                time_str = st.session_state.gig_draft["uhrzeit"].strftime("%H:%M")
                # Dateiname generieren
                dateiname = f"{st.session_state.gig_draft['ensemble']}{datum_str}{final_loc_data['Stadt']}Setlist.xlsx"
                
                # Song IDs holen
                song_ids = []
                for label in selection:
                    row = df_rep[df_rep['Label'] == label].iloc[0]
                    song_ids.append(str(row['ID']))
                
                ws_ev = sh.worksheet("Events")
                ws_ev.append_row([
                    str(datetime.datetime.now()), 
                    datum_str, time_str,
                    st.session_state.gig_draft["ensemble"],
                    final_loc_data["Name"], final_loc_data["Strasse"],
                    str(final_loc_data["PLZ"]), final_loc_data["Stadt"],
                    dateiname, ",".join(song_ids)
                ])
                
                st.balloons()
                st.success(f"Gespeichert! Setlist: {dateiname}")
                
                # Draft zurücksetzen
                st.session_state.gig_draft["selected_songs"] = []
                st.session_state.gig_draft["location_selection"] = "Bitte wählen..."
                st.session_state.gig_draft["new_loc_name"] = ""
                # Datum lassen wir stehen (praktisch für mehrere Einträge)
                
                time.sleep(2)
                st.rerun()

    else:
        st.warning("Repertoire leer.")

# ==========================================
# ANDERE SEITEN (Repertoire, Orte, Archiv)
# ==========================================
elif st.session_state.page == "repertoire":
    st.subheader("Repertoire verwalten")
    # (Code für Repertoire-Seite bleibt gleich wie V3, hier gekürzt der Übersicht halber)
    # Wenn du hier Änderungen brauchst, sag Bescheid, sonst nutze den existierenden Code
    # WICHTIG: Füge hier den Repertoire-Code von V3 ein oder ich poste ihn nochmal komplett
    # Damit der Code hier läuft, füge ich eine Basic Version ein:
    
    with st.form("simple_rep_add", clear_on_submit=True):
        st.write("Neues Stück anlegen (Vollständige Bearbeitung im Popup oben möglich)")
        c1, c2 = st.columns([3,1])
        t = c1.text_input("Titel"); d = c2.text_input("Dauer", "03:00")
        k = st.text_input("Komponist Nachname")
        if st.form_submit_button("Speichern"):
            save_song_direct(t, k, "", "", "", d, "")
            st.success("Gespeichert"); st.rerun()
            
    st.divider()
    df_rep = load_repertoire()
    st.dataframe(df_rep, use_container_width=True)

elif st.session_state.page == "orte":
    st.subheader("📍 Locations verwalten")
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
    else:
        st.info("Leer.")
