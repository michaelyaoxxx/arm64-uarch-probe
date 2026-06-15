from pathlib import Path


REPOSITORY_ID = "github.com/michaelyaoxxx/arm64-uarch-probe"
STATE_ROOT = Path("/var/lib/arm64-uarch-probe")
CONTROLLER_ORDER = (
    "linux.cpufreq",
    "linux.hugepage",
    "linux.transparent-hugepage",
)
OBSERVATION_STATUSES = frozenset(
    {
        "available",
        "unsupported",
        "permission-denied",
        "degraded",
        "unavailable",
    }
)
JOURNAL_STATES = frozenset(
    {
        "created",
        "applying",
        "prepared",
        "restoring",
        "restored",
        "restore-failed",
    }
)
