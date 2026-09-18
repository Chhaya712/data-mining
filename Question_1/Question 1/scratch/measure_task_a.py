import glob, os

files = glob.glob('data/sales/SALES_*.csv')
total_bytes = sum(os.path.getsize(f) for f in files)
print(f"Total flat files: {len(files)}")
print(f"Total flat bytes: {total_bytes} bytes ({total_bytes / (1024*1024):.2f} MB)")

# S01 in October 2024 (202410)
s01_oct_files = glob.glob('data/sales/SALES_S01_202410*.csv')
s01_oct_bytes = sum(os.path.getsize(f) for f in s01_oct_files)
print(f"\nS01 October 2024 files: {len(s01_oct_files)}")
print(f"S01 October 2024 bytes: {s01_oct_bytes} bytes ({s01_oct_bytes / (1024*1024):.2f} MB)")

# Ratio
print(f"\nFile scan reduction: {len(s01_oct_files)} / {len(files)} = {(len(s01_oct_files)/len(files))*100:.2f}% of files scanned ({100 - (len(s01_oct_files)/len(files))*100:.2f}% pruned)")
print(f"Byte scan reduction: {s01_oct_bytes} / {total_bytes} = {(s01_oct_bytes/total_bytes)*100:.2f}% of bytes scanned ({100 - (s01_oct_bytes/total_bytes)*100:.2f}% pruned)")
