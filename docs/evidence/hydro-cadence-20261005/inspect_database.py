# Read Hydro database counts and raw-log metadata without changing the database; 2026-10-05 19:50 EEST, Thomas Vikström.
import sqlite3,json,pathlib
p=pathlib.Path('/root/rf-watchkeeper')
c=sqlite3.connect('file:/root/rf-watchkeeper/data/watchkeeper.db?mode=ro',uri=True)
c.execute('PRAGMA query_only=ON')
print(json.dumps({'hydro_schema':c.execute('PRAGMA table_info(ais_met_hydro)').fetchall(),'stations':c.execute('SELECT mmsi,latitude,longitude,count(*),min(received_at),max(received_at) FROM ais_met_hydro GROUP BY mmsi,latitude,longitude').fetchall(),'raw_bytes':(p/'logs/ais-type8-raw.jsonl').stat().st_size},indent=2))
c.close()
