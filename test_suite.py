import os
import re
import secrets
from datetime import date, timedelta

from playwright.sync_api import Page, expect


URL = "https://proyectos-qhp3.vercel.app/"
EDAD_MINIMA_REQUERIDA = int(os.getenv("EDAD_MINIMA_REQUERIDA", "60"))


def campo(page: Page, etiqueta: str):
    return (
        page.locator("form label")
        .filter(has_text=re.compile(rf"^{re.escape(etiqueta)} \*$"))
        .locator("+ input")
    )


def nuevo_dni() -> str:
    return str(90000000 + secrets.randbelow(10000000))


def patron_dni(dni: str):
    return re.compile(
        r"^\s*" + r"[.\s]*".join(re.escape(c) for c in dni) + r"\s*$"
    )


def iniciar_sesion(page: Page):
    page.goto(URL)
    page.get_by_role(
        "textbox", name="Ingrese su email institucional"
    ).fill(os.environ["TEST_EMAIL"])
    page.get_by_role(
        "textbox", name="Ingrese su contraseña"
    ).fill(os.environ["TEST_PASSWORD"])
    page.get_by_role("button", name="Iniciar sesión").click()
    expect(page).to_have_url(re.compile(r".*/#dashboard$"))


def abrir_beneficiarios(page: Page):
    page.get_by_role(
        "button",
        name="Beneficiarios Padron y consulta",
        exact=True,
    ).click()


def abrir_recargas(page: Page):
    page.get_by_role(
        "button",
        name="Recargas Acreditacion de boletos",
        exact=True,
    ).click()


def fila_dni(page: Page, dni: str):
    return page.locator("tbody tr").filter(
        has=page.get_by_role("cell", name=patron_dni(dni))
    )


def buscar_dni(page: Page, dni: str):
    buscador = page.get_by_placeholder(
        "Buscar por DNI, nombre o localidad", exact=True
    )
    buscador.fill(dni)
    return fila_dni(page, dni)


def completar_alta(
    page: Page,
    dni: str,
    nombre: str = "Prueba",
    apellido: str = "QA",
    nacimiento: str = "1950-01-01",
    direccion: str = "Calle de Prueba 123",
    barrio: str = "Centro",
    localidad: str = "Oberá",
):
    page.get_by_role(
        "button", name="Nuevo beneficiario", exact=True
    ).click()

    valores = {
        "Nombre": nombre,
        "Apellido": apellido,
        "DNI": dni,
        "Fecha de nacimiento": nacimiento,
        "Dirección": direccion,
        "Barrio": barrio,
        "Localidad": localidad,
    }

    for etiqueta, valor in valores.items():
        campo(page, etiqueta).fill(valor)


def crear_beneficiario_activo(
    page: Page,
    *,
    nombre: str = "Prueba",
    apellido: str = "QA",
    nacimiento: str = "1950-01-01",
    direccion: str = "Calle de Prueba 123",
    barrio: str = "Centro",
    localidad: str = "Oberá",
):
    dni = nuevo_dni()
    abrir_beneficiarios(page)
    completar_alta(
        page,
        dni,
        nombre,
        apellido,
        nacimiento,
        direccion,
        barrio,
        localidad,
    )
    page.get_by_role(
        "button", name="Registrar Beneficiario", exact=True
    ).click()

    expect(
        page.get_by_role(
            "button", name="Registrar Beneficiario", exact=True
        )
    ).not_to_be_visible(timeout=15000)

    fila = buscar_dni(page, dni)
    expect(fila).to_have_count(1, timeout=15000)
    expect(fila.get_by_role("cell").nth(3)).to_have_text(
        re.compile(r"^\s*activo\s*$", re.IGNORECASE)
    )
    return dni


def saldo_listado(page: Page, dni: str) -> int:
    abrir_beneficiarios(page)
    fila = buscar_dni(page, dni)
    expect(fila).to_have_count(1, timeout=15000)
    texto = fila.get_by_role("cell").nth(4).inner_text()
    numeros = re.findall(r"\d+", texto)
    assert numeros, f"No pude leer el saldo de la fila: {texto!r}"
    return int(numeros[0])


def fecha_hace_anios(anios: int) -> str:
    hoy = date.today()
    try:
        nacimiento = hoy.replace(year=hoy.year - anios)
    except ValueError:
        nacimiento = hoy.replace(year=hoy.year - anios, day=28)
    return nacimiento.isoformat()


