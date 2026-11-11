#
# Copyright 2014 Hewlett-Packard Development Company, L.P.
#
# SPDX-License-Identifier: Apache-2.0
import ast
import logging
import os.path
import sys

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

LOG = logging.getLogger(__name__)


"""Various helper functions."""


def _get_attr_qual_name(node, aliases):
    """Get a the full name for the attribute node.

    This will resolve a pseudo-qualified name for the attribute
    rooted at node as long as all the deeper nodes are Names or
    Attributes. This will give you how the code referenced the name but
    will not tell you what the name actually refers to. If we
    encounter a node without a static name we punt with an
    empty string. If this encounters something more complex, such as
    foo.mylist[0](a,b) we just return empty string.

    :param node: AST Name or Attribute node
    :param aliases: Import aliases dictionary
    :returns: Qualified name referred to by the attribute or name.
    """
    if isinstance(node, ast.Name):
        if node.id in aliases:
            return aliases[node.id]
        return node.id
    elif isinstance(node, ast.Attribute):
        name = f"{_get_attr_qual_name(node.value, aliases)}.{node.attr}"
        if name in aliases:
            return aliases[name]
        return name
    else:
        return ""


def get_call_name(node, aliases):
    if isinstance(node.func, ast.Name):
        if deepgetattr(node, "func.id") in aliases:
            return aliases[deepgetattr(node, "func.id")]
        return deepgetattr(node, "func.id")
    elif isinstance(node.func, ast.Attribute):
        return _get_attr_qual_name(node.func, aliases)
    else:
        return ""


def get_func_name(node):
    return node.name  # TODO(tkelsey): get that qualname using enclosing scope


def get_qual_attr(node, aliases):
    if isinstance(node, ast.Attribute):
        try:
            val = deepgetattr(node, "value.id")
            if val in aliases:
                prefix = aliases[val]
            else:
                prefix = deepgetattr(node, "value.id")
        except Exception:
            # NOTE(tkelsey): degrade gracefully when we can't get the fully
            # qualified name for an attr, just return its base name.
            prefix = ""

        return f"{prefix}.{node.attr}"
    else:
        return ""  # TODO(tkelsey): process other node types


def deepgetattr(obj, attr):
    """Recurses through an attribute chain to get the ultimate value."""
    for key in attr.split("."):
        obj = getattr(obj, key)
    return obj


class InvalidModulePath(Exception):
    pass


class ConfigError(Exception):
    """Raised when the config file fails validation."""

    def __init__(self, message, config_file):
        self.config_file = config_file
        self.message = f"{config_file} : {message}"
        super().__init__(self.message)


class ProfileNotFound(Exception):
    """Raised when chosen profile cannot be found."""

    def __init__(self, config_file, profile):
        self.config_file = config_file
        self.profile = profile
        message = "Unable to find profile ({}) in config file: {}".format(
            self.profile,
            self.config_file,
        )
        super().__init__(message)


def warnings_formatter(
    message, category=UserWarning, filename="", lineno=-1, line=""
):
    """Monkey patch for warnings.warn to suppress cruft output."""
    return f"{message}\n"


def get_module_qualname_from_path(path):
    """Get the module's qualified name by analysis of the path.

    Resolve the absolute pathname and eliminate symlinks. This could result in
    an incorrect name if symlinks are used to restructure the python lib
    directory.

    Starting from the right-most directory component look for __init__.py in
    the directory component. If it exists then the directory name is part of
    the module name. Move left to the subsequent directory components until a
    directory is found without __init__.py.

    :param: Path to module file. Relative paths will be resolved relative to
            current working directory.
    :return: fully qualified module name
    """

    (head, tail) = os.path.split(path)
    if head == "" or tail == "":
        raise InvalidModulePath(
            f'Invalid python file path: "{path}" Missing path or file name'
        )

    qname = [os.path.splitext(tail)[0]]
    while head not in ["/", ".", ""]:
        if os.path.isfile(os.path.join(head, "__init__.py")):
            (head, tail) = os.path.split(head)
            qname.insert(0, tail)
        else:
            break

    qualname = ".".join(qname)
    return qualname


