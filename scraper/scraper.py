#!/usr/bin/env python3
"""
104人力銀行職缺爬蟲
使用 Selenium 抓取符合 CV 技能的職缺，限定雙北地區
"""

import json
import os
import re
import time
from datetime import datetime
from urllib.parse import urlencode

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config import AREAS, CV_SKILLS, KEYWORDS, MAX_PAGES, OUTPUT_DIR, REQUEST_DELAY


def create_driver():
    """建立 Chrome WebDriver"""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(options=options)
    return driver


def build_search_url(keyword: str, areas: list, page: int = 1) -> str:
    """建立搜尋 URL"""
    params = {
        "ro": 0,
        "kwop": 7,
        "keyword": keyword,
        "expansionType": "area,spec,com,job,wf,wktm",
        "area": ",".join(areas),
        "order": 15,
        "asc": 0,
        "page": page,
        "mode": "s",
    }
    return f"https://www.104.com.tw/jobs/search/?{urlencode(params)}"


def extract_jobs_from_jsonld(driver) -> list:
    """從頁面的 JSON-LD 結構化資料中提取職缺"""
    jobs = []

    try:
        # 等待頁面載入
        time.sleep(3)

        # 找到所有 JSON-LD script 標籤
        scripts = driver.find_elements(By.CSS_SELECTOR, 'script[type="application/ld+json"]')

        for script in scripts:
            try:
                data = json.loads(script.get_attribute("innerHTML"))

                # 處理列表格式
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") == "WebPage":
                            main_entity = item.get("mainEntity", [])
                            for entity in main_entity:
                                if entity.get("@type") == "ItemList":
                                    for list_item in entity.get("itemListElement", []):
                                        job_item = list_item.get("item", {})
                                        if job_item:
                                            job_url = job_item.get("url", "")
                                            job_id = job_url.split("/")[-1] if job_url else ""

                                            jobs.append(
                                                {
                                                    "job_id": job_id,
                                                    "title": job_item.get("name", ""),
                                                    "description": job_item.get("description", "")
                                                    .replace("<br>", "\n")
                                                    .replace("&lt;br&gt;", "\n"),
                                                    "url": job_url,
                                                }
                                            )
            except json.JSONDecodeError:
                continue

    except Exception as e:
        print(f"    解析 JSON-LD 失敗: {e}")

    return jobs


def extract_jobs_from_html(driver) -> list:
    """從 HTML 中提取職缺（備用方法）"""
    jobs = []

    try:
        # 等待職缺載入
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".info-job"))
        )

        # 找職缺卡片
        job_cards = driver.find_elements(By.CSS_SELECTOR, ".job-list-item, .job-mobile")

        for card in job_cards:
            try:
                # 找標題連結
                title_elem = card.find_element(By.CSS_SELECTOR, ".info-job a, a.info-job")
                title = title_elem.text.strip()
                url = title_elem.get_attribute("href")

                if not url or "/job/" not in url:
                    continue

                job_id = url.split("/job/")[-1].split("?")[0]

                # 公司名稱
                try:
                    company_elem = card.find_element(By.CSS_SELECTOR, ".name-wrapper a, .info-company a")
                    company = company_elem.text.strip()
                except Exception:
                    company = ""

                jobs.append(
                    {
                        "job_id": job_id,
                        "title": title,
                        "company": company,
                        "url": url,
                    }
                )

            except Exception:
                continue

    except Exception as e:
        print(f"    解析 HTML 失敗: {e}")

    return jobs


def get_job_detail(driver, url: str) -> dict:
    """取得職缺詳細資訊"""
    detail = {}

    try:
        driver.get(url)
        time.sleep(REQUEST_DELAY + 1)

        # 等待頁面載入
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
        )

        # 從 JSON-LD 提取詳細資訊
        scripts = driver.find_elements(By.CSS_SELECTOR, 'script[type="application/ld+json"]')
        for script in scripts:
            try:
                data = json.loads(script.get_attribute("innerHTML"))
                if isinstance(data, dict) and data.get("@type") == "JobPosting":
                    detail["title"] = data.get("title", "")
                    detail["company"] = data.get("hiringOrganization", {}).get("name", "")
                    detail["location"] = data.get("jobLocation", {}).get("address", {}).get("addressRegion", "")
                    detail["full_description"] = data.get("description", "").replace("<br>", "\n")

                    # 薪資
                    base_salary = data.get("baseSalary", {})
                    if base_salary:
                        value = base_salary.get("value", {})
                        min_val = value.get("minValue", "")
                        max_val = value.get("maxValue", "")
                        unit = value.get("unitText", "")
                        if min_val and max_val:
                            detail["salary"] = f"{min_val} - {max_val} {unit}"
                        elif min_val:
                            detail["salary"] = f"{min_val}+ {unit}"

                    break
            except json.JSONDecodeError:
                continue

        # 如果 JSON-LD 沒有完整資訊，從 HTML 補充
        if not detail.get("company"):
            try:
                company_elem = driver.find_element(By.CSS_SELECTOR, "a[data-gtm-head='公司名稱'], .company-name a")
                detail["company"] = company_elem.text.strip()
            except Exception:
                pass

        if not detail.get("salary"):
            try:
                salary_elem = driver.find_element(By.CSS_SELECTOR, ".salary-info, [class*='salary']")
                detail["salary"] = salary_elem.text.strip()
            except Exception:
                detail["salary"] = "面議"

        if not detail.get("location"):
            try:
                location_elem = driver.find_element(By.CSS_SELECTOR, ".job-location, [class*='location']")
                detail["location"] = location_elem.text.strip()
            except Exception:
                pass

        # 如果 JSON-LD 沒有完整描述，從 HTML 提取
        if not detail.get("full_description"):
            try:
                # 嘗試多種選擇器
                selectors = [
                    "div.job-description p",
                    "div[class*='job-description']",
                    "div.description",
                    "section.job-description",
                    "div.content-section",
                ]
                for selector in selectors:
                    try:
                        desc_elems = driver.find_elements(By.CSS_SELECTOR, selector)
                        if desc_elems:
                            detail["full_description"] = "\n".join(
                                [elem.text.strip() for elem in desc_elems if elem.text.strip()]
                            )
                            if detail["full_description"]:
                                break
                    except Exception:
                        continue
            except Exception:
                pass

        # 技能要求
        try:
            skill_elems = driver.find_elements(By.CSS_SELECTOR, ".category-wrapper .tag, .tools .tag, .skill-tag")
            detail["skills_required"] = [elem.text.strip() for elem in skill_elems if elem.text.strip()]
        except Exception:
            detail["skills_required"] = []

    except Exception as e:
        print(f"      取得詳情失敗: {e}")

    return detail


