from flask import Flask, render_template, request, redirect, jsonify
import sqlite3
from datetime import datetime, timedelta
import json

app = Flask(__name__)

# ---- DB初期化 ----
def init_db():
    con = sqlite3.connect("tasks.db")
    cur = con.cursor()
    
    # メインタスクテーブル
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            date TEXT,
            done INTEGER DEFAULT 0,
            repeat_type TEXT DEFAULT 'none',
            repeat_weekday INTEGER
        );
    """)
    
    # 既存テーブルに新しいカラムを追加（エラーを無視）
    try:
        cur.execute("ALTER TABLE tasks ADD COLUMN repeat_interval INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass  # カラムが既に存在する場合
    
    try:
        cur.execute("ALTER TABLE tasks ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP")
    except sqlite3.OperationalError:
        pass  # カラムが既に存在する場合
    
    # 繰り返しタスクの個別完了記録テーブル
    cur.execute("""
        CREATE TABLE IF NOT EXISTS task_completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            completion_date TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            UNIQUE(task_id, completion_date)
        );
    """)
    
    con.commit()
    con.close()

init_db()

# ---- 繰り返しイベント生成関数 ----
def generate_recurring_events(task, start, end, completions):
    """繰り返しタスクのイベントを生成"""
    events = []
    current = start
    
    while current <= end:
        should_show = False
        
        if task["repeat_type"] == "daily":
            should_show = True
        elif task["repeat_type"] == "weekly" and task["repeat_weekday"] is not None:
            should_show = (current.weekday() == task["repeat_weekday"])
        elif task["repeat_type"] == "monthly":
            # 毎月同じ日
            task_date = datetime.strptime(task["date"], "%Y-%m-%d")
            should_show = (current.day == task_date.day)
        
        if should_show:
            date_str = current.strftime("%Y-%m-%d")
            is_completed = date_str in completions
            
            events.append({
                "id": f"{task['id']}_{date_str}",
                "taskId": task["id"],
                "title": task["title"],
                "start": date_str,
                "color": "#888" if is_completed else None,
                "isRecurring": True,
                "completed": is_completed
            })
        
        current += timedelta(days=1)
    
    return events

# ---- ホーム ----
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
    
    # 全タスク取得
    cur.execute("""
        SELECT id, title, date, done, repeat_type, repeat_weekday
        FROM tasks
    """)
    rows = cur.fetchall()
    
    # 完了記録取得
    cur.execute("""
        SELECT task_id, completion_date 
        FROM task_completions
        WHERE completion_date BETWEEN ? AND ?
    """, (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")))
    
    completion_rows = cur.fetchall()
    con.close()
    
    # 完了記録を辞書化
    completions_dict = {}
    for comp in completion_rows:
        task_id = comp["task_id"]
        if task_id not in completions_dict:
            completions_dict[task_id] = set()
        completions_dict[task_id].add(comp["completion_date"])
    
    events = []
    for r in rows:
        task = dict(r)
        
        if task["repeat_type"] != "none":
            # 繰り返しタスク
            completions = completions_dict.get(task["id"], set())
            events += generate_recurring_events(task, start, end, completions)
        else:
            # 単発タスク
            events.append({
                "id": task["id"],
                "taskId": task["id"],
                "title": task["title"],
                "start": task["date"],
                "color": "#888" if task["done"] else None,
                "isRecurring": False,
                "completed": task["done"] == 1
            })
    
    return jsonify(events)

# ---- タスク追加 ----
@app.route("/add", methods=["GET", "POST"])
def add_task():
    if request.method == "POST":
        title = request.form["title"]
        date = request.form.get("date")
        repeat_type = request.form.get("repeat_type", "none")
        repeat_weekday = request.form.get("repeat_weekday")
        
        if repeat_weekday == "":
            repeat_weekday = None
        else:
            repeat_weekday = int(repeat_weekday)
        
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

# ---- タスク削除 ----
@app.route("/api/delete/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    con = sqlite3.connect("tasks.db")
    cur = con.cursor()
    
    cur.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    cur.execute("DELETE FROM task_completions WHERE task_id=?", (task_id,))
    
    con.commit()
    con.close()
    
    return jsonify({"success": True})

# ---- タスク完了切り替え ----
@app.route("/api/toggle", methods=["POST"])
def toggle():
    data = request.json
    task_id = data.get("taskId")
    date = data.get("date")
    is_recurring = data.get("isRecurring", False)
    
    con = sqlite3.connect("tasks.db")
    cur = con.cursor()
    
    if is_recurring:
        # 繰り返しタスクの特定日の完了/未完了を切り替え
        cur.execute(
            "SELECT id FROM task_completions WHERE task_id=? AND completion_date=?",
            (task_id, date)
        )
        existing = cur.fetchone()
        
        if existing:
            # 完了を解除
            cur.execute(
                "DELETE FROM task_completions WHERE task_id=? AND completion_date=?",
                (task_id, date)
            )
            new_state = False
        else:
            # 完了にする
            cur.execute(
                "INSERT INTO task_completions (task_id, completion_date) VALUES (?, ?)",
                (task_id, date)
            )
            new_state = True
    else:
        # 単発タスクの完了切り替え
        cur.execute("SELECT done FROM tasks WHERE id=?", (task_id,))
        row = cur.fetchone()
        
        if row is None:
            con.close()
            return jsonify({"error": "not found"}), 404
        
        new_done = 0 if row[0] else 1
        cur.execute("UPDATE tasks SET done=? WHERE id=?", (new_done, task_id))
        new_state = (new_done == 1)
    
    con.commit()
    con.close()
    
    return jsonify({"completed": new_state})

# ---- タスク一覧取得（管理画面用） ----
@app.route("/api/tasks/list")
def list_tasks():
    con = sqlite3.connect("tasks.db")
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    
    cur.execute("""
        SELECT id, title, date, done, repeat_type, repeat_weekday
        FROM tasks
        ORDER BY id DESC
    """)
    
    rows = cur.fetchall()
    con.close()
    
    tasks = [dict(r) for r in rows]
    return jsonify(tasks)

if __name__ == "__main__":
    app.run(debug=True)
