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


def build_nosec_ast_map(tree, nosec_lines):
    """Bind ``# nosec`` comments to the AST node(s) they actually annotate.

    The line based mapping in ``nosec_lines`` cannot distinguish a comment
    attached to an inner argument of a multi-line call from one attached to
    the enclosing call: every node whose line range contains the comment
    line would treat the comment as its own.  This walks the AST instead and
    binds each comment to the innermost node whose own line range contains
    the comment line.  As a result a comment placed on an inner call or one
    of its arguments is attached to that inner call only, never to the
    enclosing call.  Comments on the first or last line of a node bind to
    that node directly, which preserves the historical same-line behaviour.

    :param tree: Parsed AST of the file (``ast.Module``).
    :param nosec_lines: Mapping of line number to the set of test ids carried
        by the ``# nosec`` comment on that line.  An empty set represents a
        blanket ``# nosec`` without specific test ids.

    Parent links (``_bandit_parent``) are assigned to every node while
    walking the tree so the same references can be looked up later when the
    node visitor processes the tree.

    :return: Mapping of node instances to the merged set of suppressed test
        ids.  Multiple comments bound to the same node have their id sets
        merged.
    """
    nosec_nodes = {}
    if not nosec_lines:
        return nosec_nodes

    # Leaf expression nodes never own bandit checks themselves; a comment
    # next to a literal, name or attribute is intended for the enclosing
    # expression (typically a call or an assignment) rather than for the
    # leaf node.
    leaf_nodes = (
        ast.Constant,
        ast.Name,
        ast.Attribute,
        ast.Starred,
        ast.keyword,
        ast.FormattedValue,
    )

    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child._bandit_parent = node

    # Walk the tree once, keeping the deepest non-leaf node that contains
    # each comment line.  ast.walk yields parents before children, so a
    # later match for the same line is always a descendant of the earlier
    # one.
    targets = {}
    for node in ast.walk(tree):
        if not hasattr(node, "lineno") or isinstance(node, leaf_nodes):
            continue
        for comment_line, nosec in nosec_lines.items():
            if nosec is None:
                # The line holds a comment but no nosec marker.
                continue
            if node.lineno <= comment_line <= node.end_lineno:
                targets[comment_line] = node

    for comment_line, target in targets.items():
        bound = nosec_nodes.setdefault(target, set())
        bound.update(nosec_lines[comment_line])

    return nosec_nodes


def get_nosec_for_node(nosec_nodes, nosec_lines, context):
    """Return the tests suppressed for the node held in ``context``.

    Only comments actually attached to the context node (or to one of its
    parent nodes, to cover checks run against a child node such as a string
    constant) apply.  An exact line lookup is kept as a fallback so legacy
    placements that cannot be represented by a node boundary (multi-line
    strings, implicit string concatenation) keep working.  Unlike the old
    range based lookup the fallback never matches a line inside a node that
    merely encloses the checked node, so an inner call comment cannot
    suppress findings on the outer call.

    :param nosec_nodes: Mapping of node instances to suppressed test id
        sets.
    :param nosec_lines: Mapping of comment line to suppressed test id sets.
    :param context: The raw check context dictionary.
    :return: A set of test ids (empty set means a blanket suppression) or
        ``None`` when no comment applies.
    """
    nosec_tests = set()
    found = False

    candidate = context.get("node")
    while candidate is not None:
        bound = nosec_nodes.get(candidate)
        if bound is not None:
            found = True
            nosec_tests.update(bound)
        candidate = getattr(candidate, "_bandit_parent", None)

    # Exact line fallback for comments on continuation lines that do not
    # coincide with a node boundary relevant to the checked node.
    lineno = context.get("lineno")
    if lineno is not None:
        nosec = nosec_lines.get(lineno)
        if nosec is not None:
            found = True
            nosec_tests.update(nosec)

    return nosec_tests if found else None
