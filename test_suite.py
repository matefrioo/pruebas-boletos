import os
import re
import secrets
from datetime import date, timedelta

import pytest
from playwright.sync_api import Page, expect


URL = "https://proyectos-qhp3.vercel.app/"
EDAD_MINIMA_REQUERIDA = os.getenv("EDAD_MINIMA_REQUERIDA")


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

def esperar_saldo(page: Page, dni: str, saldo_esperado: int):
    abrir_beneficiarios(page)
    fila = buscar_dni(page, dni)
    expect(fila).to_have_count(1, timeout=3000)

    celda_saldo = fila.get_by_role("cell").nth(4)
    expect(celda_saldo).to_have_text(str(saldo_esperado), timeout=3000)

def fecha_hace_anios(anios: int) -> str:
    hoy = date.today()
    try:
        nacimiento = hoy.replace(year=hoy.year - anios)
    except ValueError:
        nacimiento = hoy.replace(year=hoy.year - anios, day=28)
    return nacimiento.isoformat()


def completar_recarga(page: Page, dni: str, cantidad: str):
    abrir_recargas(page)
    campo_dni = page.get_by_placeholder("Ej: 12345678", exact=True)
    campo_dni.fill(dni)
    expect(campo_dni).to_have_value(dni)

    campo_cantidad = page.get_by_role("spinbutton")
    campo_cantidad.fill(cantidad)
    expect(campo_cantidad).to_have_value(cantidad)


def aceptar_confirmacion_si_aparece(page: Page):
    # Playwright descarta por defecto los diálogos nativos. En operaciones que
    # se esperan completar, aceptar aquí asegura que se prueba el flujo positivo.
    page.once("dialog", lambda dialog: dialog.accept())


def edad_minima_configurada() -> int:
    if EDAD_MINIMA_REQUERIDA not in ("60", "65"):
        pytest.skip(
            "Requisito ambiguo en la documentación: configurar "
            "EDAD_MINIMA_REQUERIDA=60 o 65 antes de ejecutar los casos de edad."
        )
    return int(EDAD_MINIMA_REQUERIDA)


def dni_de_prueba_configurado(variable: str, estado: str) -> str:
    dni = os.getenv(variable)
    if not dni:
        pytest.skip(
            f"Falta {variable}: preparar un beneficiario de prueba en estado "
            f"{estado!r}; el caso no se considera ejecutado."
        )
    return dni


def mensaje_de_error_visible(page: Page):
    return page.locator(
        "[role='alert'], .text-destructive, [data-sonner-toast]"
    ).filter(has_text=re.compile(r"\S"))


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

    expect(mensaje_de_error_visible(page).first).to_be_visible()
    expect(page.locator("form")).to_be_visible()


# CP-02.1 / CP-02.2: edades bajo el requisito configurado deben rechazarse.
# La app observada informa un mínimo de 50; con el requisito 60/65 estos casos
# pueden revelar un incumplimiento. La expectativa se mantiene según el requisito.
@pytest.mark.parametrize(
    "edad",
    [pytest.param(59, id="59-anios"), pytest.param(50, id="50-anios")],
)
def test_cp02_rechazo_de_edad_bajo_el_minimo(page: Page, edad: int):
    iniciar_sesion(page)
    abrir_beneficiarios(page)

    completar_alta(
        page,
        nuevo_dni(),
        nombre="Edad",
        apellido="QA",
        nacimiento=fecha_hace_anios(edad),
    )
    page.get_by_role(
        "button", name="Registrar Beneficiario", exact=True
    ).click()

    expect(
        page.get_by_text(
            re.compile(r"El beneficiario debe tener al menos \d+ años", re.IGNORECASE)
        )
    ).to_be_visible()
    expect(page.locator("form")).to_be_visible()


