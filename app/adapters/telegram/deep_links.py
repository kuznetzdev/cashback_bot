"""Deep-link payload constants used when sending a user from an inline query
result (or any other external CTA) back into the bot via ``t.me/<bot>?start=<payload>``.

Both sides of the boundary — the inline query handler that *produces* the
deep link and the ``/start`` router handler that *consumes* it — must agree
on the exact payload string. Keeping the constants here prevents silent
sync bugs when one side is renamed in isolation.
"""
from __future__ import annotations


# Tapped a plain "Open the bot" onboarding result → land on /home screen.
PAYLOAD_INLINE = "inline"

# Tapped "add banks first" from inline mode with empty bank list → jump into
# the add-bank flow directly instead of showing the home menu.
PAYLOAD_INLINE_SETUP = "inline_setup"

# Explicit /start?start=add_bank deep link, e.g. from a promo site.
PAYLOAD_ADD_BANK = "add_bank"

# Explicit /start?start=top deep link.
PAYLOAD_TOP = "top"

# Explicit /start?start=help deep link.
PAYLOAD_HELP = "help"
