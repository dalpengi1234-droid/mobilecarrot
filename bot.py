import json
import time
import requests
import os
import urllib.parse
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ==========================================
# 👇 [설정] 속도 조절
# ⚠️ 경고: 5개 이상으로 올리면 서버가 터질(OOM) 확률이 매우 높습니다.
MAX_WORKERS = 10  
DEFAULT_KEYWORD = "풀카운트"
DEFAULT_CITY = "서울특별시"
# ==========================================

# 깃허브 설정값 가져오기
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_ID = os.environ.get("TG_ID")
SEARCH_KEYWORD = os.environ.get("SEARCH_KEYWORD", DEFAULT_KEYWORD)
SEARCH_CITY = os.environ.get("SEARCH_CITY", DEFAULT_CITY)

# 데이터 충돌 방지를 위한 잠금 장치
lock = threading.Lock()

def send_telegram(msg):
    if TG_TOKEN and TG_ID:
        try:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
            data = {"chat_id": TG_ID, "text": msg}
            requests.post(url, data=data)
        except Exception as e:
            print(f"텔레그램 전송 실패: {e}")

def get_driver():
    options = Options()
    options.add_argument("--headless=new") # 화면 없이 실행
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage") # 메모리 공유 비활성화 (서버 멈춤 방지)
    options.add_argument("--disable-gpu")
    options.add_argument("--blink-settings=imagesEnabled=false") # 이미지 로딩 차단 (속도 향상)
    return webdriver.Chrome(options=options)

def check_region(code, keyword, seen_links, found_items):
    """
    하나의 지역을 검사하고 브라우저를 닫는 함수 (일꾼 1명의 업무)
    """
    driver = get_driver()
    enc = urllib.parse.quote(keyword)
    url = f"https://www.daangn.com/kr/buy-sell/?in={code}&only_on_sale=true&search={enc}"
    
    found_info = None

    try:
        driver.get(url)
        try:
            # 2초 안에 결과가 뜨는지 확인
            WebDriverWait(driver, 2).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//*[contains(text(),"검색어를 수정하시거나") or contains(text(),"검색 결과가 없습니다")]')
                )
            )
        except:
            # "없습니다" 문구가 안 떴다면 -> 매물이 있다는 뜻!
            # 중복 확인 (Thread-safe 하게 접근)
            is_new = False
            with lock:
                if url not in seen_links:
                    is_new = True
            
            if is_new:
                found_info = (code, url)
                
    except Exception:
        pass # 에러 나면 그냥 넘어감 (속도 위해)
    
    finally:
        driver.quit() # 메모리 확보를 위해 칼같이 종료

    return found_info

def main():
    BASE_DIR = Path(__file__).resolve().parent
    
    # 1. 지역 코드 불러오기
    try:
        with open(BASE_DIR / "city_codes.json", "r", encoding="utf-8") as f:
            city_codes = json.load(f)
    except FileNotFoundError:
        print("city_codes.json 파일을 찾을 수 없습니다.")
        return

    # 🌍 [지역 선택 로직]
    target_codes = []
    
    if SEARCH_CITY == "전국":
        print("🌍 [전국] 초고속 모드: 전국의 모든 동네를 병렬 검색합니다.")
        for codes in city_codes.values():
            target_codes.extend(codes)
        random.shuffle(target_codes)
    else:
        target_codes = city_codes.get(SEARCH_CITY, [])
        if not target_codes:
            print(f"'{SEARCH_CITY}' 코드를 찾을 수 없습니다.")
            return
        print(f"🏙️ [{SEARCH_CITY}] 병렬 검색 모드 (총 {len(target_codes)}개 동네)")

    # 2. 기억 장치 불러오기
    seen_file = BASE_DIR / "seen.txt"
    seen_links = set()
    if seen_file.exists():
        with open(seen_file, "r", encoding="utf-8") as f:
            seen_links = set(f.read().splitlines())

    # 시작 알림
    total_cnt = len(target_codes)
    msg_start = f"🚀 [{SEARCH_CITY}] '{SEARCH_KEYWORD}' {MAX_WORKERS}배속 검색 시작! (대상: {total_cnt}곳)"
    print(msg_start)
    send_telegram(msg_start)
    
    new_items = []
    processed_count = 0
    
    # ⚡ [핵심] 멀티스레딩 (병렬 처리) 시작
    print(f"⚡ 일꾼 {MAX_WORKERS}명이 동시에 작업을 시작합니다...")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 일감(동네) 분배
        future_to_code = {executor.submit(check_region, code, SEARCH_KEYWORD, seen_links, new_items): code for code in target_codes}
        
        for future in as_completed(future_to_code):
            processed_count += 1
            result = future.result()
            
            # 결과가 있으면 처리
            if result:
                code, url = result
                print(f"✨ 발견: {code}번 지역")
                send_telegram(f"🔥 [{SEARCH_KEYWORD}] 발견!\n지역코드: {code}\n\n👇 바로가기:\n{url}")
                
                with lock:
                    seen_links.add(url)
                    new_items.append(url)

            # 진행 상황 표시 (20개마다)
            if processed_count % 20 == 0:
                print(f"🏃 {processed_count}/{total_cnt} 완료...")

    # 결과 저장
    if new_items:
        with open(seen_file, "w", encoding="utf-8") as f:
            f.write("\n".join(seen_links))
        send_telegram(f"🏁 [{SEARCH_CITY}] 검색 종료! 총 {len(new_items)}개 매물 발견.")
    else:
        send_telegram(f"🏁 [{SEARCH_CITY}] 검색 종료. (새로운 매물 없음)")

if __name__ == "__main__":
    main()