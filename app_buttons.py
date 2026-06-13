import streamlit as st
import os
import time
from datetime import datetime
from rapidfuzz import process, fuzz


# --- NEW VISIT COUNTER LOGIC ---
COUNTER_FILE = "counter.txt"

# Initialize the file if it doesn't exist
if not os.path.exists(COUNTER_FILE):
    with open(COUNTER_FILE, "w", encoding="utf-8") as f:
        f.write("0")

# Use Streamlit's session state to make sure refreshing the page 
# during the same chat session doesn't accidentally count as multiple visits
if "tracked_visit" not in st.session_state:
    st.session_state.tracked_visit = True
    # Read current count
    with open(COUNTER_FILE, "r", encoding="utf-8") as f:
        current_count = int(f.read().strip())
    # Increase by 1
    new_count = current_count + 1
    # Save it back
    with open(COUNTER_FILE, "w", encoding="utf-8") as f:
        f.write(str(new_count))
# -------------------------------

# 1. Setup the website title & page config (Adds a nice browser tab icon)
st.set_page_config(page_title="Wine Lover Assistant", page_icon="🍷")
st.title("🤖 Hola Wine Lover! 🍷")

# 2. Define your automated questions and answers
import pandas as pd
import re

# --- LOAD FAQs FROM GOOGLE SHEETS ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1gmbRsVb661CpWevHOMue5rjqo9jAAJbpMcYUj6DGl8w/edit?usp=sharing"

def get_csv_url(url):
    try:
        # This extract pattern grabs the long ID safely regardless of URL arguments
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
        if match:
            sheet_id = match.group(1)
            # Explicitly points to the export endpoint for a tab named 'FAQs'
            return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=FAQs"
    except:
        pass
    return None

CSV_URL = get_csv_url(SHEET_URL)

@st.cache_data(ttl=10) # Set to 10 seconds for fast debugging!
def load_faqs_from_sheets():
    fallback_faqs = {
        "viña concha y toro": "Vinos disponibles: Casillero del Diablo, Don Melchor.",
        "viña san pedro": "Vinos disponibles: Castillo de Molina, Gato Negro."
    }
    
    if not CSV_URL:
        return fallback_faqs

    try:
        df = pd.read_csv(CSV_URL, storage_options={"timeout": 5})
        
        # 1. Clean the column names aggressively (lowercase, strip whitespace)
        df.columns = [str(col).strip().lower() for col in df.columns]
        
        # --- DEBUG HELPER ---
        # This will print the exact columns Python sees into your Streamlit logs
        # st.sidebar.write("Python detected columns:", list(df.columns))
        # --------------------

        # 2. Explicitly scan for the column names instead of column position
        q_col = None
        a_col = None
        
        for col in df.columns:
            if 'question' in col or 'pregunta' in col:
                q_col = col
            if 'answer' in col or 'respuesta' in col:
                a_col = col

        # 3. Fallback to positions only if explicit names aren't matched
        if not q_col and len(df.columns) > 0: q_col = df.columns[0]
        if not a_col and len(df.columns) > 1: a_col = df.columns[1]

        if q_col and a_col:
            # Drop any rows where the question or answer is completely blank (NaN)
            df = df.dropna(subset=[q_col, a_col])
            
            # Map them securely to strings
            return dict(zip(df[q_col].astype(str).str.strip(), df[a_col].astype(str).str.strip()))
        
        return fallback_faqs
    except Exception as e:
        return fallback_faqs

# Dynamically build your qa_pairs dictionary safely!
qa_pairs = load_faqs_from_sheets()
# ------------------------------------


# 3. Create the user chat history & Welcome Message
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "👋 Estoy acá para ayudarte! Abajo están las viñas presentes, si haces click en una, te diré qué vinos tienen hoy para que vayas a conocerlos, que disfrutes!"}
    ]

if "waiting_for_email" not in st.session_state:
    st.session_state.waiting_for_email = None

# Display past conversation history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 4. PREDEFINED BUTTONS INTERFACE
st.write("---") 
st.write("💡 **Quick Options:**")

# Initialize button_pressed at the very start of Section 4
button_pressed = None

# Only show buttons if we aren't in the middle of capturing an email
if not st.session_state.waiting_for_email:
    
    questions_list = list(qa_pairs.keys())
    max_buttons_per_row = 5
    
    # 1. First, loop through and display the main grid of questions
    for i in range(0, len(questions_list), max_buttons_per_row):
        row_questions = questions_list[i : i + max_buttons_per_row]
        cols = st.columns(len(row_questions))
        
        for idx, question in enumerate(row_questions):
            with cols[idx]:
                global_idx = i + idx
                if st.button(question, key=f"btn_{global_idx}", use_container_width=True):
                    button_pressed = question
                    
    st.write("") # Tiny spacer below the grid
    
    # 2. NOW render the prominent "More Info" button safely UNDER the list
    if st.button("✨ Quiero más info & Updates de próximos eventos", key="btn_more_info", use_container_width=True):
        button_pressed = "more info"

