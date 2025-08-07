import streamlit as st
from supabase import create_client, Client
import supabase
from dotenv import load_dotenv
import os
import time
import streamlit.components.v1 as components
import requests
import urllib
import uuid
from google.oauth2 import id_token
from google.auth.transport import requests as grequests

st.set_page_config(layout="wide")

load_dotenv()

# 구글 OAuth2 환경변수
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8501")
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPE = "openid email profile"

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')

supabase: Client = create_client(url, key)

def get_messages():
    response = supabase.table('messages').select('*').execute()
    return response.data

def add_message(task, name=None):
    data = {'text': task}
    if name:
        data['name'] = name
    supabase.table('messages').insert(data).execute()

def delete_all_messages():
    supabase.table('messages').delete().neq('id', 0).execute()

# 구글 OAuth2 인증 URL 생성
def construct_auth_url(state):
    params = {
        'response_type': 'code',
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'scope': GOOGLE_SCOPE,
        'state': state,
        'access_type': 'offline',
        'prompt': 'consent',
    }
    return GOOGLE_AUTHORIZE_URL + '?' + urllib.parse.urlencode(params)

# 인증 코드로 토큰 교환
def exchange_code_for_token(code):
    data = {
        'code': code,
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'grant_type': 'authorization_code',
    }
    response = requests.post(GOOGLE_TOKEN_URL, data=data)
    return response.json()

# 토큰으로 사용자 정보 가져오기
def get_user_info(id_token_str):
    try:
        idinfo = id_token.verify_oauth2_token(id_token_str, grequests.Request(), GOOGLE_CLIENT_ID)
        return idinfo
    except Exception as e:
        st.error(f"토큰 검증 실패: {e}")
        return None

# 소셜 로그인 영역
st.subheader('Google 소셜 로그인')
if "oauth_state" not in st.session_state:
    st.session_state["oauth_state"] = uuid.uuid4().hex

query_params = st.query_params

# 인증 코드 처리 중복 방지 플래그
if "processing_code" not in st.session_state:
    st.session_state["processing_code"] = False

if "code" in query_params and not st.session_state["processing_code"]:
    code = query_params.get("code")
    if isinstance(code, list):
        code = code[0]
    st.session_state["processing_code"] = True  # 중복 처리 방지
    token_data = exchange_code_for_token(code)
    st.session_state["google_token"] = token_data
    # 사용자 정보 저장
    if "id_token" in token_data:
        userinfo = get_user_info(token_data["id_token"])
        st.session_state["google_userinfo"] = userinfo
    st.success("구글 로그인 성공!")
    st.query_params.clear()  # URL 파라미터 제거
    st.rerun()
elif "google_token" in st.session_state and "google_userinfo" in st.session_state:
    userinfo = st.session_state["google_userinfo"]
    st.success(f"로그인됨: {userinfo.get('name', '사용자')} ({userinfo.get('email', '')})")
    if st.button("로그아웃"):
        del st.session_state["google_token"]
        del st.session_state["google_userinfo"]
        st.session_state["processing_code"] = False
        st.success("로그아웃 되었습니다.")
        st.rerun()
else:
    if st.button("구글로 로그인"):
        auth_url = construct_auth_url(st.session_state["oauth_state"])
        st.markdown(f'<meta http-equiv="refresh" content="0; url={auth_url}">', unsafe_allow_html=True)

#streamlit 구성
st.title('채팅')

if st.button("💥 전체 메시지 삭제"):
    delete_all_messages()
    st.success("모든 메시지가 삭제되었습니다.")
    st.rerun()

# 메시지 입력 시 로그인 사용자 이름 전달
# 채팅 입력창: 로그인한 사용자만 입력 가능, name이 없으면 email 또는 '익명' 사용
if "google_userinfo" in st.session_state:
    userinfo = st.session_state["google_userinfo"]
    user_name = userinfo.get("name") or userinfo.get("email") or "익명"
    prompt = st.chat_input(f"{user_name}님, 메시지를 입력하세요.")
    if prompt:
        add_message(prompt, user_name)
else:
    st.info("구글 로그인 후 채팅을 입력할 수 있습니다.")
    prompt = None

# 메시지 표시 시 이름도 함께 출력
messages = get_messages()
if messages:
    chat_html = """
<style>
.scroll-box {
    min-width: 0;
    width: 100%;
    max-width: 100%;
    margin: 0 auto;
    padding: 10px;
    max-height: 600px;
    overflow-y: auto;
    border: 1px solid #eee;
    border-radius: 8px;
    background: #fafafa;
    box-sizing: border-box;
}
.chat-message {
    margin-bottom: 10px;
    padding: 8px 12px;
    background: #e6f0ff;
    border-radius: 6px;
    word-break: break-word;
    width: fit-content;
    max-width: 90%;
}
</style>
<div class="scroll-box" id="chatbox">
"""
    # 현재 로그인한 사용자 정보
    current_user_email = None
    if "google_userinfo" in st.session_state:
        current_user_email = st.session_state["google_userinfo"].get("email")
    
    for message in messages:
        name = message.get("name")
        text = message.get("text")
        # 현재 사용자가 작성한 메시지인지 확인
        if name and current_user_email:
            display_name = name + "(나)"
        elif name:
            display_name = name
        else:
            display_name = "익명"
        
        if display_name == "(나)":
            chat_html += f'<div class="chat-message"><b>{display_name}</b>: {text}</div>'
        else:
            chat_html += f'<div class="chat-message"><b>{display_name}</b>: {text}</div>'
    chat_html += """
    </div>
    <script>
    const chatbox = document.getElementById('chatbox');
    if (chatbox) { chatbox.scrollTop = chatbox.scrollHeight; }
    </script>
    """
    components.html(chat_html, height=600, width=1920)
else:
    st.write('아무 메세지도 없습니다.')
time.sleep(1)
st.rerun()

