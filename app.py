from flask import Flask, render_template, request, redirect, jsonify
import sqlite3
from datetime import datetime
from datetime import datetime, timedelta

app = Flask(__name__)

# 繰り返しイベント生成関数
def generate_weekly_events(task, start, end):
    events = []
    current = start

    while current <= end:
        if current.weekday() == task["repeat_weekday"]:
            events.append({
                "id": task["id"],
                "title": task["title"],
                "start": current.strftime("%Y-%m-%d"),
                "color": "#888" if task["done"] else None
            })
        current += timedelta(days=1)

    return events


# ---- DB初期化 ----
def init_db():
    con = sqlite3.connect("tasks.db")
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            date TEXT NOT NULL,
            done INTEGER DEFAULT 0,
            repeat_type TEXT DEFAULT 'none',
            repeat_weekday INTEGER
        );
    """)
    con.commit()
    con.close()

init_db()

# ---- タスク一覧（今日） ----
@app.route("/")
def index():
    return render_template("index.html")


# ---- カレンダー用API（全タスク取得） ----
@app.route("/api/tasks")
def api_tasks():
    start = datetime.fromisoformat(request.args["start"][:10])
    end = datetime.fromisoformat(request.args["end"][:10])

    con = sqlite3.connect("tasks.db")
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("""
        SELECT id, title, date, done, repeat_type, repeat_weekday
        FROM tasks
    """)
    rows = cur.fetchall()
    con.close()

    events = []

    for r in rows:
        task = dict(r)

        if task["repeat_type"] == "weekly" and task["repeat_weekday"] is not None:
            events += generate_weekly_events(task, start, end)
        else:
            events.append({
                "id": task["id"],
                "title": task["title"],
                "start": task["date"],
                "color": "#888" if task["done"] else None
            })

    return jsonify(events)


# ---- タスク追加 ----
@app.route("/add", methods=["GET", "POST"])
@app.route("/add", methods=["GET", "POST"])
def add_task():
    if request.method == "POST":
        title = request.form["title"]
        date = request.form["date"]
        repeat_type = request.form.get("repeat_type", "none")
        repeat_weekday = request.form.get("repeat_weekday")

        if repeat_weekday == "":
            repeat_weekday = None

        con = sqlite3.connect("tasks.db")
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO tasks (title, date, repeat_type, repeat_weekday)
            VALUES (?, ?, ?, ?)
            """,
            (title, date, repeat_type, repeat_weekday)
        )
        con.commit()
        con.close()
        return redirect("/")
    return render_template("add_task.html")


# ---- タスク完了API ----
@app.route("/api/finish/<int:task_id>", methods=["POST"])
def finish(task_id):
    con = sqlite3.connect("tasks.db")
    cur = con.cursor()
    cur.execute("UPDATE tasks SET done=1 WHERE id=?", (task_id,))
    con.commit()
    con.close()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True)
