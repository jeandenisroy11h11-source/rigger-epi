import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import base64
from PIL import Image
import io

# --- CONFIGURATION ---
API_URL = "https://script.google.com/macros/s/AKfycbzKcjaspmJPPAuTfV5KJ1nJOuG4MeQICEtAk1nTV8wS5H67vpNhDnBWVwAhJx3d7egXJQ/exec"
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
    df_inv = df_inv.loc[:, df_inv.columns.str.len() > 0]
    df_inv = df_inv.loc[:, ~df_inv.columns.str.contains('^Unnamed')]
    
    # Sécurité pour les nouvelles colonnes
    for col in ["No_Serie", "UID_NFC"]:
        if col not in df_inv.columns:
            df_inv[col] = ""

    df_inv = df_inv[df_inv["Marque_Modele"].astype(str).str.strip() != ""]
    
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

# --- INITIALISATION SESSION STATE (POUR LE BULK) ---
if "bulk_list" not in st.session_state:
    st.session_state.bulk_list = []

# --- BARRE LATÉRALE (AJOUT ITEM) ---
with st.sidebar:
    st.header("➕ Nouvel Item")
    with st.form("add_item", clear_on_submit=True):
        n_id = st.text_input("Marque / Modèle")
        n_serie = st.text_input("No Série")
        n_uid = st.text_input("UID NFC (Optionnel)")
        n_cat = st.selectbox("Catégorie", data['categories'])
        n_lieu = st.selectbox("Lieu initial", data['lieux'])
        if st.form_submit_button("Créer l'item", use_container_width=True):
            payload = {"Action": "AJOUT_ITEM", "No_Serie": n_serie, "Marque_Modele": n_id, 
                       "Categorie": n_cat, "Date_Achat": str(datetime.now().date()), 
                       "Duree_Vie_Ans": 10, "Nouveau_Lieu": n_lieu, "UID_NFC": n_uid}
            requests.post(API_URL, json=payload)
            st.cache_data.clear()
            st.rerun()

# --- INTERFACE PRINCIPALE ---
st.title("🛠️ Gestion EPI - JD")

# --- SECTION 1 : MODE BULK (L'idée géniale) ---
with st.expander("🛒 MODE BULK / PRÉPARATION DE KIT", expanded=len(st.session_state.bulk_list) > 0):
    st.write("Scannez ou entrez les UID/No Série pour les ajouter à la liste d'envoi.")
    
    c1, c2 = st.columns([3, 1])
    with c1:
        input_scan = st.text_input("Entrer UID ou No Série", key="bulk_input", label_visibility="collapsed", placeholder="Scanner ici...")
    with c2:
        if st.button("Ajouter", use_container_width=True) or (input_scan and len(input_scan) > 5):
            # Chercher dans No_Serie OU UID_NFC
            match = df[(df["No_Serie"] == input_scan) | (df["UID_NFC"] == input_scan)]
            if not match.empty:
                item_data = match.iloc[0].to_dict()
                if item_data["No_Serie"] not in [x["No_Serie"] for x in st.session_state.bulk_list]:
                    st.session_state.bulk_list.append(item_data)
                    st.toast(f"Ajouté : {item_data['Marque_Modele']}", icon="✅")
            else:
                st.error("Item non trouvé.")

    if st.session_state.bulk_list:
        st.write("---")
        for i, item in enumerate(st.session_state.bulk_list):
            st.text(f"• {item['Marque_Modele']} ({item['No_Serie']})")
        
        st.write("---")
        dest_bulk = st.selectbox("Destination pour tout le kit", data['lieux'], key="dest_bulk")
        
        col_b1, col_b2 = st.columns(2)
        if col_b1.button("Vider la liste", use_container_width=True):
            st.session_state.bulk_list = []
            st.rerun()
            
        if col_b2.button("DÉPLACER TOUT LE KIT", type="primary", use_container_width=True):
            with st.spinner("Mise à jour de l'inventaire..."):
                for item in st.session_state.bulk_list:
                    payload = {"Action": "MOUVEMENT", "No_Serie": item["No_Serie"], 
                               "Marque_Modele": item["Marque_Modele"], "Ancien_Lieu": item['Emplacement_Actuel'],
                               "Nouveau_Lieu": dest_bulk, "Inspecteur": MON_NOM}
                    requests.post(API_URL, json=payload)
            st.success(f"Kit déplacé vers {dest_bulk} !")
            st.session_state.bulk_list = []
            st.cache_data.clear()
            st.rerun()

# --- SECTION 2 : ACTION UNITAIRE ---
st.markdown("---")
df["Label"] = df["No_Serie"].astype(str) + " | " + df["Marque_Modele"].astype(str)
selected_sn = st.selectbox("Ou sélectionner un item précis", df["No_Serie"].tolist(), 
                           format_func=lambda x: df[df["No_Serie"] == x]["Label"].iloc[0])

if selected_sn:
    row = df[df["No_Serie"] == selected_sn].iloc[0]
    tab1, tab2, tab3 = st.tabs(["📦 Mouvement", "📋 Inspection", "📜 Historique"])

    with tab1:
        st.info(f"📍 Lieu actuel : **{row['Emplacement_Actuel']}**")
        with st.form("move_one"):
            d = st.selectbox("Destination", data['lieux'])
            if st.form_submit_button("Confirmer", type="primary", use_container_width=True):
                requests.post(API_URL, json={"Action": "MOUVEMENT", "No_Serie": selected_sn, "Marque_Modele": row["Marque_Modele"],
                                           "Ancien_Lieu": row['Emplacement_Actuel'], "Nouveau_Lieu": d, "Inspecteur": MON_NOM})
                st.cache_data.clear()
                st.rerun()

    with tab2:
        with st.form("insp_one"):
            res = st.radio("Résultat", ["✅ PASS", "⚠️ À SURVEILLER", "❌ FAIL"], horizontal=True)
            obs = st.text_area("Observations")
            if st.form_submit_button("Enregistrer l'inspection", type="primary", use_container_width=True):
                requests.post(API_URL, json={"Action": "INSPECTION", "No_Serie": selected_sn, "Marque_Modele": row["Marque_Modele"],
                                           "Derniere_Inspection": datetime.now().strftime("%Y-%m-%d"), "Inspecteur": MON_NOM,
                                           "Resultat": res, "Observations": obs, "Nouveau_Lieu": row["Emplacement_Actuel"]})
                st.cache_data.clear()
                st.rerun()

    with tab3:
        st.dataframe(data['h_loc'][data['h_loc']["No_Serie"].astype(str) == str(selected_sn)], hide_index=True)
        st.dataframe(data['h_insp'][data['h_insp']["No_Serie"].astype(str) == str(selected_sn)], hide_index=True)

# --- SECTION 3 : DASHBOARD / FILTRES (BAS DE PAGE) ---
st.markdown("---")
st.header("📊 Inventaire Complet")
cat_filter = st.multiselect("Filtrer par Catégorie", options=sorted(df["Categorie"].unique().tolist()))
df_filtered = df[df["Categorie"].isin(cat_filter)] if cat_filter else df

m1, m2, m3 = st.columns(3)
m1.metric("Items", len(df_filtered))
m2.metric("⚠️ Inspections", len(df_filtered[df_filtered["Statut_Actuel"].str.contains("inspecter", case=False, na=False)]))
m3.metric("✅ En service", len(df_filtered[df_filtered["Statut_Actuel"].str.contains("service", case=False, na=False)]))

st.dataframe(df_filtered.drop(columns=["Label", "UID_NFC"], errors="ignore"), hide_index=True, use_container_width=True)