def completar_recarga(page: Page, dni: str, cantidad: str):
    abrir_recargas(page)
    page.get_by_placeholder("Ej: 12345678", exact=True).fill(dni)
    page.get_by_role("spinbutton").fill(cantidad)


def confirmar_dialogo_nativo(page: Page):
    page.on("dialog", lambda dialog: dialog.accept())


# CP-01: alta válida, estado activo y persistencia tras recargar.
def test_cp01_alta_exitosa(page: Page):
    iniciar_sesion(page)
    dni = crear_beneficiario_activo(page)

    page.reload()
    abrir_beneficiarios(page)
    fila = buscar_dni(page, dni)

    expect(fila).to_have_count(1, timeout=15000)
    expect(fila.get_by_role("cell").nth(3)).to_have_text(
        re.compile(r"^\s*activo\s*$", re.IGNORECASE)
    )


# CP-02: rechazar a una persona claramente menor que la edad mínima.
def test_cp02_rechazo_por_edad(page: Page):
    iniciar_sesion(page)
    abrir_beneficiarios(page)

    dni = nuevo_dni()
    completar_alta(page, dni, nacimiento=fecha_hace_anios(30))
    page.get_by_role(
        "button", name="Registrar Beneficiario", exact=True
    ).click()

    expect(
        page.get_by_text(
            "El beneficiario debe tener al menos 50 años",
            exact=True,
        )
    ).to_be_visible()
    expect(page.locator("form")).to_be_visible()


# CP-04: un DNI ya registrado no debe generar una segunda fila.
def test_cp04_dni_duplicado(page: Page):
    iniciar_sesion(page)
    dni = crear_beneficiario_activo(page)

    abrir_beneficiarios(page)
    completar_alta(page, dni)
    page.get_by_role(
        "button", name="Registrar Beneficiario", exact=True
    ).click()

    fila = buscar_dni(page, dni)
    expect(fila).to_have_count(1, timeout=15000)


# CP-05: acreditar el máximo permitido de 15 boletos.
def test_cp05_recarga_de_15(page: Page):
    iniciar_sesion(page)
    dni = crear_beneficiario_activo(page)
    saldo_inicial = saldo_listado(page, dni)

    completar_recarga(page, dni, "15")
    page.get_by_role("button", name="Recargar", exact=True).click()

    assert saldo_listado(page, dni) == saldo_inicial + 15


# CP-06: 16 boletos deben superar el límite HTML de 15.
def test_cp06_rechazo_de_16_boletos(page: Page):
    iniciar_sesion(page)
    dni = crear_beneficiario_activo(page)
    saldo_inicial = saldo_listado(page, dni)

    completar_recarga(page, dni, "16")
    cantidad = page.get_by_role("spinbutton")

    assert cantidad.evaluate("(el) => el.validity.rangeOverflow")
    assert not cantidad.evaluate("(el) => el.validity.valid")
    assert saldo_listado(page, dni) == saldo_inicial


# CP-07: una persona dada de baja no debe aceptar una recarga.
def test_cp07_rechazo_a_beneficiario_dado_de_baja(page: Page):
    iniciar_sesion(page)
    dni = crear_beneficiario_activo(page)

    fila = buscar_dni(page, dni)
    page.on("dialog", lambda dialog: dialog.accept())
    fila.get_by_role(
        "button", name="Dar de baja", exact=True
    ).click()

    fila = buscar_dni(page, dni)
    expect(fila.get_by_role("cell").nth(3)).to_have_text(
        re.compile(r"^\s*baja\s*$", re.IGNORECASE),
        timeout=15000,
    )
    saldo_inicial = saldo_listado(page, dni)

    completar_recarga(page, dni, "1")
    page.get_by_role("button", name="Recargar", exact=True).click()

    assert saldo_listado(page, dni) == saldo_inicial


# CP-8: dar de baja un beneficiario de prueba.
def test_cp08_baja_de_beneficiario(page: Page):
    iniciar_sesion(page)
    dni = crear_beneficiario_activo(page)

    fila = buscar_dni(page, dni)
    page.on("dialog", lambda dialog: dialog.accept())
    fila.get_by_role(
        "button", name="Dar de baja", exact=True
    ).click()

    fila = buscar_dni(page, dni)
    expect(fila.get_by_role("cell").nth(3)).to_have_text(
        re.compile(r"^\s*baja\s*$", re.IGNORECASE),
        timeout=15000,
    )


