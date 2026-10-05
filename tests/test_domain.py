"""Behavioural tests for the control components."""

from __future__ import annotations

import tempfile
import unittest

from tunnelnet.access import AccessService, summarize
from tunnelnet.audit import (
    AuditRegistry,
    MarkSet,
    Record,
    between,
    count_by_event,
    events,
    filter_records,
    last,
    most_recent,
    summary,
)
from tunnelnet.cabin import (
    Cabin,
    Checkpoint,
    PartitionTable,
    PowerBaseline,
    PowerBook,
    Registry as CabinRegistry,
    StatusSummary,
    SuppressionLog,
    checkpoints,
    status_summary,
)
from tunnelnet.cable import (
    Cable,
    CableRegistry,
    MovingAverage,
    danger_count,
    healthy_count,
    load_factor,
)
from tunnelnet.cable.model import status_for
from tunnelnet.drain import (
    CommandGuard,
    DrainService,
    Pit,
    PumpUnit,
    average_level,
    high_count,
    low_count,
    max_level,
    utc_now,
)
from tunnelnet.env import (
    Environment,
    mean,
    percentile,
    snapshot,
    standard_deviation,
    variance,
)
from tunnelnet.fire import (
    Detector,
    FireService,
    activation_order,
    adjacent_zones,
)
from tunnelnet.ns import Chain
from tunnelnet.ns import Registry as NamespaceRegistry
from tunnelnet.ns import Stage, control_chain
from tunnelnet.patrol import CheckIn, PatrolService, overdue_cabins, progress_ratio
from tunnelnet.quota import QuotaService, baseline_report, overage_for, peak, rank, total
from tunnelnet.reporting import audit_export, store_export, telemetry_export, to_csv
from tunnelnet.store import (
    Approval,
    ExecutionMark,
    Store,
    approval_exists,
    describe_store,
    export_all,
    export_kind,
    list_approvals,
    load_approval,
    load_mark,
    mark_exists,
    revoke_approval,
    save_approval,
    save_mark,
    store_state,
    summarize as summarize_store,
)
from tunnelnet.store import record as record_module
from tunnelnet.vent import VentService


class StoreCase(unittest.TestCase):
    def test_round_trip_and_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.open(tmp)
            self.assertEqual(store.kinds(), [])
            store.save("cabin", "cabin-1", {"id": "cabin-1", "zone": "zone-1"})
            store.save("cabin", "cabin-2", {"id": "cabin-2", "zone": "zone-2"})
            store.save("mark", "k1", {"key": "k1", "executed_at": "now"})
            self.assertTrue(store.exists("cabin", "cabin-1"))
            self.assertEqual(store.load("cabin", "cabin-1"), {"id": "cabin-1", "zone": "zone-1"})
            self.assertIsNone(store.load("cabin", "missing"))
            self.assertEqual(store.list("cabin"), ["cabin-1", "cabin-2"])
            self.assertEqual(store.list("ghost"), [])
            self.assertEqual(store.count("cabin"), 2)
            self.assertEqual(store.kinds(), ["cabin", "mark"])
            self.assertEqual(store.stats(), {"cabin": 2, "mark": 1})
            self.assertEqual(store.file_count(), 3)
            self.assertGreater(store.total_bytes(), 0)
            self.assertIn("records=3", store.describe())
            self.assertTrue(store.delete("mark", "k1"))
            self.assertFalse(store.delete("mark", "k1"))
            self.assertEqual(store.root, store.root)

    def test_record_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = record_module.record_path(tmp, "cabin", "cabin-1")
            self.assertTrue(path.endswith("cabin-1.json"))
            self.assertEqual(record_module.decode(record_module.encode({"a": 1})), {"a": 1})
            self.assertIsNone(record_module.decode("not json"))
            self.assertIsNone(record_module.decode("[1, 2]"))
            self.assertEqual(record_module.record_ids(tmp, "cabin"), [])
            Store.open(tmp).save("cabin", "cabin-9", {"id": "cabin-9"})
            self.assertEqual(record_module.record_ids(tmp, "cabin"), ["cabin-9"])
            self.assertEqual(record_module.kind_names(tmp), ["cabin"])
            self.assertEqual(record_module.record_ids(f"{tmp}-missing", "cabin"), [])
            self.assertEqual(record_module.kind_names(f"{tmp}-missing"), [])


