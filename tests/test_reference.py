from pathlib import Path

import pytest

from flow_forge.harness import evaluate
from flow_forge.recipe import loads
from flow_forge.task import load

ROOT = Path(__file__).resolve().parent.parent
SETS = {"dev": ROOT / "recipes" / "reference", "heldout": ROOT / "recipes" / "reference" / "heldout"}
CASES = [(s, f) for s in SETS for f in sorted((ROOT / "tasks" / s).glob("*.yaml"))]


@pytest.mark.parametrize("set_name, path", CASES, ids=lambda x: x.stem if isinstance(x, Path) else x)
def test_reference_recipe_is_perfect(set_name, path):
    task = load(path)
    assert task.name == path.stem and task.description
    ref = (SETS[set_name] / f"{path.stem}.yaml").read_text(encoding="utf-8")
    r = evaluate(task, ref, ref)
    assert r.valid, r.validation_errors
    assert r.success and r.events_failed == 0 and r.duplicates_on_replay == 0, r
    assert r.expected > 0
    recipe = loads(ref)
    if recipe.filter:
        assert r.events_filtered > 0
        # the task must tell a careless recipe from a correct one: without the filter it fails
        unfiltered = ref.replace(f', filter: "{recipe.filter}"', "")
        assert unfiltered != ref
        assert not evaluate(task, unfiltered, ref).success


def test_dev_set_size():
    assert len(list((ROOT / "tasks" / "dev").glob("*.yaml"))) >= 16
