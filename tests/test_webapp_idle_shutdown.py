"""
Arrêt automatique de webapp.py après inactivité, pour pouvoir le lancer via
activation par socket systemd (3d-library-web.socket) sans jamais y penser :
le process ne tourne que pendant qu'on l'utilise, et systemd le relance
automatiquement à la prochaine connexion.
"""

import asyncio
import time

from fastapi.testclient import TestClient

import webapp


def test_activity_tracker_touch_resets_idle_time():
    tracker = webapp.ActivityTracker()
    tracker.last_activity = 100.0

    tracker.touch(now=150.0)

    assert tracker.idle_for(now=150.0) == 0.0


def test_activity_tracker_idle_for_measures_elapsed_time():
    tracker = webapp.ActivityTracker()
    tracker.last_activity = 100.0

    assert tracker.idle_for(now=340.0) == 240.0


def test_listen_fd_count_zero_when_not_socket_activated(monkeypatch):
    monkeypatch.delenv("LISTEN_FDS", raising=False)

    assert webapp.listen_fd_count() == 0


def test_listen_fd_count_reads_systemd_env_var(monkeypatch):
    monkeypatch.setenv("LISTEN_FDS", "1")

    assert webapp.listen_fd_count() == 1


def test_listen_fd_count_treats_garbage_value_as_zero(monkeypatch):
    monkeypatch.setenv("LISTEN_FDS", "not-a-number")

    assert webapp.listen_fd_count() == 0


def test_uvicorn_run_kwargs_uses_inherited_fd_when_socket_activated():
    assert webapp.uvicorn_run_kwargs(listen_fds=1, host="127.0.0.1", port=8000) == {"fd": 3}


def test_uvicorn_run_kwargs_uses_host_port_when_launched_manually():
    assert webapp.uvicorn_run_kwargs(listen_fds=0, host="127.0.0.1", port=8000) == {
        "host": "127.0.0.1",
        "port": 8000,
    }


def test_any_request_touches_the_activity_tracker():
    webapp.activity.last_activity = 0.0  # très ancien, pour être sûr que ça bouge
    client = TestClient(webapp.app)

    client.get("/api/stats")  # peu importe que la DB existe : on vérifie juste le middleware

    assert webapp.activity.idle_for(now=time.monotonic()) < 1.0


def test_idle_shutdown_loop_triggers_callback_once_timeout_reached():
    tracker = webapp.ActivityTracker()
    tracker.last_activity = 0.0  # idle depuis "toujours"
    calls = []

    asyncio.run(webapp.idle_shutdown_loop(
        tracker, timeout_seconds=0, check_interval=0, max_iterations=1,
        on_shutdown=lambda: calls.append(True),
    ))

    assert calls == [True]


def test_idle_shutdown_loop_does_not_trigger_while_still_active():
    tracker = webapp.ActivityTracker()  # vient d'être touché à l'instant
    calls = []

    asyncio.run(webapp.idle_shutdown_loop(
        tracker, timeout_seconds=600, check_interval=0, max_iterations=2,
        on_shutdown=lambda: calls.append(True),
    ))

    assert calls == []
