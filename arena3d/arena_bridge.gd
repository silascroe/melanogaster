class_name ArenaBridge
extends Node

## Transport layer for the live Godot ↔ Python Arena loop.
## Godot owns the world state. Python owns the persistent connectome runtime.

signal session_ready(payload: Dictionary)
signal step_ready(payload: Dictionary)
signal bridge_failed(message: String)

const DEFAULT_ENDPOINT := "http://127.0.0.1:8767/api/arena/session"

var endpoint := DEFAULT_ENDPOINT
var request: HTTPRequest
var pending_kind := ""


func _ready() -> void:
	var configured_endpoint := OS.get_environment("FLYTEST_ARENA_ENDPOINT")
	if not configured_endpoint.is_empty():
		endpoint = configured_endpoint
	request = HTTPRequest.new()
	request.timeout = 120.0
	add_child(request)
	request.request_completed.connect(_on_request_completed)


func request_session() -> void:
	var config := {
		"mode": "demo",
		"network_stage": 250,
		"duration_ms": 180,
		"coupling": 3.0,
		"turn_degrees": 15.0,
		"forward_step": 1.0,
		"visual_contrast": 1.0,
		"visual_coupling": 5.0,
	}
	_request_json(endpoint, config, "session")


func request_step(session_id: String, time_ms: float, body: Dictionary, lights: Array, threats: Array) -> void:
	if session_id.is_empty():
		bridge_failed.emit("no Arena session is active")
		return
	var payload := {
		"time_ms": time_ms,
		"body": body,
		"lights": lights,
		"threats": threats,
	}
	_request_json("%s/%s/step" % [endpoint, session_id], payload, "step")


func _request_json(url: String, payload: Dictionary, kind: String) -> void:
	if request == null:
		bridge_failed.emit("bridge is not ready")
		return
	if request.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED:
		bridge_failed.emit("a Python Arena request is already in flight")
		return
	pending_kind = kind
	var headers := PackedStringArray(["Content-Type: application/json"])
	var result := request.request(url, headers, HTTPClient.METHOD_POST, JSON.stringify(payload))
	if result != OK:
		pending_kind = ""
		bridge_failed.emit("could not start Python Arena request (%s)" % result)


func _on_request_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var kind := pending_kind
	pending_kind = ""
	if result != HTTPRequest.RESULT_SUCCESS:
		bridge_failed.emit("Python Arena unavailable (%s)" % result)
		return
	var text := body.get_string_from_utf8()
	var parsed: Variant = JSON.parse_string(text)
	if parsed == null or typeof(parsed) != TYPE_DICTIONARY:
		bridge_failed.emit("Python Arena returned invalid JSON (HTTP %s)" % response_code)
		return
	var payload: Dictionary = parsed
	if response_code < 200 or response_code >= 300:
		bridge_failed.emit(str(payload.get("error", "Python Arena request failed (HTTP %s)" % response_code)))
		return
	if kind == "session":
		if not payload.has("session_id"):
			bridge_failed.emit("Python Arena session response has no session_id")
			return
		session_ready.emit(payload)
	elif kind == "step":
		if not payload.has("frame"):
			bridge_failed.emit("Python Arena step response has no frame")
			return
		step_ready.emit(payload)
