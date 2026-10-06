import os
import re

from playwright.sync_api import Page, expect
from test_beneficiarios import campo


def test_cp02_rechazo_por_edad(page: Page):
    # DNI usado en la inspección, donde no quedó registrado.
    dni = "99002602"

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

    page.get_by_role(
        "button",
        name="Beneficiarios Padron y consulta",
        exact=True,
    ).click()

    buscador = page.get_by_placeholder(
        "Buscar por DNI, nombre o localidad", exact=True
    )
    sin_resultados = page.get_by_text(
        "No se encontraron beneficiarios.", exact=True
    )

    # 2. Comprobar que el DNI no esté registrado.
    buscador.fill(dni)
    expect(sin_resultados).to_be_visible(timeout=15000)

    # 3. Completar el alta con una persona menor de la edad mínima.
    page.get_by_role(
        "button", name="Nuevo beneficiario", exact=True
    ).click()

    datos = {
        "Nombre": "PruebaEdad",
        "Apellido": "Automatizacion",
        "DNI": dni,
        "Fecha de nacimiento": "1996-01-01",
        "Dirección": "Calle de Prueba 123",
        "Barrio": "Centro",
        "Localidad": "Oberá",
    }

    for etiqueta, valor in datos.items():
        campo(page, etiqueta).fill(valor)

    page.get_by_role(
        "button", name="Registrar Beneficiario", exact=True
    ).click()

    # 4. Comprobar el rechazo y la conservación de los datos.
    mensaje = page.get_by_text(
        "El beneficiario debe tener al menos 50 años",
        exact=True,
    )
    expect(mensaje).to_be_visible()
    expect(page.locator("form")).to_be_visible()

    for etiqueta, valor in datos.items():
        expect(campo(page, etiqueta)).to_have_value(valor)

    # 5. Cancelar y comprobar que no aparece registrado.
    page.get_by_role(
        "button", name="Cancelar", exact=True
    ).click()

    expect(page.locator("form")).to_have_count(0)
    buscador.fill(dni)
    expect(sin_resultados).to_be_visible(timeout=15000)

    # 6. Repetir la consulta después de recargar la página.
    page.reload()
    expect(buscador).to_be_visible()
    buscador.fill(dni)
    expect(sin_resultados).to_be_visible(timeout=15000)