"""Per-country settings. To add a country, add one entry to COUNTRIES and nothing else.

Each entry controls: the towns/states shown, how phone numbers are read, what the
"last 5 characters" of that country's ID look like, and the wording shown to people.
"""
import re

COUNTRIES = {
    "ZW": {
        "name": "Zimbabwe",
        "dial": "263",
        "local_phone_re": r"0\d{9}",      # 0771234567 -> +263771234567
        "phone_example": "0771234567",
        "last5_re": r"^[A-Z0-9]{5}$",
        "last5_example": "50E63",
        "last5_help": "The last 5 letters or numbers of the ID number, for example 50E63.",
        "last5_error": "Enter exactly 5 letters or numbers, for example 50E63.",
        "name_example": "Tinashe Moyo",
        "place_example": "CBZ Kuwadzana branch",
        "area_label": "town or city",
        "alt_ids": "a Passport, Driver's Licence or Birth Certificate",
        "areas": [
            "Harare", "Bulawayo", "Chitungwiza", "Mutare", "Gweru", "Kwekwe", "Kadoma", "Masvingo",
            "Chinhoyi", "Bindura", "Marondera", "Victoria Falls", "Hwange", "Beitbridge", "Gwanda",
            "Chegutu", "Norton", "Ruwa", "Epworth", "Karoi", "Rusape", "Zvishavane", "Kariba", "Other",
        ],
    },
    "ZA": {
        "name": "South Africa",
        "dial": "27",
        "local_phone_re": r"0\d{9}",      # 0821234567 -> +27821234567
        "phone_example": "0821234567",
        "last5_re": r"^\d{5}$",
        "last5_example": "08083",
        "last5_help": "The last 5 digits of the 13-digit ID number, for example 08083.",
        "last5_error": "Enter exactly the last 5 digits of the ID number, for example 08083.",
        "name_example": "Thabo Mokoena",
        "place_example": "Home Affairs, Braamfontein",
        "area_label": "town or city",
        "alt_ids": "a Passport, Driver's Licence or Birth Certificate",
        "areas": [
            "Johannesburg", "Cape Town", "Durban", "Pretoria", "Soweto", "Sandton", "Centurion",
            "Gqeberha", "East London", "Bloemfontein", "Pietermaritzburg", "Polokwane", "Mbombela",
            "Kimberley", "Rustenburg", "Mahikeng", "Welkom", "George", "Stellenbosch", "Other",
        ],
    },
    "US": {
        "name": "United States",
        "dial": "1",
        "local_phone_re": r"\d{10}",      # 2125550123 -> +12125550123
        "phone_example": "2125550123",
        "last5_re": r"^[A-Z0-9]{5}$",
        "last5_example": "4X9K2",
        "last5_help": (
            "The last 5 letters or numbers of the driver's license or state ID number. "
            "Never enter a Social Security number."
        ),
        "last5_error": "Enter exactly 5 letters or numbers from the end of the license or state ID number.",
        "name_example": "Jordan Smith",
        "place_example": "Walgreens, Main Street",
        "area_label": "state",
        "alt_ids": "a Passport, Birth Certificate or another government-issued photo ID",
        "areas": [
            "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
            "Delaware", "District of Columbia", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois",
            "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts",
            "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
            "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota",
            "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
            "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
            "West Virginia", "Wisconsin", "Wyoming", "Other",
        ],
    },
}

DEFAULT_COUNTRY = "ZW"
COUNTRY_CHOICES = [(code, c["name"]) for code, c in COUNTRIES.items()]


def get_country(code: str) -> dict:
    return COUNTRIES.get(code) or COUNTRIES[DEFAULT_COUNTRY]


def last5_matches(value: str, code: str) -> bool:
    return bool(re.match(get_country(code)["last5_re"], value))


def grouped_area_choices():
    """Choices grouped by country, for a <select> with optgroups."""
    out = [("", "Choose a place")]
    for c in COUNTRIES.values():
        out.append((c["name"], [(a, a) for a in c["areas"]]))
    return out


def js_config() -> dict:
    """The small subset the browser needs to adapt the form when the country changes."""
    return {
        code: {k: c[k] for k in (
            "name", "phone_example", "last5_example", "last5_help", "name_example",
            "place_example", "area_label",
        )}
        for code, c in COUNTRIES.items()
    }