class StoreRecordCase(unittest.TestCase):
    def test_approvals_and_marks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.open(tmp)
            approval = Approval(id="a1", cabin_id="cabin-1", requester="ops", granted_at="now")
            save_approval(store, approval)
            self.assertTrue(approval_exists(store, "a1"))
            self.assertEqual(load_approval(store, "a1"), approval)
            self.assertEqual([item.id for item in list_approvals(store)], ["a1"])
            self.assertTrue(revoke_approval(store, "a1"))
            self.assertFalse(revoke_approval(store, "a1"))
            self.assertIsNone(load_approval(store, "a1"))

            mark = ExecutionMark(key="k1", executed_at="now")
            save_mark(store, mark)
            self.assertTrue(mark_exists(store, "k1"))
            self.assertEqual(load_mark(store, "k1"), mark)
            self.assertIsNone(load_mark(store, "k2"))

    def test_exports_and_projections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.open(tmp)
            store.save("cabin", "cabin-1", {"id": "cabin-1"})
            store.save("mark", "k1", {"key": "k1"})
            self.assertEqual(export_kind(store, "cabin"), {"cabin-1": {"id": "cabin-1"}})
            self.assertEqual(set(export_all(store)), {"cabin", "mark"})
            stats = summarize_store(store)
            self.assertEqual(stats.kinds, 2)
            self.assertEqual(stats.records, 2)
            self.assertEqual(stats.as_dict()["records"], 2)
            self.assertEqual(store_state(store).as_dict(), {"kinds": ["cabin", "mark"], "records": 2})
            self.assertIn("records=2", describe_store(store))


class NamespaceCase(unittest.TestCase):
    def test_registry_operations(self) -> None:
        registry = NamespaceRegistry()
        registry.add("segment-a", "segment A")
        registry.add("segment-b", "segment B")
        self.assertEqual(registry.count(), 2)
        self.assertEqual(registry.names(), ["segment-a", "segment-b"])
        self.assertEqual([item.id for item in registry.list()], ["segment-a", "segment-b"])
        self.assertTrue(registry.exists("segment-a"))
        self.assertTrue(registry.remove("segment-a"))
        self.assertFalse(registry.remove("segment-a"))
        self.assertIn("segments=1", registry.describe())
        with self.assertRaises(ValueError):
            registry.add("", "blank")


class ChainCase(unittest.TestCase):
    def test_control_chain_is_ordered(self) -> None:
        chain = control_chain()
        self.assertEqual(chain.count(), 7)
        self.assertEqual(chain.index_of(Stage.ACCESS), 0)
        self.assertTrue(chain.before(Stage.ACCESS, Stage.FIRE))
        self.assertFalse(chain.before(Stage.AUDIT, Stage.ACCESS))
        self.assertTrue(chain.contains(Stage.ENERGY))
        self.assertEqual(chain.last(), Stage.AUDIT)
        self.assertEqual(len(chain.steps()), 7)
        self.assertEqual(chain.steps()[0].action, "approve and release the cabin door")
        self.assertIn("tunnel-control", chain.describe())

    def test_missing_stages_and_empty_chain(self) -> None:
        self.assertEqual(control_chain().index_of(Stage.ACCESS), 0)
        partial = Chain(name="partial", stages=(Stage.ACCESS,))
        self.assertEqual(partial.index_of(Stage.FIRE), -1)
        self.assertFalse(partial.contains(Stage.FIRE))
        self.assertIsNone(Chain(name="empty", stages=()).last())
        self.assertEqual(Chain(name="empty", stages=()).count(), 0)
        self.assertEqual(str(Stage.FIRE), "fire")


