import re
from collections import defaultdict

with open('data/masters.sql', 'r', encoding='utf-8') as f:
    sql = f.read()

# Parse products
prod_pattern = re.compile(r"\((\d+),'([^']+)',\s*'([^']+)',\s*'([^']+)',\s*'(?:[^']*)',\s*'(?:[^']*)',\s*'(?:[^']*)',\s*DATE '([^']+)',\s*DATE '([^']+)',\s*(TRUE|FALSE)\)")
matches = prod_pattern.findall(sql)

code_counts = defaultdict(list)
for sk, code, name, cat, vfrom, vto, is_curr in matches:
    code_counts[code].append((sk, name, cat, vfrom, vto, is_curr))

reissued = {c: lst for c, lst in code_counts.items() if len(lst) > 1}
print(f"Total reissued codes: {len(reissued)}")
for c, lst in list(reissued.items())[:5]:
    print(f"\nProduct Code: {c}")
    for item in lst:
        print(f"  SK: {item[0]}, Name: {item[1]}, Category: {item[2]}, Valid: {item[3]} to {item[4]}, Current: {item[5]}")