def namespace_path_join(base, name):
    """Extend the current namespace path with an additional name

    Take a namespace path (i.e., package.module.class) and extends it
    with an additional name (i.e., package.module.class.subclass).
    This is similar to how os.path.join works.

    :param base: (String) The base namespace path.
    :param name: (String) The new name to append to the base path.
    :returns: (String) A new namespace path resulting from combination of
              base and name.
    """
    return f"{base}.{name}"


def namespace_path_split(path):
    """Split the namespace path into a pair (head, tail).

    Tail will be the last namespace path component and head will
    be everything leading up to that in the path. This is similar to
    os.path.split.

    :param path: (String) A namespace path.
    :returns: (String, String) A tuple where the first component is the base
              path and the second is the last path component.
    """
    return tuple(path.rsplit(".", 1))


def escaped_bytes_representation(b):
    """PY3 bytes need escaping for comparison with other strings.

    In practice it turns control characters into acceptable codepoints then
    encodes them into bytes again to turn unprintable bytes into printable
    escape sequences.

    This is safe to do for the whole range 0..255 and result matches
    unicode_escape on a unicode string.
    """
    return b.decode("unicode_escape").encode("unicode_escape")


def calc_linerange(node):
    """Calculate linerange for subtree"""
    if hasattr(node, "_bandit_linerange"):
        return node._bandit_linerange

    lines_min = 9999999999
    lines_max = -1
    if hasattr(node, "lineno"):
        lines_min = node.lineno
        lines_max = node.lineno
    for n in ast.iter_child_nodes(node):
        lines_minmax = calc_linerange(n)
        lines_min = min(lines_min, lines_minmax[0])
        lines_max = max(lines_max, lines_minmax[1])

    node._bandit_linerange = (lines_min, lines_max)

    return (lines_min, lines_max)


def linerange(node):
    """Get line number range from a node."""
    if hasattr(node, "lineno"):
        return list(range(node.lineno, node.end_lineno + 1))
    else:
        if hasattr(node, "_bandit_linerange_stripped"):
            lines_minmax = node._bandit_linerange_stripped
            return list(range(lines_minmax[0], lines_minmax[1] + 1))

        strip = {
            "body": None,
            "orelse": None,
            "handlers": None,
            "finalbody": None,
        }
        for key in strip.keys():
            if hasattr(node, key):
                strip[key] = getattr(node, key)
                setattr(node, key, [])

        lines_min = 9999999999
        lines_max = -1
        if hasattr(node, "lineno"):
            lines_min = node.lineno
            lines_max = node.lineno
        for n in ast.iter_child_nodes(node):
            lines_minmax = calc_linerange(n)
            lines_min = min(lines_min, lines_minmax[0])
            lines_max = max(lines_max, lines_minmax[1])

        for key in strip.keys():
            if strip[key] is not None:
                setattr(node, key, strip[key])

        if lines_max == -1:
            lines_min = 0
            lines_max = 1

        node._bandit_linerange_stripped = (lines_min, lines_max)

        lines = list(range(lines_min, lines_max + 1))

        """Try and work around a known Python bug with multi-line strings."""
        # deal with multiline strings lineno behavior (Python issue #16806)
        if hasattr(node, "_bandit_sibling") and hasattr(
            node._bandit_sibling, "lineno"
        ):
            start = min(lines)
            delta = node._bandit_sibling.lineno - start
            if delta > 1:
                return list(range(start, node._bandit_sibling.lineno))
        return lines


