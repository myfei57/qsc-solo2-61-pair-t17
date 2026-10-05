"""End to end tests for the HTTP control console."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import tempfile
import unittest

from tunnelnet import cli
from tunnelnet.console import create_application
from tunnelnet.console.http import (
    STATUS_TEXT,
    Request,
    RequestError,
    Response,
    Router,
    build_request,
    csv_response,
    error_response,
    html_response,
    json_response,
    redirect_response,
    text_response,
)
from tunnelnet.console.routes import route_table
from tunnelnet.console.server import Server
from tunnelnet.store import Store


class ConsoleCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Store.open(f"{self._tmp.name}/data")
        self.server = Server(self.store, web_dir="web")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def call(self, method: str, path: str, payload: dict | None = None, query: dict | None = None):
        response = self.server.dispatch(method, path, payload, query)
        body = response.body.decode("utf-8")
        parsed = json.loads(body) if response.content_type.startswith("application/json") else body
        return response.status, parsed

    def test_health_snapshot_and_reports(self) -> None:
        status, health = self.call("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["kinds"], [])

        status, checks = self.call("GET", "/api/health/checks")
        self.assertEqual(status, 200)
        self.assertEqual(
            {check["name"] for check in checks["checks"]},
            {"store", "access", "drain", "ventilation", "fire", "patrol", "quota", "cables", "environment", "audit"},
        )

        status, snapshot = self.call("GET", "/api/snapshot")
        self.assertEqual(status, 200)
        self.assertEqual(
            set(snapshot),
            {
                "chain",
                "store",
                "namespaces",
                "cabins",
                "partitions",
                "access",
                "environment",
                "drain",
                "ventilation",
                "fire",
                "patrol",
                "quota",
                "cables",
                "suppression",
                "audit",
            },
        )

        status, describe = self.call("GET", "/api/describe")
        self.assertEqual(status, 200)
        self.assertIn("chain", describe)
        self.assertIn("power", describe)

        status, report = self.call("GET", "/api/report")
        self.assertEqual(status, 200)
        self.assertEqual(report["namespaces"]["count"], 2)
        self.assertEqual(report["cabins"]["total"], 3)

        status, text = self.call("GET", "/api/report.txt")
        self.assertEqual(status, 200)
        self.assertIn("tunnelnet control report", text)

    def test_metadata_routes(self) -> None:
        status, chain = self.call("GET", "/api/chain")
        self.assertEqual(status, 200)
        self.assertTrue(chain["ordered"])
        self.assertEqual(chain["last_stage"], "audit")
        self.assertEqual(len(chain["steps"]), 7)

        status, catalog = self.call("GET", "/api/catalog")
        self.assertEqual(status, 200)
        self.assertEqual(len(catalog["routes"]), len(route_table()))
        self.assertIn("/api/cabins", catalog["paths"])

        status, ops = self.call("GET", "/api/ops")
        self.assertEqual(status, 200)
        self.assertEqual(ops["cabins"], 3)

        status, telemetry = self.call("GET", "/api/telemetry")
        self.assertEqual(status, 200)
        self.assertEqual(telemetry["cabins"], 3)
        self.assertEqual(telemetry["fire_detectors"], 2)

        status, version = self.call("GET", "/api/version")
        self.assertEqual(status, 200)
        self.assertEqual(version["name"], "tunnelnet-control")

        status, system = self.call("GET", "/api/system")
        self.assertEqual(status, 200)
        self.assertIn("python", system)

        status, metrics = self.call("GET", "/api/metrics")
        self.assertEqual(status, 200)
        self.assertGreater(metrics["requests"], 0)
        status, metrics = self.call("POST", "/api/metrics/reset")
        self.assertTrue(metrics["reset"])
        _, metrics = self.call("GET", "/api/metrics")
        self.assertEqual(metrics["requests"], 1)

    def test_pages_redirect_and_errors(self) -> None:
        for page in ("/cabins", "/env", "/patrols", "/alarms"):
            status, body = self.call("GET", page)
            self.assertEqual(status, 200)
            self.assertIn("<html", body)

        response = self.server.dispatch("GET", "/")
        self.assertEqual(response.status, 302)
        self.assertIn(("Location", "/cabins"), response.headers)

        status, body = self.call("GET", "/api/missing")
        self.assertEqual(status, 404)
        self.assertIn("no route", body["error"])

        status, body = self.call("DELETE", "/api/health")
        self.assertEqual(status, 405)
        self.assertIn("not allowed", body["error"])

        status, body = self.call("POST", "/api/env/sample", {"value": "abc"})
        self.assertEqual(status, 400)
        self.assertIn("must be a number", body["error"])

        status, body = self.call("POST", "/api/cabins/door", {"id": "ghost", "release": True})
        self.assertEqual(status, 400)
        self.assertIn("not found", body["error"])

        status, body = self.call("POST", "/api/simulate", {"ticks": "abc"})
        self.assertEqual(status, 400)
        self.assertIn("must be an integer", body["error"])

        status, body = self.call("POST", "/api/env/sample", {"value": True})
        self.assertEqual(status, 400)
        self.assertIn("must be a number", body["error"])

        status, body = self.call("POST", "/api/cycle", {"samples": 5})
        self.assertEqual(status, 400)
        self.assertIn("must be a list of numbers", body["error"])

        status, body = self.call("POST", "/api/drain/levels", {"levels": 5})
        self.assertEqual(status, 400)
        self.assertIn("must be an object", body["error"])

        missing = Server(self.store, web_dir="definitely-missing")
        response = missing.dispatch("GET", "/cabins")
        self.assertEqual(response.status, 404)
        self.assertIn(b"not found", response.body)

    def test_namespaces_and_cabins(self) -> None:
        status, namespaces = self.call("GET", "/api/namespaces")
        self.assertEqual(status, 200)
        self.assertEqual(namespaces["names"], ["segment-a", "segment-b"])

        status, body = self.call("POST", "/api/namespaces", {"id": "segment-c", "name": "cfg"})
        self.assertTrue(body["added"])
        self.assertEqual(body["count"], 3)
        status, body = self.call("POST", "/api/namespaces", {"id": "segment-c"})
        self.assertTrue(body["removed"])
        status, body = self.call("POST", "/api/namespaces", {})
        self.assertEqual(status, 400)

        status, cabins = self.call("GET", "/api/cabins")
        self.assertEqual(len(cabins["items"]), 3)

        status, summary = self.call("GET", "/api/cabins/status")
        self.assertEqual(summary["total"], 3)

        status, zones = self.call("GET", "/api/cabins/zones", query={"zone": ["zone-1"]})
        self.assertEqual(zones["zones"], ["zone-1", "zone-2", "zone-3"])
        self.assertEqual(len(zones["cabins"]), 1)

        status, found = self.call("GET", "/api/cabins/zones", query={"id": ["cabin-1"]})
        self.assertTrue(found["found"])
        self.assertEqual(found["cabin"]["id"], "cabin-1")

        status, body = self.call(
            "POST", "/api/cabins/extend", {"id": "cabin-4", "name": "four", "zone": "zone-4", "partition": "part-4"}
        )
        self.assertEqual(len(body["items"]), 4)
        self.assertEqual(body["items"][-1]["revision"], 4)

        status, body = self.call("POST", "/api/cabins/rename", {"id": "cabin-4", "name": "renamed"})
        self.assertEqual(body["cabin"]["name"], "renamed")
        status, body = self.call(
            "POST", "/api/cabins/move", {"id": "cabin-4", "zone": "zone-9", "partition": "part-9"}
        )
        self.assertEqual(body["cabin"]["zone"], "zone-9")
        status, body = self.call("POST", "/api/cabins/zone", {"id": "cabin-4", "zone": "zone-8"})
        self.assertEqual(body["cabin"]["zone"], "zone-8")

        status, body = self.call("POST", "/api/cabins/door", {"id": "cabin-1", "release": True})
        self.assertTrue(body["open"])
        status, body = self.call("POST", "/api/cabins/door", {"id": "cabin-1", "release": False})
        self.assertFalse(body["open"])
        status, body = self.call("POST", "/api/cabins/valve", {"id": "cabin-1", "open": True})
        self.assertTrue(body["open"])
        status, body = self.call("POST", "/api/cabins/valve", {"id": "cabin-1", "open": False})
        self.assertFalse(body["open"])

        status, body = self.call("POST", "/api/cabins/label", {"id": "cabin-1", "label": "cold"})
        self.assertEqual(body["labels"], ["cold"])
        status, body = self.call("POST", "/api/cabins/retire", {"id": "cabin-4"})
        self.assertEqual(len(body["items"]), 4)

    def test_access_routes(self) -> None:
        status, request = self.call("POST", "/api/access/submit", {"cabin_id": "cabin-1", "requester": "ops"})
        self.assertEqual(status, 200)
        self.assertEqual(request["status"], "pending")

        status, pending = self.call("GET", "/api/access/requests")
        self.assertEqual(pending["count"], 1)
        self.assertEqual(pending["pending"][0]["id"], request["id"])

        status, approval = self.call("POST", "/api/access/grant", {"request_id": request["id"]})
        self.assertEqual(status, 200)
        self.assertEqual(approval["cabin_id"], "cabin-1")

        status, approvals = self.call("GET", "/api/access/approvals")
        self.assertEqual(status, 200)
        self.assertTrue(approvals["items"][0]["durable"])

        status, direct = self.call("POST", "/api/access/approve", {"cabin_id": "cabin-2", "requester": "ops"})
        self.assertEqual(direct["cabin_id"], "cabin-2")

        status, summary = self.call("GET", "/api/access/summary")
        self.assertEqual(summary["requests"], 1)
        self.assertEqual(summary["granted"], 1)

        status, body = self.call("POST", "/api/access/revoke", {"approval_id": direct["id"]})
        self.assertTrue(body["revoked"])
        status, body = self.call("POST", "/api/access/revoke", {"approval_id": direct["id"]})
        self.assertEqual(status, 404)

        status, body = self.call("POST", "/api/access/grant", {"request_id": "ghost"})
        self.assertEqual(status, 400)

    def test_environment_routes(self) -> None:
        status, overview = self.call("GET", "/api/env")
        self.assertEqual(status, 200)
        self.assertEqual(overview["sensor_1_cabin"], "cabin-1")
        self.assertEqual(overview["threshold"], 75.0)

        status, sensors = self.call("GET", "/api/env/sensors")
        self.assertEqual(len(sensors["sensors"]), 3)
        self.assertEqual(sensors["snapshot"]["sensors"]["sensor-1"]["count"], 2)

        status, history = self.call("GET", "/api/env/sensors", query={"sensor": ["sensor-1"]})
        self.assertEqual(len(history["history"]), 2)

        status, trend = self.call("GET", "/api/env/trend", query={"sensor": ["sensor-1"]})
        self.assertEqual(trend["count"], 2)
        self.assertGreater(trend["max"], trend["min"])

        status, body = self.call("GET", "/api/env/trend")
        self.assertEqual(status, 400)

        status, threshold = self.call("GET", "/api/env/threshold")
        self.assertEqual(threshold["threshold"], 75.0)
        status, threshold = self.call("POST", "/api/env/threshold", {"threshold": 10.0})
        self.assertEqual(threshold["threshold"], 10.0)

        status, body = self.call("POST", "/api/env/sample", {"sensor_id": "sensor-3", "value": 50.0, "at": "t"})
        self.assertTrue(body["alarmed"])
        _, overview = self.call("GET", "/api/env")
        self.assertEqual(len(overview["alarms"]), 1)

        status, moving = self.call("GET", "/api/env/filter")
        self.assertEqual(moving["size"], 3)
        status, moving = self.call("POST", "/api/env/filter/reset")
        self.assertTrue(moving["reset"])
        self.assertEqual(moving["window"], [])

        status, body = self.call(
            "POST", "/api/env/partition", {"partition_id": "part-3", "cabin_id": "cabin-1"}
        )
        self.assertEqual(body["revision"], 4)

    def test_drain_routes(self) -> None:
        status, pits = self.call("GET", "/api/drain/pits")
        self.assertEqual(pits["count"], 2)
        status, pits = self.call("GET", "/api/drain/pits", query={"id": ["pit-1"]})
        self.assertFalse(pits["is_high"])

        status, body = self.call("POST", "/api/drain/pit", {"id": "pit-3", "cabin": "cabin-3", "water_level": 0.9})
        self.assertEqual(len(body["items"]), 3)

        status, body = self.call("POST", "/api/drain/levels", {"levels": {"pit-1": 0.9}})
        self.assertEqual(body["levels"]["pit-1"], 0.9)

        status, high = self.call("GET", "/api/drain/high")
        self.assertEqual([pit["id"] for pit in high["high"]], ["pit-1", "pit-3"])
        self.assertEqual(high["count"], 2)

        status, threshold = self.call("POST", "/api/drain/threshold", {"threshold": 0.3})
        self.assertEqual(threshold["threshold"], 0.3)

        status, body = self.call("POST", "/api/drain/start", {"cabin_id": "cabin-1"})
        self.assertEqual(body["runs"], 1)
        self.assertEqual(body["state"], "pump_running")

        status, body = self.call("POST", "/api/drain/execute", {"command_key": "cmd-1"})
        self.assertTrue(body["executed"])
        self.assertEqual(body["runs"], 2)
        status, body = self.call("POST", "/api/drain/execute", {"command_key": "cmd-1"})
        self.assertFalse(body["executed"])

        status, body = self.call("POST", "/api/drain/cycle", {"cabin_id": "cabin-1", "at": "t"})
        self.assertEqual(body["count"], 3)

        status, state = self.call("GET", "/api/drain/state")
        self.assertEqual(state["state"], "idle")
        self.assertEqual(state["pump_runs"], 1)

        status, body = self.call("POST", "/api/drain/state", {"state": "manual"})
        self.assertEqual(body["state"], "manual")

        status, body = self.call("POST", "/api/drain/in-flight", {"command_key": "cmd-2"})
        self.assertTrue(body["in_flight"])
        status, body = self.call("POST", "/api/drain/in-flight", {"command_key": "cmd-2", "action": "clear"})
        self.assertFalse(body["in_flight"])
        status, body = self.call("POST", "/api/drain/in-flight", {})
        self.assertEqual(status, 400)

        status, pending = self.call("GET", "/api/drain/pending")
        self.assertEqual(pending["pending"], [])

    def test_vent_and_fire_routes(self) -> None:
        status, vent = self.call("GET", "/api/vent")
        self.assertTrue(vent["running"])
        status, vent = self.call("POST", "/api/vent/toggle")
        self.assertFalse(vent["running"])
        status, vent = self.call("POST", "/api/vent/start")
        self.assertTrue(vent["running"])

        status, detectors = self.call("GET", "/api/fire/detectors")
        self.assertEqual(detectors["count"], 2)
        status, zones = self.call("GET", "/api/fire/zones")
        self.assertEqual(zones["count"], 3)

        status, body = self.call("POST", "/api/fire/detector", {"id": "detector-3", "zone": "zone-3"})
        self.assertEqual(body["detector"]["id"], "detector-3")

        status, body = self.call("POST", "/api/fire/detect", {"detector_id": "detector-1"})
        self.assertEqual(body["zone"], "zone-1")
        _, vent = self.call("GET", "/api/vent")
        self.assertFalse(vent["running"])
        status, body = self.call("POST", "/api/fire/detect", {"detector_id": "ghost"})
        self.assertEqual(status, 404)

        status, body = self.call("POST", "/api/fire/smoke", {"zone": "zone-2"})
        self.assertTrue(body["ok"])

        status, body = self.call("POST", "/api/fire/zone", {"zone": "zone-2"})
        self.assertEqual(body["order"], ["zone-2", "zone-1", "zone-3"])
        status, suppression = self.call("GET", "/api/suppression")
        self.assertEqual(suppression["zones"], ["zone-2", "zone-1", "zone-3"])
        self.assertEqual(suppression["entries"][0]["zone"], "zone-2")

        status, body = self.call("POST", "/api/fire/alarm", {"event_key": "e1"})
        self.assertTrue(body["raised"])
        status, body = self.call("POST", "/api/fire/alarm", {"event_key": "e1"})
        self.assertFalse(body["raised"])
        status, alarms = self.call("GET", "/api/fire/alarms")
        self.assertEqual(alarms["count"], 1)
        self.assertEqual(alarms["distinct"], 1)
        status, fire_report = self.call("GET", "/api/fire/report")
        self.assertEqual(fire_report["alarm_count"], 1)
        status, body = self.call("POST", "/api/fire/clear")
        self.assertEqual(body["count"], 0)

        status, marks = self.call("GET", "/api/audit/marks", query={"key": ["e1"]})
        self.assertGreaterEqual(marks["count"], 1)
        self.assertTrue(marks["has"])
        status, body = self.call("POST", "/api/audit/marks/clear")
        self.assertEqual(body["count"], 0)

        status, body = self.call("POST", "/api/suppression/clear")
        self.assertEqual(body["count"], 0)

    def test_patrol_routes(self) -> None:
        status, patrols = self.call("GET", "/api/patrols")
        self.assertEqual(patrols["route_ids"], ["cabin-1", "cabin-2", "cabin-3"])
        self.assertEqual(patrols["missed"], ["cabin-2", "cabin-3"])
        self.assertEqual(patrols["checked_ids"], ["cabin-1"])

        status, body = self.call("POST", "/api/patrol/checkin", {"cabin_id": "cabin-2", "at": "t"})
        self.assertEqual(body["missed"], ["cabin-3"])

        status, body = self.call("POST", "/api/patrol/due", {"cabin_id": "cabin-3", "due": "2025-01-01T00:00:00Z"})
        self.assertEqual(body["due"], "2025-01-01T00:00:00Z")

        status, progress = self.call("GET", "/api/patrol/progress", query={"now": ["2026-01-01T00:00:00Z"]})
        self.assertEqual(progress["overdue"], ["cabin-3"])
        self.assertAlmostEqual(progress["progress"], 2 / 3)

        status, summary = self.call("GET", "/api/patrol/summary")
        self.assertEqual(summary["route"], 3)
        self.assertEqual(summary["missed"], 1)

        status, body = self.call("POST", "/api/patrol/rebuild")
        self.assertEqual(len(body["route"]), 3)

    def test_cable_routes(self) -> None:
        status, cables = self.call("GET", "/api/cables")
        self.assertEqual(len(cables["items"]), 2)
        self.assertEqual(cables["summary"]["samples"], 2)

        status, stats = self.call("GET", "/api/cables/stats", query={"id": ["cable-1"]})
        self.assertEqual(stats["history"], [42.0, 47.0])
        self.assertAlmostEqual(stats["average"], 44.5)
        self.assertEqual(stats["max"], 47.0)
        self.assertEqual(stats["over"], 0)

        status, body = self.call("GET", "/api/cables/stats")
        self.assertEqual(status, 400)

        status, body = self.call("POST", "/api/cables/temp", {"cable_id": "cable-1", "temp": 80.0})
        self.assertEqual(body["status"], "over")
        status, body = self.call("POST", "/api/cables/sample", {"cable_id": "cable-1", "value": 90.0})
        self.assertEqual(len(body["history"]), 3)
        status, body = self.call("POST", "/api/cables/temp", {"cable_id": "ghost", "temp": 10.0})
        self.assertEqual(status, 404)
        status, body = self.call("POST", "/api/cables/sample", {"cable_id": "ghost", "value": 10.0})
        self.assertEqual(status, 404)

        status, health = self.call("GET", "/api/cables/health")
        self.assertEqual(health["danger"], 1)
        self.assertEqual(health["healthy"], 1)
        self.assertGreater(health["load_factor"], 0)

    def test_quota_routes(self) -> None:
        status, report = self.call("GET", "/api/quota/report")
        self.assertEqual(len(report["items"]), 3)
        self.assertEqual(report["book_cabins"], ["cabin-1", "cabin-2", "cabin-3"])

        status, body = self.call("POST", "/api/quota/refresh", {"watts": 1000.0})
        self.assertEqual([item["watts"] for item in body["items"]], [1000.0, 1000.0, 1000.0])

        status, usage = self.call("GET", "/api/quota/usage")
        self.assertEqual(usage["usage"], {"cabin-1": 1200.0, "cabin-2": 900.0})
        self.assertEqual(usage["ranked"], ["cabin-1", "cabin-2"])

        status, body = self.call("POST", "/api/quota/usage", {"cabin_id": "cabin-1", "watts": 500.0})
        self.assertEqual(body["usage"], 1700.0)

        status, advanced = self.call(
            "GET", "/api/quota/advanced", query={"cabin": ["cabin-1"], "factor": ["2"]}
        )
        self.assertEqual(advanced["peak_cabin"], "cabin-1")
        self.assertEqual(advanced["forecast"], 3400.0)
        self.assertGreater(advanced["overage"], 0)

        status, summary = self.call("GET", "/api/quota/summary")
        self.assertEqual(summary["cabins"], 3)
        self.assertEqual(summary["peak_cabin"], "cabin-1")

    def test_audit_and_store_routes(self) -> None:
        self.call("POST", "/api/access/approve", {"cabin_id": "cabin-1", "requester": "ops"})
        status, audit = self.call("GET", "/api/audit")
        self.assertGreaterEqual(audit["count"], 2)

        status, body = self.call("POST", "/api/audit/append", {"event": "manual", "ref": "r1"})
        self.assertEqual(len(body["appended"]), 2)
        status, body = self.call("POST", "/api/audit/append", {})
        self.assertEqual(status, 400)

        status, query = self.call("GET", "/api/audit/query", query={"event": ["manual"]})
        self.assertEqual(len(query["filtered"]), 1)
        self.assertIn("access_approved", query["events"])
        self.assertIn("most_recent", query)
        self.assertTrue(query["latest_id"])

        status, query = self.call("GET", "/api/audit/query", query={"last": ["1"]})
        self.assertEqual(len(query["last"]), 1)
        status, query = self.call(
            "GET",
            "/api/audit/query",
            query={"start": ["2026-01-01T00:00:00Z"], "end": ["2099-01-01T00:00:00Z"]},
        )
        self.assertTrue(query["between"])

        status, summary = self.call("GET", "/api/audit/summary")
        self.assertGreaterEqual(summary["summary"]["total"], 3)
        self.assertIn("manual", summary["by_event"])

        status, store_stats = self.call("GET", "/api/store/stats")
        self.assertGreaterEqual(store_stats["summary"]["records"], 1)
        self.assertIn("approval", store_stats["kinds"])
        self.assertTrue(store_stats["root"])

        status, exported = self.call("GET", "/api/store/export", query={"kind": ["approval"]})
        self.assertEqual(len(exported["items"]), 1)
        status, exported = self.call("GET", "/api/store/export")
        self.assertIn("approval", exported["items"])

        status, body = self.call("GET", "/api/export/audit")
        self.assertTrue(body.startswith("id,event,at"))
        status, body = self.call("GET", "/api/export/telemetry")
        self.assertIn("metric,value", body)
        status, body = self.call("GET", "/api/export/store")
        self.assertIn("kind,records", body)

        status, body = self.call("POST", "/api/audit/clear")
        self.assertEqual(body["count"], 0)

    def test_cycle_and_simulate_routes(self) -> None:
        status, body = self.call(
            "POST",
            "/api/cycle",
            {
                "cabin_id": "cabin-1",
                "requester": "ops",
                "zone": "zone-1",
                "sensor_id": "sensor-1",
                "samples": [10.0, 20.0],
                "at": "t",
                "watts": 100.0,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["reading"], 15.0)
        self.assertEqual(body["zones"], ["zone-1", "zone-2", "zone-3"])
        self.assertTrue(body["alarm_raised"])
        self.assertEqual(body["usage"], 1300.0)
        self.assertEqual(body["drain_runs"], 1)
        self.assertEqual(body["audit_count"], 4)
        self.assertEqual(body["last_stage"], "audit")

        status, report = self.call("POST", "/api/simulate", {"ticks": 3})
        self.assertEqual(status, 200)
        self.assertEqual(len(report["ticks"]), 3)
        self.assertEqual(report["ticks"][0]["stage"], "access")
        self.assertEqual(report["last_stage"], "audit")

        status, report = self.call("POST", "/api/simulate", {})
        self.assertEqual(len(report["ticks"]), 5)
        status, report = self.call("POST", "/api/simulate", {"ticks": 1000})
        self.assertEqual(len(report["ticks"]), 100)
        status, report = self.call("POST", "/api/simulate", {"ticks": -3})
        self.assertEqual(len(report["ticks"]), 5)

    def test_ops_reset_store(self) -> None:
        self.call("POST", "/api/access/approve", {"cabin_id": "cabin-1", "requester": "ops"})
        _, before = self.call("GET", "/api/ops")
        self.assertGreaterEqual(before["store_records"], 1)
        status, body = self.call("POST", "/api/ops/reset-store")
        self.assertTrue(body["reset"])
        self.assertEqual(body["records"], 0)


class WsgiCase(unittest.TestCase):
    def test_wsgi_entry_point(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.open(f"{tmp}/data")
            server = Server(store, web_dir="web")
            captured: dict[str, object] = {}

            def start_response(status, headers):
                captured["status"] = status
                captured["headers"] = headers

            payload = json.dumps({"cabin_id": "cabin-1", "requester": "ops"}).encode("utf-8")

            class Stream:
                def read(self, size: int) -> bytes:
                    return payload

            environ = {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/api/access/approve",
                "QUERY_STRING": "",
                "CONTENT_LENGTH": str(len(payload)),
                "wsgi.input": Stream(),
            }
            body = b"".join(server(environ, start_response))
            self.assertEqual(captured["status"], "200 OK")
            self.assertEqual(json.loads(body)["cabin_id"], "cabin-1")

    def test_wsgi_error_branches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server = create_application(Store.open(f"{tmp}/data"), "web")
            captured: dict[str, object] = {}

            def start_response(status, headers):
                captured["status"] = status

            class Stream:
                def __init__(self, payload: bytes) -> None:
                    self._payload = payload

                def read(self, size: int) -> bytes:
                    return self._payload

            no_length = {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/api/health",
                "CONTENT_LENGTH": "abc",
            }
            body = b"".join(server(no_length, start_response))
            self.assertEqual(captured["status"], "200 OK")
            self.assertEqual(json.loads(body)["status"], "ok")

            malformed = {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/api/env/sample",
                "CONTENT_LENGTH": "4",
                "wsgi.input": Stream(b"{bad"),
            }
            body = b"".join(server(malformed, start_response))
            self.assertEqual(captured["status"], "400 Bad Request")
            self.assertIn("invalid JSON", json.loads(body)["error"])

            array = {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/api/env/sample",
                "CONTENT_LENGTH": "5",
                "wsgi.input": Stream(b"[1,2]"),
            }
            body = b"".join(server(array, start_response))
            self.assertEqual(captured["status"], "400 Bad Request")
            self.assertIn("must be an object", json.loads(body)["error"])


class HttpToolkitCase(unittest.TestCase):
    def test_request_field_helpers(self) -> None:
        request = Request(
            method="POST",
            path="/x",
            query={"a": ["1"]},
            payload={"f": 2, "n": "3", "s": 4, "nil": None, "list": [1, 2], "bool": True, "bad": "abc"},
        )
        self.assertEqual(request.float_field("f"), 2.0)
        self.assertEqual(request.float_field("missing", 5.0), 5.0)
        self.assertEqual(request.int_field("n"), 3)
        self.assertEqual(request.int_field("f"), 2)
        self.assertEqual(request.int_field("temp", 7), 7)
        self.assertEqual(request.str_field("s"), "4")
        self.assertEqual(request.str_field("nil", "d"), "d")
        self.assertEqual(request.str_field("missing", "d"), "d")
        self.assertEqual(request.float_list("list"), [1.0, 2.0])
        self.assertEqual(request.float_list("nil"), [])
        self.assertEqual(request.query_field("a"), "1")
        self.assertEqual(request.query_field("b", "z"), "z")
        with self.assertRaises(RequestError):
            request.int_field("bool")
        with self.assertRaises(RequestError):
            request.int_field("bad")
        with self.assertRaises(RequestError):
            request.float_field("bool")
        with self.assertRaises(RequestError):
            request.float_list("f")

        number = Request(method="POST", path="/x", query={}, payload={"float": 2.0, "items": [1]})
        self.assertEqual(number.int_field("float"), 2)
        with self.assertRaises(RequestError):
            number.int_field("items")

    def test_router_and_responses(self) -> None:
        router = Router()
        router.add("get", "/a", lambda server, request: json_response({}))
        self.assertIsNotNone(router.match("GET", "/a"))
        self.assertIsNone(router.match("POST", "/a"))
        self.assertTrue(router.allows("/a"))
        self.assertFalse(router.allows("/b"))
        self.assertEqual(router.paths(), ["/a"])

        self.assertEqual(json_response({"a": 1}).status, 200)
        self.assertTrue(json_response({}).content_type.startswith("application/json"))
        self.assertEqual(text_response("x").content_type, "text/plain; charset=utf-8")
        self.assertEqual(csv_response("x").content_type, "text/csv; charset=utf-8")
        self.assertEqual(html_response("<p>").content_type, "text/html; charset=utf-8")
        redirect = redirect_response("/y")
        self.assertEqual(redirect.status, 302)
        self.assertIn(("Location", "/y"), redirect.headers)
        self.assertEqual(error_response(404, "no").status, 404)
        status, headers = Response(200, b"hi", "text/plain").wsgi()
        self.assertEqual(status, "200 OK")
        self.assertIn(("Content-Length", "2"), headers)
        self.assertEqual(Response(599, b"", "text/plain").wsgi()[0], "599 Unknown")
        self.assertEqual(STATUS_TEXT[200], "OK")

    def test_build_request(self) -> None:
        request = build_request({"REQUEST_METHOD": "post", "PATH_INFO": "/api/x", "QUERY_STRING": "a=1&a=2"})
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.path, "/api/x")
        self.assertEqual(request.query["a"], ["1", "2"])
        self.assertEqual(request.payload, {})

        class Stream:
            def read(self, size: int) -> bytes:
                return b'{"k": 1}'

        request = build_request(
            {"REQUEST_METHOD": "POST", "PATH_INFO": "/x", "CONTENT_LENGTH": "8", "wsgi.input": Stream()}
        )
        self.assertEqual(request.payload, {"k": 1})

        class BadStream:
            def read(self, size: int) -> bytes:
                return b"{bad"

        with self.assertRaises(RequestError):
            build_request(
                {"REQUEST_METHOD": "POST", "PATH_INFO": "/x", "CONTENT_LENGTH": "4", "wsgi.input": BadStream()}
            )

        class ArrayStream:
            def read(self, size: int) -> bytes:
                return b"[1]"

        with self.assertRaises(RequestError):
            build_request(
                {"REQUEST_METHOD": "POST", "PATH_INFO": "/x", "CONTENT_LENGTH": "3", "wsgi.input": ArrayStream()}
            )


class CliCase(unittest.TestCase):
    def test_parser_and_address(self) -> None:
        args = cli.build_parser().parse_args([])
        self.assertEqual((args.store, args.web_dir, args.addr), ("data", "web", ":8080"))
        self.assertFalse(args.version)
        self.assertEqual(cli.parse_address("127.0.0.1:9000"), ("127.0.0.1", 9000))
        self.assertEqual(cli.parse_address(":8080"), ("0.0.0.0", 8080))
        with self.assertRaises(argparse.ArgumentTypeError):
            cli.parse_address("nope")
        self.assertEqual(cli.version_string(), "tunnelnet-control 1.0.0")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(cli.main(["--version"]), 0)
        self.assertIn("tunnelnet-control", buffer.getvalue())

    def test_create_application(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            application = create_application(Store.open(f"{tmp}/data"), "web")
            self.assertIsInstance(application, Server)


if __name__ == "__main__":
    unittest.main()
