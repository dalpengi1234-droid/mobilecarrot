import streamlit as st
import pandas as pd
import urllib.parse
import json
import time
import concurrent.futures
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ===== 페이지 기본 설정 =====
st.set_page_config(page_title="모바일 당근 검색기", layout="wide")

# ===== Selenium 드라이버 설정 (서버/모바일 호환) =====
@st.cache_resource
def get_driver_options():
    options = Options()
    options.add_argument("--headless=new")  # 화면 없이 실행 (필수)
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--blink-settings=imagesEnabled=false") # 이미지 로딩 차단 (속도 향상)
    return options

def make_driver():
    options = get_driver_options()
    driver = webdriver.Chrome(options=options)
    return driver

# ===== 코드 검사 함수 =====
def check_code(code, keyword):
    driver = make_driver()
    enc = urllib.parse.quote(keyword)
    url = f"https://www.daangn.com/kr/buy-sell/?in={code}&only_on_sale=true&search={enc}"

    result = None
    try:
        driver.get(url)
        try:
            # 요소가 로딩될 때까지 최대 1.5초 대기
            WebDriverWait(driver, 1.5).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//*[contains(text(),"검색어를 수정하시거나") or '
                               'contains(text(),"검색 결과가 없습니다") or '
                               'contains(text(),"근처엔 없어요")]')
                )
            )
            result = ("none", code, url)
        except:
            # 위 문구가 안 뜨면 결과가 있는 것으로 간주
            result = ("found", code, url)
    except Exception as e:
        result = ("error", code, str(e))
    finally:
        driver.quit()

    return result

# ===== JSON 불러오기 =====
# 파일 위치가 바뀌어도 안전하도록 현재 파일(carrot1.py) 기준으로 경로 설정
BASE_DIR = Path(__file__).resolve().parent
json_path = BASE_DIR / "city_codes.json"

try:
    with open(json_path, "r", encoding="utf-8") as f:
        city_codes = json.load(f)
except FileNotFoundError:
    st.error(f"❌ city_codes.json 파일을 찾을 수 없습니다.\n경로: {json_path}")
    st.stop()

# ===== Streamlit UI 시작 =====
st.title("🥕 당근마켓 지역 검색 (모바일용)")

# ===== 세션 상태 초기화 =====
if "codes" not in st.session_state:
    st.session_state["codes"] = []
if "df" not in st.session_state:
    st.session_state["df"] = pd.DataFrame(columns=["지역코드", "URL"])
if "logs" not in st.session_state:
    st.session_state["logs"] = []
if "total" not in st.session_state:
    st.session_state["total"] = 0
if "done" not in st.session_state:
    st.session_state["done"] = False

# ===== 모바일 최적화 레이아웃 (탭 방식) =====
tab1, tab2 = st.tabs(["🔍 검색 설정", "📊 결과 및 링크"])

# ----- 탭 1: 검색 설정 -----
with tab1:
    search_keyword = st.text_input("검색어 입력", placeholder="예: 아이폰, 자전거, 나눔")
    
    # 시/도 선택
    selected_city = st.selectbox("검색할 지역(시/도) 선택", list(city_codes.keys()))
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        # 검색 시작 버튼
        if st.button(f"🚀 {selected_city} 검색 시작", use_container_width=True):
            if not search_keyword:
                st.warning("검색어를 먼저 입력해주세요!")
            else:
                st.session_state["codes"] = city_codes[selected_city].copy()
                st.session_state["total"] = len(city_codes[selected_city])
                st.session_state["logs"] = []
                st.session_state["done"] = False
                st.session_state["df"] = pd.DataFrame(columns=["지역코드", "URL"])
                st.rerun()
            
    with col_btn2:
        # 검색 중지 버튼
        if st.button("⏹️ 검색 중지", use_container_width=True):
            st.session_state["codes"] = []
            st.session_state["done"] = True
            st.warning("검색을 중지했습니다.")

    # 진행 상황 표시
    if st.session_state["total"] > 0:
        done_count = st.session_state["total"] - len(st.session_state["codes"])
        progress = done_count / st.session_state["total"]
        st.write(f"진행률: {int(progress*100)}% ({done_count}/{st.session_state['total']})")
        st.progress(progress)

    # 로그 (접었다 폈다 할 수 있음)
    with st.expander("📝 실시간 로그 확인 (클릭해서 열기)"):
        st.text("\n".join(st.session_state["logs"][-10:]))

# ----- 탭 2: 결과 및 링크 -----
with tab2:
    if not st.session_state["df"].empty:
        st.success(f"✅ 총 {len(st.session_state['df'])}개의 결과가 발견되었습니다!")
        
        # CSV 다운로드 버튼
        csv = st.session_state["df"].to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            "📥 결과 CSV 다운로드", 
            data=csv, 
            file_name="carrot_results.csv", 
            mime="text/csv", 
            use_container_width=True
        )

        st.divider()
        st.subheader("🔗 결과 바로가기")
        st.info("아래 박스를 클릭하면 당근마켓 페이지가 새 창으로 열립니다.")

        # 결과를 최신순(역순)으로 보여주기
        results = st.session_state["df"].to_dict("records")
        
        for item in reversed(results):
            # HTML을 이용한 카드 형태의 링크 버튼 생성
            link_html = f'''
            <a href="{item['URL']}" target="_blank" style="text-decoration:none;">
                <div style="
                    background-color: #f8f9fa; 
                    border: 1px solid #dee2e6; 
                    padding: 15px; 
                    border-radius: 12px; 
                    margin-bottom: 8px; 
                    color: #ff6f0f; 
                    font-weight: bold; 
                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                ">
                    🥕 {item['지역코드']}번 지역 매물 보러가기 ↗
                </div>
            </a>
            '''
            st.markdown(link_html, unsafe_allow_html=True)
            
    else:
        st.info("아직 검색된 결과가 없습니다. '검색 설정' 탭에서 검색을 시작해주세요.")

# ===== 백그라운드 크롤링 로직 =====
if st.session_state["codes"]:
    # 무료 클라우드 자원을 고려해 동시에 2개씩만 처리
    max_workers = 2 
    batch = []
    
    # 2개씩 꺼내오기
    for _ in range(min(max_workers, len(st.session_state["codes"]))):
        code = st.session_state["codes"].pop(0)
        batch.append(code)

    # 병렬 처리 실행
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(check_code, c, search_keyword) for c in batch]
        for f in concurrent.futures.as_completed(futures):
            status, code, info = f.result()
            
            if status == "found":
                st.session_state["logs"].append(f"✅ {code}번 지역: 발견!")
                new_row = pd.DataFrame([{"지역코드": code, "URL": info}])
                st.session_state["df"] = pd.concat([st.session_state["df"], new_row], ignore_index=True)
            elif status == "none":
                st.session_state["logs"].append(f"❌ {code}번 지역: 없음")
            else:
                st.session_state["logs"].append(f"⚠️ {code}번 지역: 에러 발생")

    # 너무 빠른 새로고침 방지
    time.sleep(0.1)
    st.rerun()

# 완료 메시지
elif not st.session_state["codes"] and st.session_state["total"] > 0 and not st.session_state["done"]:
    st.session_state["done"] = True
    st.success("🎉 모든 지역 검색이 완료되었습니다!")