def concat_string(node, stop=None):
    """Builds a string from a ast.BinOp chain.

    This will build a string from a series of ast.Constant nodes wrapped in
    ast.BinOp nodes. Something like "a" + "b" + "c" or "a %s" % val etc.
    The provided node can be any participant in the BinOp chain.

    :param node: (ast.Constant or ast.BinOp) The node to process
    :param stop: (ast.Constant or ast.BinOp) Optional base node to stop at
    :returns: (Tuple) the root node of the expression, the string value
    """

    def _get(node, bits, stop=None):
        if node != stop:
            bits.append(
                _get(node.left, bits, stop)
                if isinstance(node.left, ast.BinOp)
                else node.left
            )
            bits.append(
                _get(node.right, bits, stop)
                if isinstance(node.right, ast.BinOp)
                else node.right
            )

    bits = [node]
    while isinstance(node._bandit_parent, ast.BinOp):
        node = node._bandit_parent
    if isinstance(node, ast.BinOp):
        _get(node, bits, stop)
    return (
        node,
        " ".join(
            [
                x.value
                for x in bits
                if isinstance(x, ast.Constant) and isinstance(x.value, str)
            ]
        ),
    )


def get_called_name(node):
    """Get a function name from an ast.Call node.

    An ast.Call node representing a method call with present differently to one
    wrapping a function call: thing.call() vs call(). This helper will grab the
    unqualified call name correctly in either case.

    :param node: (ast.Call) the call node
    :returns: (String) the function name
    """
    func = node.func
    try:
        return func.attr if isinstance(func, ast.Attribute) else func.id
    except AttributeError:
        return ""


def get_path_for_function(f):
    """Get the path of the file where the function is defined.

    :returns: the path, or None if one could not be found or f is not a real
        function
    """

    if hasattr(f, "__module__"):
        module_name = f.__module__
    elif hasattr(f, "im_func"):
        module_name = f.im_func.__module__
    else:
        LOG.warning("Cannot resolve file where %s is defined", f)
        return None

    module = sys.modules[module_name]
    if hasattr(module, "__file__"):
        return module.__file__
    else:
        LOG.warning("Cannot resolve file path for module %s", module_name)
        return None


def parse_ini_file(f_loc):
    config = configparser.ConfigParser()
    try:
        config.read(f_loc)
        return {k: v for k, v in config.items("bandit")}

    except (configparser.Error, KeyError, TypeError):
        LOG.warning(
            "Unable to parse config file %s or missing [bandit] " "section",
            f_loc,
        )

    return None


def check_ast_node(name):
    "Check if the given name is that of a valid AST node."
    try:
        # These ast Node types were deprecated in Python 3.12 and removed
        # in Python 3.14, but plugins may still check on them.
        if sys.version_info >= (3, 12) and name in (
            "Num",
            "Str",
            "Ellipsis",
            "NameConstant",
            "Bytes",
        ):
            return name

        node = getattr(ast, name)
        if issubclass(node, ast.AST):
            return name
    except AttributeError:  # nosec(tkelsey): catching expected exception
        pass

    raise TypeError(f"Error: {name} is not a valid node type in AST")


def get_nosec(nosec_lines, context):
    for lineno in context["linerange"]:
        nosec = nosec_lines.get(lineno, None)
        if nosec is not None:
            return nosec
    return None


