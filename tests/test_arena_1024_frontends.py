from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_browser_and_godot_default_to_the_1024_node_live_stage() -> None:
    browser = (ROOT / "src/flytest/web/fly.html").read_text(encoding="utf-8")
    bridge = (ROOT / "arena3d/arena_bridge.gd").read_text(encoding="utf-8")
    main = (ROOT / "arena3d/main.gd").read_text(encoding="utf-8")

    assert '<option value="1024" selected>' in browser
    assert "networkStage: 1024" in browser
    assert '"network_stage": 1024' in bridge
    assert "REQUESTING LIVE STAGE 1024 SESSION" in main
