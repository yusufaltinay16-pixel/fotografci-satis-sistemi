import os, sqlite3, json
from contextlib import AbstractContextManager
from datetime import date, datetime
from zoneinfo import ZoneInfo
from functools import wraps
from flask import Flask, request, redirect, url_for, session, flash, render_template
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "CHANGE-THIS-SECRET-KEY")
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DB_PATH = os.environ.get("DB_PATH", "fotografci.db")
if DB_PATH.startswith("sqlite:///"):
    DB_PATH = DB_PATH.replace("sqlite:///", "", 1)

class PostgresDB(AbstractContextManager):
    def __init__(self):
        import psycopg
        from psycopg.rows import dict_row
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL ayarlanmamış.")
        self.conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=15)

    def execute(self, sql, params=()):
        return self.conn.execute(sql.replace("?", "%s"), params)

    def executescript(self, script):
        for statement in script.split(";"):
            if statement.strip():
                self.conn.execute(statement)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            self.conn.close()
        return False

def db():
    if DATABASE_URL:
        return PostgresDB()
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with db() as c:
        if DATABASE_URL:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS users(
              id BIGSERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL,
              password TEXT NOT NULL, full_name TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'seller',
              commission DOUBLE PRECISION NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS rates(
              id BIGSERIAL PRIMARY KEY, rate_date TEXT NOT NULL, currency TEXT NOT NULL,
              rate DOUBLE PRECISION NOT NULL, UNIQUE(rate_date,currency));
            CREATE TABLE IF NOT EXISTS sales(
              id BIGSERIAL PRIMARY KEY, seller_id BIGINT NOT NULL REFERENCES users(id), sale_date TEXT NOT NULL,
              quantity INTEGER NOT NULL, currency TEXT NOT NULL, amount DOUBLE PRECISION NOT NULL,
              exchange_rate DOUBLE PRECISION NOT NULL, total_tl DOUBLE PRECISION NOT NULL,
              payment_type TEXT NOT NULL, note TEXT DEFAULT '',
              commission_rate DOUBLE PRECISION NOT NULL, commission_tl DOUBLE PRECISION NOT NULL,
              created_at TEXT);
            CREATE TABLE IF NOT EXISTS expenses(
              id BIGSERIAL PRIMARY KEY, expense_date TEXT NOT NULL, description TEXT NOT NULL,
              amount DOUBLE PRECISION NOT NULL, currency TEXT NOT NULL,
              exchange_rate DOUBLE PRECISION NOT NULL, total_tl DOUBLE PRECISION NOT NULL);
            CREATE TABLE IF NOT EXISTS payments(
              id BIGSERIAL PRIMARY KEY, seller_id BIGINT NOT NULL REFERENCES users(id), payment_date TEXT NOT NULL,
              amount DOUBLE PRECISION NOT NULL, note TEXT DEFAULT '');
            CREATE TABLE IF NOT EXISTS closures(
              id BIGSERIAL PRIMARY KEY, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
              closed_at TEXT NOT NULL, total_sales DOUBLE PRECISION NOT NULL,
              total_commission DOUBLE PRECISION NOT NULL, total_expenses DOUBLE PRECISION NOT NULL,
              shop_net DOUBLE PRECISION NOT NULL);
            CREATE TABLE IF NOT EXISTS paper_inventory(
              id INTEGER PRIMARY KEY, current_stock INTEGER NOT NULL DEFAULT 0,
              low_stock_threshold INTEGER NOT NULL DEFAULT 20);
            CREATE TABLE IF NOT EXISTS sale_changes(
              id BIGSERIAL PRIMARY KEY, sale_id BIGINT NOT NULL, changed_by BIGINT NOT NULL,
              action TEXT NOT NULL, changed_at TEXT NOT NULL, old_values TEXT NOT NULL, new_values TEXT NOT NULL);
            INSERT INTO paper_inventory(id,current_stock,low_stock_threshold)
              VALUES(1,0,20) ON CONFLICT(id) DO NOTHING;
            """)
        else:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS users(
              id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
              password TEXT NOT NULL, full_name TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'seller',
              commission REAL NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS rates(
              id INTEGER PRIMARY KEY AUTOINCREMENT, rate_date TEXT NOT NULL, currency TEXT NOT NULL,
              rate REAL NOT NULL, UNIQUE(rate_date,currency));
            CREATE TABLE IF NOT EXISTS sales(
              id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER NOT NULL, sale_date TEXT NOT NULL,
              quantity INTEGER NOT NULL, currency TEXT NOT NULL, amount REAL NOT NULL, exchange_rate REAL NOT NULL,
              total_tl REAL NOT NULL, payment_type TEXT NOT NULL, note TEXT DEFAULT '',
              commission_rate REAL NOT NULL, commission_tl REAL NOT NULL, created_at TEXT,
              FOREIGN KEY(seller_id) REFERENCES users(id));
            CREATE TABLE IF NOT EXISTS expenses(
              id INTEGER PRIMARY KEY AUTOINCREMENT, expense_date TEXT NOT NULL, description TEXT NOT NULL,
              amount REAL NOT NULL, currency TEXT NOT NULL, exchange_rate REAL NOT NULL, total_tl REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS payments(
              id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER NOT NULL, payment_date TEXT NOT NULL,
              amount REAL NOT NULL, note TEXT DEFAULT '', FOREIGN KEY(seller_id) REFERENCES users(id));
            CREATE TABLE IF NOT EXISTS closures(
              id INTEGER PRIMARY KEY AUTOINCREMENT, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
              closed_at TEXT NOT NULL, total_sales REAL NOT NULL, total_commission REAL NOT NULL,
              total_expenses REAL NOT NULL, shop_net REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS paper_inventory(
              id INTEGER PRIMARY KEY, current_stock INTEGER NOT NULL DEFAULT 0,
              low_stock_threshold INTEGER NOT NULL DEFAULT 20);
            CREATE TABLE IF NOT EXISTS sale_changes(
              id INTEGER PRIMARY KEY AUTOINCREMENT, sale_id INTEGER NOT NULL, changed_by INTEGER NOT NULL,
              action TEXT NOT NULL, changed_at TEXT NOT NULL, old_values TEXT NOT NULL, new_values TEXT NOT NULL);
            INSERT OR IGNORE INTO paper_inventory(id,current_stock,low_stock_threshold) VALUES(1,0,20);
            """)
        if DATABASE_URL:
            c.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS delivery_type TEXT NOT NULL DEFAULT 'Eski kayıt'")
            c.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS paper_count INTEGER NOT NULL DEFAULT 0")
            c.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS created_at TEXT")
        else:
            columns = [row["name"] for row in c.execute("PRAGMA table_info(sales)").fetchall()]
            if "delivery_type" not in columns:
                c.execute("ALTER TABLE sales ADD COLUMN delivery_type TEXT NOT NULL DEFAULT 'Eski kayıt'")
            if "paper_count" not in columns:
                c.execute("ALTER TABLE sales ADD COLUMN paper_count INTEGER NOT NULL DEFAULT 0")
            if "created_at" not in columns:
                c.execute("ALTER TABLE sales ADD COLUMN created_at TEXT")
        admin = c.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()
        if not admin:
            c.execute("INSERT INTO users(username,password,full_name,role,commission) VALUES(?,?,?,?,?)",
                      ("admin", generate_password_hash("Admin123!"), "Yönetici", "admin", 0))