def bind_nosec_comments(tree, nosec_lines):
    """Bind nosec comments to the AST nodes they actually annotate.

    A trailing comment on a line where a statement level node starts is
    bound to the outermost such node. A comment on a keyword argument
    line inside a multi-line call is bound to the enclosing call, and a
    comment inside a multi-line expression is bound to the deepest node
    fully containing its line. The resulting mapping is stored on the
    nodes via ``_bandit_nosec`` so that only the node producing a finding
    or one of its ancestors can suppress it; overlapping sibling nodes
    never affect each other.

    :param tree: Root AST node of the file
    :param nosec_lines: Mapping of source line -> set of test ids
                        (an empty set means a blanket ``# nosec``)
    :return: The same mapping, attached to the relevant AST nodes
    """
    nodes = [
        node
        for node in ast.walk(tree)
        if hasattr(node, "lineno") and hasattr(node, "end_lineno")
    ]

    # The visitor only attaches ``_bandit_parent`` while walking the tree,
    # so build a local parent map here to keep binding independent of the
    # traversal order.
    parent_map = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent_map[id(child)] = node

    def depth(node):
        result = 0
        parent = parent_map.get(id(node))
        while parent is not None:
            result += 1
            parent = parent_map.get(id(parent))
        return result

    def enclosing_call(node):
        parent = parent_map.get(id(node))
        while parent is not None and not isinstance(parent, ast.Call):
            parent = parent_map.get(id(parent))
        return parent

    for lineno, nosec_tests in nosec_lines.items():
        if nosec_tests is None:
            # The manager records every comment line, using None for
            # comments without a nosec marker; only bind real nosecs.
            continue
        candidates = [
            node
            for node in nodes
            if node.lineno <= lineno <= node.end_lineno
        ]
        if not candidates:
            continue

        # A trailing comment on a line where a statement level node
        # starts annotates the outermost such node (an import, a single
        # line call, the outer call of a nested expression). A keyword
        # line inside a multi-line call annotates its enclosing call.
        # Anything else binds to the deepest node fully containing the
        # line (for example a standalone comment inside a multi-line
        # expression).
        statement_types = (
            ast.stmt,
            ast.Call,
            ast.BinOp,
            ast.BoolOp,
            ast.Compare,
            ast.IfExp,
            ast.JoinedStr,
        )
        line_start_statements = [
            node
            for node in candidates
            if node.lineno == lineno and isinstance(node, statement_types)
        ]
        if line_start_statements:
            # Prefer an actual statement node (Expr, Assign, ...) over a
            # nested expression or call starting on the same line.
            stmt_only = [
                node
                for node in line_start_statements
                if isinstance(node, ast.stmt)
            ]
            target = min(stmt_only or line_start_statements, key=depth)
        else:
            # Inside a multi-line node: a keyword line annotates its
            # enclosing call; otherwise bind to the deepest enclosing
            # node (or the outermost expression ending on this line).
            keyword_candidates = [
                node for node in candidates if isinstance(node, ast.keyword)
            ]
            if keyword_candidates:
                target = max(keyword_candidates, key=depth)
                call_node = enclosing_call(target)
                if call_node is not None:
                    target = call_node
            else:
                line_end_nodes = [
                    node
                    for node in candidates
                    if node.end_lineno == lineno
                    and isinstance(node, statement_types)
                ]
                if line_end_nodes:
                    target = min(line_end_nodes, key=depth)
                else:
                    target = max(candidates, key=depth)

        existing = getattr(target, "_bandit_nosec", None)
        if existing is None:
            target._bandit_nosec = set(nosec_tests)
        else:
            existing.update(nosec_tests)

    return nosec_lines


def get_nosec_for_node(node, nosec_lines):
    """Collect nosec comments applying to a finding's AST node.

    Only comments bound to the node itself or to one of its ancestors are
    considered, so a comment inside an overlapping sibling subtree cannot
    suppress a finding produced by this node.

    :param node: The AST node that produced the finding
    :param nosec_lines: Mapping built while tokenizing the file (kept for
                        callers relying on the historical signature)
    :return: ``None`` when no comment applies, otherwise a set of test ids
             (an empty set means a blanket ``# nosec``)
    """
    if node is None:
        return None

    nosec_tests_to_skip = set()
    found = False
    current = node
    while current is not None:
        node_nosec = getattr(current, "_bandit_nosec", None)
        if node_nosec is not None:
            found = True
            nosec_tests_to_skip.update(node_nosec)
        current = getattr(current, "_bandit_parent", None)

    if found:
        return nosec_tests_to_skip

    return None
