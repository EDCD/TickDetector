#!/usr/bin/env python

"""Check if the BGS tick live database has updated recently"""

import argparse
import datetime
import dateutil.parser
import sqlite3
import pathlib
import subprocess
import time

import nagiosplugin

class BGSTickInfluenceState:
    def __init__(
        self, state: str, time_diff: float, warning: float, critical: float
    ):
        self.state = state
        self.time_diff = time_diff
        self.warning = warning
        self.critical = critical

class BGSTickInfluence(nagiosplugin.Resource):
    DATABASE_FRESHNESS = 900  # How old the file can be in seconds

    def __init__(self, db_filename: str, warning: float, critical: float):
        self.db_filename = db_filename
        self.warning = warning
        self.critical = critical


    def probe(self):
        self.db_path = pathlib.Path(self.db_filename)

        if not self.db_path.exists() or not self.db_path.is_file():
            dbs = BGSTickInfluenceState(
                'ENOFILE', -1, self.warning, self.critical
            )
        else:
            dbs = self.query_influence_age()

        return [nagiosplugin.Metric('state', dbs, context='bgstick-db')]


    def query_influence_age(self):
        conn = sqlite3.connect(
            self.db_path,
            timeout=10.0,
        )

        curs = conn.cursor()

        curs.execute(
            "SELECT LAST_SEEN FROM INFLUENCE ORDER BY LAST_SEEN DESC LIMIT 1"
        )

        res = curs.fetchone()
        if res is None:
            return BGSTickInfluenceState(
                'FAIL',
                -1,
                self.warning,
                self.critical
            )

        else:
            inf_latest = dateutil.parser.isoparse(res[0])
            time_diff = datetime.datetime.now().timestamp() - inf_latest.timestamp()

            return BGSTickInfluenceState(
                'Query Succeeded',
                time_diff,
                self.warning,
                self.critical
            )



class BGSTickInfluenceContext(nagiosplugin.Context):

    def __init__(self):
        super().__init__(name="bgstick-db")


    def evaluate(self, metric, resource):
        val = metric.value
        if val.state == "Query Succeeded":
            if val.time_diff >= val.critical:
                return nagiosplugin.state.Critical
            elif val.time_diff >= val.warning:
                return nagiosplugin.state.Warn
            else:
                return nagiosplugin.state.Ok

        return nagiosplugin.state.Critical


class BGSTickInfluenceSummary(nagiosplugin.Summary):

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
        BGSTickInfluence(args.file, float(args.warning), float(args.critical)),
        BGSTickInfluenceContext(),
        BGSTickInfluenceSummary()
    )
    check.main()


if __name__ == '__main__':
    main()

