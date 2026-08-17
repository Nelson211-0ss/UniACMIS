"""
Shared reference data.

Lives in `core` because more than one module needs it and none of them owns it.
Putting it in a domain app would force the others to import that app's models,
which the module boundaries forbid for good reason.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class SouthSudanState(models.TextChoices):
    """The ten states and three administrative areas of South Sudan.

    A constrained list rather than free text: FR-RPT-03 requires statutory returns
    disaggregated by state of origin, and free text turns that into guesswork
    ("C. Equatoria", "Central Eq.", "CES" are one place typed three ways).
    """

    CENTRAL_EQUATORIA = "central_equatoria", _("Central Equatoria")
    EASTERN_EQUATORIA = "eastern_equatoria", _("Eastern Equatoria")
    WESTERN_EQUATORIA = "western_equatoria", _("Western Equatoria")
    JONGLEI = "jonglei", _("Jonglei")
    UNITY = "unity", _("Unity")
    UPPER_NILE = "upper_nile", _("Upper Nile")
    WARRAP = "warrap", _("Warrap")
    NORTHERN_BAHR_EL_GHAZAL = "northern_bahr_el_ghazal", _("Northern Bahr el Ghazal")
    WESTERN_BAHR_EL_GHAZAL = "western_bahr_el_ghazal", _("Western Bahr el Ghazal")
    LAKES = "lakes", _("Lakes")
    ABYEI = "abyei", _("Abyei Administrative Area")
    GREATER_PIBOR = "greater_pibor", _("Greater Pibor Administrative Area")
    RUWENG = "ruweng", _("Ruweng Administrative Area")
    OUTSIDE_SOUTH_SUDAN = "outside", _("Outside South Sudan")


class Gender(models.TextChoices):
    FEMALE = "female", _("Female")
    MALE = "male", _("Male")
    OTHER = "other", _("Other")
    UNDISCLOSED = "undisclosed", _("Prefer not to say")