# CP-9: el formulario vacío no debe completar un alta.
def test_cp09_alta_con_campos_vacios(page: Page):
    iniciar_sesion(page)
    abrir_beneficiarios(page)
    page.get_by_role(
        "button", name="Nuevo beneficiario", exact=True
    ).click()

    page.get_by_role(
        "button", name="Registrar Beneficiario", exact=True
    ).click()

    expect(page.locator("form")).to_be_visible()


# CP-10: modificar domicilio y comprobarlo en la ficha.
def test_cp10_modificacion_de_domicilio(page: Page):
    iniciar_sesion(page)
    dni = crear_beneficiario_activo(page)

    fila = buscar_dni(page, dni)
    fila.get_by_role("button", name="Editar", exact=True).click()

    nueva_direccion = f"Calle QA {secrets.randbelow(9000) + 1000}"
    campo(page, "Dirección").fill(nueva_direccion)
    page.get_by_role(
        "button", name="Guardar cambios", exact=True
    ).click()

    fila = buscar_dni(page, dni)
    fila.get_by_role("button", name="Ver", exact=True).click()

    domicilio = (
        page.locator("dt")
        .filter(has_text=re.compile(r"^Domicilio$"))
        .locator("+ dd")
    )
    expect(domicilio).to_contain_text(nueva_direccion)


# CP-11: consultar un DNI inexistente sin ejecutar una recarga.
def test_cp11_dni_inexistente_en_recargas(page: Page):
    iniciar_sesion(page)
    abrir_recargas(page)

    dni = "99999998"
    page.get_by_placeholder("Ej: 12345678", exact=True).fill(dni)

    expect(
        page.get_by_text(
            "No se encontró un beneficiario con ese DNI.",
            exact=True,
        )
    ).to_be_visible()


# CP-12: cero y valores negativos deben ser inválidos.
def test_cp12_cero_y_negativo(page: Page):
    iniciar_sesion(page)
    dni = crear_beneficiario_activo(page)

    completar_recarga(page, dni, "0")
    cantidad = page.get_by_role("spinbutton")
    assert cantidad.evaluate("(el) => el.validity.rangeUnderflow")
    assert not cantidad.evaluate("(el) => el.validity.valid")

    cantidad.fill("-1")
    assert cantidad.evaluate("(el) => el.validity.rangeUnderflow")
    assert not cantidad.evaluate("(el) => el.validity.valid")


# CP-13: rechazar un DNI alfanumérico.
def test_cp13_dni_alfanumerico(page: Page):
    iniciar_sesion(page)
    abrir_beneficiarios(page)

    dni = "AB123456"
    completar_alta(page, dni)
    page.get_by_role(
        "button", name="Registrar Beneficiario", exact=True
    ).click()

    buscador = page.get_by_placeholder(
        "Buscar por DNI, nombre o localidad", exact=True
    )
    buscador.fill(dni)
    expect(
        page.get_by_text("No se encontraron beneficiarios.", exact=True)
    ).to_be_visible(timeout=15000)


# CP-14: campos obligatorios vacíos no deben borrar datos al editar.
def test_cp14_edicion_con_campos_vacios(page: Page):
    iniciar_sesion(page)
    dni = crear_beneficiario_activo(page)

    fila = buscar_dni(page, dni)
    fila.get_by_role("button", name="Editar", exact=True).click()

    for etiqueta in (
        "Nombre",
        "Apellido",
        "DNI",
        "Fecha de nacimiento",
        "Dirección",
        "Barrio",
        "Localidad",
    ):
        campo(page, etiqueta).fill("")

    page.get_by_role(
        "button", name="Guardar cambios", exact=True
    ).click()

    expect(page.locator("form")).to_be_visible()


# CP-16: acreditar el mínimo válido de 1 boleto.
def test_cp16_recarga_de_un_boleto(page: Page):
    iniciar_sesion(page)
    dni = crear_beneficiario_activo(page)
    saldo_inicial = saldo_listado(page, dni)

    completar_recarga(page, dni, "1")
    page.get_by_role("button", name="Recargar", exact=True).click()

    assert saldo_listado(page, dni) == saldo_inicial + 1


# CP-17: una cantidad fraccionaria debe ser inválida.
def test_cp17_recarga_fraccionaria(page: Page):
    iniciar_sesion(page)
    dni = crear_beneficiario_activo(page)
    saldo_inicial = saldo_listado(page, dni)

    completar_recarga(page, dni, "2.5")
    cantidad = page.get_by_role("spinbutton")

    assert cantidad.evaluate("(el) => el.validity.stepMismatch")
    assert not cantidad.evaluate("(el) => el.validity.valid")
    assert saldo_listado(page, dni) == saldo_inicial


