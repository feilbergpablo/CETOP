from flask import Flask, render_template, request, redirect, flash, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, date

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "cetop-dev-secret")

database_url = os.environ.get("DATABASE_URL")
if database_url:
    database_url = database_url.replace("postgres://", "postgresql://", 1)
else:
    database_url = "sqlite:///cetop.db"

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# ── Modelos ──────────────────────────────────────────────

class Terapeuta(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    especialidad = db.Column(db.String(100), default="Terapia Ocupacional")
    usuario = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    es_admin = db.Column(db.Boolean, default=False)
    telefono = db.Column(db.String(30), default="")


class Paciente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    fecha_nacimiento = db.Column(db.String(20), nullable=False)
    diagnostico = db.Column(db.String(200), default="")
    obra_social = db.Column(db.String(100), default="Particular")
    precio_sesion = db.Column(db.Float, default=0)
    modalidad = db.Column(db.String(20), default="particular")  # "particular" o "obra_social"
    contacto_nombre = db.Column(db.String(150), default="")
    contacto_telefono = db.Column(db.String(30), default="")
    terapeuta_id = db.Column(db.Integer, db.ForeignKey("terapeuta.id"), nullable=False)
    activo = db.Column(db.Boolean, default=True)
    terapeuta = db.relationship("Terapeuta", backref="pacientes")


class Turno(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey("paciente.id"), nullable=False)
    terapeuta_id = db.Column(db.Integer, db.ForeignKey("terapeuta.id"), nullable=False)
    fecha = db.Column(db.String(20), nullable=False)
    hora = db.Column(db.String(10), nullable=False)
    estado = db.Column(db.String(20), default="pendiente")  # pendiente, confirmado, cancelado
    notas = db.Column(db.String(300), default="")
    paciente = db.relationship("Paciente", backref="turnos")
    terapeuta = db.relationship("Terapeuta", backref="turnos")


class Sesion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey("paciente.id"), nullable=False)
    terapeuta_id = db.Column(db.Integer, db.ForeignKey("terapeuta.id"), nullable=False)
    fecha = db.Column(db.String(20), nullable=False)
    nota = db.Column(db.Text, default="")
    puntuacion = db.Column(db.Integer, default=5)
    cobrado = db.Column(db.Boolean, default=False)
    paciente = db.relationship("Paciente", backref="sesiones")


class Movimiento(db.Model):
    __tablename__ = "movimiento_cetop"
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False)  # ingreso / gasto
    descripcion = db.Column(db.String(200), nullable=False)
    monto = db.Column(db.Float, nullable=False)
    fecha = db.Column(db.String(20), nullable=False)
    categoria = db.Column(db.String(100), default="General")


# ── Helpers ──────────────────────────────────────────────

@login_manager.user_loader
def load_user(user_id):
    return Terapeuta.query.get(int(user_id))


def fmt_pesos(n):
    return f"{int(n):,}".replace(",", ".")


def edad(fecha_nac):
    try:
        nac = datetime.strptime(fecha_nac, "%Y-%m-%d").date()
        hoy = date.today()
        return hoy.year - nac.year - ((hoy.month, hoy.day) < (nac.month, nac.day))
    except:
        return "?"


# ── Auth ─────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")
        user = Terapeuta.query.filter_by(usuario=usuario).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect("/")
        flash("Usuario o contraseña incorrectos.", "error")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")


# ── Dashboard ─────────────────────────────────────────────

@app.route("/")
@login_required
def home():
    hoy = date.today().strftime("%Y-%m-%d")

    if current_user.es_admin:
        turnos_hoy = Turno.query.filter(Turno.fecha==hoy, Turno.estado!="cobrado").order_by(Turno.hora).all()
        total_pacientes = Paciente.query.filter_by(activo=True).count()
        total_terapeutas = Terapeuta.query.count()
    else:
        turnos_hoy = Turno.query.filter(Turno.fecha==hoy, Turno.terapeuta_id==current_user.id, Turno.estado!="cobrado").order_by(Turno.hora).all()
        total_pacientes = Paciente.query.filter_by(activo=True, terapeuta_id=current_user.id).count()
        total_terapeutas = None

    return render_template("index.html",
        turnos_hoy=turnos_hoy,
        total_pacientes=total_pacientes,
        total_terapeutas=total_terapeutas,
        hoy=date.today().strftime("%d/%m/%Y"),
        hoy_iso=date.today().strftime("%Y-%m-%d"),
        fmt_pesos=fmt_pesos,
        edad=edad
    )


