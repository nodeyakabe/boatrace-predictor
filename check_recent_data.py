import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

today = datetime.now().date()
start = today - timedelta(days=7)

print(f"Period: {start} to {today}")
print("="*50)

cursor.execute('''
    SELECT race_date, COUNT(*)
    FROM races
    WHERE race_date BETWEEN ? AND ?
    GROUP BY race_date
    ORDER BY race_date
''', (start.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d')))

rows = cursor.fetchall()
print('Races per day in last 7 days:')
for row in rows:
    print(f'{row[0]}: {row[1]} races')

cursor.execute('''
    SELECT COUNT(*)
    FROM races
    WHERE race_date BETWEEN ? AND ?
''', (start.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d')))

total = cursor.fetchone()[0]
print(f'\nTotal: {total} races')

# Check most recent data
cursor.execute('SELECT MAX(race_date) FROM races')
latest = cursor.fetchone()[0]
print(f'\nLatest race date in DB: {latest}')

conn.close()
