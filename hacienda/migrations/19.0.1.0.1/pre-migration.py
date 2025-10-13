import logging

from lxml import etree

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Upgrade legacy Hacienda payment method view to the list view type."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    xmlid = "hacienda.view_move_payment_method_list"

    try:
        view = env.ref(xmlid)
    except ValueError:
        _logger.info("View %s not found; skipping Hacienda payment method migration.", xmlid)
        return

    arch_db = view.arch_db or ""
    needs_arch_update = arch_db.lstrip().startswith("<tree")
    needs_type_update = view.type != "list"

    updates = {}

    if needs_arch_update:
        try:
            arch_dom = etree.fromstring(arch_db.encode())
        except etree.XMLSyntaxError:
            _logger.warning("Could not parse Hacienda payment method view arch; skipping tag conversion.")
        else:
            if arch_dom.tag == "tree":
                arch_dom.tag = "list"
                updates["arch_db"] = etree.tostring(arch_dom, encoding="unicode")
            else:
                _logger.debug("Hacienda payment method view root already %s; nothing to convert.", arch_dom.tag)

    if needs_type_update:
        updates["type"] = "list"

    if updates:
        view.with_context(check_view_ids=False).write(updates)
        _logger.info("Migrated Hacienda payment method view to list type.")
    else:
        _logger.info("Hacienda payment method view already uses the list type; no migration required.")
