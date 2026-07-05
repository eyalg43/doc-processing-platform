import pybreaker
import structlog

logger = structlog.get_logger(__name__)


class LogListener(pybreaker.CircuitBreakerListener):
    def state_change(self, cb, old_state, new_state):
        logger.warning(
            "circuit_breaker_state_change",
            name=cb.name,
            old_state=old_state.name,
            new_state=new_state.name,
        )


openai_breaker = pybreaker.CircuitBreaker(
    fail_max=3,
    reset_timeout=30,
    name="openai",
    listeners=[LogListener()],
)
