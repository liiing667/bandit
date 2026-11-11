import subprocess

# 1. Multi-line overlap: the nosec sits on an inner helper call line but
# inside the outer Popen's line range. It must not suppress the outer
# Popen's B602 finding because the comment is not bound to the outer call
# or one of its ancestors.
subprocess.Popen(
    subprocess.Popen(
        "relative/path",
        shell=True,
    ),  # nosec B602
    shell=True,
)

# 2. Overlapping sibling calls: the comment on the first sibling must not
# suppress the second sibling's finding.
subprocess.Popen(
    subprocess.Popen("relative/path", shell=True),  # nosec B602
    subprocess.Popen("relative/path", shell=True),
)

# 3. A blanket nosec without a test id is scoped to the node it annotates;
# the sibling finding is still reported.
subprocess.Popen(
    subprocess.Popen("relative/path", shell=True),  # nosec
    subprocess.Popen("relative/path", shell=True),
)

# 4. A keyword line comment binds to the enclosing call and suppresses the
# call's own B602 (and B607) finding.
subprocess.Popen(
    "relative/path",
    shell=True,  # nosec B602
)

# 5. Multiple comments on different lines of one multi-line call are all
# considered regardless of traversal order.
subprocess.Popen(
    "relative/path",
    # nosec B607
    shell=True,  # nosec B602
)

# 6. Unknown test ids still warn while parsing the comment; with no valid
# id left the comment behaves like a blanket nosec for its bound node.
subprocess.Popen(
    "relative/path",
    shell=True,  # nosec B999
)