# ── Turnos ────────────────────────────────────────────────

@app.route("/turnos")
@login_required
def turnos():
    fecha = request.args.get("fecha", date.today().strftime("%Y-%m-%d"))
    if current_user.es_admin:
        lista = Turno.query.filter(Turno.fecha==fecha, Turno.estado!="cobrado").order_by(Turno.hora).all()
        cobrados = Turno.query.filter_by(fecha=fecha, estado="cobrado").order_by(Turno.hora).all()
    else:
        lista = Turno.query.filter(Turno.fecha==fecha, Turno.terapeuta_id==current_user.id, Turno.estado!="cobrado").order_by(Turno.hora).all()
        cobrados = Turno.query.filter_by(fecha=fecha, terapeuta_id=current_user.id, estado="cobrado").order_by(Turno.hora).all()
    terapeutas = Terapeuta.query.all()
    pacientes = Paciente.query.filter_by(activo=True).all()
    return render_template("turnos.html", turnos=lista, cobrados=cobrados, fecha=fecha, terapeutas=terapeutas, pacientes=pacientes, fmt_pesos=fmt_pesos)


@app.route("/turnos/cobrar/<int:id>")
@login_required
def cobrar_turno(id):
    t = Turno.query.get(id)
    if t and t.estado != "cobrado":
        if t.paciente.precio_sesion > 0:
            modalidad = "Obra social" if t.paciente.modalidad == "obra_social" else "Particular"
            # Ingreso por la sesión completa
            m = Movimiento(
                tipo="ingreso",
                descripcion=f"Sesión — {t.paciente.nombre}",
                monto=t.paciente.precio_sesion,
                fecha=t.fecha,
                categoria=f"Sesión cobrada · {modalidad}"
            )
            db.session.add(m)
            # Si el terapeuta NO es admin (no es Andrés), generar gasto del 70%
            terapeuta = Terapeuta.query.get(t.terapeuta_id)
            if terapeuta and not terapeuta.es_admin:
                pago_colega = round(t.paciente.precio_sesion * 0.70, 2)
                gasto = Movimiento(
                    tipo="gasto",
                    descripcion=f"Pago a colega — {terapeuta.nombre}",
                    monto=pago_colega,
                    fecha=t.fecha,
                    categoria="Pago a profesional"
                )
                db.session.add(gasto)
        t.estado = "cobrado"
        db.session.commit()
    return redirect(url_for("turnos", fecha=t.fecha))


@app.route("/turnos/agregar", methods=["POST"])
@login_required
def agregar_turno():
    t = Turno(
        paciente_id=request.form.get("paciente_id"),
        terapeuta_id=request.form.get("terapeuta_id"),
        fecha=request.form.get("fecha"),
        hora=request.form.get("hora"),
        notas=request.form.get("notas", "")
    )
    db.session.add(t)
    db.session.commit()
    return redirect(url_for("turnos", fecha=t.fecha))


@app.route("/turnos/estado/<int:id>/<estado>")
@login_required
def cambiar_estado(id, estado):
    t = Turno.query.get(id)
    if t:
        t.estado = estado
        db.session.commit()
    return redirect(url_for("turnos", fecha=t.fecha))


@app.route("/turnos/eliminar/<int:id>")
@login_required
def eliminar_turno(id):
    t = Turno.query.get(id)
    if t:
        fecha = t.fecha
        db.session.delete(t)
        db.session.commit()
    return redirect(url_for("turnos", fecha=fecha))


# ── Pacientes ─────────────────────────────────────────────

@app.route("/pacientes")
@login_required
def pacientes():
    if current_user.es_admin:
        lista = Paciente.query.filter_by(activo=True).all()
    else:
        lista = Paciente.query.filter_by(activo=True, terapeuta_id=current_user.id).all()
    terapeutas = Terapeuta.query.all()
    return render_template("pacientes.html", pacientes=lista, terapeutas=terapeutas, edad=edad)


