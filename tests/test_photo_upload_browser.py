from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright, expect


@pytest.mark.browser
def test_parallel_photos_block_submit_until_all_uploads_finish():
    script = (Path(__file__).parents[1] / "src/rentflow/static/app.js").read_text()
    html = """<form><input name="csrf" value="test">
    <section><label><input type="file" class="photo-upload" data-order="test"
    data-target="photos_a"></label><input name="photos_a"><div class="photo-previews"></div></section>
    <section><label><input type="file" class="photo-upload" data-order="test"
    data-target="photos_b"></label><input name="photos_b"><div class="photo-previews"></div></section>
    <button class="primary">Speichern</button></form><script src="/app.js"></script>"""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page()
        page.route(
            "http://rentflow.test/**",
            lambda route: route.fulfill(
                content_type="application/javascript"
                if route.request.url.endswith("/app.js")
                else "text/html",
                body=script if route.request.url.endswith("/app.js") else html,
            ),
        )
        page.goto("http://rentflow.test/")
        page.evaluate("""() => {
            window.uploads=[];
            window.fetch=()=>new Promise(resolve=>uploads.push(resolve));
            window.blocked=[];
            document.querySelector('form').addEventListener('submit',event=>{
                blocked.push(event.defaultPrevented);event.preventDefault();
            });
        }""")
        inputs = page.locator(".photo-upload")
        file = {"name": "photo.png", "mimeType": "image/png", "buffer": b"test"}
        inputs.nth(0).set_input_files(file)
        inputs.nth(1).set_input_files(file)
        button = page.get_by_role("button", name="Speichern")
        expect(button).to_be_disabled()
        page.evaluate("document.querySelector('form').requestSubmit()")
        assert page.evaluate("blocked") == [True]
        page.evaluate(
            """uploads[0]({ok:true,json:async()=>({id:'first',url:'/first.png'})})"""
        )
        expect(page.locator("[name=photos_a]")).to_have_value("first")
        expect(button).to_be_disabled()
        expect(inputs.nth(0)).to_be_enabled()
        expect(inputs.nth(1)).to_be_disabled()
        page.evaluate("document.querySelector('form').requestSubmit()")
        assert page.evaluate("blocked") == [True, True]
        # A failed second upload must also release the form and show its error.
        page.evaluate("uploads[1]({ok:false})")
        expect(button).to_be_enabled()
        expect(inputs.nth(1)).to_be_enabled()
        expect(page.locator(".danger")).to_contain_text("Foto konnte nicht gespeichert")
        expect(page.locator("form")).not_to_have_attribute("aria-busy", "true")
        page.evaluate("document.querySelector('form').requestSubmit()")
        assert page.evaluate("blocked") == [True, True, False]
        browser.close()
