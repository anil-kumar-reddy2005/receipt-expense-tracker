from google import genai
from google.genai import types
import streamlit as st
from prompts import SYSTEM_PROMPT,WELCOME_MESSAGE_TEMPLATE,SUMMARY_REQUEST_PROMPT
Gemini_Api_key=st.secrets["Gemini_Api_key"]
@st.cache_resource
def get_gemini_client():
    return genai.Client(api_key=Gemini_Api_key)
gemini_client=get_gemini_client()
st.title("MacroSnap 🥗")
st.caption("Snap it.Track it. Text yourself the results.")

#step 1:onboarding (username and phone)

if 'onboarded' not in st.session_state:
    st.title("MacroSnap 🥗")
    with st.form("onboarding_form"):
        name = st.text_input("Your name")
        whatsapp_number = st.text_input(
            "WhatsApp number (with country code)",
            placeholder="+91XXXXXXXXXX",
        )
        if submitted:
            if not name.strip() or not whatsapp_number.strip():
                st.warning("Please fill in both your name and Whatsapp_number")
            else:
                st.session_state.name=name.strip()
                st.session_state.whatsapp_number=whatsapp_number.strip()
                st.session_state.chat = gemini_client.chats.create(
                model=MODEL_NAME,
                config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
            )
            st.session_state.messages = []
            st.session_state.onboarded = True
            st.rerun()
    st.stop()

#Create a chat Interface       