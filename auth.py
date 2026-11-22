from functools import wraps
from flask import Blueprint, redirect, render_template, request, session, url_for, flash
from werkzeug.security import check_password_hash, generate_password_hash
from conexiones import conexion

auth_bp = Blueprint("auth", __name__)


def login_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Debes iniciar sesión para continuar.", "warning")
            return redirect(url_for("auth.login"))
        return vista(*args, **kwargs)
    return envoltura


def rol_requerido(*roles_permitidos):
    def decorador(vista):
        @wraps(vista)
        @login_requerido
        def envoltura(*args, **kwargs):
            rol_actual = session.get("rol")
            if rol_actual not in roles_permitidos:
                flash("No tienes permisos para acceder a esta sección.", "error")
                return redirect(url_for("dashboard"))
            return vista(*args, **kwargs)
        return envoltura
    return decorador


def obtener_usuario_por_username(username):
    with conexion() as cn:
        cur = cn.cursor(dictionary=True)
        try:
            sql = """
                SELECT u.id, u.empleado_id, u.username, u.password_hash, u.rol, u.activo, e.nombre
                FROM usuario u
                JOIN empleado e ON u.empleado_id = e.id
                WHERE u.username = %s
            """
            cur.execute(sql, (username,))
            return cur.fetchone()
        finally:
            cur.close()


def crear_cuenta_usuario(empleado_id, username, password_plana, rol):
    password_hash = generate_password_hash(password_plana)
    with conexion() as cn:
        cur = cn.cursor()
        try:
            sql = """
                INSERT INTO usuario (empleado_id, username, password_hash, rol, activo)
                VALUES (%s, %s, %s, %s, 1)
            """
            cur.execute(sql, (empleado_id, username, password_hash, rol))
            cn.commit()
            return cur.lastrowid
        except Exception:
            cn.rollback()
            raise
        finally:
            cur.close()


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "usuario_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        usuario = obtener_usuario_por_username(username)
        if not usuario or not usuario["activo"]:
            flash("Usuario inexistente o inactivo.", "error")
            return render_template("login.html")

        if not check_password_hash(usuario["password_hash"], password):
            flash("Contraseña incorrecta.", "error")
            return render_template("login.html")

        session.clear()
        session["usuario_id"] = usuario["id"]
        session["empleado_id"] = usuario["empleado_id"]
        session["username"] = usuario["username"]
        session["nombre"] = usuario["nombre"]
        session["rol"] = usuario["rol"]

        flash(f"¡Bienvenido/a, {usuario['nombre']}!", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@auth_bp.route("/logout")
@login_requerido
def logout():
    session.clear()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("auth.login"))