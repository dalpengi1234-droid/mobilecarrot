import json
import time
import requests
import os
import urllib.parse
import random
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ==========================================
# 👇 [설정] 기본값
DEFAULT_KEYWORD = "아이폰"
DEFAULT_CITY = "서울특별시"
# ==========================================

# 깃허브 설정값 가져오기
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_ID = os.environ.get("TG_ID")
SEARCH_KEYWORD = os.environ.get("SEARCH_KEYWORD", DEFAULT_KEYWORD)
SEARCH_CITY = os.environ.get("SEARCH_CITY", DEFAULT_CITY)

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
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--blink-settings=imagesEnabled=false")
    return webdriver.Chrome(options=options)

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
        print("🌍 [전국] 대동여지도 모드: 대한민국의 모든 동네를 검색합니다.")
        for codes in city_codes.values():
            target_codes.extend(codes)
        # 순서는 섞어서 검색 (매번 같은 곳만 검색하는 것 방지)
        random.shuffle(target_codes)
        
    else:
        # 🏙️ [특정 도시] 모드
        target_codes = city_codes.get(SEARCH_CITY, [])
        if not target_codes:
            print(f"'{SEARCH_CITY}' 지역 코드를 찾을 수 없습니다.")
            return

    # 2. 기억 장치 불러오기
    seen_file = BASE_DIR / "seen.txt"
    seen_links = set()
    if seen_file.exists():
        with open(seen_file, "r", encoding="utf-8") as f:
            seen_links = set(f.read().splitlines())

    # 시작 알림
    total_cnt = len(target_codes)
    msg_start = f"🚀 [{SEARCH_CITY}] '{SEARCH_KEYWORD}' 검색 시작!\n(대상: 총 {total_cnt}개 지역)"
    print(msg_start)
    send_telegram(msg_start)
    
    driver = get_driver()
    new_found_count = 0
    current_seen_links = seen_links.copy()

    # 로그용 카운트
    count = 0

    for code in target_codes:
        count += 1
        enc = urllib.parse.quote(SEARCH_KEYWORD)
        url = f"https://www.daangn.com/kr/buy-sell/?in={code}&only_on_sale=true&search={enc}"
        
        try:
            driver.get(url)
            try:
                # 결과 확인 (로딩 대기)
                WebDriverWait(driver, 2).until(
                    EC.presence_of_element_located(
                        (By.XPATH, '//*[contains(text(),"검색어를 수정하시거나") or contains(text(),"검색 결과가 없습니다")]')
                    )
                )
            except:
                # 결과 발견!
                if url not in seen_links:
                    print(f"✨ 발견: {code}번 지역")
                    send_telegram(f"🔥 [{SEARCH_KEYWORD}] 발견!\n지역코드: {code}\n\n👇 바로가기:\n{url}")
                    current_seen_links.add(url)
                    new_found_count += 1
        except Exception as e:
            print(f"에러: {e}")
        
        # 100개 검색할 때마다 생존 신고 (로그 확인용)
        if count % 100 == 0:
            print(f"🏃 진행 중... ({count}/{total_cnt})")
            
        time.sleep(1) # 차단 방지

    driver.quit()

    # 결과 저장 및 종료 알림
    if new_found_count > 0:
        with open(seen_file, "w", encoding="utf-8") as f:
            f.write("\n".join(current_seen_links))
        send_telegram(f"🏁 [{SEARCH_CITY}] 검색 종료! 총 {new_found_count}개의 매물을 찾았습니다.")
    else:
        send_telegram(f"🏁 [{SEARCH_CITY}] 검색 종료. (새로운 매물 없음)")

if __name__ == "__main__":
    main()