class CabinCase(unittest.TestCase):
    def test_registry_lifecycle(self) -> None:
        registry = CabinRegistry()
        registry.upsert(Cabin(id="cabin-1", name="one", zone="zone-1", partition="part-1"))
        registry.extend(Cabin(id="cabin-2", name="two", zone="zone-2", partition="part-2"))
        self.assertEqual(registry.count(), 2)
        self.assertEqual(registry.active_count(), 2)
        self.assertEqual(registry.find("cabin-2").revision, 2)
        self.assertTrue(registry.has("cabin-1"))
        self.assertIsNone(registry.find("ghost"))
        self.assertEqual(registry.zones(), ["zone-1", "zone-2"])
        self.assertEqual([cabin.id for cabin in registry.zone_cabins("zone-1")], ["cabin-1"])

        registry.rename("cabin-1", "renamed")
        registry.assign_zone("cabin-1", "zone-9")
        registry.move("cabin-1", "zone-9", "part-9")
        self.assertEqual(registry.label("cabin-1", "cold"), ["cold"])
        self.assertEqual(registry.label("cabin-1", "cold"), ["cold"])
        self.assertEqual(registry.find("cabin-1").labels, ["cold"])

        registry.release_door("cabin-1")
        self.assertTrue(registry.door_state("cabin-1"))
        registry.seal_door("cabin-1")
        self.assertFalse(registry.door_state("cabin-1"))
        registry.open_valve("cabin-1")
        self.assertTrue(registry.valve_state("cabin-1"))
        registry.close_valve("cabin-1")
        self.assertFalse(registry.valve_state("cabin-1"))

        registry.retire("cabin-1")
        self.assertEqual(registry.active_count(), 1)
        self.assertEqual(len(registry.all()), 2)
        self.assertEqual(registry.state().total, 2)
        self.assertIn("total=2", registry.describe())
        with self.assertRaises(ValueError):
            registry.rename("ghost", "x")
        with self.assertRaises(ValueError):
            registry.upsert(Cabin(id=""))

    def test_partition_power_and_suppression(self) -> None:
        table = PartitionTable()
        self.assertEqual(table.repartition("part-1", "cabin-1"), 1)
        self.assertEqual(table.repartition("part-2", "cabin-2"), 2)
        self.assertEqual(table.cabin_of("part-1"), "cabin-1")
        self.assertEqual(table.mapping(), {"part-1": "cabin-1", "part-2": "cabin-2"})
        self.assertEqual(table.revision(), 2)
        self.assertIn("partitions=2", table.describe())

        book = PowerBook()
        book.set_baseline("cabin-1", 4200.0)
        book.set_baseline("cabin-2", 3800.0)
        self.assertEqual(book.baseline("cabin-1"), 4200.0)
        self.assertEqual(book.baseline("ghost"), 0.0)
        self.assertEqual(book.total(), 8000.0)
        self.assertEqual(book.cabins(), ["cabin-1", "cabin-2"])
        self.assertIn("baselines=2", book.describe())
        self.assertEqual(PowerBaseline("cabin-1", 4200.0).as_dict()["watts"], 4200.0)

        log = SuppressionLog()
        log.activate("zone-1")
        log.activate("zone-1")
        log.activate("zone-2")
        self.assertEqual(log.zones(), ["zone-1", "zone-1", "zone-2"])
        self.assertEqual(log.distinct_zones(), ["zone-1", "zone-2"])
        self.assertEqual(log.entries()[0].as_dict(), {"zone": "zone-1", "active": True})
        self.assertEqual(log.count(), 3)
        log.clear()
        self.assertEqual(log.count(), 0)
        self.assertEqual(log.describe(), "suppressions=0 zones=0")

    def test_status_and_checkpoints(self) -> None:
        registry = CabinRegistry()
        registry.upsert(Cabin(id="cabin-1", zone="zone-1"))
        registry.upsert(Cabin(id="cabin-2", zone="zone-2"))
        registry.release_door("cabin-1")
        registry.open_valve("cabin-2")
        summary = status_summary(registry)
        self.assertIsInstance(summary, StatusSummary)
        self.assertEqual(summary.as_dict(), {"total": 2, "active": 2, "open_doors": 1, "open_valves": 1})
        marks = checkpoints(registry)
        self.assertEqual([mark.cabin_id for mark in marks], ["cabin-1", "cabin-2"])
        self.assertEqual(marks[1].order, 1)
        self.assertIsInstance(marks[0], Checkpoint)
        self.assertEqual(marks[0].as_dict(), {"cabin_id": "cabin-1", "order": 0})

    def test_upsert_defaults_revision(self) -> None:
        registry = CabinRegistry()
        registry.upsert(Cabin(id="cabin-1", revision=0))
        self.assertEqual(registry.find("cabin-1").revision, 1)


