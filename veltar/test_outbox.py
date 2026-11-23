"""Outbox contract: a failed send is kept, never dropped; an attachment is the bot's own copy.

Run:  python3 test_outbox.py            (the veltar.py next to this file)
      VELTAR_SRC=/opt/veltar python3 test_outbox.py   (the deployed copy)
"""
import atexit, contextlib, io, json, os, shutil, sys, tempfile, threading, time, unittest

sys.path.insert(0, os.environ.get("VELTAR_SRC", os.path.dirname(os.path.abspath(__file__))))
argv = sys.argv; sys.argv = [argv[0], "status"]  # veltar.py parses its CLI at import; `status` only prints
with contextlib.redirect_stdout(io.StringIO()):
    import veltar
sys.argv = argv


class Acc:
    """Just enough of a Delta Chat account: records sends, or fails like a core error."""

    def __init__(self): self.sent, self.fail = [], False
    def get_contact_by_id(self, _): return self
    def create_chat(self): return self

    def send_message(self, text=None, file=None):
        if self.fail or (file and not os.path.exists(file)): raise RuntimeError("simulated core error")
        self.sent.append((text, file))


class OutboxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        home = cls.home = tempfile.mkdtemp(); os.makedirs(f"{home}/outbox"); atexit.register(shutil.rmtree, home, True)
        for name, value in dict(CFG=f"{home}/config.json", OUTBOX=f"{home}/outbox", FAILED=f"{home}/outbox/failed",
                                SPOOL=f"{home}/spool", LOG=f"{home}/veltar.log").items(): setattr(veltar, name, value)
        json.dump({"owner_contact_id": 1}, open(veltar.CFG, "w"))
        cls.acc = Acc(); threading.Thread(target=veltar.outbox_loop, args=(cls.acc,), daemon=True).start()

    def setUp(self): self.acc.sent.clear(); self.acc.fail = False

    def send(self, text, file=None):
        with contextlib.redirect_stdout(io.StringIO()): veltar.send(text, file)

    def refused(self, text, file=None):
        with self.assertRaises(SystemExit) as r, contextlib.redirect_stdout(io.StringIO()): veltar.send(text, file)
        return r.exception.code

    def test_text_is_sent_before_send_returns(self):
        self.send("hi")
        self.assertEqual(self.acc.sent, [("hi", None)]); self.assertEqual(os.listdir(veltar.OUTBOX), ["failed"])

    def test_attachment_is_the_bots_own_copy(self):
        src = f"{self.home}/shot.png"; open(src, "wb").write(b"png")
        self.send("with pic", src)
        ((text, sent_file),) = self.acc.sent
        self.assertEqual(text, "with pic"); self.assertTrue(sent_file.startswith(veltar.SPOOL + "/out-"))
        self.assertFalse(os.path.exists(sent_file))  # our copy goes once core has it
        self.assertTrue(os.path.exists(src)); self.assertEqual(os.listdir(veltar.SPOOL), [])

    def test_failed_send_is_kept_and_reported(self):
        self.acc.fail = True
        self.assertIn("not sent", self.refused("kept"))
        (job,) = os.listdir(veltar.FAILED)
        self.assertEqual(json.load(open(f"{veltar.FAILED}/{job}"))["text"], "kept")
        self.assertEqual(os.listdir(veltar.OUTBOX), ["failed"])

    def test_job_with_a_vanished_file_is_kept(self):  # the failure that used to delete the reply
        json.dump({"text": "old style", "file": "/nonexistent/x.png"}, open(f"{veltar.OUTBOX}/probe.json", "w"))
        for _ in range(50):
            if "probe.json" not in os.listdir(veltar.OUTBOX): break
            time.sleep(0.1)
        self.assertTrue(os.path.exists(f"{veltar.FAILED}/probe.json")); self.assertEqual(self.acc.sent, [])
        os.remove(f"{veltar.FAILED}/probe.json")

    def test_empty_message_is_refused(self):
        self.assertIn("empty", self.refused("   "))


if __name__ == "__main__": unittest.main()
