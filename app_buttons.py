import streamlit as st
import os
import time
import pandas as pd
import re
import unicodedata
import requests
from datetime import datetime
from rapidfuzz import process, fuzz

# --- VISIT COUNTER LOGIC ---
COUNTER_FILE = "counter.txt"
if not os.path.exists(COUNTER_FILE):
    with open(COUNTER_FILE, "w", encoding="utf-8") as f:
        f.write("0")

if "tracked_visit" not in st.session_state:
    st.session_state.tracked_visit = True
    with open(COUNTER_FILE, "r", encoding="utf-8") as f:
        current_count = int(f.read().strip())
    new_count = current_count + 1
    with open(COUNTER_FILE, "w", encoding="utf-8") as f:
        f.write(str(new_count))

# --- INITIALIZE SESSION STATE FOR THE TREE ---
if "current_category" not in st.session_state:
    st.session_state.current_category = "main"

# 1. Page Config
st.set_page_config(page_title="Wine Lover Assistant", page_icon="🍷")
st.title("🤖 Hola Wine Lover! 🍷")

# 2. Define URL and Load Data
SHEET_URL = "https://docs.google.com/spreadsheets/d/1gmbRsVb661CpWevHOMue5rjqo9jAAJbpMcYUj6DGl8w/edit?usp=sharing"

def get_csv_url(url):
    try:
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
        if match:
            sheet_id = match.group(1)
            return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=FAQs"
    except:
        pass
    return None

CSV_URL = get_csv_url(SHEET_URL)

def clean_string(text):
    text = str(text).lower().strip()
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

@st.cache_data(ttl=10)
def load_faqs_tree():
    fallback_df = pd.DataFrame([
        {"category": "main", "question": "🍇 Search by Vineyard", "answer": "TREE_NODE"},
        {"category": "Search by Vineyard", "question": "Viña Concha y Toro", "answer": "Vinos: Casillero del Diablo."}
    ])
    if not CSV_URL:
        return fallback_df
    try:
        df = pd.read_csv(CSV_URL, storage_options={"timeout": 5})
        df.columns = [str(col).strip().lower() for col in df.columns]
        
        # Ensure all three necessary columns exist
        if 'category' in df.columns and 'question' in df.columns and 'answer' in df.columns:
            return df.dropna(subset=['category', 'question'])
        return fallback_df
    except:
        return fallback_df

# Load the master DataFrame from the sheet
df_faqs = load_faqs_tree()

# 3. Create Chat History
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "👋 Estoy acá para ayudarte! Explora las opciones de abajo o hazme una pregunta directamente."}
    ]

if "waiting_for_email" not in st.session_state:
    st.session_state.waiting_for_email = None

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 4. PREDEFINED BUTTONS INTERFACE (DYNAMIC TREE)
st.write("---") 
st.write(f"💡 **Explore Options ({st.session_state.current_category}):**")

button_pressed = None

if not st.session_state.waiting_for_email:
    # Render Back Button if deep inside tree
    if st.session_state.current_category != "main":
        if st.button("⬅️ Volver al Menú Principal", use_container_width=True):
            st.session_state.current_category = "main"
            st.rerun()

    # Filter spreadsheet rows matching the active session category
    current_rows = df_faqs[df_faqs['category'].apply(clean_string) == clean_string(st.session_state.current_category)]
    questions_list = current_rows['question'].tolist()
    
    max_buttons_per_row = 3
    for i in range(0, len(questions_list), max_buttons_per_row):
        row_questions = questions_list[i : i + max_buttons_per_row]
        cols = st.columns(len(row_questions))
        for idx, question in enumerate(row_questions):
            with cols[idx]:
                if st.button(question, key=f"btn_{st.session_state.current_category}_{i+idx}", use_container_width=True):
                    # Check if this question is a parent category node (has sub-items)
                    cleaned_q = clean_string(question)
                    is_parent = df_faqs['category'].apply(clean_string).eq(cleaned_q).any()
                    
                    if is_parent:
                        # SILENT SWAP: Shift the view to the sub-category and rerun instantly
                        st.session_state.current_category = question
                        st.rerun()
                    else:
                        # REGULAR QUESTION: Send to the chat room
                        button_pressed = question
                        
    st.write("")
    if st.button("✨ Quiero más info & Updates de próximos eventos", key="btn_more_info", use_container_width=True):
        button_pressed = "more info"

# 5. CHAT LOGIC
st.write("---")
st.write("💬 **Chat Room:**")
placeholder_text = "Type your email here..." if st.session_state.waiting_for_email else "Type your question here..."

with st.form(key="chat_form", clear_on_submit=True):
    chat_cols = st.columns([4, 1])
    with chat_cols[0]:
        user_typed_input = st.text_input("", placeholder=placeholder_text, label_visibility="collapsed")
    with chat_cols[1]:
        submit_button = st.form_submit_button(label="Send", use_container_width=True)

final_input = None
if button_pressed:
    final_input = button_pressed
elif submit_button and user_typed_input:
    final_input = user_typed_input

if final_input:
    st.session_state.messages.append({"role": "user", "content": final_input})
    
    if st.session_state.waiting_for_email:
        user_email = final_input.strip()
        unanswered_question = st.session_state.waiting_for_email
        
        # Google Form Integration
        FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScWL62CTOoP_dRlw_XhU2Wgd6IdA9P6vhmvXRT5XXG3HiUNNg/formResponsee" # Replace with your real URL
        form_data = {
            "entry.1621915346": user_email,          # Replace with your Email ID
            "entry.409076594": unanswered_question   # Replace with your Question ID
        }
        try:
            requests.post(FORM_URL, data=form_data, timeout=5)
        except:
            with open("leads_log.txt", "a", encoding="utf-8") as f:
                f.write(f"Date: {datetime.now()} | Email: {user_email} | Question: {unanswered_question} (Form Fail)\n")
            
        bot_response = "Gracias! Nos contactaremos contigo, que disfrutes la feria."
        st.session_state.waiting_for_email = None

    else:
        clean_input = clean_string(final_input)
        
        if "more info" in clean_input or clean_input == "info":
            bot_response = "Con gusto te enviaremos más info! Por favor, déjanos tu email abajo y nos contactaremos."
            st.session_state.waiting_for_email = "Requested General More Info"
                
        else:
            # Flatten questions from across the entire sheet for open typing match matching
            all_questions = df_faqs['question'].tolist()
            best_match = process.extractOne(clean_input, [clean_string(q) for q in all_questions], scorer=fuzz.WRatio, score_cutoff=60)
                    
            if best_match:
                matched_index = best_match[2]
                bot_response = df_faqs.iloc[matched_index]['answer']
            else:
                bot_response = f"Ups, no tengo respuesta para '{final_input}', pero si me dejas tu email trataremos de responderte a la brevedad!"
                st.session_state.waiting_for_email = final_input

    st.session_state.messages.append({"role": "assistant", "content": bot_response})
    st.rerun()

# 6. SECRET ADMIN PANEL
st.write("---")
with st.expander("🔒 Admin Panel (Leads & Stats)"):
    password = st.text_input("Enter Admin Password:", type="password")
    if password == "mysecret123":
        with open(COUNTER_FILE, "r", encoding="utf-8") as f:
            total_visits = f.read().strip()
        st.write(f"📈 **Total Website Visits:** `{total_visits}`")
