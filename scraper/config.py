# 104人力銀行爬蟲設定

# 搜尋關鍵字 - 根據 CV 技能設定
KEYWORDS = [
    "Python 後端",
    "Backend Engineer Python",
    "Python Kubernetes",
    "Python Azure",
]

# 地區代碼
# 台北市: 6001001000
# 新北市: 6001002000
AREAS = ["6001001000", "6001002000"]

# 每個關鍵字最多搜尋幾頁
MAX_PAGES = 3

# 輸出資料夾
OUTPUT_DIR = "output"

# CV 技能清單 - 用於篩選匹配的職缺
CV_SKILLS = [
    "Python",
    "Django",
    "DRF",
    "Flask",
    "PostgreSQL",
    "Azure",
    "Kubernetes",
    "K8s",
    "Kafka",
    "Docker",
    "REST API",
    "微服務",
    "Microservice",
]

# 請求延遲（秒）- 避免過度請求
REQUEST_DELAY = 1.5