class EnvironmentCase(unittest.TestCase):
    def test_sampling_alarms_and_trend(self) -> None:
        table = PartitionTable()
        table.repartition("part-1", "cabin-1")
        env = Environment(MovingAverage(1), table, 75.0)
        env.bind_sensor_at("sensor-1", "part-1")
        self.assertFalse(env.sample("sensor-1", 10.0, "t1"))
        self.assertFalse(env.sample("sensor-1", 20.0, "t2"))
        self.assertTrue(env.sample("sensor-1", 90.0, "t3"))
        self.assertEqual(env.reading_count("sensor-1"), 3)
        self.assertEqual(env.sensors(), ["sensor-1"])
        self.assertEqual(env.values("sensor-1"), [10.0, 20.0, 90.0])
        self.assertAlmostEqual(env.average("sensor-1"), 40.0)
        self.assertEqual(env.maximum("sensor-1"), 90.0)
        self.assertEqual(env.minimum("sensor-1"), 10.0)
        self.assertEqual(env.trend("sensor-1"), 80.0)
        self.assertAlmostEqual(env.variance("sensor-1"), variance([10.0, 20.0, 90.0]))
        self.assertAlmostEqual(env.std_dev("sensor-1"), standard_deviation([10.0, 20.0, 90.0]))
        self.assertEqual(env.percentile("sensor-1", 0.5), 20.0)
        self.assertEqual(env.percentile("sensor-1", 5.0), 90.0)
        self.assertEqual(env.alarm_count(), 1)
        self.assertEqual(env.alarms()[0].sensor_id, "sensor-1")
        self.assertEqual(env.sample_count(), 3)
        self.assertEqual(env.partition_of("sensor-1"), "part-1")
        self.assertEqual(env.route_alarm("sensor-1"), "cabin-1")
        self.assertEqual(env.threshold(), 75.0)
        self.assertEqual(env.set_threshold(80.0), 80.0)
        self.assertEqual(env.state().samples, 3)
        self.assertEqual([reading.at for reading in env.history("sensor-1")], ["t1", "t2", "t3"])
        self.assertIn("sensors=1", env.describe())

    def test_trend_needs_two_readings(self) -> None:
        env = Environment(MovingAverage(1), PartitionTable(), 75.0)
        env.bind_sensor_at("sensor-1", "part-1")
        env.sample("sensor-1", 30.0, "t1")
        self.assertEqual(env.trend("sensor-1"), 0.0)
        self.assertEqual(env.percentile("sensor-2", 0.5), 0.0)

    def test_repartition_and_snapshot(self) -> None:
        table = PartitionTable()
        env = Environment(MovingAverage(2), table, 75.0)
        env.bind_sensor_at("sensor-1", "part-1")
        env.sample("sensor-1", 30.0, "t1")
        self.assertEqual(env.repartition("part-1", "cabin-9"), 1)
        self.assertEqual(env.route_alarm("sensor-1"), "cabin-9")
        self.assertEqual(snapshot(env)["sensors"]["sensor-1"]["count"], 1)
        self.assertEqual(snapshot(env)["alarms"], 0)
        with self.assertRaises(ValueError):
            env.repartition("", "cabin-1")

    def test_analysis_helpers(self) -> None:
        self.assertEqual(mean([]), 0.0)
        self.assertEqual(mean([2.0, 4.0]), 3.0)
        self.assertEqual(variance([]), 0.0)
        self.assertEqual(standard_deviation([]), 0.0)
        self.assertEqual(percentile([], 0.5), 0.0)
        self.assertEqual(percentile([1.0, 2.0, 3.0], 1.0), 3.0)
        self.assertEqual(percentile([1.0, 2.0, 3.0], -1.0), 1.0)


