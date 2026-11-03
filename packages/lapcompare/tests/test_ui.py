"""Drive the real Lap Compare page in a headless browser with a synthetic session.

Skipped unless Playwright and its Chromium are installed.
"""
import io
import socket
import threading
import time

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from racelog.testing import write_two_part_rcz  # noqa: E402


@pytest.fixture(scope="module")
def live_server():
    import uvicorn

    from lapcompare.server import create_app

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
        except Exception as err:
            pytest.skip(f"Chromium isn't installed for Playwright: {err}")
        pg = browser.new_page(viewport={"width": 1300, "height": 900})
        pg.errors = []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        # the tests below send bad files on purpose; the browser logs those expected 422 responses
        pg.on("console", lambda m: pg.errors.append(m.text)
              if m.type == "error" and "status of 422" not in m.text else None)
        pg.goto(live_server)
        yield pg
        browser.close()


@pytest.fixture(scope="module")
def rcz_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("ui") / "session.rcz"
    write_two_part_rcz(path, track_name="Nowhere Raceway")
    return path


def test_upload_shows_charts_and_the_part_menu(page, rcz_path):
    page.set_input_files("#file", str(rcz_path))
    page.wait_for_selector("#lv-plot .main-svg")
    assert "Part 2" in page.locator("#summary select option:checked").inner_text()
    assert page.locator("#lv-laps .chip").count() == 2
    assert page.locator("#lv-plot .scatterlayer .trace").count() >= 1
    assert "Nowhere Raceway" in page.inner_text("#summary")


def test_switching_part_reloads_the_laps(page):
    page.select_option("#summary select", "0")
    page.wait_for_function("document.querySelectorAll('#lv-laps .chip').length === 1")
    page.select_option("#summary select", "1")
    page.wait_for_function("document.querySelectorAll('#lv-laps .chip').length === 2")


def test_table_view(page):
    page.click("#lv-table")
    assert page.locator("#lv-tablewrap table").count() == 1
    page.click("#lv-table")


def test_loading_a_slides_export_marks_them(page, rcz_path):
    from lapcompare.server import match_slides  # noqa: F401  (the page uses the endpoint, not this)

    info = page.evaluate("fetch(location.pathname + 'api/sessions/' + location.hash.split('=')[1]).then(r => r.json())")
    csv = ("rank,lap,source_lap,time_in_lap_s,sector_name,session_id,session_start\n"
           f"1,1,2,12.5,T6,{info['session_id']},{info['session_start']}\n"
           f"2,2,3,4.0,T1,{info['session_id']},{info['session_start']}\n"
           "3,1,2,9.0,T3,elsewhere123,1.0\n")
    page.set_input_files("#slides-file", files=[{"name": "slides.csv", "mimeType": "text/csv", "buffer": csv.encode()}])
    page.wait_for_function("document.querySelector('#slides-msg').textContent.includes('2 slides marked')")
    assert "1 not from this session" in page.inner_text("#slides-msg")
    assert page.locator("#clear-slides").is_visible()
    page.click("#clear-slides")
    assert "choose the CSV exported from SlideFinder" in page.inner_text("#slides-msg")


def test_a_wrong_file_shows_an_error(page):
    page.set_input_files("#slides-file", files=[{"name": "x.csv", "mimeType": "text/csv", "buffer": b"a,b\n1,2\n"}])
    page.wait_for_function("document.querySelector('#slides-msg').textContent.includes('slides export')")


def test_a_bad_session_file_is_refused_on_the_drop_zone(page):
    page.click("text=Open another session")
    page.set_input_files("#file", files=[{"name": "x.csv", "mimeType": "text/csv", "buffer": b"a,b\n1,2\n"}])
    page.wait_for_function("document.querySelector('#drop-msg').textContent.includes('RaceChrono')")


def test_no_javascript_errors(page):
    assert page.errors == []
