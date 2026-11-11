#
# Copyright 2014 Hewlett-Packard Development Company, L.P.
# Copyright 2015 Nebula, Inc.
#
# SPDX-License-Identifier: Apache-2.0
import ast
import os
import shutil
import sys
import tempfile

import testtools

from bandit.core import utils as b_utils


def _touch(path):
    """Create an empty file at ``path``."""
    open(path, "w").close()


class UtilTests(testtools.TestCase):
    """This set of tests exercises bandit.core.util functions."""

    def setUp(self):
        super().setUp()
        self._setup_get_module_qualname_from_path()

    def _setup_get_module_qualname_from_path(self):
        """Setup a fake directory for testing get_module_qualname_from_path().

        Create temporary directory and then create fake .py files
        within directory structure.  We setup test cases for
        a typical module, a path misssing a middle __init__.py,
        no __init__.py anywhere in path, symlinking .py files.
        """

        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir)
        self.reltempdir = os.path.relpath(self.tempdir)

        # good/a/b/c/test_typical.py
        os.makedirs(os.path.join(self.tempdir, "good", "a", "b", "c"), 0o755)
        _touch(os.path.join(self.tempdir, "good", "__init__.py"))
        _touch(os.path.join(self.tempdir, "good", "a", "__init__.py"))
        _touch(os.path.join(self.tempdir, "good", "a", "b", "__init__.py"))
        _touch(
            os.path.join(self.tempdir, "good", "a", "b", "c", "__init__.py")
        )
        _touch(
            os.path.join(
                self.tempdir, "good", "a", "b", "c", "test_typical.py"
            )
        )

        # missingmid/a/b/c/test_missingmid.py
        os.makedirs(
            os.path.join(self.tempdir, "missingmid", "a", "b", "c"), 0o755
        )
        _touch(os.path.join(self.tempdir, "missingmid", "__init__.py"))
        # no missingmid/a/__init__.py
        _touch(
            os.path.join(self.tempdir, "missingmid", "a", "b", "__init__.py")
        )
        _touch(
            os.path.join(
                self.tempdir, "missingmid", "a", "b", "c", "__init__.py"
            )
        )
        _touch(
            os.path.join(
                self.tempdir, "missingmid", "a", "b", "c", "test_missingmid.py"
            )
        )

        # missingend/a/b/c/test_missingend.py
        os.makedirs(
            os.path.join(self.tempdir, "missingend", "a", "b", "c"), 0o755
        )
        _touch(os.path.join(self.tempdir, "missingend", "__init__.py"))
        _touch(
            os.path.join(self.tempdir, "missingend", "a", "b", "__init__.py")
        )
        # no missingend/a/b/c/__init__.py
        _touch(
            os.path.join(
                self.tempdir, "missingend", "a", "b", "c", "test_missingend.py"
            )
        )

        # syms/a/bsym/c/test_typical.py
        os.makedirs(os.path.join(self.tempdir, "syms", "a"), 0o755)
        _touch(os.path.join(self.tempdir, "syms", "__init__.py"))
        _touch(os.path.join(self.tempdir, "syms", "a", "__init__.py"))
        os.symlink(
            os.path.join(self.tempdir, "good", "a", "b"),
            os.path.join(self.tempdir, "syms", "a", "bsym"),
        )

    def test_get_module_qualname_from_path_abs_typical(self):
        """Test get_module_qualname_from_path with typical absolute paths."""

        name = b_utils.get_module_qualname_from_path(
            os.path.join(
                self.tempdir, "good", "a", "b", "c", "test_typical.py"
            )
        )
        self.assertEqual("good.a.b.c.test_typical", name)

    def test_get_module_qualname_from_path_with_dot(self):
        """Test get_module_qualname_from_path with a "." ."""

        name = b_utils.get_module_qualname_from_path(
            os.path.join(".", "__init__.py")
        )

        self.assertEqual("__init__", name)

    def test_get_module_qualname_from_path_abs_missingmid(self):
        # Test get_module_qualname_from_path with missing module
        # __init__.py

        name = b_utils.get_module_qualname_from_path(
            os.path.join(
                self.tempdir, "missingmid", "a", "b", "c", "test_missingmid.py"
            )
        )
        self.assertEqual("b.c.test_missingmid", name)

    def test_get_module_qualname_from_path_abs_missingend(self):
        # Test get_module_qualname_from_path with no __init__.py
        # last dir'''

        name = b_utils.get_module_qualname_from_path(
            os.path.join(
                self.tempdir, "missingend", "a", "b", "c", "test_missingend.py"
            )
        )
        self.assertEqual("test_missingend", name)

    def test_get_module_qualname_from_path_abs_syms(self):
        """Test get_module_qualname_from_path with symlink in path."""

        name = b_utils.get_module_qualname_from_path(
            os.path.join(
                self.tempdir, "syms", "a", "bsym", "c", "test_typical.py"
            )
        )
        self.assertEqual("syms.a.bsym.c.test_typical", name)

    def test_get_module_qualname_from_path_rel_typical(self):
        """Test get_module_qualname_from_path with typical relative paths."""

        name = b_utils.get_module_qualname_from_path(
            os.path.join(
                self.reltempdir, "good", "a", "b", "c", "test_typical.py"
            )
        )
        self.assertEqual("good.a.b.c.test_typical", name)

    def test_get_module_qualname_from_path_rel_missingmid(self):
        # Test get_module_qualname_from_path with module __init__.py
        # missing and relative paths

        name = b_utils.get_module_qualname_from_path(
            os.path.join(
                self.reltempdir,
                "missingmid",
                "a",
                "b",
                "c",
                "test_missingmid.py",
            )
        )
        self.assertEqual("b.c.test_missingmid", name)

    def test_get_module_qualname_from_path_rel_missingend(self):
        # Test get_module_qualname_from_path with __init__.py missing from
        # last dir and using relative paths

        name = b_utils.get_module_qualname_from_path(
            os.path.join(
                self.reltempdir,
                "missingend",
                "a",
                "b",
                "c",
                "test_missingend.py",
            )
        )
        self.assertEqual("test_missingend", name)

    def test_get_module_qualname_from_path_rel_syms(self):
        """Test get_module_qualname_from_path with symbolic relative paths."""
        name = b_utils.get_module_qualname_from_path(
            os.path.join(
                self.reltempdir, "syms", "a", "bsym", "c", "test_typical.py"
            )
        )
        self.assertEqual("syms.a.bsym.c.test_typical", name)

    def test_get_module_qualname_from_path_sys(self):
        """Test get_module_qualname_from_path with system module paths."""

        name = b_utils.get_module_qualname_from_path(os.__file__)
        self.assertEqual("os", name)

        # This will fail because of magic for os.path. Not sure how to fix.
        # name = b_utils.get_module_qualname_from_path(os.path.__file__)
        # self.assertEqual(name, 'os.path')

    def test_get_module_qualname_from_path_invalid_path(self):
        """Test get_module_qualname_from_path with invalid path."""

        name = b_utils.get_module_qualname_from_path("/a/b/c/d/e.py")
        self.assertEqual("e", name)

    def test_get_module_qualname_from_path_dir(self):
        """Test get_module_qualname_from_path with dir path."""

        self.assertRaises(
            b_utils.InvalidModulePath,
            b_utils.get_module_qualname_from_path,
            "/tmp/",
        )

    def test_namespace_path_join(self):
        p = b_utils.namespace_path_join("base1.base2", "name")
        self.assertEqual("base1.base2.name", p)

    def test_namespace_path_split(self):
        (head, tail) = b_utils.namespace_path_split("base1.base2.name")
        self.assertEqual("base1.base2", head)
        self.assertEqual("name", tail)

    def test_get_call_name1(self):
        """Gets a qualified call name."""
        tree = ast.parse("a.b.c.d(x,y)").body[0].value
        name = b_utils.get_call_name(tree, {})
        self.assertEqual("a.b.c.d", name)

    def test_get_call_name2(self):
        """Gets qualified call name and resolves aliases."""
        tree = ast.parse("a.b.c.d(x,y)").body[0].value

        name = b_utils.get_call_name(tree, {"a": "alias.x.y"})
        self.assertEqual("alias.x.y.b.c.d", name)

        name = b_utils.get_call_name(tree, {"a.b": "alias.x.y"})
        self.assertEqual("alias.x.y.c.d", name)

        name = b_utils.get_call_name(tree, {"a.b.c.d": "alias.x.y"})
        self.assertEqual("alias.x.y", name)

    def test_get_call_name3(self):
        """Getting name for a complex call."""
        tree = ast.parse("a.list[0](x,y)").body[0].value
        name = b_utils._get_attr_qual_name(tree, {})
        self.assertEqual("", name)
        # TODO(ljfisher) At best we might be able to get:
        # self.assertEqual(name, 'a.list[0]')

    def test_linerange(self):
        with open("./examples/jinja2_templating.py") as test_file:
            tree = ast.parse(test_file.read())
        # Check linerange returns corrent number of lines
        line = tree.body[8]
        lrange = b_utils.linerange(line)

        # line 9 should be three lines long
        self.assertEqual(3, len(lrange))

        # the range should be the correct line numbers
        self.assertEqual([11, 12, 13], list(lrange))

    def test_path_for_function(self):
        path = b_utils.get_path_for_function(b_utils.get_path_for_function)
        self.assertEqual(path, b_utils.__file__)

    def test_path_for_function_no_file(self):
        self.assertIsNone(b_utils.get_path_for_function(sys.settrace))

    def test_path_for_function_no_module(self):
        self.assertIsNone(b_utils.get_path_for_function(1))

    def test_escaped_representation_simple(self):
        res = b_utils.escaped_bytes_representation(b"ascii")
        self.assertEqual(res, b"ascii")

    def test_escaped_representation_valid_not_printable(self):
        res = b_utils.escaped_bytes_representation(b"\\u0000")
        self.assertEqual(res, b"\\x00")

    def test_escaped_representation_invalid(self):
        res = b_utils.escaped_bytes_representation(b"\\uffff")
        self.assertEqual(res, b"\\uffff")

    def test_escaped_representation_mixed(self):
        res = b_utils.escaped_bytes_representation(b"ascii\\u0000\\uffff")
        self.assertEqual(res, b"ascii\\x00\\uffff")

    def test_deepgetattr(self):
        a = type("", (), {})
        a.b = type("", (), {})
        a.b.c = type("", (), {})
        a.b.c.d = "deep value"
        a.b.c.d2 = "deep value 2"
        a.b.c.e = "a.b.c"
        self.assertEqual("deep value", b_utils.deepgetattr(a.b.c, "d"))
        self.assertEqual("deep value 2", b_utils.deepgetattr(a.b.c, "d2"))
        self.assertEqual("a.b.c", b_utils.deepgetattr(a.b.c, "e"))
        self.assertEqual("deep value", b_utils.deepgetattr(a, "b.c.d"))
        self.assertEqual("deep value 2", b_utils.deepgetattr(a, "b.c.d2"))
        self.assertRaises(AttributeError, b_utils.deepgetattr, a.b, "z")

    def test_parse_ini_file(self):
        tests = [
            {
                "content": "[bandit]\nexclude=/abc,/def",
                "expected": {"exclude": "/abc,/def"},
            },
            {"content": "[Blabla]\nsomething=something", "expected": None},
        ]

        with tempfile.NamedTemporaryFile("r+") as t:
            for test in tests:
                with open(t.name, "w") as f:
                    f.write(test["content"])

                self.assertEqual(
                    b_utils.parse_ini_file(t.name), test["expected"]
                )

    def test_check_ast_node_good(self):
        node = b_utils.check_ast_node("Call")
        self.assertEqual("Call", node)

    def test_check_ast_node_bad_node(self):
        self.assertRaises(TypeError, b_utils.check_ast_node, "Derp")

    def test_check_ast_node_bad_type(self):
        self.assertRaises(TypeError, b_utils.check_ast_node, "walk")


