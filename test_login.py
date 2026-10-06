import os
import re
from playwright.sync_api import Page, expect


def test_login_administrador(page: Page) -> None:
    page.goto("https://proyectos-qhp3.vercel.app/")

    page.get_by_role(
        "textbox", name="Ingrese su email institucional"
    ).fill(os.environ["TEST_EMAIL"])

    page.get_by_role(
        "textbox", name="Ingrese su contraseña"
    ).fill(os.environ["TEST_PASSWORD"])

    page.get_by_role("button", name="Iniciar sesión").click()

    expect(page).to_have_url(re.compile(r".*/#dashboard$"))