@app.route("/pacientes/agregar", methods=["POST"])
@login_required
def agregar_paciente():
    p = Paciente(
        nombre=request.form.get("nombre"),
        fecha_nacimiento=request.form.get("fecha_nacimiento"),
        diagnostico=request.form.get("diagnostico", ""),
        obra_social=request.form.get("obra_social", "Particular"),
        modalidad=request.form.get("modalidad", "particular"),
        precio_sesion=float(request.form.get("precio_sesion", 0) or 0),
        contacto_nombre=request.form.get("contacto_nombre", ""),
        contacto_telefono=request.form.get("contacto_telefono", ""),
        terapeuta_id=request.form.get("terapeuta_id") or current_user.id
    )
    db.session.add(p)
    db.session.commit()
    return redirect("/pacientes")


@app.route("/pacientes/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar_paciente(id):
    p = Paciente.query.get(id)
    if not p:
        return redirect("/pacientes")
    if request.method == "POST":
        p.nombre = request.form.get("nombre")
        p.fecha_nacimiento = request.form.get("fecha_nacimiento")
        p.diagnostico = request.form.get("diagnostico", "")
        p.obra_social = request.form.get("obra_social", "Particular")
        p.modalidad = request.form.get("modalidad", "particular")
        p.precio_sesion = float(request.form.get("precio_sesion", 0) or 0)
        p.contacto_nombre = request.form.get("contacto_nombre", "")
        p.contacto_telefono = request.form.get("contacto_telefono", "")
        p.terapeuta_id = request.form.get("terapeuta_id") or current_user.id
        db.session.commit()
        return redirect(f"/pacientes/{id}")
    terapeutas = Terapeuta.query.all()
    return render_template("editar_paciente.html", paciente=p, terapeutas=terapeutas)


@app.route("/pacientes/<int:id>")
@login_required
def ver_paciente(id):
    p = Paciente.query.get(id)
    if not p:
        return redirect("/pacientes")
    sesiones = Sesion.query.filter_by(paciente_id=id).order_by(Sesion.fecha.desc()).all()
    return render_template("historia.html", paciente=p, sesiones=sesiones, edad=edad, fmt_pesos=fmt_pesos)


@app.route("/pacientes/daralta/<int:id>")
@login_required
def dar_alta(id):
    p = Paciente.query.get(id)
    if p:
        p.activo = False
        db.session.commit()
    return redirect("/pacientes")


# ── Sesiones ──────────────────────────────────────────────

@app.route("/sesiones/agregar", methods=["POST"])
@login_required
def agregar_sesion():
    paciente_id = request.form.get("paciente_id")
    s = Sesion(
        paciente_id=paciente_id,
        terapeuta_id=current_user.id,
        fecha=request.form.get("fecha", date.today().strftime("%Y-%m-%d")),
        nota=request.form.get("nota", ""),
        puntuacion=int(request.form.get("puntuacion", 5))
    )
    db.session.add(s)
    db.session.commit()
    return redirect(f"/pacientes/{paciente_id}")


@app.route("/sesiones/cobrar/<int:id>")
@login_required
def cobrar_sesion(id):
    s = Sesion.query.get(id)
    if s and not s.cobrado:
        s.cobrado = True
        db.session.commit()
        # Crear movimiento de ingreso automático en consultorio
        if s.paciente.precio_sesion > 0:
            modalidad = "Obra social" if s.paciente.modalidad == "obra_social" else "Particular"
            m = Movimiento(
                tipo="ingreso",
                descripcion=f"Sesión — {s.paciente.nombre}",
                monto=s.paciente.precio_sesion,
                fecha=s.fecha,
                categoria=f"Sesión cobrada · {modalidad}"
            )
            db.session.add(m)
            db.session.commit()
    return redirect(f"/pacientes/{s.paciente_id}")


@login_required
def eliminar_sesion(id):
    s = Sesion.query.get(id)
    if s:
        pac_id = s.paciente_id
        db.session.delete(s)
        db.session.commit()
    return redirect(f"/pacientes/{pac_id}")


# ── Consultorio ───────────────────────────────────────────

@app.route("/consultorio")
@login_required
def consultorio():
    mes_str = request.args.get("mes", date.today().strftime("%Y-%m"))
    movs = Movimiento.query.filter(Movimiento.fecha.like(f"{mes_str}%")).order_by(Movimiento.fecha.desc()).all()
    ingresos = sum(m.monto for m in movs if m.tipo == "ingreso")
    gastos = sum(m.monto for m in movs if m.tipo == "gasto")
    saldo = ingresos - gastos

    # Desglose OS vs particular desde movimientos reales
    ing_os = sum(m.monto for m in movs if m.tipo == "ingreso" and "Obra social" in m.categoria)
    ing_part = sum(m.monto for m in movs if m.tipo == "ingreso" and "Particular" in m.categoria)
    sesiones_mes = len([m for m in movs if m.tipo == "ingreso"])

    meses = sorted(set(
        m.fecha[:7] for m in Movimiento.query.all()
    ), reverse=True)

    return render_template("consultorio.html",
        movimientos=movs,
        ingresos=ingresos,
        gastos=gastos,
        saldo=saldo,
        ing_os=ing_os,
        ing_part=ing_part,
        sesiones_mes=sesiones_mes,
        mes_seleccionado=mes_str,
        meses=meses,
        fmt_pesos=fmt_pesos
    )


@app.route("/consultorio/agregar", methods=["POST"])
@login_required
def agregar_movimiento():
    m = Movimiento(
        tipo=request.form.get("tipo"),
        descripcion=request.form.get("descripcion"),
        monto=float(request.form.get("monto", 0)),
        fecha=request.form.get("fecha", date.today().strftime("%Y-%m-%d")),
        categoria=request.form.get("categoria", "General")
    )
    db.session.add(m)
    db.session.commit()
    return redirect("/consultorio")


@app.route("/consultorio/eliminar/<int:id>")
@login_required
def eliminar_movimiento(id):
    m = Movimiento.query.get(id)
    if m:
        db.session.delete(m)
        db.session.commit()
    return redirect("/consultorio")


# ── Terapeutas (solo admin) ───────────────────────────────

@app.route("/terapeutas")
@login_required
def terapeutas():
    if not current_user.es_admin:
        return redirect("/")
    lista = Terapeuta.query.all()
    return render_template("terapeutas.html", terapeutas=lista)


@app.route("/terapeutas/agregar", methods=["POST"])
@login_required
def agregar_terapeuta():
    if not current_user.es_admin:
        return redirect("/")
    t = Terapeuta(
        nombre=request.form.get("nombre"),
        especialidad=request.form.get("especialidad", "Terapia Ocupacional"),
        usuario=request.form.get("usuario"),
        password=generate_password_hash(request.form.get("password")),
        telefono=request.form.get("telefono", ""),
        es_admin=False
    )
    db.session.add(t)
    db.session.commit()
    return redirect("/terapeutas")


@app.route("/terapeutas/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar_terapeuta(id):
    if not current_user.es_admin:
        return redirect("/")
    t = Terapeuta.query.get(id)
    if request.method == "POST":
        t.nombre = request.form.get("nombre")
        t.especialidad = request.form.get("especialidad")
        t.telefono = request.form.get("telefono", "")
        nueva_pass = request.form.get("password", "")
        if nueva_pass:
            t.password = generate_password_hash(nueva_pass)
        db.session.commit()
        return redirect("/terapeutas")
    return render_template("editar_terapeuta.html", terapeuta=t)


@app.route("/terapeutas/eliminar/<int:id>")
@login_required
def eliminar_terapeuta(id):
    if not current_user.es_admin:
        return redirect("/")
    t = Terapeuta.query.get(id)
    if t and not t.es_admin:
        db.session.delete(t)
        db.session.commit()
    return redirect("/terapeutas")


# ── Init DB ───────────────────────────────────────────────

with app.app_context():
    db.create_all()
    try:
        with db.engine.connect() as conn:
            conn.execute(db.text("ALTER TABLE terapeuta ALTER COLUMN password TYPE VARCHAR(256)"))
            conn.commit()
    except:
        pass
    # Crear admin por defecto si no existe
    if not Terapeuta.query.filter_by(es_admin=True).first():
        admin = Terapeuta(
            nombre="Andrés Comas",
            especialidad="Terapia Ocupacional Pediátrica",
            usuario="andres",
            password=generate_password_hash("cetop2024"),
            es_admin=True
        )
        db.session.add(admin)
        db.session.commit()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)