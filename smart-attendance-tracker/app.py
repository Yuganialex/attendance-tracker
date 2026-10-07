"""Smart Attendance Tracker - Flask backend (app.py)"""
import random
import sqlite3
from datetime import date, timedelta
from functools import wraps

from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "change-this-secret-key"   # needed for login sessions
DB = "attendance.db"
STATUSES = {"present": "Present", "absent": "Absent", "onduty": "On Duty"}


# ---------------------------------------------------------------- database
def db():
    """One database connection per request."""
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def init_db():
    """Create tables and insert sample data the first time."""
    con = sqlite3.connect(DB)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS students(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        department TEXT NOT NULL,
        email TEXT);
    CREATE TABLE IF NOT EXISTS attendance(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL,
        date TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('Present','Absent','On Duty')),
        UNIQUE(student_id, date),
        FOREIGN KEY(student_id) REFERENCES students(student_id));
    """)
    if not con.execute("SELECT 1 FROM users").fetchone():
        con.execute("INSERT INTO users(username,email,password) VALUES(?,?,?)",
                    ("yugani", "admin@college.edu", generate_password_hash("yuga123")))
        names = ["yugani","Aarav Kumar", "Priya Sharma", "Rahul Verma", "Sneha Iyer", "Karthik Raj",
                 "Divya Nair", "Arjun Reddy", "Meena Krishnan", "Vikram Singh", "Anjali Menon",
                 "Suresh Babu", "Lakshmi Priya"]
        depts = ["CSE", "ECE", "MECH", "IT"]
        for i, n in enumerate(names):
            d = depts[i % 4]
            sid = f"{d}{101 + i}"
            con.execute("INSERT INTO students(student_id,name,department,email) VALUES(?,?,?,?)",
                        (sid, n, d, n.split()[0].lower() + "@college.edu"))
            # sample attendance for the last 20 weekdays (not today)
            day, count = date.today() - timedelta(days=1), 0
            while count < 20:
                if day.weekday() < 5:
                    st = random.choices(["Present", "Absent", "On Duty"], [75, 15, 10])[0]
                    con.execute("INSERT INTO attendance(student_id,date,status) VALUES(?,?,?)",
                                (sid, str(day), st))
                    count += 1
                day -= timedelta(days=1)
    con.commit()
    con.close()


# ---------------------------------------------------------------- helpers
def login_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        if "user" not in session:
            if request.path.startswith("/api/"):
                return jsonify(error="Please login first"), 401
            return redirect(url_for("login_page"))
        return f(*a, **k)
    return wrapper


def today():
    return str(date.today())


def working_days():
    """Working days = number of different dates on which attendance was taken."""
    return db().execute("SELECT COUNT(DISTINCT date) FROM attendance").fetchone()[0]


def percent(attended, total):
    return round(attended / total * 100, 1) if total else 0


def student_rows(day, q="", dept="", status=""):
    """Students with their status on `day` and overall attendance percentage."""
    sql = """SELECT s.*,
        (SELECT status FROM attendance a WHERE a.student_id=s.student_id AND a.date=?) AS status,
        (SELECT COUNT(*) FROM attendance a WHERE a.student_id=s.student_id
            AND a.status IN ('Present','On Duty')) AS attended
        FROM students s WHERE (s.name LIKE ? OR s.student_id LIKE ?)"""
    args = [day, f"%{q}%", f"%{q}%"]
    if dept:
        sql += " AND s.department=?"
        args.append(dept)
    sql += " ORDER BY s.student_id"
    total, out = working_days(), []
    for r in db().execute(sql, args):
        d = dict(r)
        d["date"] = day
        d["status"] = d["status"] or "Not Marked"
        d["percentage"] = percent(d.pop("attended"), total)
        if not status or d["status"] == status:
            out.append(d)
    return out


def valid_day(day):
    try:
        date.fromisoformat(day)
        return True
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------- pages
@app.route("/")
def login_page():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html")


def make_page(name, title):
    def view():
        return render_template(f"{name}.html", page=name, title=title)
    view.__name__ = name
    app.route(f"/{name}")(login_required(view))


for _n, _t in [("dashboard", "Dashboard"), ("students", "Students"), ("scan", "Scan ID Card"),
               ("attendance", "Attendance"), ("reports", "Reports")]:
    make_page(_n, _t)


# ---------------------------------------------------------------- auth API
@app.post("/api/login")
def api_login():
    d = request.get_json(silent=True) or {}
    ident, pw = (d.get("username") or "").strip(), d.get("password") or ""
    if not ident or not pw:
        return jsonify(error="Enter your username/email and password"), 400
    u = db().execute("SELECT * FROM users WHERE username=? OR email=?", (ident, ident)).fetchone()
    if not u or not check_password_hash(u["password"], pw):
        return jsonify(error="Invalid username or password"), 401
    session["user"] = u["username"]
    return jsonify(ok=True)


@app.route("/logout", methods=["GET", "POST"])
@app.post("/api/logout")
def logout():
    session.clear()
    if request.path.startswith("/api/"):
        return jsonify(ok=True)
    return redirect(url_for("login_page"))


# ---------------------------------------------------------------- student API
@app.get("/api/departments")
@login_required
def departments():
    rows = db().execute("SELECT DISTINCT department FROM students ORDER BY department")
    return jsonify([r[0] for r in rows])


@app.get("/api/students")
@app.get("/api/attendance")
@login_required
def get_students():
    """Used for both the student list and attendance records (filters via query string)."""
    day = request.args.get("date") or today()
    if not valid_day(day):
        return jsonify(error="Invalid date"), 400
    return jsonify(student_rows(day, request.args.get("q", "").strip(),
                                request.args.get("department", ""), request.args.get("status", "")))


@app.post("/api/students")
@login_required
def add_student():
    d = request.get_json(silent=True) or {}
    sid = (d.get("student_id") or "").strip().upper()
    name, dept = (d.get("name") or "").strip(), (d.get("department") or "").strip().upper()
    if not sid or not name or not dept:
        return jsonify(error="Student ID, name and department are required"), 400
    if db().execute("SELECT 1 FROM students WHERE student_id=?", (sid,)).fetchone():
        return jsonify(error=f"Student ID {sid} already exists"), 409
    db().execute("INSERT INTO students(student_id,name,department,email) VALUES(?,?,?,?)",
                 (sid, name, dept, (d.get("email") or "").strip()))
    db().commit()
    return jsonify(ok=True, message="Student added"), 201


@app.get("/api/students/<sid>")
@login_required
def find_student(sid):
    """Scan / find a student by ID."""
    day = request.args.get("date") or today()
    for r in student_rows(day):
        if r["student_id"].upper() == sid.strip().upper():
            return jsonify(r)
    return jsonify(error=f"No student found with ID '{sid}'"), 404


@app.put("/api/students/<sid>")
@login_required
def update_student(sid):
    d = request.get_json(silent=True) or {}
    name, dept = (d.get("name") or "").strip(), (d.get("department") or "").strip().upper()
    if not name or not dept:
        return jsonify(error="Name and department are required"), 400
    cur = db().execute("UPDATE students SET name=?, department=?, email=? WHERE student_id=?",
                       (name, dept, (d.get("email") or "").strip(), sid))
    db().commit()
    if cur.rowcount == 0:
        return jsonify(error="Student not found"), 404
    return jsonify(ok=True, message="Student updated")


@app.delete("/api/students/<sid>")
@login_required
def delete_student(sid):
    db().execute("DELETE FROM attendance WHERE student_id=?", (sid,))
    cur = db().execute("DELETE FROM students WHERE student_id=?", (sid,))
    db().commit()
    if cur.rowcount == 0:
        return jsonify(error="Student not found"), 404
    return jsonify(ok=True, message="Student deleted")


@app.get("/api/students/<sid>/history")
@login_required
def history(sid):
    rows = db().execute("SELECT date, status FROM attendance WHERE student_id=? ORDER BY date DESC",
                        (sid,)).fetchall()
    attended = sum(1 for r in rows if r["status"] in ("Present", "On Duty"))
    return jsonify(records=[dict(r) for r in rows], percentage=percent(attended, working_days()))


# ---------------------------------------------------------------- marking API
@app.post("/api/mark/<status>")
@login_required
def mark(status):
    """status in the URL: present / absent / onduty"""
    if status not in STATUSES:
        return jsonify(error="Invalid status"), 400
    d = request.get_json(silent=True) or {}
    sid = (d.get("student_id") or "").strip().upper()
    day = d.get("date") or today()
    if not valid_day(day):
        return jsonify(error="Invalid date"), 400
    stu = db().execute("SELECT * FROM students WHERE UPPER(student_id)=?", (sid,)).fetchone()
    if not stu:
        return jsonify(error=f"No student found with ID '{sid}'"), 404
    old = db().execute("SELECT status FROM attendance WHERE student_id=? AND date=?",
                       (stu["student_id"], day)).fetchone()
    if old and not d.get("overwrite"):          # prevent duplicate records
        return jsonify(error=f"{stu['name']} is already marked {old['status']} for {day}"), 409
    db().execute("""INSERT INTO attendance(student_id,date,status) VALUES(?,?,?)
                    ON CONFLICT(student_id,date) DO UPDATE SET status=excluded.status""",
                 (stu["student_id"], day, STATUSES[status]))
    db().commit()
    return jsonify(ok=True, message=f"{stu['name']} marked {STATUSES[status]} for {day}")


# ---------------------------------------------------------------- stats & reports
@app.get("/api/stats")
@login_required
def stats():
    day = request.args.get("date") or today()
    total = db().execute("SELECT COUNT(*) FROM students").fetchone()[0]
    c = {r["status"]: r["n"] for r in db().execute(
        "SELECT status, COUNT(*) n FROM attendance WHERE date=? GROUP BY status", (day,))}
    days = working_days()
    attended = db().execute(
        "SELECT COUNT(*) FROM attendance WHERE status IN ('Present','On Duty')").fetchone()[0]
    p, a, o = c.get("Present", 0), c.get("Absent", 0), c.get("On Duty", 0)
    return jsonify(total=total, present=p, absent=a, onduty=o, not_marked=total - p - a - o,
                   overall=percent(attended, days * total), working_days=days)


@app.get("/api/reports")
@login_required
def api_reports():
    cols = """COALESCE(SUM(status='Present'),0) p, COALESCE(SUM(status='Absent'),0) a,
              COALESCE(SUM(status='On Duty'),0) o, COUNT(*) n"""
    daily = db().execute(f"SELECT date, {cols} FROM attendance GROUP BY date "
                         "ORDER BY date DESC LIMIT 14").fetchall()[::-1]
    monthly = []
    for r in db().execute(f"SELECT substr(date,1,7) month, {cols} FROM attendance "
                          "GROUP BY month ORDER BY month"):
        m = dict(r)
        m["pct"] = percent(m["p"] + m["o"], m["n"])
        monthly.append(m)
    days, stu = working_days(), []
    for r in db().execute(f"""SELECT s.student_id, s.name, s.department, {cols}
            FROM students s LEFT JOIN attendance a ON a.student_id=s.student_id
            GROUP BY s.student_id ORDER BY s.student_id"""):
        s = dict(r)
        s["percentage"] = percent(s["p"] + s["o"], days)
        stu.append(s)
    return jsonify(daily=[dict(r) for r in daily], monthly=monthly, students=stu)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
