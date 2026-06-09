import MySQLdb
from werkzeug.security import generate_password_hash

MYSQL_HOST     = 'localhost'
MYSQL_USER     = 'root'
MYSQL_PASSWORD = 'root'
MYSQL_DB       = 'hospital_db'
DEFAULT_PASS   = 'admin123'

db  = MySQLdb.connect(host=MYSQL_HOST, user=MYSQL_USER, passwd=MYSQL_PASSWORD, db=MYSQL_DB)
cur = db.cursor()

hashed = generate_password_hash(DEFAULT_PASS)
cur.execute("SELECT id, username FROM users")
users = cur.fetchall()

for uid, uname in users:
    cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (hashed, uid))
    print(f"  ✓  {uname}")

db.commit()
cur.close()
db.close()

print(f"\n✅ All {len(users)} users set to password: '{DEFAULT_PASS}'")
print("\nLogin credentials:")
print("  Receptionist : receptionist1 / admin123")
print("  Doctors      : dr.smith / admin123  |  dr.jones / admin123")
print("\nRun: python app.py  →  http://localhost:5000")
