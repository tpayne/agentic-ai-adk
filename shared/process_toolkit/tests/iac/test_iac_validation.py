from process_toolkit.iac.validation import validate_iac_files


def test_valid_terraform_hcl_passes():
    result = validate_iac_files({"main.tf": 'resource "aws_instance" "web" {\n  ami = "ami-123"\n}\n'})
    assert result["valid"] is True
    assert result["files"][0] == {"file": "main.tf", "valid": True, "best_effort": False, "format": "hcl", "error": None}


def test_malformed_terraform_hcl_fails_with_a_real_parser_error():
    result = validate_iac_files({"main.tf": 'resource "aws_instance" "web" {\n  ami =\n'})
    assert result["valid"] is False
    entry = result["files"][0]
    assert entry["valid"] is False
    assert entry["best_effort"] is False
    assert entry["format"] == "hcl"
    assert entry["error"]


def test_tfvars_also_validated_as_hcl():
    result = validate_iac_files({"terraform.tfvars": 'region = "us-east-1"\n'})
    assert result["files"][0]["format"] == "hcl"
    assert result["valid"] is True


def test_valid_cloudformation_yaml_passes():
    result = validate_iac_files({"template.yaml": "Resources:\n  Bucket:\n    Type: AWS::S3::Bucket\n"})
    assert result["valid"] is True
    assert result["files"][0]["format"] == "yaml"


def test_malformed_yaml_fails():
    result = validate_iac_files({"template.yaml": "Resources:\n  Bucket: [unclosed\n"})
    assert result["valid"] is False
    assert result["files"][0]["best_effort"] is False


def test_valid_json_passes():
    result = validate_iac_files({"template.json": '{"Resources": {}}'})
    assert result["valid"] is True
    assert result["files"][0]["format"] == "json"


def test_malformed_json_fails():
    result = validate_iac_files({"template.json": '{"a": }'})
    assert result["valid"] is False


def test_valid_python_passes():
    result = validate_iac_files({"__main__.py": "import pulumi\nbucket = pulumi.Resource()\n"})
    assert result["valid"] is True
    assert result["files"][0]["format"] == "python"


def test_malformed_python_fails():
    result = validate_iac_files({"__main__.py": "def f(:\n    pass\n"})
    assert result["valid"] is False
    assert result["files"][0]["format"] == "python"


def test_unknown_extension_uses_best_effort_and_is_clearly_flagged():
    result = validate_iac_files({"README.md": "# Notes\nsome text\n"})
    entry = result["files"][0]
    assert entry["best_effort"] is True
    assert entry["format"] == "unknown"
    assert entry["valid"] is True  # balanced, non-empty -- passes the heuristic


def test_best_effort_catches_unbalanced_brackets():
    result = validate_iac_files({"README.md": "some { unbalanced text"})
    entry = result["files"][0]
    assert entry["best_effort"] is True
    assert entry["valid"] is False
    assert "Unclosed" in entry["error"]


def test_best_effort_ignores_brackets_inside_quoted_strings():
    result = validate_iac_files({"README.md": 'a string with a "{" inside it, still fine'})
    assert result["files"][0]["valid"] is True


def test_empty_file_fails_best_effort():
    result = validate_iac_files({"README.md": "   \n  "})
    assert result["files"][0]["valid"] is False
    assert "empty" in result["files"][0]["error"].lower()


def test_one_bad_file_fails_the_whole_batch():
    result = validate_iac_files({
        "main.tf": 'resource "x" "y" {}\n',
        "broken.tf": 'resource "x" "y" {\n',
    })
    assert result["valid"] is False
    assert result["files"][0]["valid"] is True
    assert result["files"][1]["valid"] is False
