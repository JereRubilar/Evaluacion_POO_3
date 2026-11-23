from abc import ABC, abstractmethod


class Empleado(ABC):

    def __init__(self, nombre, direccion, telefono, correo, fecha_inicio_contrato, salario, empleado_id = None):
        self.id = empleado_id
        self.nombre = nombre
        self.direccion = direccion
        self.telefono = telefono
        self.correo = correo
        self.fecha_inicio_contrato = fecha_inicio_contrato
        self.salario = salario

    def validar(self):
        nombre_limpio = (self.nombre or "").strip()
        correo_limpio = (self.correo or "").strip()

        if not nombre_limpio or not any(ch.isalpha() for ch in nombre_limpio):
            raise ValueError("El nombre debe contener letras y no puede ser solo números.")

        if "@" not in correo_limpio or "." not in correo_limpio.split("@")[-1]:
            raise ValueError("Debes ingresar un correo electrónico válido.")

    def __str__(self):
        return f"[ID: {self.id}] Nombre: {self.nombre} - Dirección: {self.direccion} - Telefono {self.telefono} - Correo: {self.correo} - Salario: {self.salario} - Inicio de contrato: {self.fecha_inicio_contrato}\n"

class Gerente(Empleado):

    def __init__(self, nombre, direccion, telefono, correo, fecha_inicio_contrato, salario, presupuesto_asignado, nivel_autorizacion, empleado_id=None):
        super().__init__(nombre, direccion, telefono, correo, fecha_inicio_contrato, salario, empleado_id)
        self.presupuesto_asignado = presupuesto_asignado
        self.nivel_autorizacion = nivel_autorizacion

    def __str__(self):
        return f"[ID: {self.id}] Nombre: {self.nombre} - Dirección: {self.direccion} - Telefono {self.telefono} - Correo: {self.correo} - Salario: {self.salario} - Inicio de contrato: {self.fecha_inicio_contrato} - Presupuesto: {self.presupuesto_asignado} - Nivel de autorizacion: {self.nivel_autorizacion}\n"

class Departamento(ABC):

    def __init__(self, nombre, gerente, empleados, id = None):
        self.id = id
        self.nombre = nombre
        self.gerente = gerente
        self.empleados = empleados
        
    def __str__(self):
        return f"\n[ID: {self.id}] Nombre: {self.nombre} - Gerente: {self.gerente} - Empleados:"

class Proyecto(ABC):

    def __init__(self, nombre, descripcion, fecha_inicio, empleados = None, id = None):
        self.id = id
        self.nombre = nombre
        self.descripcion= descripcion
        self.fecha_inicio = fecha_inicio
        self.empleados = empleados if empleados is not None else []

    def __str__(self):
        return f"\n[ID: {self.id}] Nombre: {self.nombre} - Descripción: {self.descripcion} - Fecha de inicio: {self.fecha_inicio}"

class RegistroTiempo(ABC):

    def __init__(self, fecha, horas_trabajadas, descripcion, empleado, proyecto, id = None):
        self.id = id
        self.fecha = fecha
        self.horas_trabajadas = horas_trabajadas
        self.descripcion = descripcion
        self.empleado = empleado
        self.proyecto = proyecto

    def __str__(self):
        return f"[ID: {self.id}] Fecha: {self.fecha} - Horas_trabajadas: {self.horas_trabajadas} - Descripción: {self.descripcion} - Empleado: {self.empleado} - Proyecto: {self.proyecto}\n"

class Usuario:
    def __init__(self, empleado_id, username, rol="EMPLEADO", activo=True, password_hash=None, usuario_id=None):
        self.id = usuario_id
        self.empleado_id = empleado_id
        self.username = username
        self.rol = rol
        self.activo = activo
        self.password_hash = password_hash

    def __str__(self):
        estado = "Activo" if self.activo else "Inactivo"
        return f"[ID: {self.id}] Usuario: {self.username} - Rol: {self.rol} - Empleado ID: {self.empleado_id} ({estado})"