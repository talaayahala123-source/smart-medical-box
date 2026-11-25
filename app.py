from datetime import datetime
import sqlite3
from flask import Flask, jsonify, render_template,request

app = Flask(__name__)
DB_NAME = "medical_box.db"


def get_db():
  conn = sqlite3.connect(DB_NAME)
  conn.row_factory = sqlite3.Row
  return conn


def init_db():
  conn = get_db()
  cur = conn.cursor()

  # جدول المرضى
  cur.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            age INTEGER,
            notes TEXT,
            created_at TEXT NOT NULL
        )
    """)

  # جدول القراءات والحالات القادمة من ESP32
  cur.execute("""
        CREATE TABLE IF NOT EXISTS telemetry_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            status TEXT DEFAULT 'NORMAL',
            body_temp REAL,
            room_temp REAL,
            humidity REAL,
            pulse_sim REAL,
            fall_detected INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients (id)
        )
    """)

  # إضافة مريض افتراضي إذا كان الجدول فارغاً
  cur.execute("SELECT COUNT(*) AS cnt FROM patients")
  if cur.fetchone()["cnt"] == 0:
    cur.execute(
        "INSERT INTO patients (name, age, notes, created_at) VALUES (?, ?,"
        " ?, ?)",
        ("مريض 1", 65, "مريض افتراضي للاختبار", datetime.now().isoformat()),
    )

  conn.commit()
  conn.close()


# 1) جلب قائمة المرضى
@app.route("/api/patients", methods=["GET"])
def get_patients():
  conn = get_db()
  rows = conn.execute("SELECT * FROM patients ORDER BY id ASC").fetchall()
  conn.close()
  return jsonify([dict(r) for r in rows]), 200


# 2) إضافة مريض جديد
@app.route("/api/patients", methods=["POST"])
def add_patient():
  data = request.get_json(silent=True) or {}
  name = (data.get("name") or "").strip()
  if not name:
    return jsonify({"error": "اسم المريض مطلوب"}), 400

  age = data.get("age")
  notes = (data.get("notes") or "").strip()
  now = datetime.now().isoformat()

  conn = get_db()
  cur = conn.cursor()
  cur.execute(
      "INSERT INTO patients (name, age, notes, created_at) VALUES (?, ?, ?, ?)",
      (name, age, notes, now),
  )
  conn.commit()
  new_id = cur.lastrowid
  patient = dict(
      conn.execute("SELECT * FROM patients WHERE id = ?", (new_id,)).fetchone()
  )
  conn.close()

  return jsonify(patient), 201


# 3) استقبال بيانات القراءات من ESP32
@app.route("/api/telemetry", methods=["POST"])
def receive_telemetry():
  data = request.get_json(silent=True) or {}
  patient_id = data.get("patient_id", 1)

  conn = get_db()
  # التحقق من وجود المريض
  patient = conn.execute(
      "SELECT id FROM patients WHERE id = ?", (patient_id,)
  ).fetchone()
  if not patient:
    conn.close()
    return jsonify({"error": f"المريض برقم {patient_id} غير موجود"}), 404

  status = (data.get("status") or "NORMAL").strip()
  body_temp = data.get("body_temp")
  room_temp = data.get("room_temp")
  humidity = data.get("humidity")
  pulse_sim = data.get("pulse_sim")
  fall_detected = 1 if data.get("fall_detected") else 0
  now = datetime.now().isoformat()

  cur = conn.cursor()
  cur.execute(
      """
        INSERT INTO telemetry_logs
        (patient_id, status, body_temp, room_temp, humidity, pulse_sim, fall_detected, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
      (
          patient_id,
          status,
          body_temp,
          room_temp,
          humidity,
          pulse_sim,
          fall_detected,
          now,
      ),
  )
  conn.commit()
  log_id = cur.lastrowid
  conn.close()

  return (
      jsonify(
          {"message": "تم حفظ القراءة بنجاح", "id": log_id, "created_at": now}
      ),
      201,
  )


# 4) جلب قراءات مريض معين (الأحدث أولاً)
@app.route("/api/patients/<int:patient_id>/telemetry", methods=["GET"])
def get_patient_telemetry(patient_id):
  limit = request.args.get("limit", default=20, type=int)
  conn = get_db()
  rows = conn.execute(
      """
        SELECT * FROM telemetry_logs
        WHERE patient_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
      (patient_id, limit),
  ).fetchall()
  conn.close()
  return jsonify([dict(r) for r in rows]), 200
   
@app.route("/")
def dashboard():
  return render_template("index.html")
if __name__ == "__main__":
  init_db()
  app.run(host="0.0.0.0", port=5000, debug=True)