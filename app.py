import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import datetime
import time
import os
import openpyxl

# --- KONFIGURATION ---
DB_NAME = "GEMA_Datenbank"
# ACHTUNG: Bitte sicherstellen, dass im Drive Ordner "Templates" die Datei "Setlist_Template.xlsx" liegt!

st.set_page_config(page_title="GEMA Manager", page_icon="xj", layout="centered")

# --- SESSION STATE ---
if 'gig_draft' not in st.session_state:
    st.session_state.gig_draft = {
        "event_id": None, "datum": datetime.date.today(), "uhrzeit": datetime.time(19, 0),
        "ensemble": "Tutti", "location_selection": "Bitte wählen...", 
        "new_loc_data": {}
    }

if 'gig_song_selector' not in st.session_state: st.session_state.gig_song_selector = []
if 'rep_edit_state' not in st.session_state: st.session_state.rep_edit_state = {"id": None, "titel": "", "dauer": "", "kn": "", "kv": "", "bn": "", "bv": "", "verlag": ""}
if 'page' not in st.session_state: st.session_state.page = "speichern"
if 'db_checked' not in st.session_state: st.session_state.db_checked = False

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
    st.error(f"Verbindungsfehler zur Datenbank: {e}"); st.stop()

# --- DRIVE HELPER (MIT DIAGNOSE) ---

def get_folder_id(folder_name):
    """Sucht Ordner und gibt ID zurück. Zeigt Fehler im UI, wenn nicht gefunden."""
    try:
        query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        items = results.get('files', [])
        if items: 
            return items[0]['id']
        else:
            # Fallback: Vielleicht ist er im Papierkorb oder nicht geteilt?
            return None
    except Exception as e:
        st.error(f"Fehler bei Ordner-Suche '{folder_name}': {e}")
        return None

def download_template(filename):
    """Lädt das Template herunter"""
    folder_id = get_folder_id("Templates")
    if not folder_id: 
        return None, "Ordner 'Templates' nicht gefunden. Bitte erstellen und mit Bot teilen!"
    
    query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
    results = drive_service.files().list(q=query, fields="files(id)").execute()
    items = results.get('files', [])
    if not items: 
        return None, f"Datei '{filename}' nicht im Ordner 'Templates' gefunden."
    
    try:
        file_id = items[0]['id']
        content = drive_service.files().get_media(fileId=file_id).execute()
        with open(filename, "wb") as f:
            f.write(content)
        return filename, None
    except Exception as e:
        return None, f"Fehler beim Download: {e}"

