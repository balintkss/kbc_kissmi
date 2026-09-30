"""KBC product variants per topic.

Illustrative catalogue for the PoC: names follow KBC's product families, but the
descriptions and any rates are placeholders, not real KBC terms.
An anonymous visitor sees every variant of a topic; a logged-in customer sees one
highlighted variant (chosen by the recommender) and the others collapsed.
"""

CATALOG = {
    "car_loan": {
        "title": "Car loans",
        "variants": {
            "new_car_loan": dict(name="Car loan – new car", summary="Finance a new car over up to 84 months.",
                                 features=["Fixed monthly payment", "Up to 84 months", "Decision in minutes in KBC Mobile"]),
            "used_car_loan": dict(name="Car loan – second-hand car", summary="Finance a used car up to 5 years old.",
                                  features=["Fixed monthly payment", "Up to 60 months", "No down payment required"]),
            "green_car_loan": dict(name="Green car loan", summary="Lower rate for electric and plug-in hybrid cars.",
                                   features=["Reduced green rate", "Up to 84 months", "Combine with a home charger"]),
        },
    },
    "car_insurance": {
        "title": "Car insurance",
        "variants": {
            "liability": dict(name="Third-party liability (BA)", summary="The legal minimum: damage you cause to others.",
                              features=["Mandatory cover", "Lowest premium", "Legal assistance optional"]),
            "mini_omnium": dict(name="Mini-omnium", summary="Liability plus theft, fire, glass and natural events.",
                                features=["Theft & fire", "Glass breakage", "Storm, hail and flooding"]),
            "omnium": dict(name="Full omnium", summary="Everything, including damage to your own car.",
                           features=["Own damage covered", "New-value compensation for the first years", "Replacement car"]),
        },
    },
    "savings": {
        "title": "Saving & investing",
        "variants": {
            "savings_account": dict(name="Savings account", summary="Instantly available money for unexpected costs.",
                                    features=["Available any time", "Tax-free interest up to the legal limit", "Automatic monthly transfer"]),
            "pension_savings": dict(name="Pension savings", summary="Save for later and get a tax reduction every year.",
                                    features=["25–30% tax reduction", "From €10 a month", "Long-term growth"]),
            "investment_plan": dict(name="Investment plan", summary="Invest a fixed amount every month in funds.",
                                    features=["From €25 a month", "Spread over time", "Change or stop any time"]),
        },
    },
    "home": {
        "title": "Home",
        "variants": {
            "home_loan": dict(name="Home loan", summary="Buy your first or next home.",
                              features=["Fixed or variable rate", "Simulation in KBC Mobile", "Certainty within 10 minutes"]),
            "renovation_loan": dict(name="Energy renovation loan", summary="Insulation, heat pump, solar panels.",
                                    features=["Reduced rate for energy works", "No mortgage deed needed", "Lower energy bills"]),
            "home_insurance": dict(name="Home insurance", summary="Fire, water damage, storm and theft for your home.",
                                   features=["For owners and tenants", "Assistance 24/7", "Contents included"]),
        },
    },
    "family": {
        "title": "Family",
        "variants": {
            "child_savings": dict(name="Savings account for your child", summary="Put the child benefit to work for later.",
                                  features=["In your child's name", "Automatic monthly transfer", "Grandparents can contribute"]),
            "hospital_insurance": dict(name="Hospitalisation insurance", summary="Hospital costs covered for the whole family.",
                                       features=["Add a newborn without a waiting period", "Private room option", "Pre- and post-hospital costs"]),
            "family_liability": dict(name="Family liability insurance", summary="Damage your family or pets cause to others.",
                                     features=["Whole household incl. pets", "Low yearly premium", "Legal assistance"]),
        },
    },
}
