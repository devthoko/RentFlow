import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import sync_playwright, expect
from sqlalchemy.orm import Session

from rentflow.models import Order
from test_documents import offered


@pytest.mark.browser
def test_mobile_tablet_navigation_forms_and_touch_signature(offered, app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    base = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [sock]}, daemon=True
    )
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    artifacts = Path("/tmp/rentflow-mobile-artifacts")
    artifacts.mkdir(exist_ok=True)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox"])
            context = browser.new_context(
                viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base + "/login")
            page.locator("[name=email]").fill("admin@example.com")
            page.locator("[name=password]").fill("Testpassword123!")
            page.get_by_role("button", name="Anmelden").tap()
            page.wait_for_url(base + "/")
            with Session(app.state.engine) as db:
                doc = db.get(Order, offered).offer_id
            paths = [
                "/",
                "/customers",
                "/items",
                "/orders",
                "/orders/new",
                f"/orders/{offered}?step=3",
                f"/documents/{doc}",
                "/settings",
                "/admin/backups",
            ]
            for width, height in [
                (320, 740),
                (390, 844),
                (768, 1024),
                (820, 1180),
                (1024, 768),
            ]:
                page.set_viewport_size({"width": width, "height": height})
                for path in paths:
                    response = page.goto(base + path)
                    assert response.status == 200
                    assert (
                        page.locator("body").evaluate("(el)=>el.scrollWidth") <= width
                    ), (width, path)
                    expect(
                        page.get_by_role("button", name="Menü öffnen")
                    ).to_be_visible()
                    expect(page.get_by_role("navigation")).to_be_hidden()
                page.get_by_role("button", name="Menü öffnen").tap()
                expect(page.get_by_role("navigation")).to_be_visible()
                expect(page.get_by_role("button", name="Abmelden")).to_be_visible()
                page.locator("#theme-toggle").tap()
                assert page.locator("html").get_attribute("data-theme") in (
                    "dark",
                    "light",
                )
                page.screenshot(
                    path=str(artifacts / f"menu-{width}.png"), full_page=True
                )
                page.get_by_role("button", name="Menü schließen").focus()
                page.keyboard.press("Escape")
                expect(page.get_by_role("navigation")).to_be_hidden()
                page.goto(base + f"/orders/{offered}?step=3")
                page.screenshot(
                    path=str(artifacts / f"order-{width}.png"), full_page=True
                )
            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(base + f"/documents/{doc}")
            form = page.locator(".signature-form")
            form.locator("[name=signer]").fill("Mobile Testperson")
            form.locator("[name=consent]").check()
            canvas = form.locator("canvas")
            canvas.evaluate("el => el.scrollIntoView({block: 'center'})")
            page.wait_for_timeout(150)
            box = canvas.bounding_box()
            cdp = context.new_cdp_session(page)
            points = [(20, 70), (40, 30), (75, 120), (110, 40), (160, 90)]
            for index, (x, y) in enumerate(points):
                cdp.send(
                    "Input.dispatchTouchEvent",
                    {
                        "type": "touchStart" if index == 0 else "touchMove",
                        "touchPoints": [{"x": box["x"] + x, "y": box["y"] + y}],
                    },
                )
            cdp.send(
                "Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []}
            )
            page.wait_for_timeout(350)
            form.get_by_role(
                "button", name="Unterschrift speichern", exact=True
            ).click()
            page.wait_for_load_state("networkidle")
            expect(
                page.get_by_role("heading", name="Unterschrift gespeichert")
            ).to_be_visible()
            page.screenshot(path=str(artifacts / "signed-phone.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})
            expect(page.get_by_role("navigation")).to_be_visible()
            expect(page.locator(".mobile-nav-toggle")).to_be_hidden()
            assert not errors, errors
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
