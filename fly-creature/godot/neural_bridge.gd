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
var queued_model := "lif"


func _ready() -> void:
	var configured := OS.get_environment("FLY_CREATURE_ENDPOINT")
	if not configured.is_empty():
		endpoint = configured.trim_suffix("/")
	request = HTTPRequest.new()
	request.timeout = 10.0
	add_child(request)
	request.request_completed.connect(_on_request_completed)


func start_session(condition: String, steering_model: String = "lif") -> void:
	if not pending_kind.is_empty():
		queued_condition = condition
		queued_model = steering_model
		return
	_send("/session", {"condition": condition, "steering_model": steering_model}, "session")


func step(session_id: String, fly: Dictionary, object_state: Dictionary, target_state: Dictionary,
		sugar_state: Dictionary = {}, touch_state: Dictionary = {},
		obstacle_state: Dictionary = {}) -> void:
	_send("/session/%s/step" % session_id, {
		"dt_ms": 50.0,
		"fly": fly,
		"object": object_state,
		"target": target_state,
		"sugar": sugar_state if not sugar_state.is_empty() else {"active": false},
		"touch": touch_state if not touch_state.is_empty() else {"active": false},
		"obstacle": obstacle_state if not obstacle_state.is_empty() else {"active": false},
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
		start_session(next_condition, queued_model)
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


func step_fixed(session_id: String, fly: Dictionary, object_state: Dictionary, target_state: Dictionary) -> Dictionary:
	# Experimental loopback lockstep: do not drop ticks while HTTP is pending.
	var client := HTTPClient.new()
	var address := endpoint.trim_prefix("http://").split(":")
	if not endpoint.begins_with("http://") or address.size() != 2:
		bridge_failed.emit("Experimental mode needs an HTTP host:port endpoint")
		return {}
	if client.connect_to_host(address[0], int(address[1])) != OK:
		bridge_failed.emit("Experimental bridge connection failed")
		return {}
	var deadline := Time.get_ticks_msec() + 10000
	while client.get_status() in [HTTPClient.STATUS_RESOLVING, HTTPClient.STATUS_CONNECTING]:
		client.poll()
		if Time.get_ticks_msec() > deadline:
			bridge_failed.emit("Experimental bridge timed out")
			return {}
		OS.delay_msec(1)
	var body := JSON.stringify({"dt_ms": 10, "fly": fly, "object": object_state, "target": target_state})
	if client.request(HTTPClient.METHOD_POST, "/session/%s/step" % session_id,
		PackedStringArray(["Content-Type: application/json"]), body) != OK:
		bridge_failed.emit("Experimental bridge request failed")
		return {}
	while client.get_status() == HTTPClient.STATUS_REQUESTING:
		client.poll()
		if Time.get_ticks_msec() > deadline:
			bridge_failed.emit("Experimental bridge timed out")
			return {}
		OS.delay_msec(1)
	var bytes := PackedByteArray()
	var code := client.get_response_code()
	while client.get_status() == HTTPClient.STATUS_BODY:
		client.poll()
		bytes.append_array(client.read_response_body_chunk())
		if Time.get_ticks_msec() > deadline:
			bridge_failed.emit("Experimental response timed out")
			return {}
		OS.delay_msec(1)
	var parsed: Variant = JSON.parse_string(bytes.get_string_from_utf8())
	if code != 200 or typeof(parsed) != TYPE_DICTIONARY:
		bridge_failed.emit("Experimental bridge returned an invalid response (%s)" % code)
		return {}
	return parsed
