"""Local JSON bridge for the standalone Godot creature scene."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from uuid import uuid4

from .circuit import load_circuit
from .controller import CreatureSession
from .steering_diagnostic import load_candidate
from .steering_diagnostic import condition_circuit


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Fly Creature neural bridge")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    circuit = load_circuit()
    steering_circuit = load_candidate()
    sessions: dict[str, CreatureSession] = {}

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, code: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path != "/health":
                self._reply(404, {"error": "Unknown route"})
                return
            self._reply(200, {
                "project": "Fly Creature",
                "neurons": len(circuit.neurons),
                "connections": len(circuit.connections),
                "steering_neurons": len(steering_circuit.neurons),
                "steering_connections": len(steering_circuit.connections),
                "active_sessions": len(sessions),
            })

        def do_POST(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65_536:
                    raise ValueError("JSON body is missing or too large")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("JSON body must be an object")
                if self.path == "/session":
                    condition = str(payload.get("condition", "intact"))
                    session = CreatureSession(circuit, condition=condition,
                                              steering_circuit=steering_circuit)
                    session_id = uuid4().hex
                    # This first project has one local scene/client at a time.
                    sessions.clear()
                    sessions[session_id] = session
                    self._reply(200, {
                        "session_id": session_id,
                        "condition": condition,
                        "neurons": len(circuit.neurons),
                        "connections": len(circuit.connections) if condition == "intact" else 0,
                        "steering_neurons": len(steering_circuit.neurons),
                        "steering_connections": len(condition_circuit(
                            steering_circuit,
                            "intact" if condition == "intact" else "bridge_removed"
                        ).connections),
                    })
                    return
                parts = self.path.strip("/").split("/")
                if len(parts) == 3 and parts[0] == "session" and parts[2] == "step":
                    session = sessions.get(parts[1])
                    if session is None:
                        self._reply(404, {"error": "Unknown session; restart the scene"})
                        return
                    self._reply(200, session.step(payload))
                    return
                self._reply(404, {"error": "Unknown route"})
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                self._reply(400, {"error": str(error)})

    server = HTTPServer((args.host, args.port), Handler)
    print(f"Fly Creature neural bridge: http://{args.host}:{args.port}", flush=True)
    print(f"Loaded {len(circuit.neurons)} neurons and {len(circuit.connections)} connections", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
