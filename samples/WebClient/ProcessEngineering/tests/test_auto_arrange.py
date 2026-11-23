from pathlib import Path


WEBCLIENT_ROOT = Path(__file__).resolve().parents[1]


def test_auto_arrange_buttons_present_in_html():
    html = (WEBCLIENT_ROOT / "public" / "index.html").read_text(encoding="utf-8")

    # 1. Agent Network tab (toolbar + zoom controls)
    assert 'id="networkAutoArrangeBtn"' in html
    assert 'id="networkAutoArrangeZoomBtn"' in html
    assert 'title="Auto-arrange layout"' in html

    # 2. Artefact Browser tab (toolbar)
    assert 'id="artifactAutoArrangeBtn"' in html
    assert 'title="Auto-arrange tree"' in html

    # 3. Diagrams tab (toolbar + zoom controls)
    assert 'id="cloudarchAutoArrangeBtn"' in html
    assert 'id="cloudarchAutoArrangeZoomBtn"' in html
    assert 'title="Auto-arrange diagram"' in html

    # 4. Token Usage tab (toolbar + zoom controls)
    assert 'id="usageAutoArrangeBtn"' in html
    assert 'id="usageAutoArrangeZoomBtn"' in html
    assert 'title="Auto-arrange chart"' in html

    # 5. Chat tab (composer toolbar)
    assert 'id="chatAutoArrangeBtn"' in html
    assert 'title="Auto-arrange chat"' in html


def test_auto_arrange_functions_and_wiring_in_app_js():
    app = (WEBCLIENT_ROOT / "public" / "app.js").read_text(encoding="utf-8")

    # Element cache in `el`
    assert 'networkAutoArrangeBtn: document.getElementById("networkAutoArrangeBtn")' in app
    assert 'networkAutoArrangeZoomBtn: document.getElementById("networkAutoArrangeZoomBtn")' in app
    assert 'artifactAutoArrangeBtn: document.getElementById("artifactAutoArrangeBtn")' in app
    assert 'cloudarchAutoArrangeBtn: document.getElementById("cloudarchAutoArrangeBtn")' in app
    assert 'cloudarchAutoArrangeZoomBtn: document.getElementById("cloudarchAutoArrangeZoomBtn")' in app
    assert 'usageAutoArrangeBtn: document.getElementById("usageAutoArrangeBtn")' in app
    assert 'usageAutoArrangeZoomBtn: document.getElementById("usageAutoArrangeZoomBtn")' in app
    assert 'chatAutoArrangeBtn: document.getElementById("chatAutoArrangeBtn")' in app

    # Functions defined
    assert "function autoArrangeNetwork()" in app
    assert "function autoArrangeDiagram()" in app
    assert "function autoArrangeArtifacts()" in app
    assert "function autoArrangeUsage()" in app
    assert "function autoArrangeChat()" in app

    # autoArrangeNetwork clears manual positioning and resets autoFit
    assert "delete node.manualX" in app
    assert "delete node.manualY" in app
    assert "state.network.autoFit = true" in app

    # autoArrangeArtifacts resets expandedPaths to root and top-level keys
    assert 'state.dataExplorer.expandedPaths = new Set(["$"])' in app

    # Event listener attachments
    assert 'el.networkAutoArrangeBtn.addEventListener("click", autoArrangeNetwork)' in app
    assert 'el.networkAutoArrangeZoomBtn.addEventListener("click", autoArrangeNetwork)' in app
    assert 'el.artifactAutoArrangeBtn.addEventListener("click", autoArrangeArtifacts)' in app
    assert 'el.cloudarchAutoArrangeBtn.addEventListener("click", autoArrangeDiagram)' in app
    assert 'el.cloudarchAutoArrangeZoomBtn.addEventListener("click", autoArrangeDiagram)' in app
    assert 'el.usageAutoArrangeBtn.addEventListener("click", autoArrangeUsage)' in app
    assert 'el.usageAutoArrangeZoomBtn.addEventListener("click", autoArrangeUsage)' in app
    assert 'el.chatAutoArrangeBtn.addEventListener("click", autoArrangeChat)' in app
