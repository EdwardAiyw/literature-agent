import logging

from literature_agent.launcher import main


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BaseException:
        logging.getLogger("literature_agent").exception("Literature Agent terminated during startup")
        raise
