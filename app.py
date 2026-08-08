import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta

# 設定網頁頁面
st.set_page_config(page_title="外資高持股監控系統", layout="wide")

@st.cache_data(ttl=1800)
def fetch_foreign_holding_data(date_str):
    """
    優先從 FinMind API 獲取外資持股資料 (避免 TWSE 對雲端伺服器之 IP 封鎖)
    """
    # 格式轉換 YYYYMMDD -> YYYY-MM-DD
    formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    
    # 1. 嘗試使用 FinMind API
    finmind_url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockForeignHoldingInfo",
        "start_date": formatted_date,
        "end_date": formatted_date
    }
    
    try:
        res = requests.get(finmind_url, params=params, timeout=12)
        data = res.json()
        if data.get("msg") == "success" and data.get("data"):
            df = pd.DataFrame(data["data"])
            # 整理欄位
            df = df.rename(columns={
                "stock_id": "證券代號",
                "stock_name": "證券名稱",
                "foreignInvestmentSharesRatio": "全體外資及陸資持股比率(%)"
            })
            df["全體外資及陸資持股比率(%)"] = pd.to_numeric(df["全體外資及陸資持股比率(%)"], errors='coerce')
            return df[['證券代號', '證券名稱', '全體外資及陸資持股比率(%)']]
    except Exception as e:
        pass

    # 2. 備援：若 FinMind 失敗，嘗試直連 TWSE API
    twse_url = f"https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS?response=json&date={date_str}&selectType=ALL"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.get(twse_url, headers=headers, timeout=10)
        data = res.json()
        if data.get('stat') == 'OK' and 'data' in data:
            df = pd.DataFrame(data['data'], columns=data['fields'])
            df = df[['證券代號', '證券名稱', '全體外資及陸資持股比率(%)']].copy()
            df['全體外資及陸資持股比率(%)'] = df['全體外資及陸資持股比率(%)'].astype(str).str.replace(',', '', regex=False)
            df['全體外資及陸資持股比率(%)'] = pd.to_numeric(df['全體外資及陸資持股比率(%)'], errors='coerce')
            return df
    except Exception as e:
        pass

    return pd.DataFrame()

# UI 介面設計
st.title("📈 台灣集中市場 - 外資高持股監控")
st.markdown("本系統採用開放資料 API，支援手機直接瀏覽、篩選與排序。")

selected_date = st.date_input("📅 請選擇交易日 (T)", datetime.today())

if st.button("🚀 開始抓取與比對分析", use_container_width=True):
    with st.spinner("正在獲取資料，請稍候..."):
        date_t_str = selected_date.strftime("%Y%m%d")
        
        # 1. 獲取 T 日資料
        df_t = fetch_foreign_holding_data(date_t_str)
        
        if df_t.empty:
            st.warning(f"⚠️ 日期 {date_t_str} 無資料！可能為假日（未開盤）、當日尚未收盤結算，或 API 進行例行維護。")
        else:
            # 2. 篩選持股比率 > 30.0%
            df_t_filtered = df_t[df_t['全體外資及陸資持股比率(%)'] > 30.0].copy()
            
            # 3. 自動往前尋找 T-1 個交易日 (最多尋找 10 天跳過假日)
            df_t1 = pd.DataFrame()
            days_back = 1
            st.info("已取得當日資料，正在比對前一交易日相差值...")
            
            while days_back <= 10:
                t1_date = selected_date - timedelta(days=days_back)
                date_t1_str = t1_date.strftime("%Y%m%d")
                df_t1 = fetch_foreign_holding_data(date_t1_str)
                if not df_t1.empty:
                    break
                days_back += 1
                
            if df_t1.empty:
                st.warning("無法取得前一交易日資料，僅顯示當日持股比率。")
                final_df = df_t_filtered
                final_df['外資持股比率相差(%)'] = 0.0
            else:
                # 4. 計算持股相差
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
