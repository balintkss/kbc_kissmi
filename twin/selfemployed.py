"""Self-employed reserve envelope: what to put aside from every invoice for social contributions and tax.

KBC's self-employed offer has no VAT/tax reserve envelopes and no proactive planning nudges
(docs/research/kbc_invest_business.md). For a twin whose employment is self_employed this module takes

  * the invoice inflows of the last 90 days (subcategory 'invoice', this customer only), annualised, and
  * the observed social-contribution payments (subcategory 'social_contributions', this customer only),

and suggests a percentage of every invoice to set aside for
  (a) social contributions (sociale bijdragen), with the next expected payment and the legal deadline, and
  (b) income-tax prepayments (voorafbetalingen), with the remaining 2026 deadlines.

Everything is an INDICATIVE ESTIMATE, not tax advice:
  * invoices are gross: we can't see business costs, so the real taxable income (and both amounts) is lower;
  * we assume a sole proprietorship (eenmanszaak) in main occupation, since invoices land on a personal account;
  * VAT: the transactions don't tell us whether the customer is VAT-registered or uses the small-business
    exemption, so VAT is left out entirely instead of guessed;
  * income tax: 2026 federal brackets, the basic tax-free amount, and a 7% municipal surcharge (average);
    no deductions, family allowances or other income are modelled.

Belgian figures (checked 2026-09-30):
  * Social contributions 2026: 20.5% of net taxable professional income up to EUR 75,024.54, 14.16% up to
    EUR 110,562.42, nothing above; main-occupation minimum EUR 890.42 per quarter; due by the last day of each
    quarter. Accountable, "Sociale bijdragen voor zelfstandigen in 2026",
    https://www.accountable.eu/nl-be/blog/sociale-bijdragen/ ; Liantis, "Nieuwe bijdragetabel 2026",
    https://www.liantis.be/nl/nieuws/nieuwe-bijdragetabel-2026
  * Provisional contributions are based on the income of 3 years earlier and are regularised once the tax
    assessment is known (usually 2-3 years later, most often with an extra payment). Acerta, "Sociale bijdragen
    berekenen", https://www.acerta.be/nl/starters/je-voorbereiding/sociale-bijdragen-betalen-als-starter/sociale-bijdragen-berekenen
  * Tax prepayments, income year 2026 (tax year 2027): 10 April, 10 July, 12 October and 21 December 2026.
    FPS Finance, "Voorafbetalingen", https://finance.belgium.be/en/node/124 ; SBB, "Voorafbetalingen belastingen
    2026", https://www.sbb.be/nl/magazine/voorafbetalen-belastingen-2026 (SBB also reports that the surcharge for
    insufficient prepayments is abolished for sole proprietors from income year 2026, that prepaying still earns a
    bonus, and a new fifth prepayment by 22 February 2027).
  * Personal income tax, income year 2026: 25% to EUR 16,720, 40% to EUR 29,510, 45% to EUR 51,070, 50% above;
    basic tax-free amount EUR 11,550. Practicali, "De geindexeerde bedragen aanslagjaar 2027",
    https://www.practicali.be/blog/geindexeerde-bedragen-aj-2027
  * Municipal surcharge: Flemish average 7.22% in 2026 (0% to over 9%); we use 7%.
    https://www.hildecrevits.be/belastingtarieven_in_gemeenten_stabiel_voor_2026

All SQL is scoped with `customer_id = ?`.
"""
import calendar
from datetime import date, timedelta

from twin.engine import AS_OF
from twin.recommender import _fact, _nice_date

TODAY = AS_OF.date()
WINDOW_DAYS = 90

SOCIAL_BANDS = ((75_024.54, 0.205), (110_562.42, 0.1416))  # (upper bound, rate); nothing above the last bound
SOCIAL_MIN_QUARTER = 890.42
TAX_BRACKETS = ((16_720, 0.25), (29_510, 0.40), (51_070, 0.45), (float("inf"), 0.50))
TAX_FREE = 11_550
MUNICIPAL = 0.07
PREPAYMENT_DEADLINES = (date(2026, 4, 10), date(2026, 7, 10), date(2026, 10, 12), date(2026, 12, 21))
PREPAYMENT_WORDS = ("voorafbetaling", "versement anticip", "advance payment", "prepayment")

DISCLAIMER = ("Indicative estimate from your incoming invoices, not tax advice. We can't see your business costs, "
              "so the real amounts are probably lower; check with your accountant.")
VAT_NOTE = ("We can't tell from your transactions whether you're VAT-registered or use the small-business exemption, "
            "so VAT isn't in this envelope. If your invoices include VAT, that part goes to the VAT return first "
            "and the percentages above apply to the rest.")