# CP-03: provocar un HTTP 500 en la API de validación de residencia.
# CP03_API_URL_REGEX debe ser una expresión regular acotada a esa API, obtenida
# de la pestaña Network. Sin ese dato se reporta como bloqueado, no aprobado.
def test_cp03_residencia_no_validada_con_error_api(page: Page):
    patron_api = os.getenv("CP03_API_URL_REGEX")
    if not patron_api:
        pytest.skip(
            "Bloqueado: configurar CP03_API_URL_REGEX con la URL observada "
            "para la API de validación de residencia."
        )

    llamadas_interceptadas = []

    def responder_error_500(route):
        llamadas_interceptadas.append(route.request.url)
        route.fulfill(status=500, content_type="application/json", body='{"error":"simulated test failure"}')

    page.route(re.compile(patron_api), responder_error_500)
    iniciar_sesion(page)
    abrir_beneficiarios(page)
    dni = nuevo_dni()
    completar_alta(
        page,
        dni,
        nombre="Residencia",
        apellido="QA",
        localidad="Campo Viera",
    )
    page.get_by_role("button", name="Registrar Beneficiario", exact=True).click()

    assert llamadas_interceptadas, (
        "No se llamó a la API configurada durante el alta; revisar la integración "
        "de validación de residencia o el patrón CP03_API_URL_REGEX."
    )
    expect(mensaje_de_error_visible(page).first).to_be_visible()
    formulario = page.locator("form")
    if formulario.is_visible():
        page.get_by_role("button", name="Cancelar", exact=True).click()
        expect(formulario).to_have_count(0)
    expect(buscar_dni(page, dni)).to_have_count(0, timeout=15000)


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



# CP-05: acreditar cantidades válidas de 14 y 15 boletos.
@pytest.mark.parametrize(
    "cantidad",
    [
        pytest.param("14", id="14-boletos"),
        pytest.param("15", id="15-boletos"),
    ],
)
def test_cp05_recarga_en_limite_superior(page: Page, cantidad: str):
    iniciar_sesion(page)
    dni = crear_beneficiario_activo(page)
    saldo_inicial = saldo_listado(page, dni)

    # Pasos basados en la grabación de Playwright.
    page.get_by_role(
        "button", name="Recargas Acreditacion de"
    ).click()

    campo_dni = page.get_by_role("textbox", name="Ej:")
    campo_dni.fill(dni)
    expect(campo_dni).to_have_value(dni)

    campo_cantidad = page.get_by_role("spinbutton")
    campo_cantidad.fill(cantidad)
    expect(campo_cantidad).to_have_value(cantidad)

    page.get_by_role("button", name="Recargar").click()

    # Se espera que el saldo aumente exactamente la cantidad ingresada.
    esperar_saldo(page, dni, saldo_inicial + int(cantidad))


# CP-06: cantidades superiores a 15 deben superar el límite HTML.
@pytest.mark.parametrize(
    "cantidad_invalida",
    [pytest.param("16", id="16-boletos"), pytest.param("50", id="50-boletos")],
)
def test_cp06_rechazo_de_cantidad_superior_al_maximo(
    page: Page, cantidad_invalida: str
):
    iniciar_sesion(page)
    dni = crear_beneficiario_activo(page)
    saldo_inicial = saldo_listado(page, dni)

    completar_recarga(page, dni, cantidad_invalida)
    cantidad = page.get_by_role("spinbutton")

    assert cantidad.evaluate("(el) => el.validity.rangeOverflow")
    assert not cantidad.evaluate("(el) => el.validity.valid")
    page.get_by_role("button", name="Recargar", exact=True).click()
    assert saldo_listado(page, dni) == saldo_inicial