class NosecNodeTests(testtools.TestCase):
    """Tests for AST node bound ``# nosec`` comments."""

    NESTED_CALLS = """
outer(
    inner(
        "arg",
        shell=False,  # nosec
    ),
    shell=True,
)
adjacent()
"""

    def _parse(self, source):
        tree = ast.parse(source)
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                child._bandit_parent = node
        return tree

    def _calls(self, tree):
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        ]
        return calls

    def _call_by_name(self, tree, func_name):
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == func_name
            ):
                return node
        self.fail(f"call {func_name} not found")

    def test_nosec_binds_to_inner_node_only(self):
        tree = self._parse(self.NESTED_CALLS)
        inner = self._call_by_name(tree, "inner")
        outer = self._call_by_name(tree, "outer")
        adjacent = self._call_by_name(tree, "adjacent")
        nosec_nodes = b_utils.build_nosec_ast_map(tree, {5: set()})

        self.assertIn(inner, nosec_nodes)
        self.assertNotIn(outer, nosec_nodes)
        self.assertNotIn(adjacent, nosec_nodes)

    def test_nosec_does_not_suppress_enclosing_call(self):
        tree = self._parse(self.NESTED_CALLS)
        inner = self._call_by_name(tree, "inner")
        outer = self._call_by_name(tree, "outer")
        adjacent = self._call_by_name(tree, "adjacent")
        nosec_nodes = b_utils.build_nosec_ast_map(tree, {5: set()})

        inner_context = {"node": inner, "lineno": inner.lineno}
        outer_context = {"node": outer, "lineno": outer.lineno}
        adjacent_context = {"node": adjacent, "lineno": adjacent.lineno}

        self.assertEqual(
            set(),
            b_utils.get_nosec_for_node(
                nosec_nodes, {}, inner_context
            ),
        )
        self.assertIsNone(
            b_utils.get_nosec_for_node(
                nosec_nodes, {}, outer_context
            )
        )
        self.assertIsNone(
            b_utils.get_nosec_for_node(
                nosec_nodes, {}, adjacent_context
            )
        )

    def test_precise_ids_merged_for_same_node(self):
        source = (
            "outer(  # nosec B602\n"
            "    value,\n"
            ")  # nosec B607\n"
        )
        tree = self._parse(source)
        call = self._calls(tree)[0]
        nosec_nodes = b_utils.build_nosec_ast_map(
            tree, {1: {"B602"}, 3: {"B607"}}
        )

        self.assertEqual({"B602", "B607"}, nosec_nodes[call])

    def test_comments_without_nosec_are_ignored(self):
        tree = self._parse("outer(value)  # plain comment\n")
        nosec_nodes = b_utils.build_nosec_ast_map(tree, {1: None})
        self.assertEqual({}, nosec_nodes)

    def test_same_line_nosec_still_matches(self):
        source = "outer(value)  # nosec\n"
        tree = self._parse(source)
        call = self._calls(tree)[0]
        nosec_lines = {1: set()}
        nosec_nodes = b_utils.build_nosec_ast_map(tree, nosec_lines)
        context = {"node": call, "lineno": call.lineno}

        self.assertEqual(
            set(),
            b_utils.get_nosec_for_node(
                nosec_nodes, nosec_lines, context
            ),
        )

    def test_exact_line_fallback_for_multiline_strings(self):
        # The comment sits on a continuation line that does not coincide
        # with the node boundary where the check is triggered.
        source = (
            'query = ("SELECT * "\n'
            '         "FROM foo "  # nosec\n'
            '         f"WHERE id = {x}")\n'
        )
        tree = self._parse(source)
        constant = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        )
        nosec_lines = {2: set()}
        nosec_nodes = b_utils.build_nosec_ast_map(tree, nosec_lines)
        context = {"node": constant, "lineno": constant.lineno}

        self.assertEqual(
            set(),
            b_utils.get_nosec_for_node(
                nosec_nodes, nosec_lines, context
            ),
        )
