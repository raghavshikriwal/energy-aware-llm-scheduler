import sqlite3
c = sqlite3.connect('scheduler_runs.db')
cols = c.execute("PRAGMA table_info(comparison_runs)").fetchall()
print("COLUMNS:")
for col in cols:
    print(col)

print()
print("ROW COUNT:", c.execute("SELECT COUNT(*) FROM comparison_runs").fetchone()[0])

print()
print("LAST 5 ROWS:")
rows = c.execute("SELECT * FROM comparison_runs ORDER BY id DESC LIMIT 5").fetchall()
for r in rows:
    print(r)
