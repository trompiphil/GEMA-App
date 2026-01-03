import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# Titel der App
st.title("GEMA App - Verbindungstest 🎵")

# Verbindung zu Google Drive herstellen
try:
    # Wir holen uns die geheimen Zugangsdaten aus den Streamlit Secrets
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    # Hier lesen wir die Infos, die wir gleich in Streamlit hinterlegen
    s_info = st.secrets["gcp_service_account"]

    creds = Credentials.from_service_account_info(
        s_info,
        scopes=scopes
    )
    client = gspread.authorize(creds)

    # Versuch, die Datenbank zu öffnen
    st.write("Verbinde mit Google Drive...")

    # ACHTUNG: Hier muss exakt der Name deiner Google Tabelle stehen!
    sheet_name = "GEMA_Datenbank" 
    sh = client.open(sheet_name)

    st.success(f"Erfolg! 🎉 Ich habe die Datei '{sheet_name}' gefunden.")

    # Test: Zeige die Arbeitsblätter an
    worksheets = sh.worksheets()
    names = [ws.title for ws in worksheets]
    st.write(f"Gefundene Tabellenblätter: {names}")

except Exception as e:
    st.error("Fehler bei der Verbindung!")
    st.write("Fehlermeldung:", e)
    st.info("Tipp: Hast du die Datei 'GEMA_Datenbank' wirklich genau so genannt und für den Service Account (E-Mail) freigegeben?")
