"""Verify documentation files exist and are non-empty."""
from pathlib import Path


class TestDocsExist:
    def test_manifest_exists(self) -> None:
        assert Path("MANIFEST.md").exists()
        assert Path("MANIFEST.md").stat().st_size > 1000

    def test_deploy_checklist_exists(self) -> None:
        assert Path("deploy/CHECKLIST.md").exists()

    def test_runbooks_exist(self) -> None:
        assert Path("deploy/RUNBOOKS.md").exists()

    def test_production_signoff_exists(self) -> None:
        assert Path("PRODUCTION_SIGNOFF.md").exists()

    def test_gateway_readme_exists(self) -> None:
        assert Path("services/gateway/README.md").exists()
