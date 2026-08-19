"""
Merit list ranking and quotas (FR-ADM-06).

The policy under test is stated in merit_list.py's module docstring; these
exercise each numbered point, including the two easy-to-get-wrong ones: an
under-filled reserved category releasing its seats to the general pool, and
rank reflecting merit regardless of who was actually admitted.
"""

from __future__ import annotations

from decimal import Decimal

from apps.admissions.merit_list import Candidate, generate_merit_list


def _candidate(app_id: int, score: str | None, **attrs) -> Candidate:
    return Candidate(
        application_id=app_id,
        score=Decimal(score) if score is not None else None,
        attributes=attrs,
    )


def test_no_quota_ranks_everyone_and_admits_everyone():
    candidates = [_candidate(1, "70"), _candidate(2, "90"), _candidate(3, "50")]
    entries = generate_merit_list(candidates, None)

    by_id = {e.application_id: e for e in entries}
    assert all(e.admitted for e in entries)
    assert by_id[2].rank == 1  # highest score first
    assert by_id[1].rank == 2
    assert by_id[3].rank == 3


def test_scores_rank_descending():
    candidates = [_candidate(1, "60"), _candidate(2, "95"), _candidate(3, "80")]
    entries = generate_merit_list(candidates, {"total_seats": 10})
    ranks = {e.application_id: e.rank for e in entries}
    assert ranks == {2: 1, 3: 2, 1: 3}


def test_missing_score_ranks_last():
    candidates = [_candidate(1, "60"), _candidate(2, None), _candidate(3, "10")]
    entries = generate_merit_list(candidates, None)
    ranks = {e.application_id: e.rank for e in entries}
    assert ranks[2] == 3  # unscored is worst, even below a low real score


def test_ties_break_on_application_id_for_reproducibility():
    candidates = [_candidate(5, "70"), _candidate(2, "70"), _candidate(9, "70")]
    entries = generate_merit_list(candidates, None)
    ranks = {e.application_id: e.rank for e in entries}
    assert ranks == {2: 1, 5: 2, 9: 3}


def test_total_seats_caps_admission_in_rank_order():
    candidates = [_candidate(i, str(100 - i)) for i in range(1, 6)]  # 1 best .. 5 worst
    entries = generate_merit_list(candidates, {"total_seats": 3})

    admitted = {e.application_id for e in entries if e.admitted}
    assert admitted == {1, 2, 3}
    not_admitted = [e for e in entries if not e.admitted]
    assert {e.application_id for e in not_admitted} == {4, 5}
    # Rank is assigned regardless of admission outcome.
    assert {e.rank for e in not_admitted} == {4, 5}


def test_a_reserved_category_is_filled_first_from_its_own_best_ranked():
    candidates = [
        _candidate(1, "90", state="central_equatoria"),
        _candidate(2, "80", state="warrap"),
        _candidate(3, "70", state="warrap"),
        _candidate(4, "60", state="warrap"),
    ]
    quota = {"total_seats": 2, "reserved": [{"category": "state", "value": "warrap", "seats": 1}]}
    entries = generate_merit_list(candidates, quota)
    by_id = {e.application_id: e for e in entries}

    # One Warrap seat goes to the best-ranked Warrap candidate (id 2, score 80),
    # not the best-ranked Warrap candidate overall rank position.
    assert by_id[2].admitted and by_id[2].quota_category == "state:warrap"
    # The remaining seat fills from general merit: candidate 1 (score 90).
    assert by_id[1].admitted and by_id[1].quota_category is None
    assert not by_id[3].admitted
    assert not by_id[4].admitted


def test_an_underfilled_reserved_category_releases_its_seats_to_the_general_pool():
    """Policy #4: a quota that cannot find enough matching candidates must not
    leave seats empty — real quota policy returns them to general merit."""
    candidates = [
        _candidate(1, "90", state="central_equatoria"),
        _candidate(2, "80", state="central_equatoria"),
        _candidate(3, "70", state="warrap"),  # only one Warrap candidate exists
    ]
    quota = {"total_seats": 3, "reserved": [{"category": "state", "value": "warrap", "seats": 2}]}
    entries = generate_merit_list(candidates, quota)

    # Only 1 of the 2 reserved Warrap seats could be filled; the other reverts
    # to general merit and is filled by the next-best candidate overall.
    assert all(e.admitted for e in entries)
    by_id = {e.application_id: e for e in entries}
    assert by_id[3].quota_category == "state:warrap"
    assert by_id[1].quota_category is None
    assert by_id[2].quota_category is None


def test_multiple_reserved_categories_are_filled_in_declared_order():
    candidates = [
        _candidate(1, "95", gender="male", state="lakes"),
        _candidate(2, "40", gender="female", state="warrap"),
        _candidate(3, "30", gender="female", state="lakes"),
    ]
    quota = {
        "total_seats": 2,
        "reserved": [
            {"category": "state", "value": "warrap", "seats": 1},
            {"category": "gender", "value": "female", "seats": 1},
        ],
    }
    entries = generate_merit_list(candidates, quota)
    by_id = {e.application_id: e for e in entries}

    # Warrap bucket takes candidate 2 (only Warrap applicant).
    assert by_id[2].admitted and by_id[2].quota_category == "state:warrap"
    # Gender bucket wants a female candidate not yet admitted: candidate 3.
    assert by_id[3].admitted and by_id[3].quota_category == "gender:female"
    # Seats exhausted — candidate 1 (highest raw score) does not get in.
    assert not by_id[1].admitted


def test_a_candidate_already_admitted_by_one_quota_is_not_double_counted():
    candidates = [
        _candidate(1, "90", gender="female", state="warrap"),
        _candidate(2, "50", gender="female", state="lakes"),
    ]
    quota = {
        "total_seats": 5,
        "reserved": [
            {"category": "state", "value": "warrap", "seats": 1},
            {"category": "gender", "value": "female", "seats": 1},
        ],
    }
    entries = generate_merit_list(candidates, quota)
    by_id = {e.application_id: e for e in entries}

    # Candidate 1 fills the state quota first (declared first); the gender
    # quota then looks for a not-yet-admitted female and finds candidate 2.
    assert by_id[1].quota_category == "state:warrap"
    assert by_id[2].quota_category == "gender:female"
    assert by_id[1].admitted and by_id[2].admitted


def test_empty_candidate_list_returns_empty():
    assert generate_merit_list([], {"total_seats": 10}) == []


def test_zero_seats_admits_no_one_but_still_ranks():
    candidates = [_candidate(1, "90"), _candidate(2, "80")]
    entries = generate_merit_list(candidates, {"total_seats": 0})
    assert not any(e.admitted for e in entries)
    assert {e.rank for e in entries} == {1, 2}