# =====================================================================
# 5. CHAT LOGIC (Using a standard layout box instead of a floating input)
# =====================================================================
st.write("---")
st.write("💬 **Chat Room:**")

# Create a clean side-by-side layout for typing and submitting
placeholder_text = "Type your email here..." if st.session_state.waiting_for_email else "Type your question here..."

# Form layout forces the text input box and send button to sit on a fixed row
with st.form(key="chat_form", clear_on_submit=True):
    chat_cols = st.columns([4, 1]) # 4 parts text box, 1 part button
    with chat_cols[0]:
        user_typed_input = st.text_input("", placeholder=placeholder_text, label_visibility="collapsed")
    with chat_cols[1]:
        submit_button = st.form_submit_button(label="Send", use_container_width=True)

# Determine what action triggered the message
final_input = None
if button_pressed:
    final_input = button_pressed
elif submit_button and user_typed_input:
    final_input = user_typed_input

if final_input:
    # Append user message to history
    st.session_state.messages.append({"role": "user", "content": final_input})
    
    # Process the bot response
    if st.session_state.waiting_for_email:
        user_email = final_input.strip()
        unanswered_question = st.session_state.waiting_for_email
        
        log_entry = f"Date: {datetime.now()} | Email: {user_email} | Question: {unanswered_question}\n"
        with open("leads_log.txt", "a", encoding="utf-8") as f:
            f.write(log_entry)
            
        bot_response = "Gracias! Nos contactaremos contigo, que disfrutes la feria."
        st.session_state.waiting_for_email = None

    # --- THIS IS THE UPDATED ACCENT-PROOF MATCHING BLOCK ---
    else:
        # Helper function to strip accents and special characters cleanly (e.g., ñ -> n, á -> a)
        import unicodedata
        def clean_string(text):
            text = str(text).lower().strip()
            text = ''.join(
                c for c in unicodedata.normalize('NFD', text)
                if unicodedata.category(c) != 'Mn'
            )
            return text

        # 1. Clean the user's input (whether typed or button clicked)
        clean_input = clean_string(final_input)
        
        # 2. Check if they clicked the button or typed "more info"
        if "more info" in clean_input or clean_input == "info":
            bot_response = "Con gusto te enviaremos más info! Por favor, déjanos tu email abajo y nos contactaremos."
            st.session_state.waiting_for_email = "Requested General More Info"
                
        else:
            # 3. Build a temporary dictionary with completely flattened/cleaned keys
            flat_qa_pairs = {clean_string(k): v for k, v in qa_pairs.items()}
            flat_questions = list(flat_qa_pairs.keys())
            
            # 4. Perform the fuzzy match on the cleaned lists
            best_match = process.extractOne(
                clean_input, 
                flat_questions, 
                scorer=fuzz.WRatio, 
                score_cutoff=60  # Lowered slightly to capture close matches perfectly
            )
                    
            if best_match:
                matched_flat_question = best_match[0]
                # Pull the original perfect answer string using our matched flat key
                bot_response = flat_qa_pairs[matched_flat_question]
            else:
                bot_response = f"Ups, no tengo respuesta para '{final_input}', pero si me dejas tu email trataremos de responderte a la brevedad!"
                st.session_state.waiting_for_email = final_input # Saves the exact weird question they asked

    st.session_state.messages.append({"role": "assistant", "content": bot_response})
    st.rerun()

# 6. SECRET ADMIN PANEL (With permanently tracked visits)
st.write("---")
with st.expander("🔒 Admin Panel (Leads & Stats)"):
    password = st.text_input("Enter Admin Password:", type="password")
    
    if password == "mysecret123":
        # Read the total visits to display
        with open(COUNTER_FILE, "r", encoding="utf-8") as f:
            total_visits = f.read().strip()
            
        # Display the stats in a nice badge layout
        st.write(f"📈 **Total Website Visits:** `{total_visits}`")
        st.write("---")
        
        if os.path.exists("leads_log.txt"):
            with open("leads_log.txt", "r", encoding="utf-8") as f:
                leads_data = f.read()
            
            st.text_area("Current Leads:", leads_data, height=200)
            
            st.download_button(
                label="📥 Download leads_log.txt",
                data=leads_data,
                file_name="leads_log.txt",
                mime="text/plain"
            )
        else:
            st.write("No leads collected yet!")
