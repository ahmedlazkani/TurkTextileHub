"""
bot/states.py
=============
ConversationHandler State Constants
====================================

Purpose:
    Defines all integer state constants used by python-telegram-bot's
    ConversationHandler across every flow in the bot.

Naming Convention:
    States are grouped by flow and assigned non-overlapping integer ranges
    to prevent cross-flow conflicts.

    Range   Flow
    ─────   ─────────────────────────────────────────────────
    1–6     Supplier Registration
    10–13   Trader Registration
    20–28   Product Addition (legacy 20-23, KAYISOFT 24-28)
    30–31   Product Browsing
    40–44   Request for Quotation (RFQ)
    50–53   Channel Connection
    60–64   Channel Post Editing

Author:
    TurkTextileHub Engineering Team
"""

# ──────────────────────────────────────────────────────────
# SUPPLIER REGISTRATION  (1–6)
# ──────────────────────────────────────────────────────────

COMPANY_NAME        = 1   # Enter company / store name
CONTACT_NAME        = 2   # Enter responsible contact person's name
SUPPLIER_CITY       = 3   # Select city
PHONE_NUMBER        = 4   # Enter phone number with country code
SALES_REP           = 5   # Does the supplier have a sales representative?
SALES_REP_USERNAME  = 6   # Enter sales representative's Telegram username

# ──────────────────────────────────────────────────────────
# TRADER REGISTRATION  (10–13)
# ──────────────────────────────────────────────────────────

TRADER_FULL_NAME     = 10  # Enter trader's full name
TRADER_PHONE         = 11  # Enter trader's phone number
TRADER_COUNTRY       = 12  # Enter trader's country
TRADER_BUSINESS_TYPE = 13  # Select business activity type

# ──────────────────────────────────────────────────────────
# PRODUCT ADDITION — KAYISOFT API FLOW  (20–28)
#
# Full flow:
#   GETTING_MAIN_CATEGORY
#       → GETTING_SUB_CATEGORY  (if sub-categories exist)
#           → GETTING_ATTRIBUTES  (form, one field at a time)
#               → GETTING_IMAGES  (per variant or general)
#                   → CONFIRM_KAYISOFT_PRODUCT
#
# Note: GETTING_IMAGES (20) is shared between legacy and KAYISOFT flows.
# ──────────────────────────────────────────────────────────

GETTING_IMAGES            = 20  # Receive product images (shared: legacy + KAYISOFT)
GETTING_CATEGORY          = 21  # Legacy: select product category
GETTING_PRICE             = 22  # Legacy: enter product price
CONFIRM_ADD_PRODUCT       = 23  # Legacy: confirm product publication

GETTING_MAIN_CATEGORY     = 24  # Select root category from KAYISOFT dynamic tree
GETTING_SUB_CATEGORY      = 25  # Select sub-category (skipped if none exist)
GETTING_ATTRIBUTES        = 26  # Fill product attributes (colors, sizes, brand…)
GETTING_MIN_QUANTITY      = 27  # Enter minimum order quantity
CONFIRM_KAYISOFT_PRODUCT  = 28  # Confirm and publish product to KAYISOFT + channel

# ──────────────────────────────────────────────────────────
# PRODUCT BROWSING  (30–31)
# ──────────────────────────────────────────────────────────

BROWSING_CATEGORY = 30  # Select category to browse
BROWSING_PRODUCTS = 31  # Navigate through product listings

# ──────────────────────────────────────────────────────────
# REQUEST FOR QUOTATION (RFQ)  (40–44)
# ──────────────────────────────────────────────────────────

GETTING_QUOTE_QUANTITY      = 40  # Enter requested quantity (optional)
GETTING_QUOTE_COLOR         = 41  # Enter requested color (optional)
GETTING_QUOTE_SIZE          = 42  # Enter requested size (optional)
GETTING_QUOTE_DELIVERY_DATE = 43  # Enter requested delivery date (optional)
CONFIRM_QUOTE_REQUEST       = 44  # Confirm and send RFQ to supplier

# ──────────────────────────────────────────────────────────
# CHANNEL CONNECTION  (50–53)
# ──────────────────────────────────────────────────────────

CHANNEL_WAITING_READY       = 50  # Waiting for supplier to add bot as admin
CHANNEL_WAITING_USERNAME    = 51  # Waiting for supplier to send channel @username
CHANNEL_CONFIRM_CONNECT     = 52  # Confirm channel connection after triple verification
CHANNEL_CONFIRM_ADD_ANOTHER = 53  # Ask supplier whether to add another channel

# ──────────────────────────────────────────────────────────
# CHANNEL POST EDITING  (60–64)
# ──────────────────────────────────────────────────────────

EDIT_POST_TITLE_AR = 60  # Edit Arabic product title
EDIT_POST_TITLE_EN = 61  # Edit English product title
EDIT_POST_PRICE    = 62  # Edit product price
EDIT_POST_CATEGORY = 63  # Change product category
EDIT_POST_CONFIRM  = 64  # Confirm all edits before re-submitting
