# app/services/ups_repo.py (เฉพาะส่วนที่เกี่ยวกับ connection)
from urllib.parse import urlparse, unquote
import os, pymysql
from dotenv import load_dotenv

class UPSRepository:
    def __init__(self):
        load_dotenv()

    def _connect(self):
        dsn = os.getenv("SQLALCHEMY_DATABASE_URL", "").strip()
        if not dsn:
            # fallback เป็นตัวแปรแยกฟิลด์ถ้าจำเป็น
            return pymysql.connect(
                host=os.getenv("DB_HOST","127.0.0.1"),
                port=int(os.getenv("DB_PORT","3306")),
                user=os.getenv("DB_USER","root"),
                password=os.getenv("DB_PASS",""),
                database=os.getenv("DB_NAME","ups_dashboard"),
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
            )

        parsed = urlparse(dsn)
        return pymysql.connect(
            host=parsed.hostname or "127.0.0.1",
            port=int(parsed.port or 3306),
            user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            database=(parsed.path or "/").lstrip("/") or None,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )

    # ตัวอย่างเมธอดใช้ connection แบบเปิด–ปิด
    def get_device_by_ip(self, ip: str):
        sql = """
          SELECT id, ip_address, brand, model, location, is_active
          FROM ups_devices WHERE ip_address=%s LIMIT 1
        """
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                conn.ping(reconnect=True)
                cur.execute(sql, (ip,))
                return cur.fetchone()
        finally:
            conn.close()

    def get_all_ips(self):
        sql = "SELECT ip_address FROM ups_devices WHERE is_active=1 ORDER BY INET_ATON(ip_address)"
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                conn.ping(reconnect=True)
                cur.execute(sql)
                rows = cur.fetchall()
                return [r["ip_address"] for r in rows]
        finally:
            conn.close()

    def get_profile_id_for_ups(self, ups_id: str):
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                conn.ping(reconnect=True)
                cur.execute("SELECT profile_id FROM ups_device_profile WHERE ups_id=%s LIMIT 1", (ups_id,))
                row = cur.fetchone()
                if row and row.get("profile_id") is not None:
                    return int(row["profile_id"])
                cur.execute("SELECT id FROM snmp_profile WHERE name='STANDARD' LIMIT 1")
                r = cur.fetchone()
                return int(r["id"]) if r else None
        finally:
            conn.close()

    def get_oids_for_profile(self, profile_id: int):
        from collections import defaultdict
        primary_oids, fallbacks, scale_key_map = {}, defaultdict(list), {}
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                conn.ping(reconnect=True)
                cur.execute("""
                  SELECT oid_key, oid, priority
                  FROM snmp_profile_oid
                  WHERE profile_id=%s
                  ORDER BY oid_key ASC, priority ASC
                """, (profile_id,))
                for r in cur.fetchall():
                    fallbacks[r["oid_key"]].append(r["oid"])
                for k, lst in fallbacks.items():
                    if lst: primary_oids[k] = lst[0]

                cur.execute("SELECT oid_key, scale_key FROM snmp_oid_key")
                for r in cur.fetchall():
                    if r["scale_key"]:
                        scale_key_map[r["oid_key"]] = r["scale_key"]
        finally:
            conn.close()
        return primary_oids, dict(fallbacks), scale_key_map
