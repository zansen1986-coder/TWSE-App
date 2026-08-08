import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
import urllib.parse

# 設定網頁頁面
st.set_page_config(page_title="外資高持股監控系統", layout="wide")

@st.cache_data(ttl=1800)
def fetch_twse_data_proxy(date_str):
    """
    透過代理伺服器從 TWSE 取得資料，以繞過 Streamlit Cloud (AWS) 的 IP 封鎖。
    """
    target_url = f"https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS?response=json&date={date_str}&selectType=ALL"
    
    # 準備備援代理路由 (將網址編碼後交由公開代理伺服器代為抓取)
    proxies = [
        f"https://api.allorigins.win/raw?url={urllib.parse.quote(target_url)}",
        f"https://corsproxy.io/?{urllib.parse.quote(target_url)}",
        target_url # 最後嘗試直連
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for p_url in proxies:
        try:
            res = requests.get(p_url, headers=headers, timeout=15)
            if res.status_code == 200:
                data = res.json()
                # 確認證交所回傳的資料狀態為 OK 且具備 data 欄位
                if data.get('stat') == 'OK' and 'data' in data:
                    df = pd.DataFrame(data['data'], columns=data['fields'])
                    
                    # 僅取出目標的 3 個欄位
                    target_cols = ['證券代號', '證券名稱', '全體外資及陸資持股比率(%)']
                    df = df[target_cols].copy()
                    
                    # 清除千分位逗號並轉為浮點數
                    df['全體外資及陸資持股比率(%)'] = df['全體外資及陸資持股比率(%)'].astype(str).str.replace(',', '', regex=False)
                    df['全體外資及陸資持股比率(%)'] = pd.to_numeric(df['全體外資及陸資持股比率(%)'], errors='coerce')
                    
                    return df
                elif data.get('stat') != 'OK':
                    # 證交所明確回傳非 OK (代表該日確實沒開盤或無資料)，直接中斷尋找
                    return pd.DataFrame()
        except Exception:
            # 發生網路阻擋或超時，自動嘗試下一個代理
            continue
            
    return pd.DataFrame()

# UI 介面設計
st.title("📈 台灣集中市場 - 外資高持股監控")
st.markdown("本系統透過多重海外代理節點連線證交所，支援手機直接瀏覽、篩選與排序。")

selected_date = st.date_input("📅 請選擇交易日 (T)", datetime.today())

if st.button("🚀 開始抓取與比對分析", use_container_width=True):
    with st.spinner(f"正在透過海外節點獲取資料，請稍候..."):
        date_t_str = selected_date.strftime("%Y%m%d")
        
        # 1. 獲取 T 日資料
        df_t = fetch_twse_data_proxy(date_t_str)
        
        if df_t.empty:
            st.warning(f"⚠️ 日期 {date_t_str} 無資料！可能為假日（未開盤）、當日尚未收盤結算，或證交所 API 進行阻擋。")
        else:
            # 2. 篩選持股比率 > 30.0%
            df_t_filtered = df_t[df_t['全體外資及陸資持股比率(%)'] > 30.0].copy()
            
            # 3. 自動往前尋找 T-1 個交易日 (最多 10 天跳過連假)
            df_t1 = pd.DataFrame()
            days_back = 1
            st.info("✅ 已取得當日資料，正在比對前一交易日相差值...")
            
            while days_back <= 10:
                t1_date = selected_date - timedelta(days=days_back)
                date_t1_str = t1_date.strftime("%Y%m%d")
                df_t1 = fetch_twse_data_proxy(date_t1_str)
                if not df_t1.empty:
                    break
                days_back += 1
                
            if df_t1.empty:
                st.warning("無法取得前一交易日資料，僅顯示當日持股比率。")
                final_df = df_t_filtered
                final_df['外資持股比率相差(%)'] = 0.0
            else:
                # 4. 重新命名昨日欄位並計算持股相差
                df_t1_merged = df_t1[['證券代號', '全體外資及陸資持股比率(%)']].rename(
                    columns={'全體外資及陸資持股比率(%)': '昨日比率'}
                )
                
                result_df = pd.merge(df_t_filtered, df_t1_merged, on='證券代號', how='left')
                result_df['外資持股比率相差(%)'] = result_df['全體外資及陸資持股比率(%)'] - result_df['昨日比率']
                
                final_df = result_df[['證券代號', '證券名稱', '全體外資及陸資持股比率(%)', '外資持股比率相差(%)']]
            
            st.success(f"✅ 分析完成！共找到 {len(final_df)} 檔外資持股逾 30.0% 的證券。")
            
            # 5. 呈現可排序、篩選的互動式表格
            st.dataframe(
                final_df, 
                use_container_width=True,
                hide_index=True
            )

st.markdown("---")
st.markdown("⚠️ **資料解讀限制與注意事項：** 除集中市場外資淨買賣數外，另有借券交易、海外存託憑證異動、公司增減資或 ETF 申購買回等非集中市場因素會影響外資持股數。")
