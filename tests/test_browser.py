import os, threading, time, socket
from pathlib import Path
import pytest, uvicorn
from playwright.sync_api import sync_playwright
from test_documents import offered


@pytest.mark.browser
def test_desktop_tablet_and_digital_signature(offered, app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [sock]}, daemon=True
    )
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    artifacts = Path(
        os.environ.get("RF_TEST_ARTIFACTS", "/tmp/rentflow-browser-artifacts")
    )
    artifacts.mkdir(exist_ok=True)
    errors = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{port}/login")
            page.locator("[name=email]").fill("admin@example.com")
            page.locator("[name=password]").fill("Testpassword123!")
            page.get_by_role("button", name="Anmelden").click()
            page.wait_for_url(f"http://127.0.0.1:{port}/")
            page.screenshot(
                path=str(artifacts / "dashboard-desktop.png"), full_page=True
            )
            for path in [
                "/customers",
                "/items",
                "/orders",
                f"/orders/{offered}",
                "/settings",
                "/admin/backups",
            ]:
                response = page.goto(f"http://127.0.0.1:{port}" + path)
                assert response.status == 200
                assert page.locator("body").evaluate("(el)=>el.scrollWidth") <= 1440
            page.goto(f"http://127.0.0.1:{port}/orders/{offered}?step=3")
            page.screenshot(path=str(artifacts / "order-desktop.png"), full_page=True)
            from sqlalchemy.orm import Session
            from rentflow.models import Order

            with Session(app.state.engine) as db:
                docid = db.get(Order, offered).offer_id
            page.goto(f"http://127.0.0.1:{port}/documents/" + docid)
            canvas = page.locator("canvas")
            box = canvas.bounding_box()
            assert box
            page.mouse.move(box["x"] + 20, box["y"] + 60)
            page.mouse.down()
            for x, y in [(40, 30), (65, 100), (100, 35), (150, 75), (220, 55)]:
                page.mouse.move(box["x"] + x, box["y"] + y, steps=3)
            page.mouse.up()
            # The canvas form holds the pointer signature as a PNG.
            form = canvas.locator("xpath=ancestor::form")
            form.locator("[name=signer]").fill("Test Kunde")
            form.locator("[name=consent]").check()
            form.get_by_role(
                "button", name="Unterschrift speichern", exact=True
            ).click()
            page.wait_for_load_state("networkidle")
            assert (
                "Unterschrift gespeichert" in page.content()
                or "Unterzeichnet" in page.content()
                or "Unterschrieben" in page.content()
            )
            page.set_viewport_size({"width": 820, "height": 1180})
            page.goto(f"http://127.0.0.1:{port}/orders/{offered}")
            page.screenshot(path=str(artifacts / "order-tablet.png"), full_page=True)
            assert page.locator("body").evaluate("(el)=>el.scrollWidth") <= 820
            page.evaluate("document.documentElement.dataset.theme='dark'")
            page.screenshot(path=str(artifacts / "order-dark.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(f"http://127.0.0.1:{port}/customers")
            assert page.locator("body").evaluate("(el)=>el.scrollWidth") <= 390
            assert errors == [], errors
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