# CP-07.1 / CP-07.2: no se debe recargar a beneficiarios Inactivo o Suspendido.
# Se usan datos sembrados para no sustituir esos estados por "Baja".
@pytest.mark.parametrize(
    ("variable_dni", "estado"),
    [
        pytest.param("CP07_DNI_INACTIVO", "Inactivo", id="inactivo"),
        pytest.param("CP07_DNI_SUSPENDIDO", "Suspendido", id="suspendido"),
    ],
)
def test_cp07_rechazo_de_recarga_por_estado_no_habilitado(
    page: Page, variable_dni: str, estado: str
):
    iniciar_sesion(page)
    dni = dni_de_prueba_configurado(variable_dni, estado)
    abrir_beneficiarios(page)
    fila = buscar_dni(page, dni)
    expect(fila).to_have_count(1)
    expect(fila.get_by_role("cell").nth(3)).to_have_text(
        re.compile(rf"^\s*{re.escape(estado)}\s*$", re.IGNORECASE)
    )
    saldo_inicial = saldo_listado(page, dni)

    completar_recarga(page, dni, "1")
    boton_recargar = page.get_by_role("button", name="Recargar", exact=True)
    if boton_recargar.is_enabled():
        aceptar_confirmacion_si_aparece(page)
        boton_recargar.click()

    assert saldo_listado(page, dni) == saldo_inicial


# CP-8: dar de baja un beneficiario de prueba.
# CP-08: dar de baja un beneficiario de prueba.
def test_cp08_baja_de_beneficiario(page: Page):
    iniciar_sesion(page)
    dni = crear_beneficiario_activo(page)

    fila = buscar_dni(page, dni)
    expect(fila).to_have_count(1)

    fila.get_by_role(
        "button", name="Dar de baja", exact=True
    ).click()

    confirmar_baja = page.get_by_role(
        "button", name="Confirmar baja", exact=True
    )
    expect(confirmar_baja).to_be_visible()
    confirmar_baja.click()

    fila = buscar_dni(page, dni)
    expect(fila).to_have_count(1)
    expect(fila.get_by_role("cell").nth(3)).to_have_text(
        re.compile(r"^\s*baja\s*$", re.IGNORECASE),
        timeout=15000,
    )

