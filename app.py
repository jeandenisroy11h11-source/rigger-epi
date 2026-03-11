import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import base64
from PIL import Image
import io

# --- CONFIGURATION ---
API_URL = "https://script.google.com/macros/s/AKfycbzzZvhMHJGVU267o7eIqHpmeI5z-ThItEXIbMjLg8c-7YxLvB4ryQ0fCXLEfpTEEsbDFQ/exec"
MON_NOM = "JD"

st.set_page_config(page_title="Rigger EPI - JD", layout="centered", page_icon="🛠️")

# --- FONCTIONS UTILES ---
def clean_date(val):
    s = str(val)
    return s[:10] if len(s) >= 10 and s[0].isdigit() else s

@st.cache_data(ttl=2)
def load_all_data():
    res = requests.get(API_URL).json()
    headers = res['inventaire'][0]
    rows = res['inventaire'][1:]
    
    df_inv = pd.DataFrame(rows, columns=headers)
    
    # Nettoyage des colonnes fantômes
    df_inv = df_inv.loc[:, df_inv.columns.str.len() > 0]
    df_inv = df_inv.loc[:, ~df_inv.columns.str.contains('^Unnamed')]
    
    # Sécurité No_Serie : Si la colonne n'existe pas, on la crée pour éviter le crash
    if "No_Serie" not in df_inv.columns:
        df_inv["No_Serie"] = "N/A"

    # On ne garde que les vrais items
    df_inv = df_inv[df_inv["Marque_Modele"].astype(str).str.strip() != ""]
    
    for col in ["Derniere_Inspection", "Date_Achat"]:
        if col in df_inv.columns: 
            df_inv[col] = df_inv[col].apply(clean_date)
    
    df_conf = pd.DataFrame(res['config'][1:], columns=res['config'][0])
    
    return {
        "inv": df_inv,
        "lieux": df_conf["Lieux"].dropna().unique().tolist() if "Lieux" in df_conf.columns else [],
        "categories": df_conf["Categories"].dropna().unique().tolist() if "Categories" in df_conf.columns else [],
        "h_loc": pd.DataFrame(res['hist_loc'][1:], columns=res['hist_loc'][0]),
        "h_insp": pd.DataFrame(res['hist_insp'][1:], columns=res['hist_insp'][0])
    }

# --- CHARGEMENT ---
try:
    data = load_all_data()
    df = data['inv']
except Exception as e:
    st.error(f"Erreur de chargement : {e}")
    st.stop()

# --- BARRE LATÉRALE (AJOUT ITEM) ---
with st.sidebar:
    st.header("➕ Nouvel Item")
    with st.form("add_item", clear_on_submit=True):
        n_serie = st.text_input("Numéro de Série")
        n_id = st.text_input("Marque / Modèle")
        n_cat = st.selectbox("Catégorie", data['categories'])
        n_date = st.date_input("Date d'achat", datetime.now())
        n_vie = st.number_input("Vie utile (ans)", 10)
        n_lieu = st.selectbox("Lieu initial", data['lieux'])
        
        if st.form_submit_button("Créer l'item", use_container_width=True):
            if n_serie and n_id:
                payload = {
                    "Action": "AJOUT_ITEM", "No_Serie": n_serie, "Marque_Modele": n_id, 
                    "Categorie": n_cat, "Date_Achat": str(n_date), "Duree_Vie_Ans": n_vie, 
                    "Nouveau_Lieu": n_lieu
                }
                requests.post(API_URL, json=payload)
                st.cache_data.clear()
                st.rerun()

# --- INTERFACE PRINCIPALE (EN HAUT) ---
st.title("🛠️ Gestion EPI - JD")

# Liste pour le sélecteur
df["Label"] = df["No_Serie"].astype(str) + " | " + df["Marque_Modele"].astype(str)
list_sn = df["No_Serie"].tolist()

# Scan NFC
query_params = st.query_params
scan_id = query_params.get("id")
default_idx = list_sn.index(scan_id) if scan_id in list_sn else None

selected_sn = st.selectbox("Sélectionner l'équipement", list_sn, index=default_idx, 
                           format_func=lambda x: df[df["No_Serie"] == x]["Label"].iloc[0])

if selected_sn:
    row = df[df["No_Serie"] == selected_sn].iloc[0]
    
    tab1, tab2, tab3 = st.tabs(["📦 Mouvement", "📋 Inspection", "📜 Historique"])

    with tab1:
        st.info(f"📍 Lieu actuel : **{row['Emplacement_Actuel']}**")
        with st.form("move_form"):
            dest = st.selectbox("Destination", data['lieux'] + ["+ Nouveau lieu"])
            nouveau = st.text_input("Si nouveau :")
            f_dest = nouveau if dest == "+ Nouveau lieu" else dest
            if st.form_submit_button("Déplacer", type="primary", use_container_width=True):
                payload = {
                    "Action": "MOUVEMENT", "No_Serie": selected_sn, "Marque_Modele": row["Marque_Modele"],
                    "Ancien_Lieu": row['Emplacement_Actuel'], "Nouveau_Lieu": f_dest, "Inspecteur": MON_NOM
                }
                requests.post(API_URL, json=payload)
                st.cache_data.clear()
                st.rerun()

    with tab2:
        st.warning(f"🗓️ Dernière insp. : {row['Derniere_Inspection']}")
        with st.form("insp_form"):
            res_insp = st.radio("Résultat", ["✅ PASS", "⚠️ À SURVEILLER", "❌ FAIL"], horizontal=True)
            obs = st.text_area("Observations")
            photo = st.camera_input("Photo (Optionnelle)")
            if st.form_submit_button("Enregistrer", type="primary", use_container_width=True):
                img_b64 = ""
                if photo:
                    img = Image.open(photo); img.thumbnail((400, 400))
                    buf = io.BytesIO(); img.save(buf, format="JPEG", quality=70)
                    img_b64 = base64.b64encode(buf.getvalue()).decode()
                
                payload = {
                    "Action": "INSPECTION", "No_Serie": selected_sn, "Marque_Modele": row["Marque_Modele"],
                    "Derniere_Inspection": datetime.now().strftime("%Y-%m-%d"), "Inspecteur": MON_NOM,
                    "Resultat": res_insp, "Observations": obs, "Photo": img_b64, "Nouveau_Lieu": row["Emplacement_Actuel"]
                }
                requests.post(API_URL, json=payload)
                st.cache_data.clear()
                st.rerun()

    with tab3:
        st.dataframe(data['h_loc'][data['h_loc']["No_Serie"] == selected_sn], hide_index=True, use_container_width=True)
        st.dataframe(data['h_insp'][data['h_insp']["No_Serie"] == selected_sn], hide_index=True, use_container_width=True)

# --- DASHBOARD (EN BAS) ---
st.markdown("---")
st.subheader("📊 Aperçu global")
c1, c2, c3 = st.columns(3)
c1.metric("Total Items", len(df))
# On utilise str.contains pour être flexible sur les majuscules
c2.metric("⚠️ À inspecter", len(df[df["Statut_Actuel"].str.contains("inspecter", case=False, na=False)]))
c3.metric("✅ En service", len(df[df["Statut_Actuel"].str.contains("service", case=False, na=False)]))