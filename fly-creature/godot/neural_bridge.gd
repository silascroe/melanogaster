class_name NeuralBridge
extends Node

signal session_ready(payload: Dictionary)
signal step_ready(payload: Dictionary)
signal bridge_failed(message: String)

const DEFAULT_ENDPOINT := "http://127.0.0.1:8768"

var endpoint := DEFAULT_ENDPOINT
var request: HTTPRequest
var pending_kind := ""
var queued_condition := ""


func _ready() -> void:
	var configured := OS.get_environment("FLY_CREATURE_ENDPOINT")
	if not configured.is_empty():
		endpoint = configured.trim_suffix("/")
	request = HTTPRequest.new()
	request.timeout = 10.0
	add_child(request)
	request.request_completed.connect(_on_request_completed)


func start_session(condition: String) -> void:
	if not pending_kind.is_empty():
		queued_condition = condition
		return
	_send("/session", {"condition": condition}, "session")


func step(session_id: String, fly: Dictionary, object_state: Dictionary) -> void:
	_send("/session/%s/step" % session_id, {
		"dt_ms": 50.0,
		"fly": fly,
		"object": object_state,
	}, "step")


func _send(path: String, payload: Dictionary, kind: String) -> void:
	if not pending_kind.is_empty():
		return
	pending_kind = kind
	var headers := PackedStringArray(["Content-Type: application/json"])
	var error := request.request(endpoint + path, headers, HTTPClient.METHOD_POST, JSON.stringify(payload))
	if error != OK:
		pending_kind = ""
		bridge_failed.emit("Could not contact neural service (error %s)" % error)


func _on_request_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var kind := pending_kind
	pending_kind = ""
	if not queued_condition.is_empty():
		var next_condition := queued_condition
		queued_condition = ""
		start_session(next_condition)
		return
	if result != HTTPRequest.RESULT_SUCCESS:
		bridge_failed.emit("Neural service unavailable (request %s)" % result)
		return
	var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
	if typeof(parsed) != TYPE_DICTIONARY:
		bridge_failed.emit("Neural service returned invalid JSON")
		return
	var payload: Dictionary = parsed
	if response_code < 200 or response_code >= 300:
		bridge_failed.emit(str(payload.get("error", "Neural service error %s" % response_code)))
		return
	if kind == "session":
		session_ready.emit(payload)
	elif kind == "step":
		step_ready.emit(payload)
