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
    # Inventaire : On ignore les lignes vides (colonne A vide)
    df_inv = pd.DataFrame(res['inventaire'][1:], columns=res['inventaire'][0])
    df_inv = df_inv[df_inv["Marque_Modele"].str.strip() != ""]
    # Suppression des colonnes fantômes
    df_inv = df_inv.loc[:, [c for c in df_inv.columns if c and not c.startswith('Unnamed')]]
    
    # Formatage des dates
    for col in ["Derniere_Inspection", "Date_Achat"]:
        if col in df_inv.columns: 
            df_inv[col] = df_inv[col].apply(clean_date)
    
    # Config
    df_conf = pd.DataFrame(res['config'][1:], columns=res['config'][0])
    
    return {
        "inv": df_inv,
        "lieux": df_conf["Lieux"].dropna().unique().tolist(),
        "categories": df_conf["Categories"].dropna().unique().tolist() if "Categories" in df_conf.columns else [],
        "h_loc": pd.DataFrame(res['hist_loc'][1:], columns=res['hist_loc'][0]),
        "h_insp": pd.DataFrame(res['hist_insp'][1:], columns=res['hist_insp'][0])
    }

# --- CHARGEMENT ---
try:
    data = load_all_data()
    df = data['inv']
except Exception as e:
    st.error(f"Erreur de connexion : {e}")
    st.stop()

# --- BARRE LATÉRALE (AJOUT ITEM AVEC NO_SERIE) ---
with st.sidebar:
    st.header("➕ Nouvel Item")
    with st.form("add_item", clear_on_submit=True):
        n_serie = st.text_input("Numéro de Série (Unique)")
        n_id = st.text_input("Marque / Modèle")
        n_cat = st.selectbox("Catégorie", data['categories'])
        n_date = st.date_input("Date d'achat", datetime.now())
        n_vie = st.number_input("Vie utile (ans)", 10)
        n_lieu = st.selectbox("Lieu initial", data['lieux'])
        
        if st.form_submit_button("Créer l'item", use_container_width=True):
            if n_serie and n_id:
                payload = {
                    "Action": "AJOUT_ITEM", 
                    "No_Serie": n_serie,
                    "Marque_Modele": n_id, 
                    "Categorie": n_cat, 
                    "Date_Achat": str(n_date), 
                    "Duree_Vie_Ans": n_vie, 
                    "Nouveau_Lieu": n_lieu,
                    "Derniere_Inspection": "" 
                }
                requests.post(API_URL, json=payload)
                st.cache_data.clear()
                st.rerun()
            else:
                st.warning("Le No de Série et le Modèle sont obligatoires.")

# --- INTERFACE PRINCIPALE ---
st.title("🛠️ Gestion EPI - JD")

# Préparation de la liste pour le sélecteur (No_Serie comme identifiant)
df["Display_Label"] = df["No_Serie"].astype(str) + " | " + df["Marque_Modele"].astype(str)
list_no_serie = df["No_Serie"].tolist()

# Détection automatique du scan NFC (via URL ?id=SN123)
query_params = st.query_params
scan_id = query_params.get("id")
default_idx = list_no_serie.index(scan_id) if scan_id in list_no_serie else None

selected_no_serie = st.selectbox(
    "Scanner ou Sélectionner l'item", 
    list_no_serie, 
    index=default_idx,
    format_func=lambda x: df[df["No_Serie"] == x]["Display_Label"].iloc[0]
)

if selected_no_serie:
    row = df[df["No_Serie"] == selected_no_serie].iloc[0]
    item_nom = row["Marque_Modele"]
    
    tab1, tab2, tab3 = st.tabs(["📦 Mouvement", "📋 Inspection", "📜 Historique"])

    with tab1:
        st.info(f"📍 Lieu actuel : **{row['Emplacement_Actuel']}**")
        with st.form("move_form"):
            dest_choice = st.selectbox("Destination", data['lieux'] + ["+ Nouveau lieu"])
            nouveau_nom = st.text_input("Si nouveau, nom du lieu :")
            final_dest = nouveau_nom if dest_choice == "+ Nouveau lieu" else dest_choice
            
            if st.form_submit_button("Confirmer le déplacement", type="primary", use_container_width=True):
                payload = {
                    "Action": "MOUVEMENT", 
                    "Marque_Modele": item_nom, 
                    "No_Serie": selected_no_serie, # Identifiant pour le script
                    "Ancien_Lieu": row['Emplacement_Actuel'],
                    "Nouveau_Lieu": final_dest, 
                    "Derniere_Inspection": row['Derniere_Inspection'], 
                    "Inspecteur": MON_NOM
                }
                requests.post(API_URL, json=payload)
                st.cache_data.clear()
                st.rerun()

    with tab2:
        st.warning(f"🗓️ Dernière insp. : {row['Derniere_Inspection']}")
        with st.form("insp_form"):
            res_insp = st.radio("Résultat", ["✅ PASS", "⚠️ À SURVEILLER", "❌ FAIL"], horizontal=True)
            obs = st.text_area("Observations")
            photo = st.camera_input("Photo")
            
            if st.form_submit_button("Enregistrer l'inspection", type="primary", use_container_width=True):
                photo_b64 = ""
                if photo:
                    img = Image.open(photo); img.thumbnail((400, 400))
                    buf = io.BytesIO(); img.save(buf, format="JPEG", quality=70)
                    photo_b64 = base64.b64encode(buf.getvalue()).decode()
                
                payload = {
                    "Action": "INSPECTION", 
                    "Marque_Modele": item_nom, 
                    "No_Serie": selected_no_serie,
                    "Nouveau_Lieu": row['Emplacement_Actuel'],
                    "Derniere_Inspection": datetime.now().strftime("%Y-%m-%d"), 
                    "Inspecteur": MON_NOM,
                    "Resultat": res_insp, 
                    "Observations": obs, 
                    "Photo": photo_b64
                }
                requests.post(API_URL, json=payload)
                st.cache_data.clear()
                st.rerun()

    with tab3:
        st.subheader("Historique de l'item")
        # Filtrage des historiques par Marque_Modele OU No_Serie selon comment tu as rempli tes feuilles
        st.write("**Déplacements**")
        h_loc_item = data['h_loc'][data['h_loc']["Marque_Modele"].astype(str).isin([str(item_nom), str(selected_no_serie)])]
        st.dataframe(h_loc_item, hide_index=True, use_container_width=True)
        
        st.write("**Inspections**")
        h_insp_item = data['h_insp'][data['h_insp']["Marque_Modele"].astype(str).isin([str(item_nom), str(selected_no_serie)])]
        st.dataframe(h_insp_item, hide_index=True, use_container_width=True)

# --- DASHBOARD ---
st.divider()
st.subheader("📊 État de l'inventaire")
c1, c2, c3 = st.columns(3)
c1.metric("Total Items", len(df))
c2.metric("⚠️ À inspecter", len(df[df["Statut_Actuel"].str.contains("inspecter", case=False, na=False)]))
c3.metric("✅ En service", len(df[df["Statut_Actuel"].str.contains("service", case=False, na=False)]))