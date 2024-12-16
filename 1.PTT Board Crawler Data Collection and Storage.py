"""
利用 Python 所實現的爬蟲程式，針對 PTT 多個看板進行批量資料抓取並將結果整合儲存為 CSV
文件。程式可依需求自由設定抓取的看板名稱與頁數，自動處理抓取的資料並進行格式化
"""
import pandas as pd
from ptt_data_scraper_tool import crawl_ptt_page  # 假設 crawl_ptt_page 函式已正確定義於 ptt_data_scraper_tool 模組中
# 抓取多個看板的資料
broad = ['womentalk', 'Contacts', 'optical', 'Laser_eye']  # 定義要抓取的看板列表
container = pd.DataFrame()  # 初始化一個空的 DataFrame 用來存放結果
# 迴圈抓取每個看板的資料
for i in broad:
    try:
        print(f"正在抓取看板：{i}")
        # 呼叫 crawl_ptt_page 函式抓取指定看板資料
        elephants = crawl_ptt_page(Board_Name=i, page_num=50)  # 假設每個看板抓取 50 頁
        container = pd.concat([container, elephants], axis=0)  # 合併新抓取的資料
    except Exception as e:
        # 若出現錯誤，列印錯誤訊息並跳過當前看板
        print(f"抓取看板 {i} 時發生錯誤：{e}")
        continue
# 儲存結果為 CSV 檔案
container.to_csv(
    'ptt資料.csv',  # 輸出的檔案名稱
    encoding='utf-8-sig',  # 編碼格式，確保中文顯示正常
    index=False  # 不儲存索引
)
print("所有看板資料已儲存到 ptt資料.csv")
