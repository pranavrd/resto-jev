"""The questions asked of Jev for every building, versioned.

Jev reads questions literally, counts badly and answers one thing per field (TypeSafe's guidance), so:
each question asks one thing, the options say what they mean, and the facts it needs (counts, shares,
distances) are already computed in the evidence text. Changing any wording means a new PROMPT_VERSION.
"""

from typesafe_sdk import Choice, Noul

from streetwalker.groundtruth import D1_CLASSES

PROMPT_VERSION = "p1"  # default; later versions are listed in PROMPTS
PROMPT_VERSIONS = ("p1", "p2")
MODEL_VERSION = "jev-1.13.0"  # pinned; never jev-latest in pipelines

D2_TYPES = ("restaurant", "cafe", "bar", "retail", "grocery", "office", "personal services", "other", "none")

D1_CRITERIA = {
    "residential": "People live here and no business operates here: houses, rowhouses, apartment buildings, and garages or sheds that belong to homes.",
    "commercial": "Used for business and not for housing: stores, restaurants, offices, hotels, and larger buildings with businesses on their floors.",
    "mixed-use": "Combines housing with a business: typically a small rowhouse-sized building with a shop, restaurant or office on the ground floor and homes above.",
    "industrial": "Used for making, storing or moving goods: factories, warehouses, workshops, utility buildings.",
    "civic-institutional": "Places of worship, schools, universities, libraries, hospitals, government buildings, museums, theaters and sports centers.",
    "vacant": "Empty or abandoned, with no current use.",
    "other": "Parking garages and anything that fits none of the other options.",
}

D2_CRITERIA = {
    "restaurant": "A restaurant, fast-food place or food hall.",
    "cafe": "A cafe, coffee shop or ice cream shop.",
    "bar": "A bar, pub or brewery taproom.",
    "retail": "A shop selling goods that are not mainly food.",
    "grocery": "A grocery, convenience store, butcher or market.",
    "office": "An office, bank or professional service.",
    "personal services": "A salon, clinic, gym or similar service to individuals.",
    "other": "Some other kind of business.",
    "none": "No business operates in this building.",
}

D1_INSTRUCTIONS = (
    "What is the main use of this building? Judge from the tags and points of interest listed for the "
    "building, its footprint, and its street. When the building itself has no tags or points of interest, "
    "the neighbouring buildings, the street type and the block summary are the evidence."
)
D2_INSTRUCTIONS = "If a business operates in this building, which kind is the main one?"
D3_INSTRUCTIONS = "Does a business that prepares or serves food or drink to customers operate in this building?"


# p2 (experiment): tells Jev how to weigh block context when the building itself is silent.
D1_INSTRUCTIONS_P2 = (
    D1_INSTRUCTIONS
    + " A rowhouse-sized building attached to its neighbours that has no tags of its own, on a street where the"
    " block summary shows several business points of interest, is often a business on the ground floor with"
    " homes above (mixed-use). The same building on a block with no businesses is residential."
)


def build_questions(version: str = PROMPT_VERSION) -> dict:
    assert set(D1_CRITERIA) == set(D1_CLASSES) and set(D2_CRITERIA) == set(D2_TYPES)
    assert version in PROMPT_VERSIONS, version
    return {
        "d1": Choice(instructions=D1_INSTRUCTIONS_P2 if version == "p2" else D1_INSTRUCTIONS, criteria=D1_CRITERIA),
        "d2": Choice(instructions=D2_INSTRUCTIONS, criteria=D2_CRITERIA),
        "d3": Noul(
            instructions=D3_INSTRUCTIONS,
            criteria={
                "true": "A restaurant, cafe, bar, bakery or similar food or drink business is evident here.",
                "false": "No food or drink business is evident, or the only businesses are shops, offices or services.",
            },
        ),
    }


D5_INSTRUCTIONS = (
    "A vision model described a street photo that was aimed at the target building. Does the description say that "
    "the target building itself has a shop sign, awning, shop window or entrance, as opposed to saying nothing "
    "about it or only describing neighbouring buildings?"
)


def build_tier1_questions(version: str = PROMPT_VERSION) -> dict:
    """Tier 1: the D1 to D3 questions plus D5, which asks whether the photo description is about the target building."""
    return {
        **build_questions(version),
        "d5": Noul(
            instructions=D5_INSTRUCTIONS,
            criteria={
                "true": "The description reports a sign, awning, shop window or entrance on the target building itself.",
                "false": "The description says the ground floor is not visible, or reports signs only on neighbouring buildings.",
            },
        ),
    }