class DrainCase(unittest.TestCase):
    def _service(self, tmp: str) -> tuple[DrainService, CabinRegistry, Store]:
        store = Store.open(tmp)
        cabins = CabinRegistry()
        cabins.upsert(Cabin(id="cabin-1"))
        service = DrainService(cabins, PumpUnit(), store)
        return service, cabins, store

    def test_pits_and_levels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _, _ = self._service(tmp)
            service.add_pit(Pit(id="pit-1", cabin="cabin-1", water_level=0.2))
            service.add_pit(Pit(id="pit-2", cabin="cabin-2", water_level=0.8))
            self.assertEqual(service.pit_count(), 2)
            self.assertTrue(service.set_level("pit-1", 0.9))
            self.assertFalse(service.set_level("ghost", 0.1))
            self.assertEqual(service.level("pit-1"), (0.9, True))
            self.assertEqual(service.level("ghost"), (0.0, False))
            self.assertEqual(set(service.levels()), {"pit-1", "pit-2"})
            self.assertEqual(service.set_levels({"pit-2": 0.4})["pit-2"], 0.4)
            self.assertEqual([pit.id for pit in service.pits()], ["pit-1", "pit-2"])
            self.assertTrue(service.is_high("pit-1"))
            self.assertFalse(service.is_high("pit-2"))
            self.assertEqual([pit.id for pit in service.high_pits()], ["pit-1"])
            service.set_threshold(0.2)
            self.assertEqual(service.threshold(), 0.2)
            self.assertAlmostEqual(service.average_level(), 0.65)
            self.assertEqual(service.max_level(), 0.9)
            self.assertEqual(service.high_count(), 2)
            self.assertEqual(service.low_count(), 0)
            self.assertEqual(service.state().runs, 0)
            self.assertIn("pits=2", service.describe())
            with self.assertRaises(ValueError):
                service.set_threshold(-1.0)

    def test_start_drain_and_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, cabins, _ = self._service(tmp)
            service.start_drain("cabin-1")
            self.assertTrue(cabins.valve_state("cabin-1"))
            self.assertEqual(service.run_count(), 1)
            self.assertEqual(service.state_name(), "pump_running")
            service.record_cycle("cabin-1", "t1")
            service.record_cycle("cabin-1", "t2")
            self.assertEqual(service.cycle_count(), 2)
            self.assertEqual([cycle.cabin_id for cycle in service.cycles()], ["cabin-1", "cabin-1"])
            self.assertEqual(service.state_name(), "idle")
            self.assertEqual(service.set_state("manual"), "manual")
            self.assertEqual(service.state().cycles[0].as_dict()["started_at"], "t1")

    def test_execute_is_de_duplicated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _, store = self._service(tmp)
            self.assertTrue(service.execute("cmd-1"))
            self.assertTrue(mark_exists(store, "cmd-1"))
            self.assertEqual(service.run_count(), 1)
            self.assertFalse(service.execute("cmd-1"))
            self.assertEqual(service.run_count(), 1)
            service.mark_in_flight("cmd-2")
            self.assertTrue(service.in_flight("cmd-2"))
            self.assertEqual(service.pending_commands(), ["cmd-2"])
            service.clear_in_flight("cmd-2")
            self.assertFalse(service.in_flight("cmd-2"))

    def test_command_guard_clears_in_flight_on_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            guard = CommandGuard(Store.open(tmp), clock=lambda: "stamp")
            self.assertFalse(guard.executed("k1"))
            self.assertTrue(guard.execute("k1", lambda: None))
            self.assertTrue(guard.executed("k1"))
            self.assertFalse(guard.execute("k1", lambda: None))

            def boom() -> None:
                raise RuntimeError("boom")

            with self.assertRaises(RuntimeError):
                guard.execute("k2", boom)
            self.assertFalse(guard.in_flight("k2"))

    def test_analysis_helpers(self) -> None:
        self.assertEqual(average_level([]), 0.0)
        self.assertEqual(max_level([]), 0.0)
        self.assertEqual(max_level([0.5, 1.5]), 1.5)
        self.assertEqual(high_count([0.5, 1.5], 1.0), 1)
        self.assertEqual(low_count([0.5, 1.5], 1.0), 1)
        self.assertTrue(utc_now().endswith("Z"))


class VentCase(unittest.TestCase):
    def test_toggle_and_status(self) -> None:
        vent = VentService()
        self.assertTrue(vent.running())
        self.assertEqual(vent.status(), "running")
        self.assertFalse(vent.stop())
        self.assertEqual(vent.status(), "stopped")
        self.assertTrue(vent.toggle())
        self.assertTrue(vent.start())
        self.assertEqual(vent.state().as_dict(), {"running": True, "status": "running"})
        self.assertIn("ventilation", vent.describe())


class FireCase(unittest.TestCase):
    def test_detectors_dampers_and_alarms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.open(tmp)
            vent = VentService()
            suppression = SuppressionLog()
            marks = MarkSet()
            fire = FireService(store, vent, suppression, marks, ("zone-1", "zone-2", "zone-3"))
            fire.add_detector(Detector(id="detector-1", zone="zone-1"))
            fire.add_detector(Detector(id="detector-2", zone="zone-2"))
            self.assertEqual(fire.detector_count(), 2)
            self.assertEqual([item.id for item in fire.detectors()], ["detector-1", "detector-2"])
            self.assertEqual(fire.zone_of_detector("detector-2"), "zone-2")
            self.assertEqual(fire.zones(), ["zone-1", "zone-2", "zone-3"])
            self.assertEqual(fire.zone_count(), 3)

            self.assertTrue(fire.detect("detector-1"))
            self.assertFalse(vent.running())
            self.assertEqual(store.load("damper", "zone-1")["closed"], True)

            order = fire.activate_zones("zone-2")
            self.assertEqual(order, ["zone-2", "zone-1", "zone-3"])
            self.assertEqual(suppression.zones(), ["zone-2", "zone-1", "zone-3"])

            self.assertTrue(fire.raise_alarm("event-1"))
            self.assertFalse(fire.raise_alarm("event-1"))
            self.assertEqual(fire.alarms(), ["event-1"])
            self.assertEqual(fire.alarm_count(), 1)
            self.assertEqual(fire.distinct_alarms(), 1)
            self.assertEqual(fire.report().as_dict()["alarm_count"], 1)
            self.assertEqual(fire.clear_alarms(), 0)
            self.assertIn("detectors=2", fire.describe())

    def test_zone_helpers(self) -> None:
        self.assertEqual(adjacent_zones(("a", "b", "c"), "b"), ["a", "c"])
        self.assertEqual(activation_order(("a", "b", "c"), "b"), ["b", "a", "c"])
        self.assertEqual(activation_order(("a", "b", "c"), "z"), ["a", "b", "c"])


