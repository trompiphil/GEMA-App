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
from openpyxl.cell.cell import MergedCell
from io import BytesIO

# --- KONFIGURATION ---
DB_NAME = "GEMA_Datenbank"

st.set_page_config(page_title="GEMA Manager", page_icon="xj", layout="centered")

# --- 1. SESSION STATE & NAVIGATION (JETZT GANZ OBEN) ---

def reset_draft_logic(keep_download=False):
    """Setzt das Formular zurück."""
    st.session_state.gig_draft = {
        "event_id": None, "datum": datetime.date.today(), "uhrzeit": datetime.time(19, 0),
        "ensemble": "Tutti", "location_selection": "Bitte wählen...", 
        "new_loc_data": {}
    }
    st.session_state.gig_song_selector = []
    
    if not keep_download:
        st.session_state.last_download = None
        st.session_state.uploaded_file_link = None

# Variablen initialisieren
if 'gig_draft' not in st.session_state: reset_draft_logic()
if 'gig_song_selector' not in st.session_state: st.session_state.gig_song_selector = []
if 'rep_edit_state' not in st.session_state: st.session_state.rep_edit_state = {"id": None, "titel": "", "dauer": "", "kn": "", "kv": "", "bn": "", "bv": "", "verlag": ""}
if 'page' not in st.session_state: st.session_state.page = "speichern"
if 'db_checked' not in st.session_state: st.session_state.db_checked = False
if 'last_download' not in st.session_state: st.session_state.last_download = None
if 'uploaded_file_link' not in st.session_state: st.session_state.uploaded_file_link = None
if 'trigger_reset' not in st.session_state: st.session_state.trigger_reset = False

# Reset Trigger
if st.session_state.trigger_reset:
    reset_draft_logic(keep_download=True)
    st.session_state.trigger_reset = False
    st.rerun()

# DEFINITION DER NAVIGATION (Hier oben ist sie sicher!)
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

# --- 2. GOOGLE DIENSTE ---

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
    st.error(f"Verbindungsfehler: {e}"); st.stop()

# --- 3. HELPER FUNKTIONEN (DRIVE & EXCEL) ---

def get_folder_id(folder_name, parent_id=None):
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id: query += f" and '{parent_id}' in parents"
    try:
        results = drive_service.files().list(q=query, fields="files(id)").execute()
        items = results.get('files', [])
        if items: return items[0]['id']
    except: pass
    return None

def list_files_in_templates():
    root_id = get_folder_id("GEMA Bpol")
    if not root_id: return [], "Hauptordner 'GEMA Bpol' nicht gefunden."
    fid = get_folder_id("Templates", parent_id=root_id)
    if not fid: fid = get_folder_id("Templates") 
    if not fid: return [], "Ordner 'Templates' nicht gefunden."
    
    query = f"'{fid}' in parents and trashed = false"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    return results.get('files', []), None

def download_specific_template(file_id, local_filename):
    try:
        content = drive_service.files().get_media(fileId=file_id).execute()
        with open(local_filename, "wb") as f: f.write(content)
        return True, None
    except Exception as e: return False, str(e)

def safe_write(ws, row, col, value):
    """Schreibt in Zelle, ignoriert MergedCell Fehler"""
    try:
        cell = ws.cell(row=row, column=col)
        if isinstance(cell, MergedCell):
            for r in ws.merged_cells.ranges:
                if cell.coordinate in r:
                    ws.cell(r.min_row, r.min_col).value = value; break
        else: cell.value = value
    except: pass

