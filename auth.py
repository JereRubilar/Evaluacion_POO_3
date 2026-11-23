from functools import wraps
from flask import Blueprint, redirect, render_template, request, session, url_for, flash
from werkzeug.security import check_password_hash
from repositorios import UsuarioRepositorio

auth_bp = Blueprint("auth", __name__)
usuario_repo = UsuarioRepositorio()


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
    return usuario_repo.obtener_por_username(username)


def crear_cuenta_usuario(empleado_id, username, password_plana, rol):
    return usuario_repo.crear_cuenta(empleado_id, username, password_plana, rol)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "usuario_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        usuario = usuario_repo.obtener_por_username(username)
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