class PatrolCase(unittest.TestCase):
    def test_route_checkins_and_overdue(self) -> None:
        cabins = CabinRegistry()
        cabins.upsert(Cabin(id="cabin-1", zone="zone-1"))
        cabins.upsert(Cabin(id="cabin-2", zone="zone-2"))
        patrol = PatrolService(cabins)
        self.assertEqual(patrol.route_ids(), ["cabin-1", "cabin-2"])
        self.assertEqual(patrol.missed(), ["cabin-1", "cabin-2"])
        check = patrol.check_in("cabin-1", "t1")
        self.assertEqual(check.as_dict(), {"cabin_id": "cabin-1", "at": "t1"})
        self.assertEqual(patrol.checked_cabin_ids(), ["cabin-1"])
        self.assertEqual(patrol.missed(), ["cabin-2"])
        patrol.set_due("cabin-2", "2026-01-01T00:00:00Z")
        self.assertEqual(patrol.due("cabin-2"), "2026-01-01T00:00:00Z")
        self.assertEqual(patrol.overdue("2026-02-01T00:00:00Z"), ["cabin-2"])
        self.assertEqual(patrol.overdue("2025-01-01T00:00:00Z"), [])
        self.assertEqual(patrol.progress(), 0.5)
        self.assertEqual(patrol.route_len(), 2)
        self.assertEqual(patrol.checked_count(), 1)
        self.assertEqual(patrol.summary().as_dict(), {"route": 2, "checked": 1, "missed": 1})
        self.assertEqual(patrol.sorted_route(), ["cabin-1", "cabin-2"])
        self.assertEqual(patrol.state().progress, 0.5)
        self.assertIn("route=2", patrol.describe())

        cabins.upsert(Cabin(id="cabin-3", zone="zone-3"))
        patrol.rebuild_route()
        self.assertEqual(patrol.route_ids(), ["cabin-1", "cabin-2", "cabin-3"])
        self.assertEqual([item.cabin_id for item in patrol.route()], ["cabin-1", "cabin-2", "cabin-3"])
        self.assertEqual(len(patrol.check_ins()), 1)

    def test_schedule_helpers(self) -> None:
        self.assertEqual(progress_ratio(0, []), 0.0)
        self.assertEqual(progress_ratio(4, [CheckIn("a", "t")]), 0.25)
        self.assertEqual(overdue_cabins([], [], {}, "now"), [])


class AccessCase(unittest.TestCase):
    def test_requests_and_durable_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.open(tmp)
            cabins = CabinRegistry()
            cabins.upsert(Cabin(id="cabin-1"))
            cabins.upsert(Cabin(id="cabin-2"))
            access = AccessService(store, cabins)

            request = access.submit("cabin-1", "ops")
            self.assertEqual(request.status, "pending")
            self.assertEqual(access.request_count(), 1)
            self.assertEqual([item.id for item in access.pending()], [request.id])
            self.assertEqual(access.summary(), {"requests": 1, "pending": 1, "granted": 0})

            approval = access.grant(request.id)
            self.assertTrue(cabins.door_state("cabin-1"))
            self.assertTrue(access.approved(approval.id))
            self.assertEqual(approval.cabin_id, "cabin-1")
            self.assertEqual(access.summary()["granted"], 1)
            self.assertEqual(access.pending(), [])

            direct = access.approve("cabin-2", "ops")
            self.assertTrue(cabins.door_state("cabin-2"))
            self.assertTrue(access.approved(direct.id))
            self.assertEqual(access.state().granted, 1)
            self.assertEqual(len(list_approvals(store)), 2)
            self.assertIn("requests=1", access.describe())

            with self.assertRaises(ValueError):
                access.grant("ghost")

    def test_summary_helper(self) -> None:
        self.assertEqual(summarize([]), {"requests": 0, "pending": 0, "granted": 0})


