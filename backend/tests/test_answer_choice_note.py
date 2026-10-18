from app.services.export.answer_format import choice_note


def test_choice_note_for_extra_points():
    assert "any 2 of the following 5 points" in choice_note(5, 2)
    assert "any 5 of the following 8 points" in choice_note(8, 5)


def test_no_choice_note_when_there_are_no_spare_points():
    assert choice_note(1, 1) == ""
    assert choice_note(3, 3) == ""
    assert choice_note(2, 5) == ""
