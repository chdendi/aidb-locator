def test_capture_returns_png(client, monkeypatch, tmp_path):
    png_bytes = b"\x89PNG\r\n\x1a\nVIEWIMG"
    png_file = tmp_path / "view.png"
    png_file.write_bytes(png_bytes)

    monkeypatch.setattr(
        "aidb_locator.ui.api.capture.CodeLocator.capture_view",
        lambda self, addr, output=None: png_file,
    )

    resp = client.get("/api/capture/abc123")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")
    assert resp.headers["content-disposition"] == 'attachment; filename="view_abc123.png"'
    assert resp.content == png_bytes
    assert not png_file.exists()
