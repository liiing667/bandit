"""Nested multi-line calls with ``# nosec`` on inner arguments.

The ``# nosec`` comments below annotate the inner call only.  Findings on
the enclosing call and on adjacent statements must still be reported.
"""
from subprocess import Popen


def nested_blanket_nosec():
    # The blanket nosec belongs to the inner Popen call, the outer call's
    # shell=True finding (B602) must not be suppressed.
    Popen(
        Popen(
            "ls -l",
            shell=False,  # nosec
        ),
        shell=True,
    )

    # Adjacent statement without any comment is always reported.
    Popen("ls -l", shell=True)


def nested_precise_nosec():
    # Only B603 (start_process_without_shell_equals_true) is suppressed on
    # the inner call; the inner B607 partial path finding survives.
    Popen(
        Popen(
            "ls -l",
            shell=False,  # nosec B603
        ),
        shell=True,
    )
