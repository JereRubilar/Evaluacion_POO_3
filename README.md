# Sistema de Gestión de Empleados

Aplicación web desarrollada en Python con Flask y MySQL aplicando Programación Orientada a Objetos (POO) y patrón Repositorio. Permite administrar empleados, gerentes, departamentos, proyectos y registros de horas trabajadas bajo un sistema de autenticación y control de acceso por roles (`ADMIN`, `GERENTE` y `EMPLEADO`). Incluye además un panel con consulta de clima en tiempo real y conversión de divisas mediante APIs externas.

## Requisitos previos

- Python 3.10 o superior
- Servidor MySQL en ejecución
- Acceso a internet (para los servicios externos de clima y tipo de cambio)

## Instalación y configuración

1. **Clonar el repositorio**

   ```bash
   git clone <URL_DEL_REPOSITORIO>
   cd <CARPETA_DEL_PROYECTO>

2. **Crear y activar entorno virtual**

    ```python -m venv .venv
    # En Linux / macOS:
    source .venv/bin/activate
    # En Windows:
    .venv\Scripts\activate

3. **Instalar dependencias**

    ```
    pip install -r requirements.txt

4. **Configurar BBDD**
    Ver archivo [SQL](./script_diagrama_POO.sql)

5. **Cear primer usuario**

```
python -c "from repositorios import UsuarioRepositorio; uid = UsuarioRepositorio().crear_cuenta(2, 'agomez', 'Admin123', 'ADMIN'); print('Usuario creado con ID:', uid)"
``
username: agomez

password: Admin123
