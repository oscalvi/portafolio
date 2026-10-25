#!/usr/bin/env python3
"""
job_manager.py — Generic library for background jobs with a live,
poll-based progress log. Nothing here knows anything about IMAP, email,
or any other specific task: any project that needs the pattern "kick off
a long-running task, then let a frontend poll for its live log and
completion status" can drop this file into a new project unchanged.

Design:
  - JobManager is the only class a Flask (or any other) app talks to.
    It's configured with simple parameters (currently just ttl_seconds)
    and knows nothing about what a job actually does.
  - BaseWorker is the extension point: every kind of background task
    is its own BaseWorker subclass implementing run(). JobManager works
    with ANY subclass identically - this is the polymorphism that makes
    the manager reusable: teach it once, reuse it for every task type.
  - ThreadLocalLogger solves the "which job does this log line belong
    to" problem without threading a logger through every function call:
    existing code that already calls a plain module-level log(msg)
    function (like imap_core.py's) can keep doing exactly that; the
    logger just needs to be told which job's log list is "live" on the
    current thread before the worker starts running.

Usage:
    from job_manager import BaseWorker, ThreadLocalLogger, JobManager

    my_logger = ThreadLocalLogger()

    class MyWorker(BaseWorker):
        def __init__(self, some_param):
            super().__init__(my_logger)
            self.some_param = some_param

        def run(self):
            self.log(f"Starting work on {self.some_param}...")
            ...
            self.log("Done.")

    manager = JobManager(ttl_seconds=1800)
    job_id = manager.start(MyWorker("example"))
    status = manager.status(job_id, since=0)
    # status = {"done": False, "error": None, "log": [...], "next_since": N}
"""

import threading
import time
import uuid
from abc import ABC, abstractmethod


class ThreadLocalLogger:
    """Routes log(msg) calls to whichever job's log list is bound on the
    CURRENT thread, so concurrent jobs (different users, different
    requests) never mix their output - without passing a logger object
    through every function call in between."""

    def __init__(self):
        self._local = threading.local()

    def bind(self, log_list):
        """Call once at the start of a job's worker thread, before doing
        any work: every log() call on this thread from here on appends
        to log_list instead of printing."""
        self._local.log_list = log_list

    def log(self, msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        log_list = getattr(self._local, "log_list", None)
        if log_list is not None:
            log_list.append(line)
        else:
            print(line, flush=True)  # fallback: no job bound (e.g. plain CLI use)


class BaseWorker(ABC):
    """Extend this for every distinct kind of background task. Give your
    subclass's __init__ whatever parameters that task needs (a config
    dict, a file path, a list of items to process, ...) - JobManager
    never inspects them, it only ever calls run().

    A subclass can either call self.log(...) directly, or (as
    imap_core.IMAPMigrationWorker does) call into existing code that
    already calls a module-level log() function bound to the same
    logger instance - both work, since the logger is just told which
    job it's serving before run() starts."""

    def __init__(self, logger: ThreadLocalLogger):
        self.logger = logger

    def log(self, msg):
        self.logger.log(msg)

    @abstractmethod
    def run(self):
        """Do the actual work. Raise on failure - JobManager records the
        exception message and marks the job done with that error."""
        raise NotImplementedError


class Job:
    """Plain data holder for one job's live state. Not part of the
    public API - use JobManager.status() to read it."""
    __slots__ = ("log", "done", "error", "created")

    def __init__(self):
        self.log = []
        self.done = False
        self.error = None
        self.created = time.time()


class JobManager:
    """Generic in-memory job store and background runner.

    Parameters:
        ttl_seconds: how long a finished job's result stays available
            for polling before being pruned. No database, no disk -
            jobs live only in this process's memory, so restarting the
            server clears everything (which is the intended behavior
            for a tool that promises not to store anything).
    """

    def __init__(self, ttl_seconds=1800):
        self._jobs = {}
        self._lock = threading.Lock()
        self._ttl_seconds = ttl_seconds

    def start(self, worker: BaseWorker) -> str:
        """Start any BaseWorker subclass as a new background job and
        return its job_id immediately (the work happens on its own
        thread). Works identically no matter what kind of worker it is
        - that's the polymorphism doing its job."""
        job_id = uuid.uuid4().hex
        job = Job()
        with self._lock:
            self._jobs[job_id] = job

        def _run():
            worker.logger.bind(job.log)
            try:
                worker.run()
            except Exception as e:
                job.error = str(e)
                job.log.append(f"[ERROR] {e}")
            finally:
                job.done = True
                self._prune_old_jobs()

        threading.Thread(target=_run, daemon=True).start()
        return job_id

    def status(self, job_id, since=0):
        """Returns None if job_id is unknown (e.g. expired). Otherwise
        a dict with only the log lines added since `since`, so a
        frontend can poll cheaply without re-fetching the whole log
        every time."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return None
        return {
            "done": job.done,
            "error": job.error,
            "log": job.log[since:],
            "next_since": len(job.log),
        }

    def _prune_old_jobs(self):
        cutoff = time.time() - self._ttl_seconds
        with self._lock:
            stale = [jid for jid, j in self._jobs.items() if j.done and j.created < cutoff]
            for jid in stale:
                del self._jobs[jid]
