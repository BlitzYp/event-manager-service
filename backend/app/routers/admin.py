"""Assemble admin routes; edit the matching admin_* module for endpoint behavior."""

from fastapi import APIRouter, Depends

from ..dependencies import require_admin_event_access
from . import (
    admin_accounts,
    admin_actions,
    admin_common,
    admin_coupons,
    admin_events,
    admin_participant_import,
    admin_participants,
    admin_reporting,
    admin_vendors,
    admin_wallets,
)

# Compatibility exports for callers/tests; implementations belong in the feature modules.
require_super_admin = admin_accounts.require_super_admin
list_admin_accounts = admin_accounts.list_admin_accounts
impersonate_admin = admin_accounts.impersonate_admin
set_admin_account_status = admin_accounts.set_admin_account_status

list_events = admin_events.list_events
create_event = admin_events.create_event
update_event = admin_events.update_event
update_event_approval = admin_events.update_event_approval
delete_event = admin_events.delete_event

list_participants = admin_participants.list_participants
create_participant = admin_participants.create_participant
update_participant = admin_participants.update_participant
delete_participant = admin_participants.delete_participant
rotate_link = admin_participants.rotate_link
create_wallet_preview = admin_participants.create_wallet_preview

import_participants = admin_participant_import.import_participants

set_wallet_enabled = admin_wallets.set_wallet_enabled
adjust_wallet = admin_wallets.adjust_wallet
reverse_transaction = admin_wallets.reverse_transaction

list_vendors = admin_vendors.list_vendors
create_vendor = admin_vendors.create_vendor
update_vendor = admin_vendors.update_vendor
delete_vendor = admin_vendors.delete_vendor
rotate_vendor_pin = admin_vendors.rotate_vendor_pin

coupon_templates = admin_coupons.coupon_templates
create_coupon_template = admin_coupons.create_coupon_template
update_coupon_template = admin_coupons.update_coupon_template
delete_coupon_template = admin_coupons.delete_coupon_template
set_coupon_status = admin_coupons.set_coupon_status
list_coupon_instances = admin_coupons.list_coupon_instances
set_individual_coupon_status = admin_coupons.set_individual_coupon_status
issue_event_coupons = admin_coupons.issue_event_coupons

coupon_audits = admin_reporting.coupon_audits
export_transactions = admin_reporting.export_transactions
ledger_rows = admin_reporting.ledger_rows
transaction_query = admin_reporting.transaction_query
transactions = admin_reporting.transactions

apply_action_wallet_scope = admin_actions.apply_action_wallet_scope
create_action = admin_actions.create_action
delete_action = admin_actions.delete_action
list_actions = admin_actions.list_actions
run_action_now = admin_actions.run_action_now
set_action_enabled = admin_actions.set_action_enabled
update_action = admin_actions.update_action
validate_action_email_template = admin_actions.validate_action_email_template

event_json = admin_common.event_json
get_event = admin_common.get_event

# All child routes inherit the event-access guard, URL prefix, and API tag here.
router = APIRouter(
    prefix="/admin",
    tags=["administration"],
    dependencies=[Depends(require_admin_event_access)],
)

router.include_router(admin_accounts.router)
router.include_router(admin_events.router)
router.include_router(admin_participants.router)
router.include_router(admin_participant_import.router)
router.include_router(admin_wallets.router)
router.include_router(admin_vendors.router)
router.include_router(admin_coupons.router)
router.include_router(admin_reporting.router)
router.include_router(admin_actions.router)