# CP-15: reactivar un beneficiario Inactivo. Se exige una fixture dedicada;
# no se transforma artificialmente una Baja o una suspensión en Inactivo.
def test_cp15_reactivacion_de_beneficiario_inactivo(page: Page):
    iniciar_sesion(page)
    dni = dni_de_prueba_configurado("CP15_DNI_INACTIVO", "Inactivo")
    abrir_beneficiarios(page)
    fila = buscar_dni(page, dni)
    expect(fila).to_have_count(1)
    expect(fila.get_by_role("cell").nth(3)).to_have_text(
        re.compile(r"^\s*inactivo\s*$", re.IGNORECASE)
    )

    accion_reactivar = fila.get_by_role(
        "button", name=re.compile(r"reactivar|activar|desbloquear", re.IGNORECASE)
    )
    expect(accion_reactivar).to_have_count(1)
    aceptar_confirmacion_si_aparece(page)
    accion_reactivar.click()

    fila = buscar_dni(page, dni)
    expect(fila.get_by_role("cell").nth(3)).to_have_text(
        re.compile(r"^\s*activo\s*$", re.IGNORECASE), timeout=15000
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
@pytest.mark.parametrize(
    "cantidad_invalida",
    [pytest.param("0", id="cero"), pytest.param("-1", id="negativo")],
)
def test_cp12_cantidad_cero_o_negativa(page: Page, cantidad_invalida: str):
    iniciar_sesion(page)
    dni = crear_beneficiario_activo(page)
    saldo_inicial = saldo_listado(page, dni)

    completar_recarga(page, dni, cantidad_invalida)
    cantidad = page.get_by_role("spinbutton")
    assert cantidad.evaluate("(el) => el.validity.rangeUnderflow")
    assert not cantidad.evaluate("(el) => el.validity.valid")
    page.get_by_role("button", name="Recargar", exact=True).click()
    assert saldo_listado(page, dni) == saldo_inicial


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
    aceptar_confirmacion_si_aparece(page)
    page.get_by_role("button", name="Recargar", exact=True).click()

    esperar_saldo(page, dni, saldo_inicial + 1)


# CP-17: cantidades fraccionarias deben ser inválidas.
@pytest.mark.parametrize(
    "cantidad_fraccionaria",
    [pytest.param("0.5", id="medio-boleto"), pytest.param("2.5", id="dos-y-medio")],
)
def test_cp17_recarga_fraccionaria(page: Page, cantidad_fraccionaria: str):
    iniciar_sesion(page)
    dni = crear_beneficiario_activo(page)
    saldo_inicial = saldo_listado(page, dni)

    completar_recarga(page, dni, cantidad_fraccionaria)
    cantidad = page.get_by_role("spinbutton")

    assert cantidad.evaluate("(el) => el.validity.stepMismatch")
    assert not cantidad.evaluate("(el) => el.validity.valid")
    page.get_by_role("button", name="Recargar", exact=True).click()
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


# CP-18.1: repetir el caso de cantidad vacía en emulación móvil Android.
@pytest.mark.only_browser("chromium")
def test_cp18_movil_android_sin_cantidad(browser, playwright):
    contexto = browser.new_context(**playwright.devices["Pixel 5"])
    page = contexto.new_page()
    page.set_default_timeout(10000)

    try:
        iniciar_sesion(page)

        boton_recargas = page.get_by_role(
            "button", name="Recargas", exact=True
        )
        expect(boton_recargas).to_be_visible(timeout=10000)
        boton_recargas.click(timeout=10000)

        cantidad = page.get_by_role("spinbutton")
        expect(cantidad).to_be_visible(timeout=10000)
        cantidad.fill("")

        boton_recargar = page.get_by_role(
            "button", name="Recargar", exact=True
        )
        expect(boton_recargar).to_be_disabled(timeout=10000)
    finally:
        contexto.close()

# CP-19: validar la frontera indicada por el requisito.
# Configurá EDAD_MINIMA_REQUERIDA=65 si el requisito aplicable es 65.
def test_cp19_edad_en_limite_requerido(page: Page):
    edad_minima = edad_minima_configurada()

    iniciar_sesion(page)
    abrir_beneficiarios(page)

    hoy = date.today()
    nacimiento_limite = fecha_hace_anios(edad_minima)
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
            f"{edad_minima} años",
            exact=True,
        )
    ).to_be_visible()


# CP-20: entradas con marcado o carga XSS se deben mostrar como texto.
@pytest.mark.parametrize(
    "texto",
    [
        pytest.param("QA <b>texto</b>", id="etiqueta-html"),
        pytest.param("<script>alert('XSS')</script>", id="etiqueta-script"),
        pytest.param('\"><img src=x onerror=alert(1)>', id="atributo-onerror"),
    ],
)
def test_cp20_sanitizacion_de_texto(page: Page, texto: str):
    iniciar_sesion(page)
    abrir_beneficiarios(page)

    dni = nuevo_dni()
    completar_alta(page, dni, nombre=texto)

    dialogos = []

    def cerrar_dialogo(dialog):
        dialogos.append((dialog.type, dialog.message))
        dialog.dismiss()

    page.on("dialog", cerrar_dialogo)

    page.get_by_role(
        "button", name="Registrar Beneficiario", exact=True
    ).click()

    fila = buscar_dni(page, dni)
    expect(fila).to_have_count(1, timeout=15000)
    celda_nombre = fila.get_by_role("cell").nth(1)
    # La tabla representa la columna como "Apellido, Nombre".
    expect(celda_nombre).to_have_text(f"QA, {texto}")
    expect(celda_nombre.locator("b, script, img[onerror]")).to_have_count(0)
    assert not dialogos, f"Se abrió un diálogo por la entrada: {dialogos!r}"


