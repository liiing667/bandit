#
# Copyright 2014 Hewlett-Packard Development Company, L.P.
#
# SPDX-License-Identifier: Apache-2.0
import copy
import logging
import warnings

from bandit.core import constants
from bandit.core import context as b_context
from bandit.core import utils

warnings.formatwarning = utils.warnings_formatter
LOG = logging.getLogger(__name__)


class BanditTester:
    def __init__(self, testset, debug, nosec_lines, nosec_nodes, metrics):
        self.results = []
        self.testset = testset
        self.last_result = None
        self.debug = debug
        self.nosec_lines = nosec_lines
        self.nosec_nodes = nosec_nodes
        self.metrics = metrics

    def run_tests(self, raw_context, checktype):
        """Runs all tests for a certain type of check, for example

        Runs all tests for a certain type of check, for example 'functions'
        store results in results.

        :param raw_context: Raw context dictionary
        :param checktype: The type of checks to run
        :return: a score based on the number and type of test results with
                extra metrics about nosec comments
        """

        scores = {
            "SEVERITY": [0] * len(constants.RANKING),
            "CONFIDENCE": [0] * len(constants.RANKING),
        }

        tests = self.testset.get_tests(checktype)
        for test in tests:
            name = test.__name__
            # execute test with an instance of the context class
            temp_context = copy.copy(raw_context)
            context = b_context.Context(temp_context)
            try:
                if hasattr(test, "_config"):
                    result = test(context, test._config)
                else:
                    result = test(context)

                if result is not None:
                    nosec_tests_to_skip = self._get_nosecs_from_contexts(
                        temp_context
                    )

                    if isinstance(temp_context["filename"], bytes):
                        result.fname = temp_context["filename"].decode("utf-8")
                    else:
                        result.fname = temp_context["filename"]
                    result.fdata = temp_context["file_data"]

                    if result.lineno is None:
                        result.lineno = temp_context["lineno"]
                    if result.linerange == []:
                        result.linerange = temp_context["linerange"]
                    if result.col_offset == -1:
                        result.col_offset = temp_context["col_offset"]
                    result.end_col_offset = temp_context.get(
                        "end_col_offset", 0
                    )
                    result.test = name
                    if result.test_id == "":
                        result.test_id = test._test_id

                    # don't skip the test if there was no nosec comment
                    if nosec_tests_to_skip is not None:
                        # If the set is empty then it means that nosec was
                        # used without test number -> update nosecs counter.
                        # If the test id is in the set of tests to skip,
                        # log and increment the skip by test count.
                        if not nosec_tests_to_skip:
                            LOG.debug("skipped, nosec without test number")
                            # Only comments that actually suppress an issue
                            # are counted, so a comment attached to an inner
                            # call never inflates the totals for the outer
                            # call which still reports its findings.
                            self.metrics.note_nosec()
                            continue
                        if result.test_id in nosec_tests_to_skip:
                            LOG.debug(
                                f"skipped, nosec for test {result.test_id}"
                            )
                            self.metrics.note_skipped_test()
                            continue

                    self.results.append(result)

                    LOG.debug("Issue identified by %s: %s", name, result)
                    sev = constants.RANKING.index(result.severity)
                    val = constants.RANKING_VALUES[result.severity]
                    scores["SEVERITY"][sev] += val
                    con = constants.RANKING.index(result.confidence)
                    val = constants.RANKING_VALUES[result.confidence]
                    scores["CONFIDENCE"][con] += val
                else:
                    nosec_tests_to_skip = self._get_nosecs_from_contexts(
                        temp_context
                    )
                    if (
                        nosec_tests_to_skip
                        and test._test_id in nosec_tests_to_skip
                    ):
                        LOG.warning(
                            f"nosec encountered ({test._test_id}), but no "
                            f"failed test on file "
                            f"{temp_context['filename']}:"
                            f"{temp_context['lineno']}"
                        )

            except Exception as e:
                self.report_error(name, context, e)
                if self.debug:
                    raise
        LOG.debug("Returning scores: %s", scores)
        return scores

    def _get_nosecs_from_contexts(self, context):
        """Get the tests suppressed for the node held in ``context``.

        :param context: temp context
        :return: set of test ids to skip, an empty set for a blanket
            ``# nosec``, or ``None`` when no comment applies
        """
        return utils.get_nosec_for_node(
            self.nosec_nodes, self.nosec_lines, context
        )

    @staticmethod
    def report_error(test, context, error):
        what = "Bandit internal error running: "
        what += f"{test} "
        what += "on file %s at line %i: " % (
            context._context["filename"],
            context._context["lineno"],
        )
        what += str(error)
        import traceback

        what += traceback.format_exc()
        LOG.error(what)
