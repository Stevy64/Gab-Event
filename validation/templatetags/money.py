from django import template

register = template.Library()

MONEY_LABEL = "F CFA"


@register.filter
def fcfa(amount):
    if amount is None or amount == "":
        return "—"
    return f"{amount} {MONEY_LABEL}"


@register.simple_tag
def money_label():
    return MONEY_LABEL
