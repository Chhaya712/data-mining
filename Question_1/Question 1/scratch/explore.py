import re

with open('data/masters.sql', 'r', encoding='utf-8') as f:
    sql = f.read()

# Let's find products with biscuit in name
biscuit_lines = [line for line in sql.splitlines() if 'Biscuit' in line or 'biscuit' in line]
print(f"Total biscuit lines in SQL: {len(biscuit_lines)}")
for line in biscuit_lines[:10]:
    print(line)

# Let's check price revisions for product 1008 (Britannia Cream Biscuit 60g)
print("\nPrice revisions for 1008:")
rev_lines = [line for line in sql.splitlines() if 'price_revisions' in line or ',1008,' in line]
for line in rev_lines[:10]:
    print(line)
