from flow_forge.harness import evaluate
from flow_forge.task import parse

TASK = parse({
    "name": "won_deal_invoice",
    "description": "When a deal is won, invoice the deal's contact in billing (create the customer if needed).",
    "seed": 5,
    "apps": ["crm", "billing", "chat"],
    "world": {"contacts": 8, "billing_customers": 4, "channels": ["sales"]},
    "events": [{"type": "deal.stage_changed", "count": 10, "stages": {"won": 4, "lost": 3, "proposal": 3}}],
})

REF = """
name: ref
trigger: {app: crm, event: deal.stage_changed, filter: "trigger.deal.stage == 'won'"}
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
      currency: "{{trigger.deal.currency}}"
      external_ref: "{{trigger.deal.id}}"
"""


def test_reference_matches_itself():
    r = evaluate(TASK, REF, REF)
    assert r.valid and r.success and r.precision == 1.0 and r.recall == 1.0
    assert (r.expected, r.events_ok, r.events_filtered, r.duplicates_on_replay) == (r.produced, 4, 6, 0)
    assert r.expected >= 4  # at least one invoice per won deal


def test_missing_filter_produces_unexpected_invoices():
    r = evaluate(TASK, REF.replace(', filter: "trigger.deal.stage == \'won\'"', ""), REF)
    assert r.valid and not r.success and r.recall == 1.0 and r.precision < 1.0
    assert r.unexpected and r.unexpected[0].startswith("billing.")


def test_wrong_field_is_missing_and_unexpected():
    r = evaluate(TASK, REF.replace('external_ref: "{{trigger.deal.id}}"', 'external_ref: "{{trigger.deal.name}}"'), REF)
    assert not r.success and r.missing and r.unexpected


def test_invalid_recipe():
    r = evaluate(TASK, REF.replace("crm.get_contact", "crm.read_contact"), REF)
    assert not r.valid and "no action 'read_contact'" in r.validation_errors[0]
    assert r.expected > 0 and r.produced == 0


def test_yaml_error_is_invalid():
    r = evaluate(TASK, "name: [", REF)
    assert not r.valid and "invalid YAML" in r.validation_errors[0]


def test_duplicates_on_replay_without_idempotent_lookup():
    # creating the customer unconditionally fails on the second won deal for the same contact
    # (409) or creates duplicates on replay; either way the report shows it
    bad = REF.replace('    if: "steps.customer is null"\n', "")
    r = evaluate(TASK, bad, REF)
    assert not r.success
    assert r.events_failed > 0 or r.duplicates_on_replay > 0
