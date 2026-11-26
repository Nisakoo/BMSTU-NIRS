"""Russian stop words used by the BM25 analyzer and the context rule.

The list is data, not logic: one place for every consumer. Terms are written in
their normal form after ``pymorphy3`` lemmatization, therefore documents and
queries are filtered the same way.

Only words that carry no topic are listed here. Character names
(``CHARACTER_NAME_TERMS`` in ``context.py``), topic nouns (``игра``, ``футбол``,
``мороз``, ``зуб``) and meaning-bearing adjectives (``новый``, ``нужный``) are
kept on purpose: removing them would erase the signal the search exists for.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

# Pronouns, particles, prepositions, conjunctions and adverbs.
FUNCTION_WORDS: frozenset[str] = frozenset(
    """
    а без более бы был была были было в вам вас ваш весь во вот впрочем
    все всё всегда вы где да даже для до его ее ей ему если есть еще ещё же за
    затем зачем здесь и из или им ими их к как какая какие каким каких какой
    когда кто куда ли либо между меня мне много мной мною мой моя моё мы на над
    надо наконец нас наш не него нее неё нет ни никогда ним них ничего но ну о об
    обо однако он она они оно от очень по под пока после потом потому поэтому при
    про просто разве с сам сама сами само свое своё свои свой своя себе себя
    сейчас со совсем так также такой там тебе тебя тем теперь то тогда тоже
    только том тот ту ты у уж уже хотя чего чей чем через что чтобы чье чья эта
    эти это этого этой этом этому этот эту я
    """.split()
)

# Light verbs: they describe an action in general, never the topic of a story.
LIGHT_VERBS: frozenset[str] = frozenset(
    """
    быть видеть говорить давать делать думать знать иметь мочь сделать сказать
    хотеть являться
    """.split()
)

STOP_WORDS: frozenset[str] = FUNCTION_WORDS | LIGHT_VERBS


def drop_stop_words(terms: Iterable[str]) -> tuple[str, ...]:
    """Keep the original order and duplicates, remove stop words."""

    return tuple(term for term in terms if term and term not in STOP_WORDS)


def stop_word_share(terms: Sequence[str]) -> float:
    """Share of stop words in a term sequence; handy for diagnostics."""

    if not terms:
        return 0.0
    return sum(1 for term in terms if term in STOP_WORDS) / len(terms)


__all__ = [
    "FUNCTION_WORDS",
    "LIGHT_VERBS",
    "STOP_WORDS",
    "drop_stop_words",
    "stop_word_share",
]
