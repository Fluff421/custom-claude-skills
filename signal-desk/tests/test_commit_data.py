"""Local bare-repository fixtures only. These tests never contact GitHub."""
import pathlib
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / ".github/scripts/commit_data.sh"


class DataPublication(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.remote = self.root / "remote.git"
        self.work = self.root / "work"
        self.rival = self.root / "rival"
        self.git(self.root, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.git(self.root, "clone", str(self.remote), str(self.work))
        self.identity(self.work)
        (self.work / "scope.csv").write_text("initial\n")
        (self.work / "other.txt").write_text("initial unrelated\n")
        self.git(self.work, "add", ".")
        self.git(self.work, "commit", "-m", "Synthetic fixture baseline")
        self.git(self.work, "push", "origin", "main")
        self.git(self.root, "clone", str(self.remote), str(self.rival))
        self.identity(self.rival)

    def git(self, cwd, *args):
        return subprocess.run(["git", *args], cwd=cwd, text=True,
                              capture_output=True, check=True).stdout.strip()

    def identity(self, path):
        self.git(path, "config", "user.name", "Synthetic fixture")
        self.git(path, "config", "user.email", "fixture@example.invalid")

    def advance(self, name, content):
        (self.rival / name).write_text(content)
        self.git(self.rival, "add", name)
        self.git(self.rival, "commit", "-m", "Synthetic concurrent change")
        self.git(self.rival, "push", "origin", "main")

    def helper(self):
        return subprocess.run(["bash", str(SCRIPT), "Synthetic data publication", "scope.csv"],
                              cwd=self.work, text=True, capture_output=True)

    def test_scoped_outputs_publish_with_unrelated_dirty_tracked_file(self):
        self.advance("remote.txt", "unrelated concurrent change\n")
        (self.work / "scope.csv").write_text("new generated observation\n")
        (self.work / "other.txt").write_text("unrelated local working change\n")
        run = self.helper()
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(self.git(self.root, "--git-dir", str(self.remote), "show", "main:scope.csv"),
                         "new generated observation")
        self.assertEqual((self.work / "other.txt").read_text(), "unrelated local working change\n")
        self.assertEqual(self.git(self.root, "--git-dir", str(self.remote), "show", "main:other.txt"),
                         "initial unrelated")
        message = self.git(self.root, "--git-dir", str(self.remote), "log", "-1", "--format=%B")
        self.assertEqual(message.count("Co-authored-by: Perplexity <noreply@perplexity.ai>"), 1)

    def test_publication_conflict_is_failure_not_green_skip(self):
        self.advance("scope.csv", "concurrent generated observation\n")
        (self.work / "scope.csv").write_text("different generated observation\n")
        run = self.helper()
        self.assertNotEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(self.git(self.root, "--git-dir", str(self.remote), "show", "main:scope.csv"),
                         "concurrent generated observation")
