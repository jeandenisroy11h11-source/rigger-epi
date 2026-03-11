import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import base64
from PIL import Image
import io

API_URL = "https://script.google.com/macros/s/AKfycbzzZvhMHJGVU267o7eIqHpmeI5z-ThItEXIbMjLg8c-7YxLvB4ryQ0fCXLEfpTEEsbDFQ/exec"
MON_NOM = "JD"

st.set_page_config(page_title="Rigger EPI - JD", layout="centered")

@st.cache_data(ttl=2)
def load_data():
    res = requests.get(API_URL)
    data = res.json()
    
    # 1. Création du DataFrame initial
    full_df = pd.DataFrame(data[1:], columns=data[0])
    
    # 2. SUPPRESSION DES COLONNES SANS NOM (doublons vides)
    # On ne garde que les colonnes dont le nom n'est pas vide et n'est pas None
    full_df = full_df.loc[:, [c for c in full_df.columns if c and not c.startswith('Unnamed')]]
    
    # 3. NETTOYAGE DES LIGNES : On ne garde que là où il y a un item
    return full_df[full_df["Marque_Modele"].str.strip() != ""]

df = load_data()

# --- RÉCUPÉRATION DES LISTES ---
# On récupère les lieux uniques déjà utilisés + une option vide
lieux_existants = sorted(df["Emplacement_Actuel"].unique().tolist())
categories = sorted(df["Categorie"].unique().tolist()) if "Categorie" in df.columns else []

st.title("🛠️ Gestion EPI - JD")

# --- DASHBOARD & FILTRES ---
with st.expander("📊 Aperçu de l'inventaire", expanded=False):
    # Sécurité pour les catégories
    if "Categorie" in df.columns:
        categories = sorted(df["Categorie"].unique().tolist())
        cat_filter = st.multiselect("Filtrer par catégorie", categories)
        temp_df = df[df["Categorie"].isin(cat_filter)] if cat_filter else df
    else:
        temp_df = df

    c1, c2, c3 = st.columns(3)
    c1.metric("Total", len(temp_df))
    # On gère le cas où "Statut_Actuel" pourrait avoir des espaces
    a_inspecter = len(temp_df[temp_df["Statut_Actuel"].str.contains("inspecter", case=False, na=False)])
    en_service = len(temp_df[temp_df["Statut_Actuel"].str.contains("service", case=False, na=False)])
    
    c1.metric("Total Items", len(temp_df))
    c2.metric("⚠️ À inspecter", a_inspecter)
    c3.metric("✅ En service", en_service)
    
    st.dataframe(temp_df, hide_index=True, use_container_width=True)

st.divider()

# --- SÉLECTION DE L'ITEM ---
item_list = df["Marque_Modele"].tolist()
selected_item = st.selectbox("Scanner / Choisir l'item", item_list, index=None, placeholder="En attente...")

if selected_item:
    row = df[df["Marque_Modele"] == selected_item].iloc[0]
    lieu_actuel = str(row["Emplacement_Actuel"])
    # NETTOYAGE DATE : on prend juste les 10 premiers caractères (AAAA-MM-JJ)
    derniere_insp_brute = str(row["Derniere_Inspection"])
    derniere_insp = derniere_insp_brute[:10] if len(derniere_insp_brute) >= 10 else "N/A"
    
    tab1, tab2 = st.tabs(["📦 Mouvement", "📋 Inspection"])

    with tab1:
        st.info(f"📍 Lieu actuel : **{lieu_actuel}**")
        with st.form("move_form"):
            mode_lieu = st.radio("Mode de destination", ["Liste existante", "Saisie manuelle"], horizontal=True)
            
            if mode_lieu == "Liste existante":
                dest = st.selectbox("Sélectionner le lieu", lieux_existants)
            else:
                dest = st.text_input("Saisir le nouveau lieu (ex: Location Client X)")
            
            if st.form_submit_button("Confirmer le transfert", type="primary", use_container_width=True):
                if dest:
                    payload = {
                        "Action": "MOUVEMENT",
                        "Marque_Modele": selected_item,
                        "Ancien_Lieu": lieu_actuel,
                        "Nouveau_Lieu": dest,
                        "Derniere_Inspection": derniere_insp,
                        "Inspecteur": MON_NOM
                    }
                    requests.post(API_URL, json=payload)
                    st.success(f"Déplacé vers {dest}")
                    st.cache_data.clear()
                    st.rerun()

    with tab2:
        st.warning(f"🗓️ Dernière insp. : {derniere_insp}")
        with st.form("insp_form"):
            resultat = st.radio("Résultat", ["✅ PASS", "⚠️ À SURVEILLER", "❌ FAIL"], horizontal=True)
            obs = st.text_area("Observations", placeholder="État général, hernies, usure...")
            photo_file = st.camera_input("Photo (Optionnel)")
            
            if st.form_submit_button("Enregistrer l'inspection", type="primary", use_container_width=True):
                photo_b64 = ""
                if photo_file:
                    img = Image.open(photo_file)
                    img.thumbnail((400, 400))
                    buffered = io.BytesIO()
                    img.save(buffered, format="JPEG", quality=70)
                    photo_b64 = base64.b64encode(buffered.getvalue()).decode()

                payload = {
                    "Action": "INSPECTION",
                    "Marque_Modele": selected_item,
                    "Nouveau_Lieu": lieu_actuel,
                    "Derniere_Inspection": datetime.now().strftime("%Y-%m-%d"),
                    "Inspecteur": MON_NOM,
                    "Resultat": resultat,
                    "Observations": obs,
                    "Photo": photo_b64
                }
                requests.post(API_URL, json=payload)
                st.success("Inspection enregistrée !")
                st.cache_data.clear()
                st.rerun()