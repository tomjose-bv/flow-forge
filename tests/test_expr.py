import pytest

from flow_forge.expr import ExprError, condition, evaluate, render

CTX = {
    "trigger": {"deal": {"name": "Acme", "amount": 1500, "currency": "USD", "stage": "won", "owner": None,
                         "tags": ["a", "b"]}},
    "steps": {"customer": {"id": "cus_1", "email": "Ada@Example.com"}, "none": None},
}


@pytest.mark.parametrize(
    "src, want",
    [
        ("trigger.deal.amount", 1500),
        ("trigger.deal.amount >= 1000 and trigger.deal.currency == 'USD'", True),
        ("trigger.deal.amount > 2000 or trigger.deal.stage == \"won\"", True),
        ("not (trigger.deal.stage == 'won')", False),
        ("trigger.deal.stage in ['won', 'lost']", True),
        ("trigger.deal.stage not in ['won']", False),
        ("'b' in trigger.deal.tags", True),
        ("steps.none is null", True),
        ("steps.missing is null", True),
        ("steps.customer is not null", True),
        ("trigger.deal.owner | default:'nobody'", "nobody"),
        ("trigger.deal.nope | default:0", 0),
        ("steps.customer.email | lower", "ada@example.com"),
        ("trigger.deal.amount | number | round:1", 1500.0),
        ("trigger.deal.tags | length", 2),
        ("trigger.deal.tags[1]", "b"),
        ("12.5 < 13", True),
    ],
)
def test_evaluate(src, want):
    assert evaluate(src, CTX) == want


@pytest.mark.parametrize(
    "src, msg",
    [
        ("trigger.deal.amont", "unknown path 'trigger.deal.amont'"),
        ("trigger.deal.amount >", "unexpected end"),
        ("trigger.deal.name | shout", "unknown filter"),
        ("trigger.deal.name > 3", "cannot compare"),
        ("__import__('os')", "expected"),
        ("trigger.deal.name ; 1", "unexpected character"),
        ("trigger.deal.tags[9]", "unknown path"),
    ],
)
def test_errors(src, msg):
    with pytest.raises(ExprError, match=msg):
        evaluate(src, CTX)


def test_render_keeps_type_for_whole_values():
    assert render("{{trigger.deal.amount}}", CTX) == 1500
    assert render("Deal {{trigger.deal.name}} won ({{trigger.deal.amount}} {{trigger.deal.currency}})", CTX) == \
        "Deal Acme won (1500 USD)"
    assert render({"a": ["{{steps.customer.id}}", 3], "b": "x"}, CTX) == {"a": ["cus_1", 3], "b": "x"}
    assert render("owner: {{trigger.deal.owner}}", CTX) == "owner: "


def test_condition():
    assert condition("{{trigger.deal.amount > 100}}", CTX) is True
    assert condition("trigger.deal.stage == 'lost'", CTX) is False
    assert condition(True, CTX) is True


def test_short_circuit():
    assert evaluate("steps.missing is null or steps.missing.id == 'x'", CTX) is True
    assert evaluate("steps.missing is not null and steps.missing.id == 'x'", CTX) is False
    assert evaluate("true or (steps.nope | upper) in ['A']", CTX) is True
    with pytest.raises(ExprError, match="expected"):
        evaluate("true or (steps.nope ==", CTX)  # syntax still checked
    with pytest.raises(ExprError, match="unknown path"):
        evaluate("false or steps.missing.id == 'x'", CTX)
