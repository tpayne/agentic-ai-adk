from process_toolkit.cloudarch import attack_simulation as atk
from process_toolkit.cloudarch import simulation as sim
from process_toolkit.drawio.graph import parse_drawio_graph

_SAMPLE_XML = """
<mxfile host="app.diagrams.net">
  <diagram id="d1" name="Page-1">
    <mxGraphModel dx="800" dy="600">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="apigw" value="Public API Gateway" style="sketch=0;shape=mxgraph.aws4.api_gateway;" vertex="1" parent="1">
          <mxGeometry x="0" y="0" width="48" height="48" as="geometry" />
        </mxCell>
        <mxCell id="rds" value="Orders DB" style="sketch=0;shape=mxgraph.aws4.rds;" vertex="1" parent="1">
          <mxGeometry x="0" y="0" width="48" height="48" as="geometry" />
        </mxCell>
        <mxCell id="admin_role" value="Admin Role" style="sketch=0;shape=mxgraph.aws4.iam;" vertex="1" parent="1">
          <mxGeometry x="0" y="0" width="48" height="48" as="geometry" />
        </mxCell>
        <mxCell id="edge_1" edge="1" parent="1" source="apigw" target="rds">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="edge_2" edge="1" parent="1" source="apigw" target="admin_role">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""


def _fixture_graph():
    return parse_drawio_graph(_SAMPLE_XML)


def test_entry_point_detection_matches_known_keywords():
    vertices = [
        {"id": "a", "value": "Public API Gateway", "shape_slug": "api_gateway"},
        {"id": "b", "value": "Internal Worker", "shape_slug": "lambda"},
    ]
    entry_points = atk._detect_entry_points(vertices)
    assert {v["id"] for v in entry_points} == {"a"}


def test_control_classification_matches_waf_firewall_mfa_encryption_keywords():
    vertices = [
        {"id": "waf", "value": "WAF", "shape_slug": "waf"},
        {"id": "fw", "value": "Security Group", "shape_slug": "security_group"},
        {"id": "sso", "value": "Cognito SSO", "shape_slug": "cognito"},
        {"id": "kms", "value": "KMS Key", "shape_slug": "key_management_service"},
        {"id": "ec2", "value": "Web Tier", "shape_slug": "ec2"},
    ]
    controls = atk._classify_controls(vertices)
    assert {c["id"] for c in controls["waf"]} == {"waf"}
    assert {c["id"] for c in controls["firewall_segmentation"]} == {"fw"}
    assert {c["id"] for c in controls["identity_mfa_sso"]} == {"sso"}
    assert {c["id"] for c in controls["encryption_kms"]} == {"kms"}
    assert controls["monitoring_detection"] == []


def test_adjacency_is_undirected():
    graph = _fixture_graph()
    adjacency = atk._build_adjacency(graph["vertices"], graph["edges"])
    impacts = sim._build_impacts_graph(graph["vertices"], graph["edges"])
    # simulation's impacts graph is directed (target depends on source);
    # attack_simulation's adjacency must see BOTH directions.
    assert "apigw" in adjacency["rds"]
    assert "rds" in adjacency["apigw"]
    assert "apigw" not in impacts["apigw"]  # sanity: directed graph has no self/reverse edge here
    assert adjacency["apigw"] == {"rds", "admin_role"}


def test_reachable_through_stops_at_blocking_control():
    adjacency = {"a": {"b"}, "b": {"a", "fw"}, "fw": {"b", "c"}, "c": {"fw"}}
    reached = atk._reachable_through({"a"}, adjacency, blocking_ids={"fw"})
    assert reached == {"a", "b", "fw"}  # fw itself included, but not expanded past
    assert "c" not in reached


def test_unauthenticated_access_flags_entry_point_without_waf():
    entry = {"id": "apigw", "value": "API Gateway"}
    store = {"id": "rds", "value": "Orders DB"}
    by_id = {"apigw": entry, "rds": store}
    adjacency = {"apigw": {"rds"}, "rds": {"apigw"}}
    controls = {"waf": []}
    findings = atk._analyze_unauthenticated_access(
        [entry], adjacency, controls, by_id, data_store_ids={"rds"}, identity_ids=set()
    )
    assert len(findings) == 1
    assert findings[0]["severity"] == "High"  # neighbor is a data store
    assert findings[0]["missing_controls"] == ["waf"]


def test_unauthenticated_access_not_flagged_behind_waf():
    entry = {"id": "cf", "value": "CloudFront"}
    waf = {"id": "waf", "value": "WAF"}
    by_id = {"cf": entry, "waf": waf}
    adjacency = {"cf": {"waf"}, "waf": {"cf"}}
    controls = {"waf": [waf]}
    findings = atk._analyze_unauthenticated_access(
        [entry], adjacency, controls, by_id, data_store_ids=set(), identity_ids=set()
    )
    assert findings == []


def test_lateral_movement_flagged_without_segmentation():
    entry = {"id": "apigw", "value": "API Gateway"}
    by_id = {"apigw": entry, "web": {"id": "web", "value": "Web"}, "app": {"id": "app", "value": "App"}}
    adjacency = {"apigw": {"web"}, "web": {"apigw", "app"}, "app": {"web"}}
    controls = {"firewall_segmentation": []}
    findings = atk._analyze_lateral_movement([entry], adjacency, controls, by_id, total=10)
    assert len(findings) == 1
    assert findings[0]["severity"] == "High"
    assert findings[0]["missing_controls"] == ["network_segmentation"]


def test_lateral_movement_not_flagged_when_blocked_immediately():
    entry = {"id": "apigw", "value": "API Gateway"}
    fw = {"id": "fw", "value": "Firewall"}
    by_id = {"apigw": entry, "fw": fw}
    adjacency = {"apigw": {"fw"}, "fw": {"apigw", "app"}, "app": {"fw"}}
    controls = {"firewall_segmentation": [fw]}
    findings = atk._analyze_lateral_movement([entry], adjacency, controls, by_id, total=10)
    # reachable (excluding self) = {fw} only -- traversal stops at the blocking node -- size 1, not flagged
    assert findings == []


def test_privilege_escalation_flags_admin_identity_without_mfa_sso():
    admin = {"id": "admin_role", "value": "Admin Role"}
    controls = {"identity_mfa_sso": []}
    findings = atk._analyze_privilege_escalation([admin], controls)
    assert len(findings) == 1
    assert findings[0]["severity"] == "High"


def test_privilege_escalation_not_flagged_when_mfa_sso_present():
    admin = {"id": "admin_role", "value": "Admin Role"}
    sso = {"id": "sso", "value": "SSO"}
    controls = {"identity_mfa_sso": [sso]}
    findings = atk._analyze_privilege_escalation([admin], controls)
    assert findings == []


def test_data_exfiltration_flags_unencrypted_reachable_store():
    entry = {"id": "apigw", "value": "API Gateway"}
    store = {"id": "rds", "value": "Orders DB"}
    by_id = {"apigw": entry, "rds": store}
    adjacency = {"apigw": {"rds"}, "rds": {"apigw"}}
    controls = {"waf": [], "firewall_segmentation": [], "encryption_kms": []}
    findings = atk._analyze_data_exfiltration([entry], [store], adjacency, controls, by_id)
    assert len(findings) == 1
    assert findings[0]["severity"] == "High"
    assert findings[0]["missing_controls"] == ["encryption_kms"]


def test_data_exfiltration_medium_when_store_encrypted():
    entry = {"id": "apigw", "value": "API Gateway"}
    store = {"id": "s3", "value": "Backups"}
    kms = {"id": "kms", "value": "KMS Key"}
    by_id = {"apigw": entry, "s3": store, "kms": kms}
    adjacency = {"apigw": {"s3"}, "s3": {"apigw", "kms"}, "kms": {"s3"}}
    controls = {"waf": [], "firewall_segmentation": [], "encryption_kms": [kms]}
    findings = atk._analyze_data_exfiltration([entry], [store], adjacency, controls, by_id)
    assert len(findings) == 1
    assert findings[0]["severity"] == "Medium"
    assert findings[0]["missing_controls"] == []


def test_data_exfiltration_not_flagged_when_store_unreachable():
    entry = {"id": "apigw", "value": "API Gateway"}
    store = {"id": "rds", "value": "Orders DB"}
    by_id = {"apigw": entry, "rds": store}
    adjacency = {"apigw": set(), "rds": set()}
    controls = {"waf": [], "firewall_segmentation": [], "encryption_kms": []}
    findings = atk._analyze_data_exfiltration([entry], [store], adjacency, controls, by_id)
    assert findings == []


def test_credential_compromise_flags_missing_mfa_sso_and_reports_blast_scope():
    entry = {"id": "apigw", "value": "API Gateway"}
    by_id = {"apigw": entry, "web": {"id": "web", "value": "Web"}, "app": {"id": "app", "value": "App"}}
    adjacency = {"apigw": {"web"}, "web": {"apigw", "app"}, "app": {"web"}}
    controls = {"identity_mfa_sso": []}
    findings = atk._analyze_credential_compromise([entry], [], adjacency, controls, by_id, total=10)
    assert len(findings) == 1
    assert {r["id"] for r in findings[0]["reachable"]} == {"web", "app"}


def test_credential_compromise_not_flagged_when_mfa_sso_present():
    entry = {"id": "apigw", "value": "API Gateway"}
    by_id = {"apigw": entry}
    adjacency = {"apigw": set()}
    controls = {"identity_mfa_sso": [{"id": "sso", "value": "SSO"}]}
    findings = atk._analyze_credential_compromise([entry], [], adjacency, controls, by_id, total=10)
    assert findings == []


def test_simulate_cloudarch_attack_returns_expected_top_level_shape():
    result_json = atk.simulate_cloudarch_attack(_SAMPLE_XML)
    import json
    result = json.loads(result_json)
    assert set(result["technique_summaries"].keys()) == set(atk._TECHNIQUE_CATEGORIES)
    assert result["overall_risk_rating"] in ("Low", "Medium", "High")
    # apigw has no WAF and is wired directly to a data store and an identity
    assert result["technique_summaries"]["unauthenticated_access"]["flagged"] is True
    assert result["technique_summaries"]["data_exfiltration"]["flagged"] is True


def test_simulate_cloudarch_attack_errors_on_no_vertices():
    empty_xml = '<mxfile><diagram><mxGraphModel><root><mxCell id="0" /><mxCell id="1" parent="0" /></root></mxGraphModel></diagram></mxfile>'
    import json
    result = json.loads(atk.simulate_cloudarch_attack(empty_xml))
    assert result["error"] == "cloudarch_attack_simulation_failed"


def test_simulate_cloudarch_attack_reports_clean_result_when_no_entry_points():
    xml_no_entry = """
    <mxfile><diagram><mxGraphModel><root>
      <mxCell id="0" /><mxCell id="1" parent="0" />
      <mxCell id="lam" value="Internal Worker" style="shape=mxgraph.aws4.lambda;" vertex="1" parent="1">
        <mxGeometry x="0" y="0" width="48" height="48" as="geometry" />
      </mxCell>
    </root></mxGraphModel></diagram></mxfile>
    """
    import json
    result = json.loads(atk.simulate_cloudarch_attack(xml_no_entry))
    assert result["entry_points"] == []
    assert result["overall_risk_rating"] == "Low"
    assert all(not s["flagged"] for s in result["technique_summaries"].values())