def match_cv_skills(job_info: dict) -> list:
    """檢查職缺與 CV 技能的匹配度"""
    matched = []
    text_to_search = " ".join(
        [
            job_info.get("description", ""),
            job_info.get("full_description", ""),
            job_info.get("title", ""),
            " ".join(job_info.get("skills_required", [])),
        ]
    ).lower()

    for skill in CV_SKILLS:
        if skill.lower() in text_to_search:
            matched.append(skill)

    return list(set(matched))


def save_results(jobs: list, filename: str = None):
    """儲存結果為 JSON"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if filename is None:
        filename = f"jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    filepath = os.path.join(OUTPUT_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)

    print(f"結果已儲存至: {filepath}")
    return filepath


def main():
    """主程式"""
    print("=" * 60)
    print("104人力銀行職缺爬蟲")
    print("=" * 60)

    driver = create_driver()
    all_jobs = {}  # 用 job_id 作為 key 去重

    try:
        for keyword in KEYWORDS:
            print(f"\n搜尋關鍵字: {keyword}")

            for page in range(1, MAX_PAGES + 1):
                print(f"  第 {page} 頁...")

                url = build_search_url(keyword, AREAS, page)
                driver.get(url)
                time.sleep(REQUEST_DELAY + 2)

                # 先嘗試從 JSON-LD 提取
                jobs = extract_jobs_from_jsonld(driver)

                # 如果 JSON-LD 沒有結果，使用 HTML 解析
                if not jobs:
                    jobs = extract_jobs_from_html(driver)

                if not jobs:
                    print(f"    無更多結果")
                    break

                print(f"    找到 {len(jobs)} 個職缺")

                for job in jobs:
                    job_id = job.get("job_id")

                    if not job_id or job_id in all_jobs:
                        continue

                    # 取得詳細資訊
                    job_url = job.get("url") or f"https://www.104.com.tw/job/{job_id}"
                    print(f"    取得詳情: {job['title'][:30]}...")
                    detail = get_job_detail(driver, job_url)
                    job.update(detail)

                    # 匹配 CV 技能
                    matched_skills = match_cv_skills(job)
                    job["skills_matched"] = matched_skills
                    job["match_count"] = len(matched_skills)

                    # 跳過沒有匹配技能的職缺
                    if job["match_count"] == 0:
                        print(f"      - {job.get('title', '')[:40]} (跳過: 無匹配技能)")
                        continue

                    all_jobs[job_id] = job
                    print(
                        f"      + {job.get('title', '')[:40]} @ {job.get('company', '未知')} ({len(matched_skills)} 技能匹配)"
                    )

    except KeyboardInterrupt:
        print("\n\n使用者中斷...")

    finally:
        driver.quit()

    # 整理結果
    jobs_list = list(all_jobs.values())

    # 依照匹配技能數量排序
    jobs_list.sort(key=lambda x: x.get("match_count", 0), reverse=True)

    print(f"\n{'=' * 60}")
    print(f"共找到 {len(jobs_list)} 個職缺")

    if jobs_list:
        # 顯示 Top 10
        print(f"\nTop 10 匹配職缺:")
        for i, job in enumerate(jobs_list[:10], 1):
            print(f"  {i}. {job.get('title', '未知職缺')} @ {job.get('company', '未知公司')}")
            print(f"     薪資: {job.get('salary', '面議')}")
            print(f"     地點: {job.get('location', '未知')}")
            print(f"     匹配技能: {', '.join(job.get('skills_matched', [])) or '無'}")
            print(f"     連結: {job.get('url', '')}")
            print()

        # 儲存結果
        save_results(jobs_list)

    print("完成!")


if __name__ == "__main__":
    main()