# CP-20 Manual: variante de seguridad requerida en Firefox.
@pytest.mark.only_browser("firefox")
def test_cp20_manual_sanitizacion_firefox(page: Page):
    texto = "<script>alert('XSS')</script>"
    iniciar_sesion(page)
    dni = nuevo_dni()
    abrir_beneficiarios(page)
    completar_alta(page, dni, nombre=texto)

    dialogos = []

    def capturar_dialogo(dialog):
        dialogos.append((dialog.type, dialog.message))
        dialog.dismiss()

    page.on("dialog", capturar_dialogo)
    page.get_by_role("button", name="Registrar Beneficiario", exact=True).click()
    fila = buscar_dni(page, dni)
    expect(fila).to_have_count(1, timeout=15000)
    celda_nombre = fila.get_by_role("cell").nth(1)
    expect(celda_nombre).to_have_text(f"QA, {texto}")
    expect(celda_nombre.locator("script")).to_have_count(0)
    assert not dialogos, f"Se ejecutó un diálogo con payload XSS: {dialogos!r}"


# CP-21: buscar un beneficiario usando parte del apellido.
def test_cp21_busqueda_por_apellido_parcial(page: Page):
    iniciar_sesion(page)
    abrir_beneficiarios(page)

    token = "".join(
        secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(8)
    )
    fragmento = token[:6]
    apellido = f"ApellidoQA{token}"

    buscador = page.get_by_placeholder(
        "Buscar por DNI, nombre o localidad", exact=True
    )

    # Comprueba que el fragmento no coincida con datos anteriores.
    buscador.fill(fragmento)
    filas_coincidentes = page.locator("tbody tr").filter(
        has_text=re.compile(re.escape(fragmento), re.IGNORECASE)
    )
    expect(filas_coincidentes).to_have_count(0, timeout=10000)

    dni = crear_beneficiario_activo(page, apellido=apellido)

    buscador.fill(fragmento)
    filas_coincidentes = page.locator("tbody tr").filter(
        has_text=re.compile(re.escape(fragmento), re.IGNORECASE)
    )
    expect(filas_coincidentes).to_have_count(1, timeout=15000)

    fila = filas_coincidentes.filter(
        has=page.get_by_role("cell", name=patron_dni(dni))
    )
    expect(fila).to_have_count(1)
    expect(fila.get_by_role("cell").nth(1)).to_contain_text(fragmento)


# CP-23: el buscador de DNI debe tolerar puntos y espacios.
@pytest.mark.parametrize(
    "separador",
    [pytest.param(".", id="puntos"), pytest.param(" ", id="espacios")],
)
def test_cp23_normalizacion_de_dni_en_recargas(page: Page, separador: str):
    iniciar_sesion(page)
    dni = crear_beneficiario_activo(page)

    abrir_recargas(page)
    campo_dni = page.get_by_placeholder("Ej: 12345678", exact=True)
    entrada = f"{dni[:2]}{separador}{dni[2:5]}{separador}{dni[5:]}"
    campo_dni.fill(entrada)
    expect(campo_dni).to_have_value(dni)



# CP-22: la recarga debe pedir confirmación y poder cancelarse.
def test_cp22_cancelacion_de_confirmacion_de_recarga(page: Page):
    iniciar_sesion(page)
    dni = crear_beneficiario_activo(page)
    saldo_inicial = saldo_listado(page, dni)

    # Pasos obtenidos con Playwright Codegen.
    page.get_by_role("button", name="Recargas Acreditacion de").click()
    page.get_by_role("textbox", name="Ej:").fill(dni)
    page.get_by_role("spinbutton").fill("1")

    dialogos = []

    def cancelar_dialogo(dialog):
        dialogos.append((dialog.type, dialog.message))
        dialog.dismiss()

    page.once("dialog", cancelar_dialogo)
    page.get_by_role("button", name="Recargar", exact=True).click()

    assert dialogos, (
        "CP-22 falló: no se mostró una confirmación cancelable "
        "al iniciar la recarga."
    )
    assert dialogos[0][0] == "confirm", (
        f"Se esperaba una confirmación; se observó {dialogos[0][0]!r}."
    )

    assert saldo_listado(page, dni) == saldo_inicial