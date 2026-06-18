import pandas as pd
import numpy as np

def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate technical indicators for the given K-line DataFrame.
    Expected input columns (case-insensitive or normalized):
        'Open', 'High', 'Low', 'Close', 'Volume'
    Returns a copy of the DataFrame with calculated indicator columns.
    """
    # Create a copy and normalize columns
    df = df.copy()
    
    # Ensure numeric columns
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']
    
    # 1. Simple Moving Averages (SMA)
    for w in [5, 10, 20, 30, 60, 120, 250]:
        df[f'SMA_{w}'] = close.rolling(window=w).mean()
        
    # 2. Exponential Moving Averages (EMA)
    for w in [5, 10, 20]:
        df[f'EMA_{w}'] = close.ewm(span=w, adjust=False).mean()
        
    # 3. MACD
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    df['DIF'] = ema_12 - ema_26
    df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD'] = 2 * (df['DIF'] - df['DEA'])
    
    # 4. RSI (Relative Strength Index)
    # Wilder's RSI using ewm
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    for r_period in [6, 12, 24]:
        avg_gain = gain.ewm(alpha=1/r_period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/r_period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df[f'RSI_{r_period}'] = 100 - (100 / (1 + rs)).fillna(100)
        
    # 5. Bollinger Bands (BOLL)
    df['BOLL_MID'] = close.rolling(window=20).mean()
    boll_std = close.rolling(window=20).std()
    df['BOLL_UP'] = df['BOLL_MID'] + 2 * boll_std
    df['BOLL_LB'] = df['BOLL_MID'] - 2 * boll_std
    
    # 6. KDJ
    low_min = low.rolling(window=9, min_periods=1).min()
    high_max = high.rolling(window=9, min_periods=1).max()
    denom = (high_max - low_min).replace(0, np.nan)
    rsv = (close - low_min) / denom * 100
    rsv = rsv.fillna(50)
    
    k_vals = []
    d_vals = []
    curr_k = 50.0
    curr_d = 50.0
    for val in rsv:
        if pd.isna(val):
            curr_k = 50.0
            curr_d = 50.0
        else:
            curr_k = (2/3) * curr_k + (1/3) * val
            curr_d = (2/3) * curr_d + (1/3) * curr_k
        k_vals.append(curr_k)
        d_vals.append(curr_d)
        
    df['KDJ_K'] = k_vals
    df['KDJ_D'] = d_vals
    df['KDJ_J'] = 3 * df['KDJ_K'] - 2 * df['KDJ_D']
    
    # 7. ATR (Average True Range)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['ATR'] = tr.ewm(alpha=1/14, adjust=False).mean()
    
    # 8. CCI (Commodity Channel Index)
    tp = (high + low + close) / 3
    tp_sma = tp.rolling(14).mean()
    tp_md = tp.rolling(14).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    df['CCI'] = (tp - tp_sma) / (0.015 * tp_md.replace(0, np.nan))
    
    # 9. Williams %R (WR)
    high_max_14 = high.rolling(window=14).max()
    low_min_14 = low.rolling(window=14).min()
    df['WR'] = (high_max_14 - close) / (high_max_14 - low_min_14).replace(0, np.nan) * -100
    
    # 10. VWMA (Volume Weighted Moving Average)
    pv = close * volume
    df['VWMA'] = pv.rolling(20).sum() / volume.rolling(20).sum().replace(0, np.nan)
    
    # 11. MFI (Money Flow Index)
    tp = (high + low + close) / 3
    rmf = tp * volume
    diff = tp.diff()
    pos_flow = pd.Series(np.where(diff > 0, rmf, 0), index=df.index)
    neg_flow = pd.Series(np.where(diff < 0, rmf, 0), index=df.index)
    pos_sum = pos_flow.rolling(14).sum()
    neg_sum = neg_flow.rolling(14).sum()
    mr = pos_sum / neg_sum.replace(0, np.nan)
    df['MFI'] = 100 - (100 / (1 + mr)).fillna(50)
    
    return df