# CP-18: según el caso, Recargar debe estar deshabilitado si falta cantidad.
# La inspección observó que está habilitado; es posible que esta prueba falle.
def test_cp18_boton_bloqueado_sin_cantidad(page: Page):
    iniciar_sesion(page)
    abrir_recargas(page)

    cantidad = page.get_by_role("spinbutton")
    cantidad.fill("")

    expect(page.get_by_role(
        "button", name="Recargar", exact=True
    )).to_be_disabled()


# CP-19: validar la frontera indicada por el requisito.
# Configurá EDAD_MINIMA_REQUERIDA=65 si el requisito aplicable es 65.
def test_cp19_edad_en_limite_requerido(page: Page):
    assert EDAD_MINIMA_REQUERIDA in (60, 65), (
        "Definí EDAD_MINIMA_REQUERIDA como 60 o 65 según el requisito."
    )

    iniciar_sesion(page)
    abrir_beneficiarios(page)

    hoy = date.today()
    nacimiento_limite = fecha_hace_anios(EDAD_MINIMA_REQUERIDA)
    dni_limite = nuevo_dni()

    completar_alta(
        page,
        dni_limite,
        nombre="Limite",
        apellido="QA",
        nacimiento=nacimiento_limite,
    )
    page.get_by_role(
        "button", name="Registrar Beneficiario", exact=True
    ).click()

    expect(
        page.get_by_role(
            "button", name="Registrar Beneficiario", exact=True
        )
    ).not_to_be_visible(timeout=15000)

    # Un día más joven que la edad requerida debe rechazarse.
    nacimiento_menor = (
        date.fromisoformat(nacimiento_limite) + timedelta(days=1)
    ).isoformat()
    dni_menor = nuevo_dni()

    abrir_beneficiarios(page)
    completar_alta(
        page,
        dni_menor,
        nombre="Menor",
        apellido="QA",
        nacimiento=nacimiento_menor,
    )
    page.get_by_role(
        "button", name="Registrar Beneficiario", exact=True
    ).click()

    expect(
        page.get_by_text(
            f"El beneficiario debe tener al menos "
            f"{EDAD_MINIMA_REQUERIDA} años",
            exact=True,
        )
    ).to_be_visible()


# CP-20: el texto ingresado debe mostrarse como texto, no como HTML.
def test_cp20_sanitizacion_de_texto(page: Page):
    iniciar_sesion(page)
    abrir_beneficiarios(page)

    dni = nuevo_dni()
    texto = "QA <b>texto</b>"
    completar_alta(page, dni, nombre=texto)

    page.get_by_role(
        "button", name="Registrar Beneficiario", exact=True
    ).click()

    fila = buscar_dni(page, dni)
    expect(fila).to_have_count(1, timeout=15000)
    expect(fila.get_by_role("cell").nth(1)).to_contain_text(texto)
    expect(fila.locator("b")).to_have_count(0)


# CP-21: buscar un beneficiario usando parte del apellido.
def test_cp21_busqueda_por_apellido_parcial(page: Page):
    iniciar_sesion(page)
    apellido = f"ApellidoQA{secrets.randbelow(100000)}"
    dni = crear_beneficiario_activo(page, apellido=apellido)

    fila = buscar_dni(page, dni)
    expect(fila).to_have_count(1)

    buscador = page.get_by_placeholder(
        "Buscar por DNI, nombre o localidad", exact=True
    )
    buscador.fill(apellido[:10])

    expect(
        page.locator("tbody tr").filter(
            has_text=re.compile(re.escape(apellido[:10]), re.IGNORECASE)
        )
    ).to_have_count(1)


# CP-23: los puntos y espacios del DNI deben normalizarse al ingresarlo.
def test_cp23_normalizacion_de_dni_en_recargas(page: Page):
    iniciar_sesion(page)
    dni = crear_beneficiario_activo(page)

    abrir_recargas(page)
    campo_dni = page.get_by_placeholder("Ej: 12345678", exact=True)

    campo_dni.fill(f"{dni[:2]}.{dni[2:5]}.{dni[5:]}")
    expect(campo_dni).to_have_value(dni)

    campo_dni.fill(f"{dni[:2]} {dni[2:5]} {dni[5:]}")
    expect(campo_dni).to_have_value(dni)