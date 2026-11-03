import pytest

from slidefinder.sync import locate_clip, parse_clip_lengths, parse_duration


def test_parse_duration():
    assert parse_duration("12:48") == 768.0
    assert parse_duration("768") == 768.0
    assert parse_duration(" 0:30.5 ") == 30.5


def test_parse_clip_lengths():
    assert parse_clip_lengths("12:48,10:00") == [768.0, 600.0]


def test_locate_clip_example_from_the_brief():
    # a slide at 13 minutes is clip 2, 12 seconds in
    assert locate_clip(13 * 60, [768.0]) == (2, "00:12.00")


@pytest.mark.parametrize("t, expected", [
    (0.0, (1, "00:00.00")),
    (767.9, (1, "12:47.90")),
    (768.0, (2, "00:00.00")),
    (-1.0, ("", "")),
])
def test_locate_clip_boundaries(t, expected):
    assert locate_clip(t, [768.0]) == expected


def test_last_length_repeats_and_lists_are_respected():
    lengths = [768.0, 700.0, 100.0]
    assert locate_clip(1600, lengths) == (4, "00:32.00")
    assert locate_clip(768 + 699, lengths)[0] == 2


def test_solve_offset_round_trips_with_locate_clip():
    from slidefinder.sync import solve_offset

    lengths = [768.0, 750.0]
    # a slide at 14:20 into the data was seen 02:00 into clip 2
    offset = solve_offset(14 * 60 + 20, lengths, clip=2, clip_time=120.0)
    assert offset == pytest.approx(768 + 120 - 860)
    assert locate_clip(14 * 60 + 20 + offset, lengths) == (2, "02:00.00")


def test_solve_offset_in_the_first_clip_and_beyond_the_list():
    from slidefinder.sync import solve_offset

    assert solve_offset(100.0, [768.0], clip=1, clip_time=90.0) == -10.0
    assert solve_offset(0.0, [768.0, 500.0], clip=4, clip_time=0.0) == 768 + 500 + 500
    with pytest.raises(ValueError):
        solve_offset(0.0, [768.0], clip=0, clip_time=0.0)
