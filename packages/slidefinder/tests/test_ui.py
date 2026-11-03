"""Drive the real web page in a headless browser with a synthetic session.

Skipped unless Playwright and its Chromium are installed (`pip install playwright` and
`playwright install chromium`).
"""
import socket
import threading
import time

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from racelog.testing import write_racechrono_csv  # noqa: E402


@pytest.fixture(scope="module")
def live_server():
    import uvicorn

    from slidefinder.server import create_app

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def page(live_server):
    with playwright.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as err:   # browser binaries not downloaded
            pytest.skip(f"Chromium isn't installed for Playwright: {err}")
        pg = browser.new_page(viewport={"width": 1300, "height": 900})
        pg.errors = []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        pg.on("console", lambda m: pg.errors.append(m.text) if m.type == "error" else None)
        pg.goto(live_server)
        yield pg
        browser.close()


@pytest.fixture(scope="module")
def csv_path(tmp_path_factory):
    from racelog.testing import make_session

    path = tmp_path_factory.mktemp("ui") / "session.csv"
    write_racechrono_csv(make_session([(10.0, 0.6), (30.0, 3.0)]), path, track="Nowhere Raceway")
    return path


def test_upload_shows_ranked_slides_with_clips(page, csv_path):
    page.set_input_files("#file", str(csv_path))
    page.wait_for_selector("#slides-table tbody tr")
    assert page.inner_text("#count") == "1 slide"                    # strict drops the 0.6 s one
    assert "Nowhere Raceway" in page.inner_text("#summary")
    assert "No track file" in page.inner_text("#summary")
    assert page.locator("#slides-table tbody tr").first.locator(".clip").inner_text().startswith("Clip")


def test_sensitivity_changes_the_count(page):
    page.click("#sens button:text('Balanced')")
    page.wait_for_function("document.querySelector('#count').textContent.startsWith('2')")
    page.click("#sens button:text('Strict')")
    page.wait_for_function("document.querySelector('#count').textContent.startsWith('1')")


def test_advanced_slider_makes_it_custom_and_reset_restores(page):
    page.click("#advanced summary")
    page.locator("#adv-fields input[type=range]").first.evaluate(
        "el => { el.value = 0.4; el.dispatchEvent(new Event('input', {bubbles: true})); }")
    page.wait_for_function("document.querySelector('#count').textContent.startsWith('Custom')")
    assert page.locator("#sens button[aria-checked=true]").count() == 0
    page.click("#reset")
    page.wait_for_function("document.querySelector('#count').textContent === '1 slide'")


def test_hide_and_restore_a_slide(page):
    page.click("#slides-table tbody tr:first-child .rowbtn:text('Not a slide')")
    assert page.inner_text("#count") == "0 slides"
    page.click("#toggle-hidden")
    page.click("#slides-table tbody tr.hidden-row .rowbtn:text('Restore')")
    assert page.inner_text("#count") == "1 slide"


def test_offset_moves_the_clip(page):
    first = lambda: page.locator("#slides-table tbody tr").first.locator(".clip").inner_text()
    page.fill("#cliplen", "0:20"); page.fill("#tstart", "0")
    page.wait_for_function("document.querySelector('.clip').textContent.includes('Clip 2')")   # 30 s -> clip 2
    page.fill("#offset", "-15")
    page.wait_for_function("document.querySelector('.clip').textContent.includes('Clip 1')")   # 15 s -> clip 1
    assert first().startswith("Clip 1")


def test_sync_helper_solves_the_offset(page):
    page.click("#sync summary")
    page.fill("#sync-clip", "2"); page.fill("#sync-time", "00:05")
    page.click("#sync-go")
    page.wait_for_function("document.querySelector('#sync-msg').textContent.includes('Offset set')")
    # slide at 30 s, seen 5 s into clip 2 (clips are 20 s) -> video 25 s -> offset -5
    assert float(page.input_value("#offset")) == pytest.approx(-5.0, abs=0.1)


def test_there_is_no_lap_viewer_on_this_page(page):
    assert page.locator("#tab-laps-btn, #lv-plot, .tabs").count() == 0
    assert page.locator("#slides-table tbody .rowbtn:text('View')").count() == 0
    assert page.locator("#slides-table tbody .rowbtn:text('Not a slide')").count() >= 1


def test_no_javascript_errors(page):
    assert page.errors == []


def test_rcz_upload_with_a_part_selector(page, tmp_path_factory):
    import dataclasses

    from racelog.testing import make_session
    from racelog.testing import write_racechrono_rcz

    first = make_session([])
    second = dataclasses.replace(make_session([(30.0, 3.0)]), t0=first.t0 + 6 * 3600)
    path = tmp_path_factory.mktemp("ui_rcz") / "session.rcz"
    write_racechrono_rcz(path, [first, second], [[(1, 0.0, None)], [(2, 0.0, 30.0), (3, 30.0, None)]],
                         track_name="Nowhere Raceway")
    page.click("text=Open another session")
    page.set_input_files("#file", str(path))
    page.wait_for_selector("#summary select")
    assert "Part 2" in page.locator("#summary select option:checked").inner_text()
    page.wait_for_function("document.querySelector('#count').textContent === '1 slide'")
    page.select_option("#summary select", "0")
    page.wait_for_function("document.querySelector('#count').textContent === '0 slides'")
    page.select_option("#summary select", "1")
    page.wait_for_function("document.querySelector('#count').textContent === '1 slide'")
    assert page.errors == []
