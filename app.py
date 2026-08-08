import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
import time

# 設定網頁介面參數
st.set_page_config(page_title="外資高持股監控系統", layout="wide", initial_sidebar_state="expanded")

@st.cache_data(ttl=3600)
def fetch_twse_data(date_str):
    """向 TWSE 獲取特定日期的外資持股統計資料 (不受瀏覽器 CORS 限制)"""
    url = f"https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS?response=json&date={date_str}&selectType=ALL"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(url, headers=headers, timeout=15)
        data = res.json()
        if data.get('stat') == 'OK' and 'data' in data:
            df = pd.DataFrame(data['data'], columns=data['fields'])
            return df
    except Exception as e:
        st.error(f"連線異常，請稍後再試: {e}")
    return pd.DataFrame()

def process_data(df):
    """清理資料並轉型為數字"""
    if df.empty: 
        return df
    cols = ['證券代號', '證券名稱', '全體外資及陸資持股比率(%)']
    df = df[cols].copy()
    # 移除千分位逗號並轉換為浮點數
    df['全體外資及陸資持股比率(%)'] = df['全體外資及陸資持股比率(%)'].astype(str).str.replace(',', '', regex=False)
    df['全體外資及陸資持股比率(%)'] = pd.to_numeric(df['全體外資及陸資持股比率(%)'], errors='coerce')
    return df

# UI 介面設計
st.title("📈 台灣集中市場 - 外資高持股監控")
st.markdown("本系統直接由雲端伺服器連線證交所，支援手機直接瀏覽與互動。")

# 日期選擇器
selected_date = st.date_input("📅 請選擇交易日 (T)", datetime.today())

if st.button("🚀 開始抓取與比對分析", use_container_width=True):
    with st.spinner("正在向證交所獲取資料，請稍候..."):
        date_t_str = selected_date.strftime("%Y%m%d")
        
        # 1. 取得 T 日資料
        df_t = fetch_twse_data(date_t_str)
        
        if df_t.empty:
            st.warning(f"⚠️ {date_t_str} 無資料！可能為假日、尚未收盤，或證交所尚未更新。")
        else:
            df_t = process_data(df_t)
            
            # 2. 篩選 T 日持股大於 30.0% 的標的
            df_t_filtered = df_t[df_t['全體外資及陸資持股比率(%)'] > 30.0].copy()
            
            # 3. 往前尋找 T-1 日資料 (最多找10天避開長假)
            df_t1 = pd.DataFrame()
            days_back = 1
            st.info("已取得當日資料，正在計算前一交易日相差值...")
            
            while days_back <= 10:
                t1_date = selected_date - timedelta(days=days_back)
                date_t1_str = t1_date.strftime("%Y%m%d")
                time.sleep(1)  # 禮貌性延遲，避免被證交所阻擋
                df_t1 = fetch_twse_data(date_t1_str)
                if not df_t1.empty:
                    break
                days_back += 1
                
            if df_t1.empty:
                st.warning("無法取得前一交易日資料進行比對。")
            else:
                # 4. 資料合併與計算相差
                df_t1 = process_data(df_t1)
                df_t1_merged = df_t1[['證券代號', '全體外資及陸資持股比率(%)']].rename(columns={'全體外資及陸資持股比率(%)': '昨日比率'})
                
                result_df = pd.merge(df_t_filtered, df_t1_merged, on='證券代號', how='left')
                result_df['外資持股比率相差(%)'] = result_df['全體外資及陸資持股比率(%)'] - result_df['昨日比率']
                
                final_df = result_df[['證券代號', '證券名稱', '全體外資及陸資持股比率(%)', '外資持股比率相差(%)']]
                
                st.success(f"✅ 計算完成！共找到 {len(final_df)} 檔外資持股逾 30.0% 的證券。")
                
                # 5. 顯示可排序、篩選的資料表
                st.dataframe(
                    final_df, 
                    use_container_width=True,
                    hide_index=True
                )

st.markdown("---")
st.markdown("⚠️ **資料解讀限制與注意事項：** 除集中市場外資淨買賣數外，另有借券市場交易、海外存託憑證異動等非集中市場交易因素會同時影響外資持股數。")
