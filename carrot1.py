import streamlit as st
import pandas as pd
import urllib.parse
import json
import time
import requests # 텔레그램용
import concurrent.futures
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ===== 페이지 설정 =====
st.set_page_config(page_title="당근 실시간 알림", layout="wide", page_icon="🥕")

# ===== 텔레그램 전송 함수 =====
def send_telegram_msg(token, chat_id, msg):
    if token and chat_id:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = {"chat_id": chat_id, "text": msg}
            requests.post(url, data=data)
        except:
            pass

# ===== Selenium 설정 =====
@st.cache_resource
def get_driver_options():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--blink-settings=imagesEnabled=false")
    return options

def make_driver():
    options = get_driver_options()
    driver = webdriver.Chrome(options=options)
    return driver

# ===== 크롤링 로직 =====
def check_code(code, keyword):
    driver = make_driver()
    enc = urllib.parse.quote(keyword)
    url = f"https://www.daangn.com/kr/buy-sell/?in={code}&only_on_sale=true&search={enc}"
    result = None
    try:
        driver.get(url)
        try:
            WebDriverWait(driver, 1.5).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//*[contains(text(),"검색어를 수정하시거나") or contains(text(),"검색 결과가 없습니다") or contains(text(),"근처엔 없어요")]')
                )
            )
            result = ("none", code, url)
        except:
            result = ("found", code, url)
    except Exception as e:
        result = ("error", code, str(e))
    finally:
        driver.quit()
    return result

# ===== 데이터 로드 =====
BASE_DIR = Path(__file__).resolve().parent
json_path = BASE_DIR / "city_codes.json"
try:
    with open(json_path, "r", encoding="utf-8") as f:
        city_codes = json.load(f)
except:
    st.error("city_codes.json 파일이 없습니다.")
    st.stop()

# ===== 상태 초기화 =====
if "codes" not in st.session_state: st.session_state["codes"] = []
if "results" not in st.session_state: st.session_state["results"] = []
if "total" not in st.session_state: st.session_state["total"] = 0
if "done" not in st.session_state: st.session_state["done"] = False
if "is_running" not in st.session_state: st.session_state["is_running"] = False

# ===== 사이드바: 텔레그램 설정 =====
with st.sidebar:
    st.header("📲 알림 설정")
    tg_token = st.text_input("봇 토큰 (Bot Token)", type="password")
    tg_id = st.text_input("내 아이디 (Chat ID)")
    st.caption("입력하면 발견 즉시 메시지를 보냅니다.")

# ===== 메인 UI =====
st.title("🥕 당근마켓 실시간 알리미")
st.markdown("검색 버튼을 누르면 하나씩 찾아서 **화면**과 **텔레그램**으로 알려줍니다.")

# 검색창
with st.container():
    col1, col2, col3 = st.columns([2, 1, 1])
    search_keyword = col1.text_input("키워드", placeholder="예: 아이폰, 자전거")
    selected_city = col2.selectbox("지역", list(city_codes.keys()))
    
    # 버튼 동작
    if col3.button("🚀 검색 시작", use_container_width=True):
        if search_keyword:
            st.session_state["codes"] = city_codes[selected_city].copy()
            st.session_state["total"] = len(city_codes[selected_city])
            st.session_state["results"] = []
            st.session_state["done"] = False
            st.session_state["is_running"] = True
            
            # 시작 알림
            send_telegram_msg(tg_token, tg_id, f"🚀 [{selected_city}] '{search_keyword}' 검색을 시작합니다!")
            st.rerun()

    if st.session_state["is_running"]:
        if st.button("⏹️ 중지", use_container_width=True):
            st.session_state["codes"] = []
            st.session_state["done"] = True
            st.session_state["is_running"] = False
            send_telegram_msg(tg_token, tg_id, "⏹️ 검색을 중지했습니다.")
            st.rerun()

# 진행률
if st.session_state["total"] > 0:
    remain = len(st.session_state["codes"])
    done = st.session_state["total"] - remain
    prog = done / st.session_state["total"]
    st.progress(prog, text=f"검색 중... ({done}/{st.session_state['total']})")

# 결과 화면 (최신순)
for item in reversed(st.session_state["results"]):
    st.success(f"✅ **{item['code']}번 지역 발견!** [바로가기]({item['url']})")

# ===== 백그라운드 작업 =====
if st.session_state["codes"]:
    # 텔레그램 전송 속도를 위해 1개씩 처리 권장 (너무 빠르면 차단될 수 있음)
    code = st.session_state["codes"].pop(0)
    
    # 검색 수행
    status, code_res, info = check_code(code, search_keyword)
    
    if status == "found":
        # 1. 화면에 추가
        st.session_state["results"].append({"code": code_res, "url": info})
        
        # 2. 텔레그램 전송 (핵심!)
        msg = f"🥕 심봤다! [{code_res}번 지역]\n키워드: {search_keyword}\n\n👇 바로가기:\n{info}"
        send_telegram_msg(tg_token, tg_id, msg)
        
    # 자동 새로고침 (다음 지역 검색)
    time.sleep(0.1)
    st.rerun()

elif not st.session_state["codes"] and st.session_state["is_running"]:
    st.session_state["done"] = True
    st.session_state["is_running"] = False
    send_telegram_msg(tg_token, tg_id, "🏁 모든 지역 검색이 끝났습니다!")
    st.success("검색 완료!")