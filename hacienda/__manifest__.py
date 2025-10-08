{
    "name": "Hacienda - Costa Rica Electronic Invoicing",
    "summary": "Adds Costa Rican electronic invoicing support (XML 4.4) for Odoo 19.",
    "description": """Costa Rican localization helpers for electronic invoicing (XML schema 4.4).\nIncludes journals, taxes, products, partners and electronic document management.""",
    "version": "19.0.1.0.0",
    "category": "Accounting",
    "author": "OpenAI Assistant",
    "website": "https://www.hacienda.go.cr/",
    "license": "LGPL-3",
    # ``signxml`` is imported lazily only when generating signed XML payloads.
    # Leaving it out of the external dependency list prevents the module
    # installation from failing on instances where the package is not yet
    # available (e.g., minimal staging environments).  Users will still receive
    # a clear error message at runtime if the optional dependency is missing.
    "external_dependencies": {"python": ["cryptography", "lxml"]},
    "depends": [
        "base",
        "account",
        "contacts",
        "product",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/hacienda_menus.xml",
        "views/account_journal_views.xml",
        "views/account_move_views.xml",
        "views/account_tax_views.xml",
        "views/product_template_views.xml",
        "views/res_partner_views.xml",
        "views/hacienda_config_views.xml",
        "views/hacienda_document_views.xml",
        "views/hacienda_catalog_views.xml",
    ],
    "application": True,
}
