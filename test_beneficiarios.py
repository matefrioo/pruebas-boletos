import os
import re
import secrets

from playwright.sync_api import Page, expect


def campo(page: Page, etiqueta: str):
    return (
        page.locator("form")
        .locator("label")
        .filter(has_text=re.compile(rf"^{re.escape(etiqueta)} \*$"))
        .locator("+ input")
    )


def test_cp01_alta_exitosa(page: Page):
    # Generamos un DNI sintético de ocho dígitos.
    dni = str(90000000 + secrets.randbelow(10000000))

    # Reconoce el DNI con o sin puntos en la tabla.
    patron_dni = re.compile(
        r"^\s*"
        + r"\.?".join(re.escape(digito) for digito in dni)
        + r"\s*$"
    )

    estado_activo = re.compile(r"^\s*activo\s*$", re.IGNORECASE)

    # 1. Iniciar sesión.
    page.goto("https://proyectos-qhp3.vercel.app/")

    page.get_by_role(
        "textbox", name="Ingrese su email institucional"
    ).fill(os.environ["TEST_EMAIL"])

    page.get_by_role(
        "textbox", name="Ingrese su contraseña"
    ).fill(os.environ["TEST_PASSWORD"])

    page.get_by_role("button", name="Iniciar sesión").click()

    expect(page).to_have_url(re.compile(r".*/#dashboard$"))

    # 2. Abrir Beneficiarios.
    page.get_by_role(
        "button",
        name="Beneficiarios Padron y consulta",
        exact=True,
    ).click()

    buscador = page.get_by_placeholder(
        "Buscar por DNI, nombre o localidad",
        exact=True,
    )
    expect(buscador).to_be_visible()

    # 3. Comprobar que el DNI no aparece en el listado.
    buscador.fill("")

    fila = page.locator("tbody tr").filter(
        has=page.get_by_role("cell", name=patron_dni)
    )
    expect(fila).to_have_count(0)

    # 4. Abrir y completar el formulario.
    page.get_by_role(
        "button", name="Nuevo beneficiario", exact=True
    ).click()

    datos = {
        "Nombre": "Prueba",
        "Apellido": "Automatizacion",
        "DNI": dni,
        "Fecha de nacimiento": "1950-01-01",
        "Dirección": "Calle de Prueba 123",
        "Barrio": "Centro",
        "Localidad": "Oberá",
    }

    for etiqueta, valor in datos.items():
        campo(page, etiqueta).fill(valor)

    # 5. Registrar al beneficiario.
    page.get_by_role(
        "button", name="Registrar Beneficiario", exact=True
    ).click()

    expect(
        page.get_by_role(
            "button", name="Registrar Beneficiario", exact=True
        )
    ).not_to_be_visible(timeout=15000)

    # 6. Buscar y comprobar el registro creado.
    buscador.fill(dni)

    expect(fila).to_have_count(1, timeout=15000)

    nombre_listado = fila.get_by_role("cell").nth(1)
    expect(nombre_listado).to_contain_text("Prueba")
    expect(nombre_listado).to_contain_text("Automatizacion")

    expect(
        fila.get_by_role("cell").nth(3)
    ).to_have_text(estado_activo)

    # 7. Recargar y comprobar que el registro persiste.
    page.reload()

    page.get_by_role(
        "button",
        name="Beneficiarios Padron y consulta",
        exact=True,
    ).click()

    buscador.fill(dni)

    expect(fila).to_have_count(1, timeout=15000)
    expect(
        fila.get_by_role("cell").nth(3)
    ).to_have_text(estado_activo)

    # 8. Abrir la ficha y comprobar su estado.
    fila.get_by_role(
        "button", name="Ver", exact=True
    ).click()

    estado_ficha = (
        page.locator("dt")
        .filter(has_text=re.compile(r"^Estado$"))
        .locator("+ dd")
    )

    expect(estado_ficha).to_have_text(estado_activo)