def generate_and_upload_excel(datum, uhrzeit, ensemble, ort_data, songs_list, filename):
    # 1. Template holen
    template_name = "Setlist_Template.xlsx" 
    temp_file, err = download_template(template_name)
    if err: return None, err

    # 2. Excel bearbeiten
    try:
        wb = openpyxl.load_workbook(temp_file)
        ws = wb.active 
        
        # Header schreiben (Anpassung auf Zeile 1-13)
        # Beispielhaft: Ensemble oben
        ws['B1'] = ensemble 
        ws['B2'] = datum 
        ws['B3'] = ort_data.get('Stadt', '')
        
        start_row = 14
        current_row = start_row
        
        # Zeilen leeren
        for row in ws.iter_rows(min_row=start_row, max_row=100):
            for cell in row: cell.value = None

        for song in songs_list:
            ws.cell(row=current_row, column=2, value=song['Titel']) # B
            ws.cell(row=current_row, column=5, value=song['Dauer']) # E
            
            k_name = f"{song['Komponist_Nachname']}, {song['Komponist_Vorname']}"
            ws.cell(row=current_row, column=6, value=k_name) # F
            
            if song['Bearbeiter_Nachname']:
                b_name = f"{song['Bearbeiter_Nachname']}, {song['Bearbeiter_Vorname']}"
                ws.cell(row=current_row, column=16, value=b_name) # P
            
            ws.cell(row=current_row, column=10, value=song['Verlag']) # J
            ws.cell(row=current_row, column=11, value="Live") # K
            
            current_row += 1
            
        wb.save(filename)
        
    except Exception as e:
        return None, f"Fehler beim Excel-Schreiben (OpenPyXL): {e}"

    # 3. Upload
    try:
        output_folder_id = get_folder_id("Output")
        if not output_folder_id:
            # Versuch Ordner zu erstellen
            # Wir brauchen die ID vom Parent Folder "GEMA Bpol", sonst landet es im Nirgendwo
            parent_id = get_folder_id("GEMA Bpol")
            if parent_id:
                file_metadata = {'name': 'Output', 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent_id]}
                folder = drive_service.files().create(body=file_metadata, fields='id').execute()
                output_folder_id = folder.get('id')
            else:
                return None, "Konnte 'Output' Ordner nicht finden und auch nicht erstellen (Hauptordner fehlt)."

        file_metadata = {'name': filename, 'parents': [output_folder_id]}
        media = MediaFileUpload(filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        
        # Aufräumen
        if os.path.exists(template_name): os.remove(template_name)
        if os.path.exists(filename): os.remove(filename)
        
        return file.get('webViewLink'), None
    except Exception as e:
        return None, f"Fehler beim Upload zu Drive: {e}"


# --- DB FUNKTIONEN ---

def check_and_fix_db():
    if st.session_state.db_checked: return
    try: ws_rep = sh.worksheet("Repertoire")
    except: ws_rep = sh.add_worksheet(title="Repertoire", rows=100, cols=15)
    rep_headers = ['ID', 'Titel', 'Komponist_Nachname', 'Komponist_Vorname', 'Bearbeiter_Nachname', 'Bearbeiter_Vorname', 'Dauer', 'Verlag', 'Werkeart', 'ISWC']
    if not ws_rep.row_values(1): ws_rep.update('A1:J1', [rep_headers])
    
    try: ws_ev = sh.worksheet("Events")
    except: ws_ev = sh.add_worksheet(title="Events", rows=100, cols=15)
    event_headers = ['Event_ID', 'Datum', 'Uhrzeit', 'Ensemble', 'Location_Name', 'Strasse', 'PLZ', 'Stadt', 'Setlist_Name', 'Songs_IDs', 'File_Link']
    curr = ws_ev.row_values(1)
    if not curr or 'File_Link' not in curr:
        ws_ev.clear(); ws_ev.update('A1:K1', [event_headers]) 

    try: ws_loc = sh.worksheet("Locations")
    except: ws_loc = sh.add_worksheet(title="Locations", rows=50, cols=5)
    loc_headers = ['ID', 'Name', 'Strasse', 'PLZ', 'Stadt']
    if not ws_loc.row_values(1): ws_loc.update('A1:E1', [loc_headers])
    st.session_state.db_checked = True

@st.cache_data(ttl=600)
def get_data_repertoire():
    ws = sh.worksheet("Repertoire")
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    required = ['ID', 'Titel', 'Komponist_Nachname', 'Bearbeiter_Nachname', 'Verlag', 'Komponist_Vorname', 'Bearbeiter_Vorname', 'Dauer']
    for col in required:
        if col not in df.columns: df[col] = ""
    if not df.empty:
        df['ID'] = df['ID'].apply(lambda x: str(int(float(str(x).replace(',','.')))) if str(x).replace(',','.',1).replace('.','',1).isdigit() else str(x))
        df['Label'] = df.apply(lambda row: f"{row['Titel']} ({row['Komponist_Nachname']})" + (f" / Arr: {row['Bearbeiter_Nachname']}" if row['Bearbeiter_Nachname'] else ""), axis=1)
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
    get_data_repertoire.clear(); get_data_locations.clear(); get_data_events.clear()

def clean_id_list_from_string(raw_input):
    if not raw_input: return []
    parts = str(raw_input).split(',')
    clean = []
    for p in parts:
        s = p.strip()
        if not s: continue
        try: clean.append(str(int(float(s))))
        except: clean.append(s)
    return clean

def reset_draft():
    st.session_state.gig_draft = {"event_id": None, "datum": datetime.date.today(), "uhrzeit": datetime.time(19, 0), "ensemble": "Tutti", "location_selection": "Bitte wählen...", "new_loc_data": {}}
    st.session_state.gig_song_selector = []

def save_song_direct(mode, song_id, titel, kn, kv, bn, bv, dauer, verlag):
    ws = sh.worksheet("Repertoire")
    if mode == "Neu":
        col_ids = ws.col_values(1)[1:] 
        ids = [int(x) for x in col_ids if str(x).isdigit()]
        new_id = max(ids) + 1 if ids else 1
        row = [new_id, titel, kn, kv, bn, bv, dauer, verlag, "U-Musik", ""]
        ws.append_row(row)
        msg = f"'{titel}' angelegt!"
    else: 
        try:
            cell = ws.find(str(song_id), in_column=1)
            r = cell.row
            ws.update(f"B{r}:H{r}", [[titel, kn, kv, bn, bv, dauer, verlag]])
            msg = f"'{titel}' aktualisiert!"
        except: return False, "Fehler beim Update"
    clear_all_caches(); return True, msg

def save_location_direct(name, strasse, plz, stadt):
    ws = sh.worksheet("Locations")
    col_ids = ws.col_values(1)[1:]
    ids = [int(x) for x in col_ids if str(x).isdigit()]
    new_id = max(ids) + 1 if ids else 1
    ws.append_row([new_id, name, strasse, plz, stadt])
    clear_all_caches(); return True

def update_event_in_db(event_id, row_data):
    ws = sh.worksheet("Events")
    try:
        cell = ws.find(str(event_id), in_column=1)
        row_num = cell.row
        ws.update(f"A{row_num}:K{row_num}", [[event_id] + row_data])
        clear_all_caches(); return True
    except: return False

# --- NAVIGATION ---
def navigation_bar():
    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("💾 Speichern / Edit", use_container_width=True, type="primary" if st.session_state.page == "speichern" else "secondary"): st.session_state.page = "speichern"; st.rerun()
    if c2.button("🎵 Repertoire", use_container_width=True, type="primary" if st.session_state.page == "repertoire" else "secondary"): st.session_state.page = "repertoire"; st.rerun()
    if c3.button("📍 Orte", use_container_width=True, type="primary" if st.session_state.page == "orte" else "secondary"): st.session_state.page = "orte"; st.rerun()
    if c4.button("📂 Archiv", use_container_width=True, type="primary" if st.session_state.page == "archiv" else "secondary"): st.session_state.page = "archiv"; st.rerun()
    st.markdown("---")

# --- MAIN ---
check_and_fix_db()
st.title("Orchester Manager 🎻")
navigation_bar()

# === SEITE 1: SPEICHERN ===
if st.session_state.page == "speichern":
    df_loc = get_data_locations()
    df_rep = get_data_repertoire()
    df_events = get_data_events()
    
    # Editier-Auswahl
    if st.session_state.gig_draft["event_id"] is None:
        with st.expander("🛠 Bereits gespeicherten Auftritt bearbeiten", expanded=False):
            if not df_events.empty:
                df_events['Label'] = df_events.apply(lambda x: f"{x['Datum']} - {x['Location_Name']} ({x['Ensemble']})", axis=1)
                df_events = df_events.sort_values(by='Datum_Obj', ascending=False)
                
                edit_sel = st.selectbox("Wähle einen Auftritt:", ["Bitte wählen..."] + df_events['Label'].tolist())
                if st.button("Laden") and edit_sel != "Bitte wählen...":
                    row = df_events[df_events['Label'] == edit_sel].iloc[0]
                    st.session_state.gig_draft["event_id"] = row['Event_ID']
                    st.session_state.gig_draft["datum"] = datetime.datetime.strptime(row['Datum'], "%d.%m.%Y").date()
                    try: st.session_state.gig_draft["uhrzeit"] = datetime.datetime.strptime(row['Uhrzeit'], "%H:%M").time()
                    except: st.session_state.gig_draft["uhrzeit"] = datetime.time(19, 0)
                    st.session_state.gig_draft["ensemble"] = row['Ensemble']
                    st.session_state.gig_draft["location_selection"] = row['Location_Name']
                    
                    saved_ids = clean_id_list_from_string(row['Songs_IDs'])
                    restored_labels = []
                    if not df_rep.empty:
                        rows = df_rep[df_rep['ID'].isin(saved_ids)]
                        restored_labels = rows['Label'].tolist()
                    
                    st.session_state.gig_song_selector = restored_labels
                    st.toast("Geladen!", icon="✏️"); time.sleep(0.5); st.rerun()

    if st.session_state.gig_draft["event_id"]:
        cb, ch = st.columns([1,3])
        if cb.button("⬅️ Zurück"): reset_draft(); st.rerun()
        ch.header(f"✏️ Bearbeiten (ID: {st.session_state.gig_draft['event_id']})")
    else: st.header("📝 Neuen Auftritt erfassen")

    c_date, c_time = st.columns(2)
    st.session_state.gig_draft["datum"] = c_date.date_input("Datum", value=st.session_state.gig_draft["datum"])
    st.session_state.gig_draft["uhrzeit"] = c_time.time_input("Uhrzeit", value=st.session_state.gig_draft["uhrzeit"])
    
    ens_opts = ["Tutti", "BQ", "Quartett", "Duo"]
    st.session_state.gig_draft["ensemble"] = st.selectbox("Ensemble", ens_opts, index=ens_opts.index(st.session_state.gig_draft["ensemble"]))

    st.write("📍 **Spielort**")
    loc_opts = ["Bitte wählen..."] + df_loc['Name'].tolist() + ["➕ Neuer Ort..."]
    try: sel_idx = loc_opts.index(st.session_state.gig_draft["location_selection"])
    except: sel_idx = 0
    sel_loc = st.selectbox("Ort:", options=loc_opts, index=sel_idx)
    st.session_state.gig_draft["location_selection"] = sel_loc

    final_loc = {}
    if sel_loc == "➕ Neuer Ort...":
        with st.form("new_loc_form"):
            n = st.text_input("Name*"); s = st.text_input("Str."); p = st.text_input("PLZ"); ci = st.text_input("Stadt*")
            if st.form_submit_button("Bestätigen"):
                st.session_state.gig_draft["new_loc_data"] = {"Name": n, "Strasse": s, "PLZ": p, "Stadt": ci}
                st.rerun()
        if st.session_state.gig_draft["new_loc_data"]: final_loc = st.session_state.gig_draft["new_loc_data"]
    elif sel_loc != "Bitte wählen...":
        final_loc = df_loc[df_loc['Name'] == sel_loc].iloc[0].to_dict()

    st.markdown("---")
    st.write("🎵 **Programm**")
    with st.expander("➕ Titel fehlt? Hier sofort anlegen"):
        with st.form("quick_add"):
            c1, c2 = st.columns([3,1]); t=c1.text_input("Titel"); d=c2.text_input("Dauer", "03:00")
            c3, c4 = st.columns(2); kn=c3.text_input("Komp NN"); kv=c4.text_input("Komp VN")
            c5, c6 = st.columns(2); bn=c5.text_input("Bearb NN"); bv=c6.text_input("Bearb VN")
            ver = st.text_input("Verlag")
            if st.form_submit_button("Speichern"):
                if t and kn:
                    save_song_direct("Neu", None, t, kn, kv, bn, bv, d, ver)
                    st.rerun()

    if not df_rep.empty:
        selection = st.multiselect("Suche:", options=df_rep['Label'].tolist(), key="gig_song_selector")
        
        st.markdown("---")
        btn_txt = "🔄 Aktualisieren" if st.session_state.gig_draft["event_id"] else "✅ Final speichern & Excel erstellen"
        if st.button(btn_txt, type="primary", use_container_width=True):
            if not final_loc.get("Name") or not selection:
                st.error("Ort und Programm fehlen!")
            else:
                if sel_loc == "➕ Neuer Ort...":
                    save_location_direct(final_loc["Name"], final_loc["Strasse"], final_loc["PLZ"], final_loc["Stadt"])
                
                # Excel Generierung vorbereiten
                datum_str = st.session_state.gig_draft["datum"].strftime("%d.%m.%Y")
                time_str = st.session_state.gig_draft["uhrzeit"].strftime("%H:%M")
                dateiname = f"{st.session_state.gig_draft['ensemble']}{datum_str}{final_loc['Stadt']}Setlist.xlsx"
                
                # Songs Objekte holen für Excel
                selected_songs_data = []
                song_ids = []
                for label in selection:
                    row = df_rep[df_rep['Label'] == label].iloc[0]
                    song_ids.append(str(row['ID']))
                    selected_songs_data.append(row.to_dict())
                
                with st.spinner("Erstelle Excel-Datei und lade hoch..."):
                    # EXCEL GENERIERUNG
                    web_link, err = generate_and_upload_excel(datum_str, time_str, st.session_state.gig_draft['ensemble'], final_loc, selected_songs_data, dateiname)
                    
                    if err:
                        st.error(f"⚠️ {err}")
                        st.info("TIPP: Hast du 'requirements.txt' aktualisiert? Hast du den Ordner 'Templates' und die Datei 'Setlist_Template.xlsx' im Drive?")
                    else:
                        row_data = [
                            datum_str, time_str, st.session_state.gig_draft["ensemble"],
                            final_loc["Name"], final_loc["Strasse"], str(final_loc["PLZ"]), final_loc["Stadt"],
                            dateiname, ",".join(song_ids), web_link
                        ]
                        
                        if st.session_state.gig_draft["event_id"]:
                            update_event_in_db(st.session_state.gig_draft["event_id"], row_data)
                        else:
                            ws_ev = sh.worksheet("Events"); col_ids = ws_ev.col_values(1)[1:]
                            e_ids = [int(x) for x in col_ids if str(x).isdigit()]
                            new_ev_id = max(e_ids) + 1 if e_ids else 1
                            ws_ev.append_row([new_ev_id] + row_data)
                            clear_all_caches()
                        
                        st.balloons()
                        st.success(f"Fertig! Datei erstellt: {dateiname}")
                        reset_draft(); time.sleep(3); st.rerun()
    else: st.warning("Repertoire leer.")

# === SEITE 2: REPERTOIRE ===
elif st.session_state.page == "repertoire":
    st.subheader("Repertoire verwalten")
    mode = st.radio("Modus:", ["Neu", "Bearbeiten"], horizontal=True)
    df_rep = get_data_repertoire()
    
    if mode == "Bearbeiten" and not df_rep.empty:
        sel = st.selectbox("Suchen:", df_rep['Label'].tolist(), index=None)
        if sel:
            r = df_rep[df_rep['Label'] == sel].iloc[0]
            if st.session_state.rep_edit_state["id"] != r['ID']:
                st.session_state.rep_edit_state = {"id": r['ID'], "titel": r['Titel'], "dauer": str(r['Dauer']), "kn": r['Komponist_Nachname'], "kv": r['Komponist_Vorname'], "bn": r['Bearbeiter_Nachname'], "bv": r['Bearbeiter_Vorname'], "verlag": r['Verlag']}
    elif mode == "Neu" and st.session_state.rep_edit_state["id"]:
        st.session_state.rep_edit_state = {"id": None, "titel": "", "dauer": "03:00", "kn": "", "kv": "", "bn": "", "bv": "", "verlag": ""}

    with st.form("rep"):
        s = st.session_state.rep_edit_state
        c1,c2=st.columns([3,1]); t=c1.text_input("Titel", s["titel"]); d=c2.text_input("Dauer", s["dauer"])
        c3,c4=st.columns(2); kn=c3.text_input("Komp NN", s["kn"]); kv=c4.text_input("Komp VN", s["kv"])
        c5,c6=st.columns(2); bn=c5.text_input("Bearb NN", s["bn"]); bv=c6.text_input("Bearb VN", s["bv"])
        v=st.text_input("Verlag", s["verlag"])
        if st.form_submit_button("Speichern"):
            save_song_direct("Edit" if s["id"] else "Neu", s["id"], t, kn, kv, bn, bv, d, v)
            st.session_state.rep_edit_state = {"id": None, "titel": "", "dauer": "", "kn": "", "kv": "", "bn": "", "bv": "", "verlag": ""}
            st.rerun()
    st.dataframe(df_rep, use_container_width=True)

# === SEITE 3: ORTE ===
elif st.session_state.page == "orte":
    st.subheader("Locations"); df_loc = get_data_locations()
    with st.form("loc"):
        n=st.text_input("Name"); ci=st.text_input("Stadt")
        if st.form_submit_button("Speichern"): save_location_direct(n, "", "", ci); st.rerun()
    st.dataframe(df_loc, use_container_width=True)

# === SEITE 4: ARCHIV ===
elif st.session_state.page == "archiv":
    st.subheader("📂 Setlist Archiv")
    df_events = get_data_events()
    if not df_events.empty:
        df_events = df_events.sort_values(by='Datum_Obj', ascending=False)
        for year in df_events['Datum_Obj'].dt.year.unique():
            st.markdown(f"### {year}")
            df_y = df_events[df_events['Datum_Obj'].dt.year == year]
            for m in df_y['Datum_Obj'].dt.month.unique():
                m_name = datetime.date(2000, int(m), 1).strftime('%B')
                with st.expander(f"{m_name} ({len(df_y[df_y['Datum_Obj'].dt.month == m])})"):
                    for _, row in df_y[df_y['Datum_Obj'].dt.month == m].iterrows():
                        c1, c2 = st.columns([3, 1])
                        c1.write(f"**{row['Datum']}** | {row['Location_Name']} ({row['Ensemble']})")
                        c1.caption(f"Datei: {row['Setlist_Name']}")
                        
                        if 'File_Link' in row and row['File_Link']:
                            c2.link_button("👁️ Ansehen", row['File_Link'])
                        else:
                            c2.caption("Kein Link")
                        st.divider()
