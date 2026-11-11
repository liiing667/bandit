# Copyright (c) 2015 VMware, Inc.
#
# SPDX-License-Identifier: Apache-2.0
import collections
import json
import tempfile
import textwrap
from unittest import mock

import testtools

import bandit
from bandit.core import config
from bandit.core import constants
from bandit.core import issue
from bandit.core import manager
from bandit.core import metrics
from bandit.formatters import json as b_json


class JsonFormatterTests(testtools.TestCase):
    def setUp(self):
        super().setUp()
        conf = config.BanditConfig()
        self.manager = manager.BanditManager(conf, "file")
        (tmp_fd, self.tmp_fname) = tempfile.mkstemp()
        self.context = {
            "filename": self.tmp_fname,
            "lineno": 4,
            "linerange": [4],
        }
        self.check_name = "hardcoded_bind_all_interfaces"
        self.issue = issue.Issue(
            bandit.MEDIUM,
            issue.Cwe.MULTIPLE_BINDS,
            bandit.MEDIUM,
            "Possible binding to all interfaces.",
        )

        self.candidates = [
            issue.Issue(
                issue.Cwe.MULTIPLE_BINDS,
                bandit.LOW,
                bandit.LOW,
                "Candidate A",
                lineno=1,
            ),
            issue.Issue(
                bandit.HIGH,
                issue.Cwe.MULTIPLE_BINDS,
                bandit.HIGH,
                "Candiate B",
                lineno=2,
            ),
        ]

        self.manager.out_file = self.tmp_fname

        self.issue.fname = self.context["filename"]
        self.issue.lineno = self.context["lineno"]
        self.issue.linerange = self.context["linerange"]
        self.issue.test = self.check_name

        self.manager.results.append(self.issue)
        self.manager.metrics = metrics.Metrics()

        # mock up the metrics
        for key in ["_totals", "binding.py"]:
            self.manager.metrics.data[key] = {"loc": 4, "nosec": 2}
            for criteria, default in constants.CRITERIA:
                for rank in constants.RANKING:
                    self.manager.metrics.data[key][f"{criteria}.{rank}"] = 0

    @mock.patch("bandit.core.manager.BanditManager.get_issue_list")
    def test_report(self, get_issue_list):
        self.manager.files_list = ["binding.py"]
        self.manager.scores = [
            {
                "SEVERITY": [0] * len(constants.RANKING),
                "CONFIDENCE": [0] * len(constants.RANKING),
            }
        ]

        get_issue_list.return_value = collections.OrderedDict(
            [(self.issue, self.candidates)]
        )

        with open(self.tmp_fname, "w") as tmp_file:
            b_json.report(
                self.manager,
                tmp_file,
                self.issue.severity,
                self.issue.confidence,
            )

        with open(self.tmp_fname) as f:
            data = json.loads(f.read())
            self.assertIsNotNone(data["generated_at"])
            self.assertEqual(self.tmp_fname, data["results"][0]["filename"])
            self.assertEqual(
                self.issue.severity, data["results"][0]["issue_severity"]
            )
            self.assertEqual(
                self.issue.confidence, data["results"][0]["issue_confidence"]
            )
            self.assertEqual(self.issue.text, data["results"][0]["issue_text"])
            self.assertEqual(
                self.context["lineno"], data["results"][0]["line_number"]
            )
            self.assertEqual(
                self.context["linerange"], data["results"][0]["line_range"]
            )
            self.assertEqual(self.check_name, data["results"][0]["test_name"])
            self.assertIn("candidates", data["results"][0])
            self.assertIn("more_info", data["results"][0])
            self.assertIsNotNone(data["results"][0]["more_info"])

    def test_report_preserves_fields_with_nosec_suppression(self):
        """Nosec suppression keeps the JSON schema unchanged."""
        conf = config.BanditConfig()
        b_mgr = manager.BanditManager(conf, "file")
        (tmp_fd, tmp_fname) = tempfile.mkstemp()

        suppressed_source = textwrap.dedent(
            """\
            import subprocess
            run(
                subprocess.Popen("relative/path", shell=True),
                subprocess.Popen("relative/path", shell=True),
            )  # nosec B602
            """
        )
        reported_source = textwrap.dedent(
            """\
            import subprocess
            run(
                subprocess.Popen("relative/path", shell=True),  # nosec B602
                subprocess.Popen("relative/path", shell=True),
            )
            """
        )
        with open(tmp_fname, "w") as tmp_file:
            tmp_file.write(suppressed_source)

        b_mgr.discover_files([tmp_fname], True)
        b_mgr.run_tests()
        # The nosec is bound to the outer run() call, an ancestor of both
        # Popen calls, so both B602 findings are suppressed. B607 findings
        # (which are not listed in the nosec) and the B404 import finding
        # are unaffected.
        suppressed_ids = {issue.test_id for issue in b_mgr.results}
        self.assertNotIn("B602", suppressed_ids)
        self.assertIn("B607", suppressed_ids)
        self.assertIn("B404", suppressed_ids)

        with open(tmp_fname, "w") as tmp_file:
            tmp_file.write(reported_source)
        reported_manager = manager.BanditManager(conf, "file")
        reported_manager.discover_files([tmp_fname], True)
        reported_manager.run_tests()
        # The comment is bound to the first sibling call only; the second
        # sibling's B602 finding must still be reported.
        reported = {
            issue.test_id: issue.lineno
            for issue in reported_manager.results
        }
        self.assertEqual(reported["B602"], 4)
        self.assertNotIn(3, reported.values())

        with open(tmp_fname, "w") as tmp_file:
            b_json.report(
                reported_manager,
                tmp_file,
                constants.LOW,
                constants.LOW,
            )

        with open(tmp_fname) as tmp_file:
            data = json.loads(tmp_file.read())

        expected_keys = {
            "code",
            "col_offset",
            "end_col_offset",
            "filename",
            "issue_confidence",
            "issue_cwe",
            "issue_severity",
            "issue_text",
            "line_number",
            "line_range",
            "more_info",
            "test_id",
            "test_name",
        }
        self.assertIn("errors", data)
        self.assertIn("generated_at", data)
        # Only the second sibling's B602 survives; B404/B607 findings are
        # unrelated to the nosec and remain in the report.
        b602_results = [
            result
            for result in data["results"]
            if result["test_id"] == "B602"
        ]
        self.assertEqual(1, len(b602_results))
        self.assertEqual(4, b602_results[0]["line_number"])
        for result in data["results"]:
            self.assertEqual(expected_keys, set(result.keys()))