class CableCase(unittest.TestCase):
    def test_registry_history_and_analysis(self) -> None:
        registry = CableRegistry()
        registry.add(Cable(id="cable-1", cabin="cabin-1", temp=42.0))
        registry.add(Cable(id="cable-2", cabin="cabin-2", temp=80.0))
        self.assertEqual(registry.count(), 2)
        self.assertEqual(registry.get("cable-2").status, "over")
        self.assertIsNone(registry.get("ghost"))
        self.assertEqual([item.id for item in registry.list()], ["cable-1", "cable-2"])
        self.assertTrue(registry.set_temp("cable-1", 76.0))
        self.assertFalse(registry.set_temp("ghost", 10.0))
        self.assertTrue(registry.sample("cable-1", 50.0))
        self.assertTrue(registry.sample("cable-1", 60.0))
        self.assertFalse(registry.sample("ghost", 10.0))
        self.assertEqual(registry.history("cable-1"), [50.0, 60.0])
        self.assertAlmostEqual(registry.average("cable-1"), 55.0)
        self.assertEqual(registry.maximum("cable-1"), 60.0)
        self.assertEqual(registry.minimum("cable-1"), 50.0)
        self.assertEqual(registry.over("cable-1", 55.0), 1)
        self.assertEqual(registry.sample_count(), 2)
        self.assertEqual(registry.summary().as_dict(), {"total": 2, "samples": 2})
        self.assertEqual(registry.temperatures(), [60.0, 80.0])
        self.assertEqual(danger_count(registry, 75.0), 1)
        self.assertEqual(healthy_count(registry, 75.0), 1)
        self.assertAlmostEqual(load_factor(registry), 70.0)
        self.assertIn("total=2", registry.describe())

    def test_filter_and_status(self) -> None:
        moving = MovingAverage(2)
        self.assertEqual(moving.size(), 2)
        self.assertEqual(moving.filter(10.0), 10.0)
        self.assertEqual(moving.filter(20.0), 15.0)
        self.assertEqual(moving.filter(30.0), 25.0)
        self.assertEqual(moving.window(), [20.0, 30.0])
        moving.reset()
        self.assertEqual(moving.window(), [])
        self.assertEqual(MovingAverage(0).size(), 1)
        self.assertIn("size=2", moving.describe())
        self.assertEqual(status_for(74.9), "normal")
        self.assertEqual(status_for(75.0), "over")
        empty = CableRegistry()
        self.assertEqual(load_factor(empty), 0.0)
        self.assertEqual(danger_count(empty, 75.0), 0)


class QuotaCase(unittest.TestCase):
    def test_baselines_usage_and_overage(self) -> None:
        cabins = CabinRegistry()
        cabins.upsert(Cabin(id="cabin-1"))
        cabins.upsert(Cabin(id="cabin-2"))
        book = PowerBook()
        quota = QuotaService(cabins, book)

        baselines = quota.refresh_baseline(100.0)
        self.assertEqual([item.watts for item in baselines], [100.0, 100.0])
        self.assertEqual(book.baseline("cabin-1"), 100.0)
        self.assertEqual([item.cabin_id for item in baseline_report(cabins, book)], ["cabin-1", "cabin-2"])

        self.assertEqual(quota.add_usage("cabin-1", 40.0), 40.0)
        self.assertEqual(quota.add_usage("cabin-1", 80.0), 120.0)
        quota.add_usage("cabin-2", 50.0)
        self.assertEqual(quota.usage("cabin-1"), 120.0)
        self.assertEqual(quota.total_usage(), 170.0)
        self.assertEqual(quota.peak(), 120.0)
        self.assertEqual(quota.usage_by_cabin(), {"cabin-1": 120.0, "cabin-2": 50.0})
        self.assertEqual(quota.ranked_cabin_ids(), ["cabin-1", "cabin-2"])
        self.assertEqual(quota.overage("cabin-1"), 20.0)
        self.assertEqual(quota.overage("cabin-2"), 0.0)
        self.assertEqual(quota.allocated(), 200.0)
        self.assertEqual(quota.overage_total(), 20.0)
        self.assertEqual(quota.forecast("cabin-1", 2.0), 240.0)
        self.assertEqual(quota.peak_cabin(), "cabin-1")
        report = quota.report()
        self.assertEqual(report.as_dict()["cabins"], 2)
        self.assertIn("allocated=200.0000", quota.describe())

    def test_peak_cabin_without_usage(self) -> None:
        quota = QuotaService(CabinRegistry(), PowerBook())
        self.assertEqual(quota.peak_cabin(), "")

    def test_usage_helpers(self) -> None:
        self.assertEqual(total({"a": 2.0, "b": 3.0}), 5.0)
        self.assertEqual(peak({}), 0.0)
        self.assertEqual(rank({"a": 5.0, "b": 5.0}), ["a", "b"])
        self.assertEqual(overage_for(5.0, 10.0), 0.0)
        self.assertEqual(overage_for(15.0, 10.0), 5.0)


