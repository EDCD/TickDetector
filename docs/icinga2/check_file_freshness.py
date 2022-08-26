#!/usr/bin/env python

"""Check if the specified file has been updated recently"""

import argparse
import pathlib
import subprocess
import time

import nagiosplugin

class FileFreshnessState:
    def __init__(
        self, state: str, time_diff: float, warning: float, critical: float
    ):
        self.state = state
        self.time_diff = time_diff
        self.warning = warning
        self.critical = critical

class FileFreshness(nagiosplugin.Resource):
    DATABASE_FRESHNESS = 900  # How old the file can be in seconds

    def __init__(self, db_filename: str, warning: float, critical: float):
        self.db_filename = db_filename
        self.warning = warning
        self.critical = critical


    def probe(self):
        db = pathlib.Path(self.db_filename)

        if not db.exists() or not db.is_file():
            dbs = FileFreshnessState(
                'ENOFILE', -1, self.warning, self.critical
            )
        else:
            db_stat = db.stat()

            time_diff = time.time() - db_stat.st_mtime
            dbs = FileFreshnessState(
                'File Exists', time_diff, self.warning, self.critical
            )

        return [nagiosplugin.Metric('state', dbs, context='bgstick-db')]


class FileFreshnessContext(nagiosplugin.Context):

    def __init__(self):
        super().__init__(name="bgstick-db")


    def evaluate(self, metric, resource):
        val = metric.value
        if val.state == "File Exists":
            if val.time_diff >= val.critical:
                return nagiosplugin.state.Critical
            elif val.time_diff >= val.warning:
                return nagiosplugin.state.Warn
            else:
                return nagiosplugin.state.Ok

        return nagiosplugin.state.Critical


class FileFreshnessSummary(nagiosplugin.Summary):

    def ok(self, results):
        return '%s %s' % (
            results[0].metric.value.state,
            results[0].metric.value.time_diff,
        )

    def problem(self, results):
        res = results[0]
        if res.metric:
            val = res.metric.value
            return '%s %s' % (
                val.state,
                val.time_diff
            )
        else:
            return str(res)


@nagiosplugin.guarded
def main():
    argp = argparse.ArgumentParser(description=__doc__)
    argp.add_argument('-f', '--file', metavar='FILENAME', required=True,
        help='database file name')
    argp.add_argument('-w', '--warning', metavar='WARNING', required=True,
        help='Age to result in warning status (seconds)')
    argp.add_argument('-c', '--critical', metavar='CRITICAL', required=True,
        help='Age to result in critical status (seconds)')

    args = argp.parse_args()

    check = nagiosplugin.Check(
        FileFreshness(args.file, float(args.warning), float(args.critical)),
        FileFreshnessContext(),
        FileFreshnessSummary()
    )
    check.main()


if __name__ == '__main__':
    main()

