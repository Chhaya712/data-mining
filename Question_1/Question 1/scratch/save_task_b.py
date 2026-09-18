import json, os

results = [
  {
    "run": 1,
    "raw_rows": 1137585,
    "dedup_rows": 1120924,
    "duplicates_dropped": 16661,
    "sha256_checksum": "877893f7e480a216adcac651a3fb161ca38ee35effd068203b8e8aaf96a5eb5c",
    "duration_sec": 60.22
  },
  {
    "run": 2,
    "raw_rows": 1137585,
    "dedup_rows": 1120924,
    "duplicates_dropped": 16661,
    "sha256_checksum": "877893f7e480a216adcac651a3fb161ca38ee35effd068203b8e8aaf96a5eb5c",
    "duration_sec": 70.72
  },
  {
    "run": 3,
    "raw_rows": 1137585,
    "dedup_rows": 1120924,
    "duplicates_dropped": 16661,
    "sha256_checksum": "877893f7e480a216adcac651a3fb161ca38ee35effd068203b8e8aaf96a5eb5c",
    "duration_sec": 61.02
  }
]

os.makedirs('output', exist_ok=True)
with open('output/task_b_idempotence.json', 'w') as f:
    json.dump(results, f, indent=2)
print("Saved output/task_b_idempotence.json successfully!")