init_db()

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped

def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Bu bölüm yalnızca yöneticiye açıktır.")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapped

def current_user():
    with db() as c:
        return c.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()

@app.context_processor
def inject_user():
    return {"me": current_user() if session.get("user_id") else None}

@app.route("/")
def home():
    return redirect(url_for("dashboard") if session.get("user_id") else url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        with db() as c:
            u = c.execute("SELECT * FROM users WHERE username=? AND active=1", (request.form["username"].strip(),)).fetchone()
        if u and check_password_hash(u["password"], request.form["password"]):
            session.update(user_id=u["id"], role=u["role"], name=u["full_name"])
            return redirect(url_for("dashboard"))
        flash("Kullanıcı adı veya şifre hatalı.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/change-password", methods=["GET","POST"])
@login_required
def change_password():
    if request.method == "POST":
        old = request.form["old_password"]
        new = request.form["new_password"]
        if len(new) < 8:
            flash("Yeni şifre en az 8 karakter olmalı.")
        else:
            with db() as c:
                u = c.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
                if not check_password_hash(u["password"], old):
                    flash("Mevcut şifre yanlış.")
                else:
                    c.execute("UPDATE users SET password=? WHERE id=?", (generate_password_hash(new), session["user_id"]))
                    flash("Şifreniz değiştirildi.")
                    return redirect(url_for("dashboard"))
    return render_template("change_password.html")

@app.route("/dashboard")
@login_required
def dashboard():
    today = date.today().isoformat()
    start = request.args.get("start", today[:8]+"01")
    end = request.args.get("end", today)
    with db() as c:
        params = [start,end]
        seller_filter = ""
        if session["role"] != "admin":
            seller_filter = " AND seller_id=?"
            params.append(session["user_id"])
        sales = c.execute(f"SELECT s.*,u.full_name FROM sales s JOIN users u ON u.id=s.seller_id WHERE sale_date BETWEEN ? AND ?{seller_filter} ORDER BY s.id DESC", params).fetchall()
        totals = c.execute(f"""SELECT COALESCE(SUM(total_tl),0) sales, COALESCE(SUM(commission_tl),0) commission,
          COALESCE(SUM(quantity),0) qty,
          COALESCE(SUM(CASE WHEN delivery_type='Ücretli baskı' THEN quantity ELSE 0 END),0) paid_print_qty,
          COALESCE(SUM(CASE WHEN delivery_type='Bedelsiz baskı' THEN quantity ELSE 0 END),0) free_print_qty,
          COALESCE(SUM(CASE WHEN delivery_type='Telefona gönderim' THEN quantity ELSE 0 END),0) phone_qty,
          COALESCE(SUM(paper_count),0) paper_count
          FROM sales WHERE sale_date BETWEEN ? AND ?{seller_filter}""", params).fetchone()
        if session["role"] == "admin":
            expenses = c.execute("SELECT COALESCE(SUM(total_tl),0) n FROM expenses WHERE expense_date BETWEEN ? AND ?", (start,end)).fetchone()["n"]
            paper_inventory = c.execute("SELECT * FROM paper_inventory WHERE id=1").fetchone()
            seller_rows = c.execute("""SELECT u.id,u.full_name,u.commission,COALESCE(SUM(s.total_tl),0) sales,
              COALESCE(SUM(s.commission_tl),0) earned FROM users u LEFT JOIN sales s ON s.seller_id=u.id
              AND s.sale_date BETWEEN ? AND ? WHERE u.role='seller' AND u.active=1 GROUP BY u.id ORDER BY u.full_name""",(start,end)).fetchall()
        else:
            expenses, seller_rows, paper_inventory = 0, [], None
    return render_template("dashboard.html", sales=sales, totals=totals, expenses=expenses,
                           seller_rows=seller_rows, paper_inventory=paper_inventory, start=start, end=end)

@app.route("/sale", methods=["GET","POST"])
@login_required
def sale():
    if request.method == "POST":
        seller_id = session["user_id"] if session["role"] != "admin" else int(request.form["seller_id"])
        sale_date = request.form.get("sale_date") or date.today().isoformat()
        created_at = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y-%m-%d %H:%M:%S")
        qty = int(request.form["quantity"])
        delivery_type = request.form.get("delivery_type", "Ücretli baskı")
        if delivery_type not in ("Ücretli baskı", "Telefona gönderim", "Bedelsiz baskı") or qty < 1:
            flash("Fotoğraf adedi veya teslim türü geçersiz.")
            return redirect(url_for("sale"))
        currency = "TL" if delivery_type == "Bedelsiz baskı" else request.form["currency"]
        amount = 0.0 if delivery_type == "Bedelsiz baskı" else float(request.form.get("amount") or 0)
        if delivery_type != "Bedelsiz baskı" and amount <= 0:
            flash("Ücretli baskı veya telefona gönderimde satış tutarı sıfırdan büyük olmalı.")
            return redirect(url_for("sale"))
        payment = "Bedelsiz" if delivery_type == "Bedelsiz baskı" else request.form["payment_type"]
        paper_count = qty if delivery_type in ("Ücretli baskı", "Bedelsiz baskı") else 0
        with db() as c:
            seller = c.execute("SELECT * FROM users WHERE id=? AND role='seller'",(seller_id,)).fetchone()
            if not seller: flash("Fotoğrafçı bulunamadı."); return redirect(url_for("sale"))
            if currency == "TL":
                rate = 1.0
            else:
                rate_row = c.execute("SELECT rate FROM rates WHERE rate_date=? AND currency=?",(sale_date,currency)).fetchone()
                if not rate_row:
                    flash(f"{sale_date} tarihi için {currency} kuru girilmemiş. Önce yönetici kur girmeli.")
                    return redirect(url_for("sale"))
                rate = float(rate_row["rate"])
            if paper_count:
                stock_update = c.execute(
                    "UPDATE paper_inventory SET current_stock=current_stock-? WHERE id=1 AND current_stock>=?",
                    (paper_count, paper_count))
                if stock_update.rowcount == 0:
                    current_stock = c.execute("SELECT current_stock FROM paper_inventory WHERE id=1").fetchone()["current_stock"]
                    flash(f"Yeterli baskı kâğıdı yok. Mevcut stok: {current_stock}. Önce stok ekleyin.")
                    return redirect(url_for("sale"))
            total_tl = amount * rate
            commission = total_tl * float(seller["commission"]) / 100
            c.execute("""INSERT INTO sales(seller_id,sale_date,quantity,currency,amount,exchange_rate,total_tl,
              payment_type,note,commission_rate,commission_tl,delivery_type,paper_count,created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (seller_id,sale_date,qty,currency,amount,rate,total_tl,payment,request.form.get("note",""),
               seller["commission"],commission,delivery_type,paper_count,created_at))
        flash("Satış kaydedildi.")
        return redirect(url_for("dashboard"))
    with db() as c:
        sellers = c.execute("SELECT id,full_name FROM users WHERE role='seller' AND active=1 ORDER BY full_name").fetchall()
    return render_template("sale.html", sellers=sellers, today=date.today().isoformat())


@app.route("/sale/<int:sale_id>/edit", methods=["GET","POST"])
@login_required
def edit_sale(sale_id):
    with db() as c:
        old = c.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
        if not old:
            flash("Satış kaydı bulunamadı.")
            return redirect(url_for("dashboard"))
        if session["role"] != "admin" and old["seller_id"] != session["user_id"]:
            flash("Yalnızca kendi satışınızı düzenleyebilirsiniz.")
            return redirect(url_for("dashboard"))
        if request.method == "GET":
            sellers = c.execute("SELECT id,full_name FROM users WHERE role='seller' AND active=1 ORDER BY full_name").fetchall() if session["role"] == "admin" else []
            return render_template("sale.html", sellers=sellers, today=date.today().isoformat(),
                                   sale_record=old, edit_mode=True)
        try:
            seller_id = int(request.form["seller_id"]) if session["role"] == "admin" else old["seller_id"]
            qty = int(request.form["quantity"])
            sale_date = request.form["sale_date"]
            delivery_type = request.form["delivery_type"]
            currency = request.form.get("currency", "TL")
            amount = float(request.form.get("amount") or 0)
        except (KeyError, TypeError, ValueError):
            flash("Satış bilgilerini kontrol edip tekrar deneyin.")
            return redirect(url_for("edit_sale", sale_id=sale_id))
        if qty < 1 or delivery_type not in ("Ücretli baskı", "Telefona gönderim", "Bedelsiz baskı"):
            flash("Fotoğraf adedi veya teslim şekli geçersiz.")
            return redirect(url_for("edit_sale", sale_id=sale_id))
        if delivery_type == "Bedelsiz baskı":
            amount, currency, payment = 0.0, "TL", "Bedelsiz"
        else:
            if amount <= 0 or currency not in ("TL", "USD", "EUR"):
                flash("Ücretli satışta tutar sıfırdan büyük olmalı; para birimini kontrol edin.")
                return redirect(url_for("edit_sale", sale_id=sale_id))
            payment = request.form.get("payment_type", "Nakit")
            if payment not in ("Nakit", "Kredi kartı", "IBAN"):
                flash("Ödeme türü geçersiz.")
                return redirect(url_for("edit_sale", sale_id=sale_id))
        paper_count = qty if delivery_type in ("Ücretli baskı", "Bedelsiz baskı") else 0
        seller = c.execute("SELECT * FROM users WHERE id=? AND role='seller' AND active=1", (seller_id,)).fetchone()
        if not seller:
            flash("Fotoğrafçı bulunamadı veya hesabı kapalı.")
            return redirect(url_for("edit_sale", sale_id=sale_id))
        if currency == "TL":
            rate = 1.0
        else:
            rate_row = c.execute("SELECT rate FROM rates WHERE rate_date=? AND currency=?", (sale_date,currency)).fetchone()
            if not rate_row:
                flash(f"{sale_date} tarihi için {currency} kuru girilmemiş. Önce yönetici kur girmeli.")
                return redirect(url_for("edit_sale", sale_id=sale_id))
            rate = float(rate_row["rate"])
        total_tl = amount * rate
        commission_rate = float(seller["commission"])
        commission_tl = total_tl * commission_rate / 100
        stock_delta = paper_count - int(old["paper_count"] or 0)
        if stock_delta > 0:
            changed = c.execute("UPDATE paper_inventory SET current_stock=current_stock-? WHERE id=1 AND current_stock>=?",
                                (stock_delta,stock_delta))
            if changed.rowcount == 0:
                stock = c.execute("SELECT current_stock FROM paper_inventory WHERE id=1").fetchone()["current_stock"]
                flash(f"Yeterli kâğıt stoğu yok. Mevcut stok: {stock}.")
                return redirect(url_for("edit_sale", sale_id=sale_id))
        elif stock_delta < 0:
            c.execute("UPDATE paper_inventory SET current_stock=current_stock+? WHERE id=1", (-stock_delta,))
        changed_at = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y-%m-%d %H:%M:%S")
        old_values = json.dumps(dict(old), ensure_ascii=False, default=str)
        c.execute("""UPDATE sales SET seller_id=?,sale_date=?,quantity=?,currency=?,amount=?,exchange_rate=?,
                     total_tl=?,payment_type=?,note=?,commission_rate=?,commission_tl=?,delivery_type=?,paper_count=?
                     WHERE id=?""",
                  (seller_id,sale_date,qty,currency,amount,rate,total_tl,payment,
                   request.form.get("note",""),commission_rate,commission_tl,delivery_type,paper_count,sale_id))
        updated = c.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
        c.execute("""INSERT INTO sale_changes(sale_id,changed_by,action,changed_at,old_values,new_values)
                     VALUES(?,?,?,?,?,?)""",
                  (sale_id,session["user_id"],"Düzenlendi",changed_at,old_values,
                   json.dumps(dict(updated), ensure_ascii=False, default=str)))
    flash("Satış düzeltildi. Hakediş ve kâğıt stoğu güncellendi.")
    return redirect(url_for("dashboard"))


@app.route("/sale/<int:sale_id>/delete", methods=["POST"])
@login_required
def delete_sale(sale_id):
    with db() as c:
        old = c.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
        if not old:
            flash("Satış kaydı bulunamadı.")
            return redirect(url_for("dashboard"))
        if session["role"] != "admin" and old["seller_id"] != session["user_id"]:
            flash("Yalnızca kendi satışınızı silebilirsiniz.")
            return redirect(url_for("dashboard"))
        paper_count = int(old["paper_count"] or 0)
        if paper_count:
            c.execute("UPDATE paper_inventory SET current_stock=current_stock+? WHERE id=1", (paper_count,))
        changed_at = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""INSERT INTO sale_changes(sale_id,changed_by,action,changed_at,old_values,new_values)
                     VALUES(?,?,?,?,?,?)""",
                  (sale_id,session["user_id"],"Silindi",changed_at,
                   json.dumps(dict(old), ensure_ascii=False, default=str),"{}"))
        c.execute("DELETE FROM sales WHERE id=?", (sale_id,))
    flash("Satış silindi. Kâğıt stoğu otomatik geri eklendi; hakediş toplamı yenilendi.")
    return redirect(url_for("dashboard"))


@app.route("/sale/<int:sale_id>/history")
@login_required
def sale_history(sale_id):
    with db() as c:
        sale_row = c.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
        if sale_row and session["role"] != "admin" and sale_row["seller_id"] != session["user_id"]:
            flash("Bu satışın geçmişini görüntüleme yetkiniz yok.")
            return redirect(url_for("dashboard"))
        if not sale_row and session["role"] != "admin":
            flash("Silinmiş satış geçmişini yalnızca yönetici görebilir.")
            return redirect(url_for("dashboard"))
        changes = c.execute("""SELECT sc.*,u.full_name FROM sale_changes sc
                               LEFT JOIN users u ON u.id=sc.changed_by
                               WHERE sc.sale_id=? ORDER BY sc.id DESC""", (sale_id,)).fetchall()
    return render_template("sale_history.html", changes=changes, sale_id=sale_id)

@app.route("/paper-stock", methods=["POST"])
@login_required
@admin_required
def paper_stock():
    action = request.form.get("action")
    try:
        quantity = int(request.form.get("quantity", "0"))
    except (TypeError, ValueError):
        quantity = 0
    if quantity < 0:
        flash("Kâğıt adedi negatif olamaz.")
        return redirect(url_for("dashboard"))
    with db() as c:
        if action == "set":
            c.execute("UPDATE paper_inventory SET current_stock=? WHERE id=1", (quantity,))
            flash(f"Başlangıç kâğıt stoğu {quantity} olarak kaydedildi.")
        elif action == "add" and quantity > 0:
            c.execute("UPDATE paper_inventory SET current_stock=current_stock+? WHERE id=1", (quantity,))
            flash(f"Stoğa {quantity} kâğıt eklendi.")
        else:
            flash("Geçerli bir stok işlemi seçin ve sıfırdan büyük adet girin.")
    return redirect(url_for("dashboard"))


@app.route("/rates", methods=["GET","POST"])
@login_required
@admin_required
def rates():
    if request.method == "POST":
        with db() as c:
            c.execute("INSERT INTO rates(rate_date,currency,rate) VALUES(?,?,?) ON CONFLICT(rate_date,currency) DO UPDATE SET rate=excluded.rate",
                      (request.form["rate_date"],request.form["currency"],float(request.form["rate"])))
        flash("Kur kaydedildi.")
        return redirect(url_for("rates"))
    with db() as c:
        rows = c.execute("SELECT * FROM rates ORDER BY rate_date DESC,id DESC LIMIT 60").fetchall()
    return render_template("rates.html", rows=rows, today=date.today().isoformat())

@app.route("/expenses", methods=["GET","POST"])
@login_required
@admin_required
def expenses():
    if request.method == "POST":
        currency=request.form["currency"]; d=request.form["expense_date"]; amount=float(request.form["amount"])
        rate=1.0
        with db() as c:
            if currency != "TL":
                rr=c.execute("SELECT rate FROM rates WHERE rate_date=? AND currency=?",(d,currency)).fetchone()
                if not rr:
                    flash("Bu tarih için döviz kuru girilmemiş."); return redirect(url_for("expenses"))
                rate=float(rr["rate"])
            c.execute("INSERT INTO expenses(expense_date,description,amount,currency,exchange_rate,total_tl) VALUES(?,?,?,?,?,?)",
                      (d,request.form["description"],amount,currency,rate,amount*rate))
        flash("Masraf kaydedildi.")
        return redirect(url_for("expenses"))
    with db() as c:
        rows=c.execute("SELECT * FROM expenses ORDER BY expense_date DESC,id DESC LIMIT 100").fetchall()
    return render_template("expenses.html", rows=rows, today=date.today().isoformat())

@app.route("/sellers", methods=["GET","POST"])
@login_required
@admin_required
def sellers():
    if request.method == "POST":
        with db() as c:
            c.execute("INSERT INTO users(username,password,full_name,role,commission) VALUES(?,?,?,?,?)",
                      (request.form["username"].strip(),generate_password_hash(request.form["password"]),
                       request.form["full_name"].strip(),"seller",float(request.form["commission"])))
        flash("Fotoğrafçı hesabı oluşturuldu.")
        return redirect(url_for("sellers"))
    with db() as c:
        rows=c.execute("SELECT * FROM users WHERE role='seller' ORDER BY full_name").fetchall()
    return render_template("sellers.html", rows=rows)

@app.route("/seller/<int:sid>/update", methods=["POST"])
@login_required
@admin_required
def seller_update(sid):
    with db() as c:
        c.execute("UPDATE users SET commission=?,active=? WHERE id=? AND role='seller'",
                  (float(request.form["commission"]),int(request.form.get("active","1")),sid))
    flash("Fotoğrafçı ayarları güncellendi.")
    return redirect(url_for("sellers"))

@app.route("/payments", methods=["GET","POST"])
@login_required
@admin_required
def payments():
    if request.method == "POST":
        with db() as c:
            c.execute("INSERT INTO payments(seller_id,payment_date,amount,note) VALUES(?,?,?,?)",
                      (int(request.form["seller_id"]),request.form["payment_date"],float(request.form["amount"]),request.form.get("note","")))
        flash("Fotoğrafçı ödemesi kaydedildi.")
        return redirect(url_for("payments"))
    with db() as c:
        sellers=c.execute("SELECT id,full_name FROM users WHERE role='seller' AND active=1 ORDER BY full_name").fetchall()
        rows=c.execute("SELECT p.*,u.full_name FROM payments p JOIN users u ON u.id=p.seller_id ORDER BY payment_date DESC,p.id DESC").fetchall()
    return render_template("payments.html", sellers=sellers, rows=rows, today=date.today().isoformat())

@app.route("/reports")
@login_required
def reports():
    start=request.args.get("start",date.today().replace(day=1).isoformat()); end=request.args.get("end",date.today().isoformat())
    with db() as c:
        if session["role"]=="admin":
            rows=c.execute("""SELECT u.id,u.full_name,COALESCE(SUM(s.total_tl),0) sales,
            COALESCE(SUM(s.commission_tl),0) earned,
            COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.seller_id=u.id AND p.payment_date BETWEEN ? AND ?),0) paid
            FROM users u LEFT JOIN sales s ON s.seller_id=u.id AND s.sale_date BETWEEN ? AND ?
            WHERE u.role='seller' GROUP BY u.id ORDER BY u.full_name""",(start,end,start,end)).fetchall()
            totals=c.execute("""SELECT COALESCE(SUM(total_tl),0) sales,COALESCE(SUM(commission_tl),0) commissions,
            COALESCE(SUM(CASE WHEN delivery_type='Ücretli baskı' THEN quantity ELSE 0 END),0) paid_print_qty,
            COALESCE(SUM(CASE WHEN delivery_type='Bedelsiz baskı' THEN quantity ELSE 0 END),0) free_print_qty,
            COALESCE(SUM(CASE WHEN delivery_type='Telefona gönderim' THEN quantity ELSE 0 END),0) phone_qty,
            COALESCE(SUM(paper_count),0) paper_count
            FROM sales WHERE sale_date BETWEEN ? AND ?""",(start,end)).fetchone()
            exp=c.execute("SELECT COALESCE(SUM(total_tl),0) n FROM expenses WHERE expense_date BETWEEN ? AND ?",(start,end)).fetchone()["n"]
        else:
            rows=c.execute("""SELECT u.id,u.full_name,COALESCE(SUM(s.total_tl),0) sales,
            COALESCE(SUM(s.commission_tl),0) earned,
            COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.seller_id=u.id AND p.payment_date BETWEEN ? AND ?),0) paid
            FROM users u LEFT JOIN sales s ON s.seller_id=u.id AND s.sale_date BETWEEN ? AND ?
            WHERE u.id=? GROUP BY u.id""",(start,end,start,end,session["user_id"])).fetchall()
            totals=c.execute("""SELECT COALESCE(SUM(total_tl),0) sales,COALESCE(SUM(commission_tl),0) commissions,
            COALESCE(SUM(CASE WHEN delivery_type='Ücretli baskı' THEN quantity ELSE 0 END),0) paid_print_qty,
            COALESCE(SUM(CASE WHEN delivery_type='Bedelsiz baskı' THEN quantity ELSE 0 END),0) free_print_qty,
            COALESCE(SUM(CASE WHEN delivery_type='Telefona gönderim' THEN quantity ELSE 0 END),0) phone_qty,
            COALESCE(SUM(paper_count),0) paper_count
            FROM sales WHERE sale_date BETWEEN ? AND ? AND seller_id=?""",(start,end,session["user_id"])).fetchone()
            exp=0
    return render_template("reports.html", rows=rows, totals=totals, expenses=exp, start=start,end=end)

@app.route("/close-period", methods=["POST"])
@login_required
@admin_required
def close_period():
    start=request.form["start"]; end=request.form["end"]
    with db() as c:
        sales=c.execute("SELECT COALESCE(SUM(total_tl),0) n FROM sales WHERE sale_date BETWEEN ? AND ?",(start,end)).fetchone()["n"]
        comm=c.execute("SELECT COALESCE(SUM(commission_tl),0) n FROM sales WHERE sale_date BETWEEN ? AND ?",(start,end)).fetchone()["n"]
        exp=c.execute("SELECT COALESCE(SUM(total_tl),0) n FROM expenses WHERE expense_date BETWEEN ? AND ?",(start,end)).fetchone()["n"]
        c.execute("INSERT INTO closures(start_date,end_date,closed_at,total_sales,total_commission,total_expenses,shop_net) VALUES(?,?,?,?,?,?,?)",
                  (start,end,datetime.now().isoformat(timespec="seconds"),sales,comm,exp,sales-comm-exp))
    flash(f"Hesap kesildi. Dükkân neti: {sales-comm-exp:,.2f} TL")
    return redirect(url_for("reports",start=start,end=end))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)), debug=False)
