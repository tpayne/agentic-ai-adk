import os

import pytest

from process_toolkit.docgen.uml_diagrams import generate_uml_diagram


@pytest.mark.parametrize(
    ("descriptor", "context"),
    [
        (
            {
                "title": "Client contract intelligence and enterprise integration sequence",
                "participants": ["Client Contract Administration", "Document Intelligence Gateway"],
                "steps": [{
                    "step_number": 1,
                    "from_participant": "Client Contract Administration",
                    "to_participant": "Document Intelligence Gateway",
                    "message": "Securely ingest and validate the uploaded contract documentation package",
                }],
            },
            {},
        ),
        (
            {"title": "Payment and contract domain model"},
            {"classes": [{
                "class_name": "ContractDocumentValidationAndExtractionResult",
                "attributes": ["document_reference_id", "extracted_legal_terms", "validation_confidence_score"],
                "methods": ["validateRequiredContractTerms()", "generateStructuredExtractionResult()"],
            }]},
        ),
        (
            {"title": "Service integration"},
            {"integration_points": [{
                "source": "SharePoint Contract Document Repository",
                "target": "Azure Document Intelligence Processing Service",
                "protocol": "Secure document ingestion using managed identity",
            }]},
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
