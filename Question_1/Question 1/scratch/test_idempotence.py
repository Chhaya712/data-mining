import glob, os, re, hashlib
import pandas as pd

def load_and_dedup():
    files = sorted(glob.glob('data/sales/SALES_*.csv'))
    all_rows = []
    for fpath in files:
        fname = os.path.basename(fpath)
        m = re.match(r'SALES_([A-Za-z0-9]+)_(\d{8})', fname)
        store_id = m.group(1)
        bdate_str = m.group(2)
        bdate = f'{bdate_str[:4]}-{bdate_str[4:6]}-{bdate_str[6:8]}'
        
        if store_id in ['S01', 'S02', 'S03', 'S04', 'S05']:
            df = pd.read_csv(fpath, sep=',')
            df = df.rename(columns={'ts': 'timestamp'})
        elif store_id in ['S06', 'S07', 'S08', 'S09']:
            df = pd.read_csv(fpath, sep=';')
            df = df.rename(columns={'item_code': 'product_code', 'quantity': 'qty', 'rate': 'unit_price', 'type': 'line_type', 'txn_time': 'timestamp'})
        else:
            df = pd.read_csv(fpath, sep=',', encoding='utf-8-sig')
            df = df.rename(columns={'ts': 'timestamp'})
        
        df['business_date'] = bdate
        df['store_id'] = store_id
        all_rows.append(df[['bill_no', 'line_no', 'store_id', 'business_date', 'product_code', 'qty', 'unit_price', 'line_type', 'timestamp']])
    
    df_all = pd.concat(all_rows, ignore_index=True)
    df_dedup = df_all.drop_duplicates(subset=['bill_no', 'line_no']).sort_values(by=['bill_no', 'line_no']).reset_index(drop=True)
    
    # Calculate checksum over sorted bill_no and line_no
    # We can hash bill_no, line_no, qty, unit_price
    content = "".join(f"{b},{l},{q},{u};" for b, l, q, u in zip(df_dedup['bill_no'], df_dedup['line_no'], df_dedup['qty'], df_dedup['unit_price']))
    checksum = hashlib.sha256(content.encode('utf-8')).hexdigest()
    return len(df_dedup), checksum

for run_i in range(1, 4):
    cnt, csum = load_and_dedup()
    print(f"Run {run_i}: Row count = {cnt}, SHA-256 Checksum = {csum}")
