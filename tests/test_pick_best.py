"""Run: python -m tests.test_pick_best"""

from bot.handlers.search import pick_best


def rel(title, author=""):
    return {"title": title, "extra": {"author": author}}


def main() -> None:
    # junk first in relevance order gets skipped
    rs = [rel("Summary of Dune"), rel("Dune", "Frank Herbert"), rel("Dune Messiah", "Frank Herbert")]
    assert pick_best("dune", rs)["title"] == "Dune"
    # author in query breaks a title tie
    rs = [rel("The Road", "Jack London"), rel("The Road", "Cormac McCarthy")]
    assert pick_best("the road cormac mccarthy", rs)["extra"]["author"] == "Cormac McCarthy"
    # all junk → fall back to original list rather than nothing
    rs = [rel("Study Guide: 1984")]
    assert pick_best("1984", rs)["title"] == "Study Guide: 1984"
    # ties keep Shelfmark order
    rs = [rel("Emma", "A"), rel("Emma", "B")]
    assert pick_best("emma", rs)["extra"]["author"] == "A"
    print("ok")


if __name__ == "__main__":
    main()
