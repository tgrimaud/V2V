"""Tests for sentence boundary detection."""

from agent.sentence_splitter import find_sentence_boundary


def test_splits_at_period():
    sentence, remainder = find_sentence_boundary("Bonjour, je suis votre assistant. Comment puis-je")
    assert sentence == "Bonjour, je suis votre assistant."
    assert remainder == "Comment puis-je"


def test_splits_at_question_mark():
    sentence, remainder = find_sentence_boundary("Comment allez-vous ? Je suis bien.")
    assert sentence == "Comment allez-vous ?"
    assert remainder == "Je suis bien."


def test_splits_at_exclamation():
    sentence, remainder = find_sentence_boundary("Bienvenue chez nous ! Que puis-je faire ?")
    assert sentence == "Bienvenue chez nous !"
    assert remainder == "Que puis-je faire ?"


def test_no_split_when_too_short():
    sentence, remainder = find_sentence_boundary("Oui. Non.")
    assert sentence == ""
    assert remainder == "Oui. Non."


def test_no_split_without_boundary():
    sentence, remainder = find_sentence_boundary("Je suis en train de réfléchir à votre question")
    assert sentence == ""
    assert remainder == "Je suis en train de réfléchir à votre question"


def test_splits_at_newline():
    text = "Voici les étapes à suivre :\n1. Redémarrez la box"
    sentence, remainder = find_sentence_boundary(text)
    assert sentence == "Voici les étapes à suivre :"
    assert remainder == "1. Redémarrez la box"


def test_empty_input():
    sentence, remainder = find_sentence_boundary("")
    assert sentence == ""
    assert remainder == ""


def test_preserves_full_sentence_at_end():
    sentence, remainder = find_sentence_boundary("Redémarrez votre box internet.")
    assert sentence == "Redémarrez votre box internet."
    assert remainder == ""
