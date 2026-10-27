import base64
from pathlib import Path

from aidb_locator.models import (
    SchemaInfo,
    WActivity,
    WApplication,
    WFragment,
    WView,
)


def _fake_app() -> WApplication:
    # Bounds in WView are parent-relative — DecorView at (0,0,1080,2340).
    # Container is at parent-relative (0, 100, 1080, 1000) → absolute (0, 100, 1080, 1000).
    # TextView is parent-relative (50, 80, 350, 160) inside container →
    #   absolute (0+50, 100+80, 0+350, 100+160) = (50, 180, 350, 260).
    root = WView(class_name="DecorView", left=0, top=0, right=1080, bottom=2340)
    container = WView(class_name="FrameLayout", left=0, top=100, right=1080, bottom=1000)
    child = WView(
        class_name="TextView",
        id_str="tv_title",
        text="hello",
        left=50, top=80, right=350, bottom=160,
        mem_addr="abc123",
    )
    container.children.append(child)
    root.children.append(container)
    return WApplication(
        package_name="com.example",
        activity=WActivity(
            class_name="HomeActivity",
            decor_views=[root],
            fragments=[WFragment(class_name="HomeFragment", is_visible=True)],
        ),
        screen_width=1080,
        screen_height=2340,
        density=2.75,
        schemas=[SchemaInfo(schema="demo://home")],
    )


def test_snapshot_returns_screenshot_layout_activity(client, monkeypatch, tmp_path):
    png_bytes = b"\x89PNG\r\n\x1a\nFAKE"
    png_file = tmp_path / "shot.png"
    png_file.write_bytes(png_bytes)

    monkeypatch.setattr(
        "aidb_locator.ui.api.snapshot.CodeLocator.grab_layout",
        lambda self: _fake_app(),
    )
    monkeypatch.setattr(
        "aidb_locator.ui.api.snapshot.NativeAdb.screenshot",
        lambda self, output=None: png_file,
    )

    resp = client.get("/api/snapshot")
    assert resp.status_code == 200
    body = resp.json()

    assert base64.b64decode(body["screenshot_png_b64"]) == png_bytes
    assert body["device_size"] == {"width": 1080, "height": 2340}
    assert body["activity"]["activity"] == "HomeActivity"
    assert body["activity"]["fragments"] == ["HomeFragment"]
    assert body["layout"]["class_name"] == "DecorView"
    assert body["density"] == 2.75

    container = body["layout"]["children"][0]
    assert container["class_name"] == "FrameLayout"
    assert container["bounds"] == {"left": 0, "top": 100, "right": 1080, "bottom": 1000}

    text = container["children"][0]
    assert text["id_str"] == "tv_title"
    # absolute = parent_abs (0,100) + relative (50,80,350,160) = (50,180,350,260)
    assert text["bounds"] == {"left": 50, "top": 180, "right": 350, "bottom": 260}
    assert body["schemas"] == ["demo://home"]


def test_screenshot_returns_png(client, monkeypatch, tmp_path):
    png_bytes = b"\x89PNG\r\n\x1a\nDATA"
    png_file = tmp_path / "s.png"
    png_file.write_bytes(png_bytes)
    monkeypatch.setattr(
        "aidb_locator.ui.api.snapshot.NativeAdb.screenshot",
        lambda self, output=None: png_file,
    )

    resp = client.get("/api/screenshot")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")
    assert resp.content == png_bytes


def test_snapshot_deletes_screenshot_file(client, monkeypatch, tmp_path):
    png_file = tmp_path / "shot.png"
    png_file.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
    monkeypatch.setattr(
        "aidb_locator.ui.api.snapshot.CodeLocator.grab_layout",
        lambda self: _fake_app(),
    )
    monkeypatch.setattr(
        "aidb_locator.ui.api.snapshot.NativeAdb.screenshot",
        lambda self, output=None: png_file,
    )

    resp = client.get("/api/snapshot")
    assert resp.status_code == 200
    assert not png_file.exists()


def test_snapshot_deletes_screenshot_when_layout_fails(client, monkeypatch, tmp_path):
    png_file = tmp_path / "shot.png"
    png_file.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")

    def boom(self):
        raise RuntimeError("layout failed")

    monkeypatch.setattr("aidb_locator.ui.api.snapshot.CodeLocator.grab_layout", boom)
    monkeypatch.setattr(
        "aidb_locator.ui.api.snapshot.NativeAdb.screenshot",
        lambda self, output=None: png_file,
    )

    try:
        client.get("/api/snapshot")
        assert False, "layout failure should surface"
    except RuntimeError as e:
        assert "layout failed" in str(e)
    assert not png_file.exists()


def test_screenshot_endpoint_deletes_file(client, monkeypatch, tmp_path):
    png_bytes = b"\x89PNG\r\n\x1a\nDATA"
    png_file = tmp_path / "s.png"
    png_file.write_bytes(png_bytes)
    monkeypatch.setattr(
        "aidb_locator.ui.api.snapshot.NativeAdb.screenshot",
        lambda self, output=None: png_file,
    )

    resp = client.get("/api/screenshot")
    assert resp.status_code == 200
    assert resp.content == png_bytes
    assert not png_file.exists()


def test_layout_returns_tree(client, monkeypatch):
    monkeypatch.setattr(
        "aidb_locator.ui.api.snapshot.CodeLocator.grab_layout",
        lambda self: _fake_app(),
    )
    resp = client.get("/api/layout")
    assert resp.status_code == 200
    body = resp.json()
    assert body["class_name"] == "DecorView"
    assert len(body["children"]) == 1
