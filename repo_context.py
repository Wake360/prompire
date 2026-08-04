import collections
import fnmatch
import os
import pathlib
import re
import subprocess
import threading


class RepoContextError(ValueError):
    pass


def git_env():
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_OPTIONAL_LOCKS="0",
               GIT_PAGER="cat", GIT_TERMINAL_PROMPT="0")
    return env


def context_repo_root(start):
    result = subprocess.run(
        ["git", "--no-pager", "-c", "core.fsmonitor=false",
         "-c", "core.hooksPath=", "-C", str(pathlib.Path(start).resolve()),
         "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=git_env(),
        timeout=10,
    )
    if result.returncode:
        raise RepoContextError(result.stderr.strip() or "not inside a Git repository")
    return pathlib.Path(result.stdout.strip()).resolve()


class RepoContext:
    MAX_QUERIES = 8
    MAX_RESULT_CHARS = 8_000
    MAX_TOTAL_CHARS = 32_000
    MAX_READ_LINES = 200
    MAX_READ_START = 20_000
    MAX_READ_SCAN_CHARS = 1_000_000
    MAX_OVERVIEW_PATHS = 200
    MAX_GIT_CAPTURE = 2_000_000

    def __init__(self, root):
        self.root = pathlib.Path(root).resolve()
        self._tracked = self._git("ls-files").splitlines()
        self._tracked_set = set(self._tracked)
        self._by_operation = collections.Counter()

    @property
    def metrics(self):
        return {
            "retrieval_calls": sum(self._by_operation.values()),
            "by_operation": dict(self._by_operation),
        }

    def tracked_subset(self, paths):
        return tuple(path for path in paths if path in self._tracked_set)

    def _git(self, *args, ok=(0,), allow_truncated=False):
        argv = ["git", "--no-pager", "-c", "core.fsmonitor=false",
                "-c", "core.hooksPath=", "-C", str(self.root), *args]
        try:
            process = subprocess.Popen(
                argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=git_env())
        except OSError as exc:
            raise RepoContextError(f"git could not start: {exc}") from exc
        captured = {"stdout": [], "stderr": []}
        sizes = {"stdout": 0, "stderr": 0}
        overflow = set()

        def drain(name, stream):
            while True:
                chunk = stream.read(65_536)
                if not chunk:
                    break
                room = self.MAX_GIT_CAPTURE - sizes[name]
                if room > 0:
                    captured[name].append(chunk[:room])
                    sizes[name] += min(len(chunk), room)
                if len(chunk) > room:
                    overflow.add(name)
                    try:
                        process.terminate()
                    except OSError:
                        pass
                    break
            stream.close()

        threads = [
            threading.Thread(target=drain, args=(name, stream), daemon=True)
            for name, stream in (("stdout", process.stdout), ("stderr", process.stderr))
        ]
        for thread in threads:
            thread.start()
        try:
            returncode = process.wait(timeout=10)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.wait()
            raise RepoContextError("git repository read exceeded 10 seconds") from exc
        finally:
            for thread in threads:
                thread.join(timeout=1)
        stdout = b"".join(captured["stdout"]).decode("utf-8", "replace")
        stderr = b"".join(captured["stderr"]).decode("utf-8", "replace")
        if "stderr" in overflow or ("stdout" in overflow and not allow_truncated):
            raise RepoContextError("git repository read exceeded its output limit")
        if returncode not in ok and not (allow_truncated and "stdout" in overflow):
            raise RepoContextError(stderr.strip() or "git could not read repository context")
        return stdout

    def overview(self, request):
        words = {
            word for word in re.findall(r"[a-z0-9_]+", request.lower())
            if len(word) >= 3 and word not in {"fix", "add", "the", "with", "for", "and"}
        }

        def rank(path):
            lower = path.lower()
            matches = sum(word in lower for word in words)
            config = pathlib.PurePosixPath(path).name in {
                "pyproject.toml", "package.json", "cargo.toml", "go.mod", "makefile",
            }
            test = "test" in lower
            return matches * 10 + config * 2 + test, path

        candidates = sorted(self._tracked, key=rank, reverse=True)
        self._by_operation["overview"] += 1
        return {
            "tracked_file_count": len(self._tracked),
            "candidate_paths": candidates[:self.MAX_OVERVIEW_PATHS],
            "candidate_paths_truncated": len(candidates) > self.MAX_OVERVIEW_PATHS,
        }

    def retrieve(self, queries):
        if not isinstance(queries, list) or len(queries) > self.MAX_QUERIES:
            raise RepoContextError(f"retrieval accepts at most {self.MAX_QUERIES} queries")
        evidence = []
        remaining = self.MAX_TOTAL_CHARS
        for query in queries:
            if not isinstance(query, dict):
                raise RepoContextError("each retrieval query must be an object")
            operation = query.get("op")
            handler = getattr(self, f"_retrieve_{operation}", None)
            if handler is None:
                raise RepoContextError(f"unsupported retrieval operation: {operation}")
            self._by_operation[operation] += 1
            try:
                content = handler(query)
            except RepoContextError as exc:
                evidence.append({
                    "op": operation,
                    "query": {key: value for key, value in query.items() if key != "op"},
                    "content": "",
                    "truncated": False,
                    "error": str(exc),
                })
                continue
            limit = min(self.MAX_RESULT_CHARS, remaining)
            truncated = len(content) > limit
            content = content[:limit]
            remaining -= len(content)
            evidence.append({
                "op": operation,
                "query": {key: value for key, value in query.items() if key != "op"},
                "content": content,
                "truncated": truncated,
            })
            if remaining <= 0:
                break
        return evidence

    def _tracked_name(self, value):
        if not isinstance(value, str) or not value or value not in self._tracked_set:
            raise RepoContextError(f"path is not a tracked repository file: {value}")
        return value

    def _tracked_path(self, value):
        value = self._tracked_name(value)
        path = self.root / value
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise RepoContextError(f"path does not resolve to a repository file: {value}")
        if not path.is_file():
            raise RepoContextError(f"path is not a readable file: {value}")
        return path

    def _retrieve_list_files(self, query):
        pattern = query.get("pattern", "*")
        if not isinstance(pattern, str) or len(pattern) > 160:
            raise RepoContextError("list_files pattern must be a short string")
        return "\n".join(path for path in self._tracked if fnmatch.fnmatch(path, pattern))

    def _retrieve_search_text(self, query):
        term = query.get("query")
        if not isinstance(term, str) or not term or len(term) > 160:
            raise RepoContextError("search_text query must be a short non-empty string")
        return self._git("grep", "-n", "-I", "-F", "-e", term, "--",
                         ok=(0, 1), allow_truncated=True)

    def _retrieve_read_file(self, query):
        path = self._tracked_path(query.get("path"))
        start = query.get("start", 1)
        end = query.get("end", start + self.MAX_READ_LINES - 1)
        if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
            raise RepoContextError("read_file range must be positive integers")
        if start > self.MAX_READ_START:
            raise RepoContextError(
                f"read_file start must not exceed {self.MAX_READ_START}")
        end = min(end, start + self.MAX_READ_LINES - 1)
        selected = []
        remaining = self.MAX_RESULT_CHARS
        scanned = 0
        line_number = 1
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            while line_number <= end and remaining > 0:
                read_limit = min(
                    self.MAX_RESULT_CHARS + 1,
                    self.MAX_READ_SCAN_CHARS - scanned + 1,
                )
                chunk = handle.readline(read_limit)
                if not chunk:
                    break
                scanned += len(chunk)
                if scanned > self.MAX_READ_SCAN_CHARS:
                    raise RepoContextError("read_file exceeded its scan budget")
                complete = chunk.endswith("\n")
                if line_number >= start:
                    selected.append(chunk[:remaining])
                    remaining -= min(len(chunk), remaining)
                if (not complete and line_number < start
                        and len(chunk) == read_limit):
                    raise RepoContextError(
                        "read_file encountered an oversized physical line")
                line_number += 1
        return "".join(selected).rstrip("\n")

    def _retrieve_history(self, query):
        path = query.get("path")
        self._tracked_name(path)
        limit = query.get("limit", 5)
        if not isinstance(limit, int) or not 1 <= limit <= 10:
            raise RepoContextError("history limit must be between 1 and 10")
        return self._git("log", f"-{limit}", "--format=%h %s", "--", path)

    def _retrieve_diff(self, query):
        path = query.get("path")
        self._tracked_name(path)
        return self._git(
            "diff", "--no-ext-diff", "--no-textconv", "HEAD", "--", path,
            allow_truncated=True)
