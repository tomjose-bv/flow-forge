import flow_forge
from flow_forge.cli import main


def test_version():
    assert flow_forge.__version__


def test_cli_runs():
    assert main([]) == 0
