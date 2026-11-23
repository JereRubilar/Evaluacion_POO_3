from datetime import datetime
import os

from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

from auth import auth_bp, crear_cuenta_usuario, login_requerido, rol_requerido
from conexiones import conexion
from modelos import Empleado, Gerente, Proyecto, RegistroTiempo
from repositorios import (
    DepartamentoRepositorio,
    EmpleadoRepositorio,
    PermisosRepositorio,
    ProyectoRepositorio,
    RegistroTiempoRepositorio,
    UsuarioRepositorio
)
from servicios_externos import (
    ServicioExternoError,
    obtener_monedas_disponibles,
    convertir_moneda,
    obtener_clima_ciudad,
    buscar_sugerencias_ciudades
)

load_dotenv()

ROLES_VALIDOS = {"ADMIN", "GERENTE", "EMPLEADO"}

def crear_app():
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_KEY", "FlaskPrueba123!")
    app.register_blueprint(auth_bp)

    emp_repo = EmpleadoRepositorio()
    dep_repo = DepartamentoRepositorio()
    proy_repo = ProyectoRepositorio()
    horas_repo = RegistroTiempoRepositorio()
    perm_repo = PermisosRepositorio()
    usuario_repo=UsuarioRepositorio()

    @app.route("/")
    def index():
        if "usuario_id" in session:
            return redirect(url_for("dashboard"))
        return redirect(url_for("auth.login"))

    @app.route("/api/ciudades")
    @login_requerido
    def api_sugerencias_ciudades():
        q = request.args.get("q", "").strip()
        try:
            sugerencias = buscar_sugerencias_ciudades(q)
            return jsonify(sugerencias)
        except ServicioExternoError:
            return jsonify([])
        
    @app.route("/api/clima")
    @login_requerido
    def api_clima():
        ciudad = request.args.get("ciudad", "").strip()
        try:
            datos = obtener_clima_ciudad(ciudad)
            session["ultima_ciudad"] = datos["ciudad"]
            return jsonify({"ok": True, "data": datos})
        except ServicioExternoError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception:
            return jsonify({"ok": False, "error": "Ocurrió un error inesperado al consultar el clima."}), 500

    @app.route("/api/convertir-moneda")
    @login_requerido
    def api_convertir_moneda():
        monto = request.args.get("monto", "").strip()
        origen = request.args.get("origen", "USD").strip().upper()
        destino = request.args.get("destino", "CLP").strip().upper()
        try:
            datos = convertir_moneda(monto, origen, destino)
            return jsonify({"ok": True, "data": datos})
        except ServicioExternoError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception:
            return jsonify({"ok": False, "error": "Ocurrió un error inesperado al convertir la moneda."}), 500

    @app.route("/dashboard", methods=["GET", "POST"])
    @login_requerido
    def dashboard():
        ciudad_recordada = session.get("ultima_ciudad", "Santiago")
        resultado_clima = None
        resultado_moneda = None
        form_clima = {"ciudad": ciudad_recordada}
        form_moneda = {"monto": "1", "origen": "USD", "destino": "CLP"}
        

        if request.method == "POST":
            accion = request.form.get("accion", "").strip()

            if accion == "clima":
                ciudad = request.form.get("ciudad", "").strip()
                form_clima["ciudad"] = ciudad
                try:
                    resultado_clima = obtener_clima_ciudad(ciudad)
                    ciudad_recordada = resultado_clima["ciudad"]
                    session["ultima_ciudad"] = ciudad_recordada
                    form_clima["ciudad"] = ciudad_recordada
                except ServicioExternoError as exc:
                    flash(str(exc), "error")
                except Exception:
                    flash("Ocurrió un error inesperado al consultar el clima.", "error")

            elif accion == "moneda":
                monto = request.form.get("monto", "").strip()
                origen = request.form.get("moneda_origen", "USD").strip().upper()
                destino = request.form.get("moneda_destino", "CLP").strip().upper()
                form_moneda = {"monto": monto, "origen": origen, "destino": destino}

                try:
                    resultado_moneda = convertir_moneda(monto, origen, destino)
                except ServicioExternoError as exc:
                    flash(str(exc), "error")
                except Exception:
                    flash("Ocurrió un error inesperado al convertir la moneda.", "error")

        if resultado_clima is None:
            try:
                resultado_clima = obtener_clima_ciudad(ciudad_recordada)
            except ServicioExternoError:
                resultado_clima = None

        try:
            monedas_disponibles = obtener_monedas_disponibles()
        except ServicioExternoError:
            monedas_disponibles = [
                ("CLP", "CLP — Peso Chileno"),
                ("USD", "USD — Dólar Estadounidense"),
            ]

        return render_template(
            "dashboard.html",
            resultado_clima=resultado_clima,
            resultado_moneda=resultado_moneda,
            monedas_disponibles=monedas_disponibles,
            form_clima=form_clima,
            form_moneda=form_moneda,
        )


    @app.route("/usuarios/nuevo", methods=["GET", "POST"])
    @rol_requerido("ADMIN")
    def nuevo_usuario():
        empleados = usuario_repo.listar_empleados_para_cuenta()

        if request.method == "POST":
            empleado_id_str = request.form.get("empleado_id", "").strip()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            rol = request.form.get("rol", "EMPLEADO").strip().upper()

            if not empleado_id_str or not username or not password:
                flash("Completa todos los campos obligatorios.", "error")
                return render_template("crear_usuario.html", empleados=empleados)

            if rol not in ROLES_VALIDOS:
                flash("El rol seleccionado no es válido.", "error")
                return render_template("crear_usuario.html", empleados=empleados)

            try:
                empleado_id_num = int(empleado_id_str)
                if empleado_id_num < 1:
                    raise ValueError("El empleado seleccionado no es válido.")
                usuario_repo.crear_cuenta(empleado_id_num, username, password, rol)
                flash(f"Cuenta '{username}' creada con rol {rol}.", "success")
                return redirect(url_for("dashboard"))
            except ValueError as exc:
                flash(str(exc), "error")
            except Exception:
                flash("No se pudo crear la cuenta. Verifica que el usuario o empleado no estén ya registrados.", "error")

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
            except ValueError as exc:
                flash(str(exc), "error")
            except Exception:
                flash("No se pudo crear el empleado. Revisa los datos ingresados (por ejemplo, que el correo no exista).", "error")

        return render_template("crear_empleados.html", departamentos=departamentos)

    @app.route("/empleados/<int:empleado_id>/eliminar", methods=["POST"])
    @rol_requerido("ADMIN")
    def eliminar_empleado_web(empleado_id):
        try:
            emp_repo.eliminar(empleado_id)
            flash("Empleado eliminado.", "success")
        except Exception:
            flash("No se pudo eliminar el empleado.", "error")
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
        except ValueError as exc:
            flash(str(exc), "error")
        except Exception:
            flash("No se pudo crear el departamento.", "error")
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
        except PermissionError as exc:
            flash(str(exc), "error")
        except Exception:
            flash("No se pudo actualizar el departamento del empleado.", "error")
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
        except PermissionError as exc:
            flash(str(exc), "error")
        except Exception:
            flash("No se pudo actualizar el departamento del empleado.", "error")
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
        except ValueError as exc:
            flash(str(exc), "error")
        except Exception:
            flash("No se pudo crear el proyecto.", "error")
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
        except PermissionError as exc:
            flash(str(exc), "error")
        except Exception:
            flash("No se pudo actualizar la asignación del proyecto.", "error")
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
        except PermissionError as exc:
            flash(str(exc), "error")
        except Exception:
            flash("No se pudo actualizar la asignación del proyecto.", "error")
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
            except (ValueError, PermissionError) as exc:
                flash(str(exc), "error")
            except Exception:
                flash("No se pudo registrar las horas.", "error")

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
    modo_debug = os.getenv("FLASK_DEBUG", "false").strip().lower() in ("1", "true", "yes")
    app.run(host="127.0.0.1", port=5000, debug=modo_debug)