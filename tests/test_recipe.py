import pytest

from flow_forge.apps import make_apps
from flow_forge.recipe import RecipeError, loads, validate

APPS = make_apps()

GOOD = """
name: won_deal_invoice
trigger:
  app: crm
  event: deal.stage_changed
  filter: "trigger.deal.stage == 'won'"
steps:
  - id: contact
    action: crm.get_contact
    inputs: {id: "{{trigger.deal.contact_id}}"}
  - id: customer
    action: billing.find_customer
    inputs: {email: "{{steps.contact.email}}"}
  - id: new_customer
    if: "steps.customer is null"
    action: billing.create_customer
    inputs: {name: "{{steps.contact.name}}", email: "{{steps.contact.email}}"}
  - id: invoice
    action: billing.create_invoice
    inputs:
      customer_id: "{{steps.customer.id | default: steps.new_customer.id}}"
      amount: "{{trigger.deal.amount}}"
      currency: USD
  - id: each_tag
    for_each: "trigger.deal.tags"
    steps:
      - id: post
        action: chat.post_message
        inputs: {channel: sales, text: "{{index}}: {{item}}"}
"""


def test_good_recipe_is_valid():
    assert validate(loads(GOOD), APPS) == []


@pytest.mark.parametrize(
    "old, new, msg",
    [
        ("event: deal.stage_changed", "event: deal.won", "has no event 'deal.won'"),
        ("app: crm\n  event", "app: erp\n  event", "unknown app 'erp'"),
        ("action: crm.get_contact", "action: crm.fetch_contact", "has no action 'fetch_contact'"),
        ("action: crm.get_contact", "action: get_contact", "must be '<app>.<action>'"),
        ("currency: USD", "currency: YEN", "must be one of"),
        ("currency: USD", "currency: USD\n      amount_cents: 5", "no input 'amount_cents'"),
        ("      currency: USD\n", "", "needs input 'currency'"),
        ("{{steps.contact.email}}\"}\n  - id: new", "{{steps.invoice.id}}\"}\n  - id: new",
         "refers to step 'invoice'"),
        ("- id: customer", "- id: contact", "duplicate step id"),
        ("trigger.deal.stage == 'won'", "trigger.deal.stage = 'won'", "unexpected character"),
        ("{{trigger.deal.amount}}", "{{item}}", "only be used inside for_each"),
    ],
)
def test_validation_errors(old, new, msg):
    assert old in GOOD
    errs = validate(loads(GOOD.replace(old, new, 1)), APPS)
    assert any(msg in e for e in errs), errs


@pytest.mark.parametrize(
    "text, msg",
    [
        ("name: x\ntrigger: {app: crm}\nsteps: [{id: a, action: crm.get_deal}]", "needs 'app' and 'event'"),
        ("name: x\ntrigger: {app: crm, event: deal.created}\nsteps: []", "non-empty"),
        ("name: x\ntrigger: {app: crm, event: deal.created}\nsteps: [{action: crm.get_deal}]", "needs an id"),
        ("name: x\ntrigger: {app: crm, event: deal.created}\nsteps: [{id: a}]", "exactly one of"),
        ("name: x\ntrigger: {app: crm, event: deal.created}\nsteps: [{id: a, action: x.y, run: 1}]", "unknown keys"),
        ("name: [unclosed", "invalid YAML"),
    ],
)
def test_parse_errors(text, msg):
    with pytest.raises(RecipeError, match=msg):
        loads(text)
