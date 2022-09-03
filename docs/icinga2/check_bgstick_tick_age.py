#!/usr/bin/env python

"""Check if the age of the BGS live tick"""

import argparse
import datetime
import dateutil.parser
import sqlite3
import pathlib
import requests
import subprocess
import time

import nagiosplugin

class BGSTickAgeState:
    def __init__(
        self, state: str, time_diff: float, warning: float, critical: float
    ):
        self.state = state
        self.time_diff = time_diff
        self.warning = warning
        self.critical = critical

class BGSTickAge(nagiosplugin.Resource):
    def __init__(self, api_tick_url: str, warning: float, critical: float):
        self.api_tick_url = api_tick_url
        self.warning = warning
        self.critical = critical


    def probe(self):
        try:
            s = requests.Session()
            r = s.get(self.api_tick_url, timeout=10)
            r.raise_for_status()

        except requests.HTTPError:
            dbs = BGSTickAgeState(
                "FAIL",
                -1,
                self.warning,
                self.critical
            )
            
        tick = r.content.decode(encoding="utf-8")
        tick = tick.strip("\"")

        p = dateutil.parser.isoparser()
        tick_time = p.isoparse(tick)

        diff_secs = datetime.datetime.utcnow().timestamp() - tick_time.timestamp()

        dbs = BGSTickAgeState(
            "Query Succeeded",
            int(diff_secs / 60),  # Minute accuracy
            self.warning,
            self.critical
        )
        return [nagiosplugin.Metric("state", dbs, context="bgstick-age")]



class BGSTickAgeContext(nagiosplugin.Context):

    def __init__(self):
        super().__init__(name="bgstick-age")


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


class BGSTickAgeSummary(nagiosplugin.Summary):

    def ok(self, results):
        return "%s %s" % (
            results[0].metric.value.state,
            results[0].metric.value.time_diff,
        )

    def problem(self, results):
        res = results[0]
        if res.metric:
            val = res.metric.value
            return "%s %s" % (
                val.state,
                val.time_diff
            )
        else:
            return str(res)


@nagiosplugin.guarded
def main():
    argp = argparse.ArgumentParser(description=__doc__)
    argp.add_argument("-u", "--url", metavar="URL", required=True,
        help="API tick URL")
    argp.add_argument("-w", "--warning", metavar="WARNING", required=True,
        help="Age to result in warning status (minues)")
    argp.add_argument("-c", "--critical", metavar="CRITICAL", required=True,
        help="Age to result in critical status (minutes)")

    args = argp.parse_args()

    check = nagiosplugin.Check(
        BGSTickAge(args.url, float(args.warning), float(args.critical)),
        BGSTickAgeContext(),
        BGSTickAgeSummary()
    )
    check.main()


if __name__ == "__main__":
    main()

