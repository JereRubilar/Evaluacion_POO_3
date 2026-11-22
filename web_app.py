from datetime import datetime
import os

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for

from auth import auth_bp, crear_cuenta_usuario, login_requerido, rol_requerido
from conexiones import conexion
from modelos import Empleado, Gerente, Proyecto, RegistroTiempo
from repositorios import (
    DepartamentoRepositorio,
    EmpleadoRepositorio,
    PermisosRepositorio,
    ProyectoRepositorio,
    RegistroTiempoRepositorio,
)

load_dotenv()


def crear_app():
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "FlaskPrueba123!")
    app.register_blueprint(auth_bp)

    emp_repo = EmpleadoRepositorio()
    dep_repo = DepartamentoRepositorio()
    proy_repo = ProyectoRepositorio()
    horas_repo = RegistroTiempoRepositorio()
    perm_repo = PermisosRepositorio()

    @app.route("/")
    def index():
        if "usuario_id" in session:
            return redirect(url_for("dashboard"))
        return redirect(url_for("auth.login"))

    @app.route("/dashboard")
    @login_requerido
    def dashboard():
        return render_template("dashboard.html")

    @app.route("/usuarios/nuevo", methods=["GET", "POST"])
    @rol_requerido("ADMIN")
    def nuevo_usuario():
        with conexion() as cn:
            cur = cn.cursor(dictionary=True)
            try:
                cur.execute("SELECT id, nombre, correo FROM empleado ORDER BY nombre")
                empleados = cur.fetchall()
            finally:
                cur.close()

        if request.method == "POST":
            empleado_id = request.form.get("empleado_id", "").strip()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            rol = request.form.get("rol", "EMPLEADO").strip()

            if not empleado_id or not username or not password:
                flash("Completa todos los campos obligatorios.", "error")
                return render_template("crear_usuario.html", empleados=empleados)

            try:
                crear_cuenta_usuario(int(empleado_id), username, password, rol)
                flash(f"Cuenta '{username}' creada con rol {rol}.", "success")
                return redirect(url_for("dashboard"))
            except Exception as exc:
                flash(f"No se pudo crear la cuenta: {exc}", "error")

        return render_template("crear_usuario.html", empleados=empleados)

    @app.route("/empleados")
    @rol_requerido("ADMIN", "GERENTE")
    def listar_empleados():
        rol = session.get("rol")
        emp_sesion = int(session.get("empleado_id"))
        todos = emp_repo.listar()

        if rol == "GERENTE":
            cargo_ids = perm_repo.ids_empleados_a_cargo(emp_sesion)
            empleados = [e for e in todos if e.id in cargo_ids]
        else:
            empleados = todos

        return render_template("empleados.html", empleados=empleados)

    @app.route("/empleados/nuevo", methods=["GET", "POST"])
    @rol_requerido("ADMIN")
    def crear_empleado_web():
        departamentos = dep_repo.listar()
        if request.method == "POST":
            try:
                tipo = request.form.get("tipo", "E").upper().strip()
                nombre = request.form.get("nombre", "").strip()
                direccion = request.form.get("direccion", "").strip()
                telefono = request.form.get("telefono", "").strip()
                correo = request.form.get("correo", "").strip()
                fecha_str = request.form.get("fecha_inicio_contrato", "").strip()
                salario_str = request.form.get("salario", "0").replace(",", ".").strip()
                dep_id_str = request.form.get("departamento_id", "").strip()

                if not nombre or not correo or not fecha_str:
                    raise ValueError("Nombre, correo y fecha de inicio son obligatorios.")

                fecha_fmt = datetime.strptime(fecha_str, "%Y-%m-%d").strftime("%Y-%m-%d %H:%M:%S")
                salario = float(salario_str)
                if salario < 0:
                    raise ValueError("El salario no puede ser negativo.")

                if tipo == "E":
                    nuevo = Empleado(nombre, direccion, telefono, correo, fecha_fmt, salario)
                elif tipo == "G":
                    presupuesto = float(request.form.get("presupuesto_asignado", "0").replace(",", ".").strip())
                    nivel = int(request.form.get("nivel_autorizacion", "1").strip())
                    if presupuesto < 0 or nivel < 1:
                        raise ValueError("Presupuesto y nivel de autorización inválidos.")
                    nuevo = Gerente(nombre, direccion, telefono, correo, fecha_fmt, salario, presupuesto, nivel)
                else:
                    raise ValueError("Tipo de empleado inválido.")

                if dep_id_str:
                    nuevo.departamento_id = int(dep_id_str)

                emp_repo.crear(nuevo)
                flash(f"Empleado registrado con ID {nuevo.id}.", "success")
                return redirect(url_for("listar_empleados"))
            except Exception as exc:
                flash(f"No se pudo crear el empleado: {exc}", "error")

        return render_template("crear_empleado.html", departamentos=departamentos)

    @app.route("/empleados/<int:empleado_id>/eliminar", methods=["POST"])
    @rol_requerido("ADMIN")
    def eliminar_empleado_web(empleado_id):
        try:
            emp_repo.eliminar(empleado_id)
            flash("Empleado eliminado.", "success")
        except Exception as exc:
            flash(f"No se pudo eliminar: {exc}", "error")
        return redirect(url_for("listar_empleados"))

    @app.route("/departamentos")
    @rol_requerido("ADMIN", "GERENTE")
    def listar_departamentos_web():
        rol = session.get("rol")
        emp_sesion = int(session.get("empleado_id"))
        departamentos = dep_repo.listar()
        todos_empleados = emp_repo.listar()

        if rol == "GERENTE":
            cargo_ids = perm_repo.ids_empleados_a_cargo(emp_sesion)
            empleados_selector = [e for e in todos_empleados if e.id in cargo_ids]
        else:
            empleados_selector = todos_empleados

        detalle_deps = []
        for dep in departamentos:
            emps_dep = dep_repo.empleados_de(dep.id)
            if rol == "GERENTE":
                cargo_ids = perm_repo.ids_empleados_a_cargo(emp_sesion)
                emps_dep = [e for e in emps_dep if e.id in cargo_ids]
            detalle_deps.append({
                "dep": dep,
                "empleados": emps_dep,
            })

        return render_template(
            "departamentos.html",
            detalle_deps=detalle_deps,
            departamentos=departamentos,
            empleados=empleados_selector,
        )

    @app.route("/departamentos/nuevo", methods=["POST"])
    @rol_requerido("ADMIN")
    def crear_departamento_web():
        try:
            nombre = request.form.get("nombre", "").strip()
            gerente_str = request.form.get("gerente_id", "").strip()
            if not nombre:
                raise ValueError("El nombre del departamento es obligatorio.")
            gerente_id = int(gerente_str) if gerente_str else None
            dep = dep_repo.crear(nombre, gerente_id)
            flash(f"Departamento '{dep.nombre}' creado (ID {dep.id}).", "success")
        except Exception as exc:
            flash(f"Error al crear departamento: {exc}", "error")
        return redirect(url_for("listar_departamentos_web"))

    @app.route("/departamentos/asignar", methods=["POST"])
    @rol_requerido("ADMIN", "GERENTE")
    def asignar_departamento_web():
        try:
            dep_id = int(request.form.get("departamento_id"))
            emp_id = int(request.form.get("empleado_id"))
            if session.get("rol") == "GERENTE" and not perm_repo.puede_gestionar_empleado_como_gerente(
                int(session.get("empleado_id")), emp_id
            ):
                raise PermissionError("Solo puedes gestionar empleados bajo tu cargo.")
            dep_repo.asignar_empleado(dep_id, emp_id)
            flash("Empleado asignado al departamento.", "success")
        except Exception as exc:
            flash(f"Error al asignar: {exc}", "error")
        return redirect(url_for("listar_departamentos_web"))

    @app.route("/departamentos/quitar", methods=["POST"])
    @rol_requerido("ADMIN", "GERENTE")
    def quitar_departamento_web():
        try:
            emp_id = int(request.form.get("empleado_id"))
            if session.get("rol") == "GERENTE" and not perm_repo.puede_gestionar_empleado_como_gerente(
                int(session.get("empleado_id")), emp_id
            ):
                raise PermissionError("Solo puedes gestionar empleados bajo tu cargo.")
            dep_repo.quitar_empleado(None, emp_id)
            flash("Empleado quitado del departamento.", "success")
        except Exception as exc:
            flash(f"Error al quitar del departamento: {exc}", "error")
        return redirect(url_for("listar_departamentos_web"))

    @app.route("/proyectos")
    @rol_requerido("ADMIN", "GERENTE", "EMPLEADO")
    def listar_proyectos_web():
        rol = session.get("rol")
        emp_sesion = int(session.get("empleado_id"))

        todos_proyectos = proy_repo.listar()
        todos_empleados = emp_repo.listar()

        if rol == "EMPLEADO":
            proy_ids = perm_repo.ids_proyectos_de_empleado(emp_sesion)
            proyectos = [p for p in todos_proyectos if p.id in proy_ids]
            empleados_disponibles = []
        elif rol == "GERENTE":
            cargo_ids = perm_repo.ids_empleados_a_cargo(emp_sesion)
            proyectos = todos_proyectos
            empleados_disponibles = [e for e in todos_empleados if e.id in cargo_ids]
        else:
            proyectos = todos_proyectos
            empleados_disponibles = todos_empleados

        detalle_proys = []
        for proy in proyectos:
            emps_proy = proy_repo.empleados_de(proy.id)
            if rol == "EMPLEADO":
                emps_proy = [e for e in emps_proy if e.id == emp_sesion]
            detalle_proys.append({
                "proyecto": proy,
                "empleados": emps_proy,
                "total_horas": horas_repo.total_horas_proyecto(proy.id),
            })

        return render_template(
            "proyectos.html",
            detalle_proys=detalle_proys,
            proyectos=proyectos,
            empleados=empleados_disponibles,
        )

    @app.route("/proyectos/nuevo", methods=["POST"])
    @rol_requerido("ADMIN")
    def crear_proyecto_web():
        try:
            nombre = request.form.get("nombre", "").strip()
            descripcion = request.form.get("descripcion", "").strip()
            fecha_str = request.form.get("fecha_inicio", "").strip()
            if not nombre or not fecha_str:
                raise ValueError("Nombre y fecha de inicio son obligatorios.")
            fecha_fmt = datetime.strptime(fecha_str, "%Y-%m-%d").strftime("%Y-%m-%d %H:%M:%S")
            proyecto = Proyecto(nombre, descripcion, fecha_fmt)
            proy_repo.crear(proyecto)
            flash(f"Proyecto '{proyecto.nombre}' creado con ID {proyecto.id}.", "success")
        except Exception as exc:
            flash(f"No se pudo crear el proyecto: {exc}", "error")
        return redirect(url_for("listar_proyectos_web"))

    @app.route("/proyectos/asignar", methods=["POST"])
    @rol_requerido("ADMIN", "GERENTE")
    def asignar_proyecto_web():
        try:
            proy_id = int(request.form.get("proyecto_id"))
            emp_id = int(request.form.get("empleado_id"))
            if session.get("rol") == "GERENTE" and not perm_repo.puede_gestionar_empleado_como_gerente(
                int(session.get("empleado_id")), emp_id
            ):
                raise PermissionError("Solo puedes asignar empleados bajo tu cargo.")
            proy_repo.asignar_empleado(proy_id, emp_id)
            flash("Empleado asignado al proyecto.", "success")
        except Exception as exc:
            flash(f"No se pudo asignar al proyecto: {exc}", "error")
        return redirect(url_for("listar_proyectos_web"))

    @app.route("/proyectos/desasignar", methods=["POST"])
    @rol_requerido("ADMIN", "GERENTE")
    def desasignar_proyecto_web():
        try:
            proy_id = int(request.form.get("proyecto_id"))
            emp_id = int(request.form.get("empleado_id"))
            if session.get("rol") == "GERENTE" and not perm_repo.puede_gestionar_empleado_como_gerente(
                int(session.get("empleado_id")), emp_id
            ):
                raise PermissionError("Solo puedes desasignar empleados bajo tu cargo.")
            proy_repo.desasignar_empleado(proy_id, emp_id)
            flash("Empleado desasignado del proyecto.", "success")
        except Exception as exc:
            flash(f"No se pudo desasignar del proyecto: {exc}", "error")
        return redirect(url_for("listar_proyectos_web"))

    @app.route("/horas", methods=["GET", "POST"])
    @rol_requerido("ADMIN", "GERENTE", "EMPLEADO")
    def gestion_horas_web():
        todos_proyectos = proy_repo.listar()
        todos_empleados = emp_repo.listar()
        rol_actual = session.get("rol")
        emp_sesion_id = int(session.get("empleado_id"))

        if rol_actual == "EMPLEADO":
            proy_ids = perm_repo.ids_proyectos_de_empleado(emp_sesion_id)
            proyectos = [p for p in todos_proyectos if p.id in proy_ids]
            empleados_permitidos = [e for e in todos_empleados if e.id == emp_sesion_id]
        elif rol_actual == "GERENTE":
            cargo_ids = perm_repo.ids_empleados_a_cargo(emp_sesion_id)
            proyectos = todos_proyectos
            empleados_permitidos = [e for e in todos_empleados if e.id in cargo_ids]
        else:
            proyectos = todos_proyectos
            empleados_permitidos = todos_empleados

        ids_permitidos = {e.id for e in empleados_permitidos}

        if request.method == "POST":
            try:
                fecha_str = request.form.get("fecha", "").strip()
                horas_val = float(request.form.get("horas_trabajadas", "0").replace(",", ".").strip())
                descripcion = request.form.get("descripcion", "").strip()
                proy_id = int(request.form.get("proyecto_id"))

                if rol_actual == "EMPLEADO":
                    emp_id = emp_sesion_id
                else:
                    emp_id = int(request.form.get("empleado_id"))

                if emp_id not in ids_permitidos:
                    raise PermissionError("No tienes permiso para registrar horas de este empleado.")
                if rol_actual == "EMPLEADO" and proy_id not in perm_repo.ids_proyectos_de_empleado(emp_sesion_id):
                    raise PermissionError("Solo puedes registrar horas en proyectos donde participas.")
                if not fecha_str or not descripcion or horas_val < 0:
                    raise ValueError("Datos inválidos para el registro de horas.")

                fecha_fmt = datetime.strptime(fecha_str, "%Y-%m-%d").strftime("%Y-%m-%d %H:%M:%S")
                registro = RegistroTiempo(fecha_fmt, horas_val, descripcion, emp_id, proy_id)
                horas_repo.registrar(registro)
                flash(f"Horas registradas con ID {registro.id}.", "success")
                return redirect(url_for("gestion_horas_web", empleado_id=emp_id))
            except Exception as exc:
                flash(f"Error al registrar horas: {exc}", "error")

        if rol_actual == "EMPLEADO":
            consulta_emp_id = emp_sesion_id
        else:
            consulta_emp_str = request.args.get("empleado_id", "").strip()
            solicitado_id = int(consulta_emp_str) if consulta_emp_str else None
            if solicitado_id and solicitado_id in ids_permitidos:
                consulta_emp_id = solicitado_id
            else:
                consulta_emp_id = empleados_permitidos[0].id if empleados_permitidos else None

        registros = horas_repo.listar_por_empleado(consulta_emp_id) if consulta_emp_id else []
        if rol_actual == "EMPLEADO":
            mis_proys = perm_repo.ids_proyectos_de_empleado(emp_sesion_id)
            registros = [r for r in registros if r.proyecto in mis_proys]

        return render_template(
            "horas.html",
            proyectos=proyectos,
            empleados=empleados_permitidos,
            registros=registros,
            consulta_emp_id=consulta_emp_id,
        )

    return app


if __name__ == "__main__":
    app = crear_app()
    app.run(debug=True)