SOURCES = [
    "https://www.accountable.eu/nl-be/blog/sociale-bijdragen/",
    "https://www.acerta.be/nl/starters/je-voorbereiding/sociale-bijdragen-betalen-als-starter/sociale-bijdragen-berekenen",
    "https://finance.belgium.be/en/node/124",
    "https://www.sbb.be/nl/magazine/voorafbetalen-belastingen-2026",
    "https://www.practicali.be/blog/geindexeerde-bedragen-aj-2027",
]


def _iso(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _quarter_end(d):
    month = ((d.month - 1) // 3 + 1) * 3
    return date(d.year, month, calendar.monthrange(d.year, month)[1])


def is_self_employed(twin):
    emp = _fact(twin or {}, "employment")
    return bool(emp) and emp.get("value") == "self_employed"


def social_contribution(yearly_income):
    """Yearly social contribution on a yearly net professional income (main occupation, 2026 bands, no minimum)."""
    due, lower = 0.0, 0.0
    for upper, rate in SOCIAL_BANDS:
        if yearly_income > lower:
            due += (min(yearly_income, upper) - lower) * rate
        lower = upper
    return due


def _progressive(amount):
    tax, lower = 0.0, 0.0
    for upper, rate in TAX_BRACKETS:
        if amount > lower:
            tax += (min(amount, upper) - lower) * rate
        lower = upper
    return tax


def income_tax(taxable):
    """Federal tax after the basic tax-free amount, plus the municipal surcharge. Indicative."""
    taxable = max(0.0, taxable)
    federal = max(0.0, _progressive(taxable) - _progressive(min(TAX_FREE, taxable)))
    return federal * (1 + MUNICIPAL)


def social_payments(con, customer_id):
    """Observed social-contribution payments of this customer, oldest first: [(date, amount)]."""
    rows = con.execute("""SELECT booked_at, -amount FROM transactions
                          WHERE customer_id = ? AND subcategory = 'social_contributions' AND amount < 0
                            AND booked_at <= ? ORDER BY booked_at, tx_id""", (customer_id, TODAY.isoformat())).fetchall()
    return [(d, round(a, 2)) for d, a in ((_iso(d), a) for d, a in rows) if d]


def next_social_payment(con, customer_id, twin=None, payments=None):
    """The next social-contribution payment expected from the observed pattern, or None.

    Quarterly payments (a median gap of 80-100 days) repeat 3 calendar months later, otherwise after the median
    gap in days. Returns dict(date, amount, name, legal_deadline)."""
    if twin is not None and not is_self_employed(twin):
        return None
    payments = social_payments(con, customer_id) if payments is None else payments
    if not payments:
        return None
    last, amount = payments[-1]
    gaps = sorted((b[0] - a[0]).days for a, b in zip(payments, payments[1:]))
    gap = gaps[len(gaps) // 2] if gaps else 91
    step = (lambda d: _add_months(d, 3)) if 80 <= gap <= 100 else (lambda d: d + timedelta(days=max(gap, 28)))
    nxt = step(last)
    while nxt <= TODAY:
        nxt = step(nxt)
    name = con.execute("""SELECT counterparty FROM transactions WHERE customer_id = ? AND subcategory = 'social_contributions'
                          AND amount < 0 ORDER BY booked_at DESC, tx_id DESC LIMIT 1""", (customer_id,)).fetchone()
    return dict(date=nxt.isoformat(), amount=amount, name=(name[0] if name and name[0] else "Social insurance fund"),
                subcategory="social_contributions", legal_deadline=_quarter_end(nxt).isoformat())


def _prepayments(con, customer_id):
    """Income-tax prepayments seen this year (descriptions mentioning a prepayment), this customer only."""
    likes = " OR ".join("LOWER(COALESCE(description, '')) LIKE ?" for _ in PREPAYMENT_WORDS)
    rows = con.execute(f"""SELECT booked_at, -amount FROM transactions
                           WHERE customer_id = ? AND amount < 0 AND booked_at >= ? AND booked_at <= ?
                             AND (subcategory = 'income_tax' OR category = 'taxes') AND ({likes})
                           ORDER BY booked_at""",
                       (customer_id, f"{TODAY.year}-01-01", TODAY.isoformat(), *[f"%{w}%" for w in PREPAYMENT_WORDS])).fetchall()
    return [dict(date=d, amount=round(a, 2)) for d, a in rows]


def envelope(con, customer_id, twin):
    """The reserve envelope for a self-employed twin, or {"applicable": False} for anyone else."""
    if not is_self_employed(twin):
        return {"applicable": False}
    since = TODAY - timedelta(days=WINDOW_DAYS)
    rows = con.execute("""SELECT booked_at, amount, counterparty FROM transactions
                          WHERE customer_id = ? AND subcategory = 'invoice' AND amount > 0
                            AND booked_at > ? AND booked_at <= ? ORDER BY booked_at, tx_id""",
                       (customer_id, since.isoformat(), TODAY.isoformat())).fetchall()
    total = sum(r[1] for r in rows)
    yearly = total * 365 / WINDOW_DAYS
    social_year = social_contribution(yearly)
    tax_year = income_tax(yearly - social_year)  # social contributions are deductible; business costs are unknown
    social_pct = round(social_year / yearly * 100, 1) if yearly else SOCIAL_BANDS[0][1] * 100
    tax_pct = round(tax_year / yearly * 100, 1) if yearly else 0.0
    total_pct = round(social_pct + tax_pct, 1)

    def split(amount):
        s, t = round(amount * social_pct / 100), round(amount * tax_pct / 100)
        return dict(social_contributions=s, income_tax=t, total=s + t)

    last = None
    if rows:
        d, amount, who = rows[-1]
        last = dict(date=d, amount=round(amount, 2), counterparty=who, **split(amount))

    payments = social_payments(con, customer_id)
    nxt = next_social_payment(con, customer_id, payments=payments)
    quarterly_now = round(social_year / 4)
    observed = payments[-1][1] if payments else None
    gap = round(quarterly_now - observed) if observed is not None else None
    if not payments:
        social_note = ("We don't see social-contribution payments on your accounts. Contributions are due by the last day "
                       f"of each quarter (main-occupation minimum €{SOCIAL_MIN_QUARTER:,.2f} per quarter in 2026).")
    elif gap is not None and gap > 50:
        social_note = (f"You pay €{observed:,.0f} a quarter now. Provisional contributions are based on your income of three "
                       f"years ago and get regularised later: at today's invoice pace they'd be ≈ €{quarterly_now:,}/quarter, "
                       f"so keeping the full {social_pct:g}% aside avoids a surprise regularisation bill.")
    else:
        social_note = f"Your €{observed:,.0f} quarterly payment is in line with today's invoice pace."
    social = dict(rate_pct=social_pct, estimated_yearly=round(social_year), estimated_quarterly=quarterly_now,
                  observed_quarterly=observed, last_paid=payments[-1][0].isoformat() if payments else None,
                  next_expected=nxt["date"] if nxt else None, next_amount=nxt["amount"] if nxt else None,
                  legal_deadline=nxt["legal_deadline"] if nxt else _quarter_end(TODAY + timedelta(days=1)).isoformat(),
                  gap_per_quarter=gap, note=social_note)

    remaining = [d for d in PREPAYMENT_DEADLINES if d > TODAY]
    seen = _prepayments(con, customer_id)
    per_quarter = round(tax_year / 4)
    tax = dict(rate_pct=tax_pct, estimated_yearly=round(tax_year), per_quarter=per_quarter,
               next_deadline=remaining[0].isoformat() if remaining else None,
               remaining_deadlines=[d.isoformat() for d in remaining], observed_this_year=seen,
               note=("Prepaying is optional for a sole proprietor from income year 2026 (the surcharge was reported "
                     "abolished), but it still earns a small bonus and avoids one large tax bill in 2027."
                     + ("" if seen else " We don't see prepayments on your accounts this year.")))

    parts = [f"{social_pct:g}% for social contributions"
             + (f" (next ≈ €{nxt['amount']:,.0f} around {_nice_date(nxt['date'])})" if nxt else ""),
             f"≈ {tax_pct:.0f}% for tax prepayments"
             + (f" (next deadline {_nice_date(remaining[0])})" if remaining else "")]
    message = f"From every invoice, set aside ≈ {total_pct:.0f}%: " + " and ".join(parts) + "."
    if last:
        message += f" On your last invoice (€{last['amount']:,.0f}) that's €{last['total']:,}."
    if not rows:
        message = (f"No invoices in the last {WINDOW_DAYS} days. When the next one lands, set aside "
                   f"{social_pct:g}% for social contributions and keep a tax reserve too.")
    message += " Indicative, not tax advice."

    return dict(
        applicable=True, as_of=TODAY.isoformat(),
        basis=dict(window_days=WINDOW_DAYS, window_start=(since + timedelta(days=1)).isoformat(), invoice_count=len(rows),
                   invoices_total=round(total, 2), annualised_income=round(yearly),
                   assumption="Sole proprietor in main occupation; invoices treated as income before business costs."),
        set_aside=dict(social_contributions_pct=social_pct, income_tax_pct=tax_pct, total_pct=total_pct,
                       per_1000_invoiced=split(1000)),
        last_invoice=last, social_contributions=social, tax_prepayments=tax,
        vat=dict(known=False, note=VAT_NOTE), message=message, disclaimer=DISCLAIMER, sources=SOURCES)