class AuditCase(unittest.TestCase):
    def test_registry_and_queries(self) -> None:
        registry = AuditRegistry()
        self.assertEqual(registry.count(), 0)
        self.assertEqual(registry.latest_id(), "")
        first = registry.append(Record(id="a1", event="access", at="2026-01-01T00:00:00Z"))
        second = registry.append(Record(id="a2", event="fire", at="2026-01-02T00:00:00Z"))
        registry.append(Record(id="a3", event="access", at="2026-01-03T00:00:00Z"))
        self.assertEqual(registry.count(), 3)
        self.assertEqual(registry.latest_id(), "a3")
        self.assertEqual([item.id for item in registry.list()], ["a1", "a2", "a3"])
        self.assertEqual(registry.count_by_event(), {"access": 2, "fire": 1})
        self.assertEqual(registry.summary()["total"], 3)
        self.assertEqual(registry.state().count, 3)
        self.assertIn("records=3", registry.describe())

        records = registry.records()
        self.assertEqual([item.id for item in filter_records(records, "access")], ["a1", "a3"])
        self.assertEqual([item.id for item in last(records, 2)], ["a2", "a3"])
        self.assertEqual(last(records, 0), [])
        self.assertEqual(events(records), ["access", "fire"])
        self.assertEqual(most_recent(records).id, "a3")
        self.assertEqual([item.id for item in between(records, "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")], ["a1", "a2"])
        self.assertEqual(count_by_event(records), {"access": 2, "fire": 1})
        self.assertEqual(summary(records)["total"], 3)
        self.assertEqual(first.as_dict(), {"id": "a1", "event": "access", "at": "2026-01-01T00:00:00Z"})
        self.assertEqual(second.as_dict()["event"], "fire")
        registry.clear()
        self.assertEqual(registry.count(), 0)
        self.assertIsNone(most_recent([]))

    def test_mark_set(self) -> None:
        marks = MarkSet()
        self.assertTrue(marks.record("k1"))
        self.assertFalse(marks.record("k1"))
        self.assertTrue(marks.has("k1"))
        self.assertEqual(marks.count(), 1)
        self.assertIn("marks=1", marks.describe())
        marks.clear()
        self.assertEqual(marks.count(), 0)


class ReportingCase(unittest.TestCase):
    def test_csv_rendering_escapes_fields(self) -> None:
        text = to_csv(["a", "b"], [[1, "plain"], [2, "has,comma"], [3, 'has"quote']])
        self.assertTrue(text.startswith("a,b\n"))
        self.assertIn('2,"has,comma"', text)
        self.assertIn('3,"has""quote"', text)

    def test_audit_and_store_exports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store.open(tmp)
            store.save("approval", "a1", {"id": "a1"})
            registry = AuditRegistry()
            registry.append(Record(id="a1", event="access", at="t1"))
            columns, rows = audit_export(registry)
            self.assertEqual(columns, ["id", "event", "at"])
            self.assertEqual(rows, [["a1", "access", "t1"]])
            store_columns, store_rows = store_export(store)
            self.assertEqual(store_columns, ["kind", "records"])
            self.assertEqual(store_rows, [["approval", 1]])

            class FakeTelemetry:
                def as_dict(self) -> dict[str, int]:
                    return {"cabins": 3}

            telemetry_columns, telemetry_rows = telemetry_export(FakeTelemetry())
            self.assertEqual(telemetry_columns, ["metric", "value"])
            self.assertEqual(telemetry_rows, [["cabins", 3]])


if __name__ == "__main__":
    unittest.main()