def process_and_upload_excel(template_file_id, datum, uhrzeit, ensemble, ort_data, songs_list, target_filename):
    # 1. Download
    local_temp = "temp_template.xlsx"
    ok, err = download_specific_template(template_file_id, local_temp)
    if not ok: return None, None, f"Download Fehler: {err}"

    # 2. Excel bearbeiten
    try:
        wb = openpyxl.load_workbook(local_temp)
        ws = wb.active 
        
        # Header NICHT anfassen (Zeile 1-20 geschützt)
        start_row = 21
        current_row = start_row
        
        # Leeren ab Zeile 21
        cols = [2, 5, 6, 7, 10, 16, 17] # B,E,F,G,J,P,Q
        for r in range(start_row, 100):
            for c in cols: safe_write(ws, r, c, None)

        # Befüllen
        for song in songs_list:
            safe_write(ws, current_row, 2, song['Titel']) 
            safe_write(ws, current_row, 5, song['Dauer']) 
            safe_write(ws, current_row, 6, song['Komponist_Nachname']) 
            safe_write(ws, current_row, 7, song['Komponist_Vorname']) 
            safe_write(ws, current_row, 10, song['Verlag']) 
            safe_write(ws, current_row, 16, song['Bearbeiter_Nachname']) 
            safe_write(ws, current_row, 17, song['Bearbeiter_Vorname']) 
            current_row += 1
            
        wb.save(target_filename)
        
        output_bytes = BytesIO()
        with open(target_filename, "rb") as f: output_bytes.write(f.read())
        output_bytes.seek(0)
        
    except Exception as e:
        return None, None, f"Excel Fehler: {e}"

    # 3. Upload (Safe Mode)
    web_link = "Lokal"
    try:
        root_id = get_folder_id("GEMA Bpol")
        if root_id:
            output_id = get_folder_id("Output", parent_id=root_id)
            if output_id:
                file_metadata = {'name': target_filename, 'parents': [output_id]}
                media = MediaFileUpload(target_filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
                web_link = file.get('webViewLink')
    except Exception:
        web_link = "Upload gescheitert (Quota)" # Fehler abfangen, nicht abstürzen

    if os.path.exists(local_temp): os.remove(local_temp)
    if os.path.exists(target_filename): os.remove(target_filename)

    return output_bytes, web_link, None

# --- 4. DB FUNKTIONEN ---

def check_and_fix_db():
    if st.session_state.db_checked: return
    try: 
        ws = sh.worksheet("Repertoire")
        if not ws.row_values(1): ws.update('A1:J1', [['ID','Titel','Komponist_Nachname','Komponist_Vorname','Bearbeiter_Nachname','Bearbeiter_Vorname','Dauer','Verlag','Werkeart','ISWC']])
    except: pass
    try:
        ws = sh.worksheet("Events")
        if not ws.row_values(1): ws.update('A1:K1', [['Event_ID','Datum','Uhrzeit','Ensemble','Location_Name','Strasse','PLZ','Stadt','Setlist_Name','Songs_IDs','File_Link']])
    except: pass
    try:
        ws = sh.worksheet("Locations")
        if not ws.row_values(1): ws.update('A1:E1', [['ID','Name','Strasse','PLZ','Stadt']])
    except: pass
    st.session_state.db_checked = True

@st.cache_data(ttl=600)
def get_data_repertoire():
    ws = sh.worksheet("Repertoire"); df = pd.DataFrame(ws.get_all_records())
    for c in ['ID','Titel','Komponist_Nachname','Bearbeiter_Nachname']: 
        if c not in df.columns: df[c]=""
    if not df.empty:
        df['ID'] = df['ID'].astype(str).str.replace(r'\.0$', '', regex=True)
        df['Label'] = df.apply(lambda x: f"{x['Titel']} ({x['Komponist_Nachname']})" + (f" / Arr: {x['Bearbeiter_Nachname']}" if x['Bearbeiter_Nachname'] else ""), axis=1)
    return df

@st.cache_data(ttl=600)
def get_data_locations():
    ws = sh.worksheet("Locations"); df = pd.DataFrame(ws.get_all_records())
    return df if not df.empty else pd.DataFrame(columns=['ID','Name','Strasse','PLZ','Stadt'])

@st.cache_data(ttl=600)
def get_data_events():
    ws = sh.worksheet("Events"); df = pd.DataFrame(ws.get_all_records())
    if not df.empty and 'Datum' in df.columns: df['Datum_Obj'] = pd.to_datetime(df['Datum'], format="%d.%m.%Y", errors='coerce')
    return df

def clear_all_caches():
    get_data_repertoire.clear(); get_data_locations.clear(); get_data_events.clear()

def clean_id_list_from_string(raw):
    if not raw: return []
    return [s.strip().replace('.0','') for s in str(raw).split(',') if s.strip()]

def save_song_direct(mode, song_id, t, kn, kv, bn, bv, d, v):
    ws = sh.worksheet("Repertoire")
    if mode == "Neu":
        ids = [int(x) for x in ws.col_values(1)[1:] if str(x).isdigit()]
        new_id = max(ids)+1 if ids else 1
        ws.append_row([new_id, t, kn, kv, bn, bv, d, v, "U-Musik", ""])
        msg = f"'{t}' angelegt!"
    else:
        try:
            cell = ws.find(str(song_id), in_column=1)
            ws.update(f"B{cell.row}:H{cell.row}", [[t, kn, kv, bn, bv, d, v]])
            msg = f"'{t}' aktualisiert!"
        except: return False, "Fehler"
    clear_all_caches(); return True, msg

def save_location_direct(n, s, p, c):
    ws = sh.worksheet("Locations")
    ids = [int(x) for x in ws.col_values(1)[1:] if str(x).isdigit()]
    new_id = max(ids)+1 if ids else 1
    ws.append_row([new_id, n, s, p, c])
    clear_all_caches(); return True

def update_event_in_db(eid, data):
    ws = sh.worksheet("Events")
    try:
        cell = ws.find(str(eid), in_column=1)
        ws.update(f"A{cell.row}:K{cell.row}", [[eid]+data])
        clear_all_caches(); return True
    except: return False

# --- 5. APP UI (MAIN) ---

check_and_fix_db()
st.title("Orchester Manager 🎻")
navigation_bar() # Jetzt sicher aufrufbar!

if st.session_state.page == "speichern":
    df_loc = get_data_locations(); df_rep = get_data_repertoire(); df_events = get_data_events()
    
    # Download Button
    if st.session_state.last_download:
        d_name, d_bytes = st.session_state.last_download
        cloud_stat = st.session_state.uploaded_file_link
        st.success("✅ Datei bereit!")
        c1, c2 = st.columns(2)
        c1.download_button(f"📥 {d_name}", d_bytes, d_name, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True)
        if "http" in str(cloud_stat): c2.link_button("☁️ Drive Link", cloud_stat, use_container_width=True)
        else: c2.warning("⚠️ Cloud Upload voll. Lokal speichern.")
        st.divider()

    # Editier-Auswahl
    if not st.session_state.gig_draft["event_id"]:
        with st.expander("🛠 Bearbeiten"):
            if not df_events.empty:
                opts = df_events.sort_values('Datum_Obj', ascending=False)['Label'].tolist() if 'Label' in df_events else []
                sel = st.selectbox("Wahl:", ["-"]+opts)
                if st.button("Laden") and sel != "-":
                    row = df_events[df_events['Label']==sel].iloc[0]
                    st.session_state.gig_draft.update({"event_id": row['Event_ID'], "datum": datetime.datetime.strptime(row['Datum'], "%d.%m.%Y").date(), "ensemble": row['Ensemble'], "location_selection": row['Location_Name']})
                    ids = clean_id_list_from_string(row['Songs_IDs'])
                    st.session_state.gig_song_selector = df_rep[df_rep['ID'].isin(ids)]['Label'].tolist() if not df_rep.empty else []
                    st.session_state.last_download = None; st.rerun()

    # Formular
    if st.session_state.gig_draft["event_id"]:
        if st.button("⬅️ Zurück"): 
            st.session_state.trigger_reset = True; st.rerun()
        st.header(f"✏️ Edit ID: {st.session_state.gig_draft['event_id']}")
    else: st.header("📝 Neu")

    c1, c2 = st.columns(2)
    st.session_state.gig_draft["datum"] = c1.date_input("Datum", st.session_state.gig_draft["datum"])
    st.session_state.gig_draft["uhrzeit"] = c2.time_input("Zeit", st.session_state.gig_draft["uhrzeit"])
    ens = st.selectbox("Ensemble", ["Tutti", "BQ", "Quartett", "Duo"], index=["Tutti", "BQ", "Quartett", "Duo"].index(st.session_state.gig_draft["ensemble"]))
    st.session_state.gig_draft["ensemble"] = ens

    st.write("📍 Ort")
    locs = ["Wählen..."] + df_loc['Name'].tolist() + ["➕ Neu..."]
    try: idx = locs.index(st.session_state.gig_draft["location_selection"])
    except: idx = 0
    sel_loc = st.selectbox("Ort", locs, index=idx)
    st.session_state.gig_draft["location_selection"] = sel_loc

    fin_loc = {}
    if sel_loc == "➕ Neu...":
        with st.form("new_loc"):
            n=st.text_input("Name"); s=st.text_input("Str"); p=st.text_input("PLZ"); c=st.text_input("Stadt")
            if st.form_submit_button("Speichern"):
                if n and c:
                    save_location_direct(n,s,p,c)
                    st.session_state.gig_draft["location_selection"] = n
                    st.toast("Gespeichert!", icon="✅"); time.sleep(1); st.rerun()
                else: st.error("Name/Stadt fehlt")
    elif sel_loc != "Wählen...":
        fin_loc = df_loc[df_loc['Name']==sel_loc].iloc[0].to_dict()

    st.markdown("---")
    st.write("🎵 Programm")
    with st.expander("➕ Schnell-Anlage"):
        with st.form("quick"):
            c1,c2=st.columns([3,1]); t=c1.text_input("Titel"); d=c2.text_input("Dauer","03:00")
            c3,c4=st.columns(2); kn=c3.text_input("Komp NN"); kv=c4.text_input("Komp VN")
            c5,c6=st.columns(2); bn=c5.text_input("Bearb NN"); bv=c6.text_input("Bearb VN")
            ver=st.text_input("Verlag")
            if st.form_submit_button("Speichern"):
                if t and kn: save_song_direct("Neu",None,t,kn,kv,bn,bv,d,ver); st.rerun()

    if not df_rep.empty:
        sel_songs = st.multiselect("Suche", df_rep['Label'].tolist(), key="gig_song_selector")
        st.markdown("---")
        
        # Template Wahl
        files, err = list_files_in_templates()
        if not files: st.error(err if err else "Keine Templates gefunden")
        else:
            t_names = [f['name'] for f in files]
            t_sel = st.selectbox("Vorlage", t_names)
            t_id = next(f['id'] for f in files if f['name'] == t_sel)

            if st.button("✅ Fertigstellen", type="primary", use_container_width=True):
                if not fin_loc.get("Name") or not sel_songs:
                    st.error("Ort oder Songs fehlen")
                else:
                    d_str = st.session_state.gig_draft["datum"].strftime("%d.%m.%Y")
                    t_str = st.session_state.gig_draft["uhrzeit"].strftime("%H:%M")
                    fname = f"{ens}{d_str}{fin_loc['Stadt']}Setlist.xlsx"
                    
                    s_data = []
                    s_ids = []
                    for lbl in sel_songs:
                        r = df_rep[df_rep['Label']==lbl].iloc[0]
                        s_ids.append(str(r['ID']))
                        s_data.append(r.to_dict())

                    with st.spinner("Generiere..."):
                        b, link, err = process_and_upload_excel(t_id, d_str, t_str, ens, fin_loc, s_data, fname)
                        if err: st.error(err)
                        else:
                            row = [d_str, t_str, ens, fin_loc["Name"], fin_loc["Strasse"], str(fin_loc["PLZ"]), fin_loc["Stadt"], fname, ",".join(s_ids), str(link)]
                            eid = st.session_state.gig_draft["event_id"]
                            if eid: update_event_in_db(eid, row)
                            else:
                                ws = sh.worksheet("Events")
                                ids = [int(x) for x in ws.col_values(1)[1:] if str(x).isdigit()]
                                new_eid = max(ids)+1 if ids else 1
                                ws.append_row([new_eid]+row)
                                clear_all_caches()
                            
                            st.session_state.last_download = (fname, b.getvalue())
                            st.session_state.uploaded_file_link = link
                            st.session_state.trigger_reset = True
                            st.rerun()

# --- ANDERE SEITEN ---
elif st.session_state.page == "repertoire":
    st.subheader("Repertoire")
    mode = st.radio("Modus", ["Neu", "Edit"], horizontal=True)
    df = get_data_repertoire()
    if mode=="Edit" and not df.empty:
        sel = st.selectbox("Wahl", df['Label'].tolist(), index=None)
        if sel:
            r = df[df['Label']==sel].iloc[0]
            if st.session_state.rep_edit_state["id"] != r['ID']:
                st.session_state.rep_edit_state = {"id": r['ID'], "titel": r['Titel'], "dauer": str(r['Dauer']), "kn": r['Komponist_Nachname'], "kv": r['Komponist_Vorname'], "bn": r['Bearbeiter_Nachname'], "bv": r['Bearbeiter_Vorname'], "verlag": r['Verlag']}
    elif mode=="Neu": st.session_state.rep_edit_state = {"id": None, "titel": "", "dauer": "03:00", "kn": "", "kv": "", "bn": "", "bv": "", "verlag": ""}
    
    with st.form("r"):
        s = st.session_state.rep_edit_state
        c1,c2=st.columns([3,1]); t=c1.text_input("Titel", s['titel']); d=c2.text_input("Dauer", s['dauer'])
        c3,c4=st.columns(2); kn=c3.text_input("Komp NN", s['kn']); kv=c4.text_input("Komp VN", s['kv'])
        c5,c6=st.columns(2); bn=c5.text_input("Bearb NN", s['bn']); bv=c6.text_input("Bearb VN", s['bv'])
        v=st.text_input("Verlag", s['verlag'])
        if st.form_submit_button("Speichern"):
            save_song_direct("Edit" if s['id'] else "Neu", s['id'], t, kn, kv, bn, bv, d, v); st.rerun()
    st.dataframe(df)

elif st.session_state.page == "orte":
    st.subheader("Orte")
    with st.form("l"):
        n=st.text_input("Name"); c=st.text_input("Stadt")
        if st.form_submit_button("Speichern"): save_location_direct(n,"","",c); st.rerun()
    st.dataframe(get_data_locations())

elif st.session_state.page == "archiv":
    st.subheader("Archiv")
    df = get_data_events()
    if not df.empty:
        df = df.sort_values('Datum_Obj', ascending=False)
        for y in df['Datum_Obj'].dt.year.unique():
            st.markdown(f"### {y}")
            dfy = df[df['Datum_Obj'].dt.year==y]
            for m in dfy['Datum_Obj'].dt.month.unique():
                mn = datetime.date(2000,int(m),1).strftime('%B')
                with st.expander(f"{mn} ({len(dfy[dfy['Datum_Obj'].dt.month==m])})"):
                    for _,r in dfy[dfy['Datum_Obj'].dt.month==m].iterrows():
                        st.write(f"**{r['Datum']}** | {r['Location_Name']}"); st.caption(r['Setlist_Name'])
                        if "http" in str(r.get('File_Link','')): st.link_button("☁️ Cloud", r['File_Link'])
                        else: st.caption("Lokal")
                        st.divider()
