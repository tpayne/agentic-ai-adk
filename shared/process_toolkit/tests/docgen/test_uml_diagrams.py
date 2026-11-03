import os

import pytest

from process_toolkit.docgen.uml_diagrams import generate_uml_diagram


@pytest.mark.parametrize(
    ("descriptor", "context"),
    [
        (
            {
                "title": "Payment authorization",
                "participants": ["Client", "Gateway"],
                "steps": [{
                    "step_number": 1,
                    "from_participant": "Client",
                    "to_participant": "Gateway",
                    "message": "Authorize payment",
                }],
            },
            {},
        ),
        (
            {"title": "Payment model"},
            {"classes": [{"class_name": "Payment", "attributes": ["id"], "methods": ["authorize()"]}]},
        ),
        (
            {"title": "Service integration"},
            {"integration_points": [{"source": "Portal", "target": "API", "protocol": "HTTPS"}]},
        ),
        (
            {"title": "System context"},
            {"external_systems": [{"name": "Identity Provider"}]},
        ),
        (
            {"title": "Deployment environments"},
            {"environments": [{"name": "Production", "infrastructure": "Cloud"}]},
        ),
    ],
)
def test_design_diagrams_render_with_the_shared_visual_style(tmp_path, descriptor, context):
    diagram_path = generate_uml_diagram(
        descriptor, context, system_name="Payment Platform", output_dir=str(tmp_path)
    )

    assert os.path.isfile(diagram_path)
    assert os.path.getsize(diagram_path) > 0
