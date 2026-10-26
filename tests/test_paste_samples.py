"""The two pasteable sample meetings behave as documented for manual testing."""

from conftest import MANAGER, notes


def paste(c, name, date, mangle=False):
    text = notes(name)
    if mangle:  # what copy-paste often does: CRLF, extra spaces, everything on one line
        text = "  " + text.replace("\n", "\r\n   ").replace(". ", ".  ")
    r = c.post("/extract", json={"notes": text, "meeting_date": date}, headers=MANAGER)
    assert r.status_code == 200, r.text
    return r.json()


def test_sample_meetings_end_to_end(client):
    assert paste(client, "sample_meeting_A", "2026-10-20")["items"] == 4
    assert paste(client, "sample_meeting_B", "2026-10-27", mangle=True)["items"] == 5
    st = client.get("/state", headers=MANAGER).json()
    acts = {a["text"]: a for a in st["actions"]}
    listing = acts["Update the app store listing"]
    assert listing["owner"] is None and "owner" in listing["missing_info"]  # model guessed Asha; code refused
    login = acts["Finish the login screen"]
    assert login["deadline_date"] == "2026-10-30" and login["deadline_status"] == "needs_confirmation"
    assert acts["Test the login screen"]["depends_on"] == [login["id"]]
    assert acts["Write the test plan"]["depends_on"] == [acts["Approve the testing budget"]["id"]]
    risk = next(r for r in st["risks"] if "push" in r["text"].lower())
    assert risk["owner"] is None
    cross = [c for c in st["conflicts"] if c["source"] == "cross_meeting"]
    assert [(c["previous"], c["current"]) for c in cross] == [("Launch the beta on Android first", "Launch the beta on iOS first")]
