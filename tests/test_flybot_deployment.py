from pathlib import Path


SERVICE_PATH = Path(__file__).parents[1] / "deploy" / "flybot" / "flybot.service"


def test_flybot_unit_has_isolated_runtime_and_state_paths():
    text = SERVICE_PATH.read_text(encoding="utf-8")
    required = (
        "User=flybot",
        "Group=flybot",
        "EnvironmentFile=/etc/flytest/flybot.env",
        "Environment=PYTHONPATH=/opt/flytest-discord/src",
        "WorkingDirectory=/var/lib/flytest-discord",
        "--spool /var/lib/flytest-discord/events.jsonl",
        "--state-file /var/lib/flytest-discord/events.jsonl.offset",
        "Restart=on-failure",
        "NoNewPrivileges=yes",
        "ProtectSystem=strict",
        "ReadWritePaths=/var/lib/flytest-discord",
    )
    assert all(item in text for item in required)


def test_flybot_unit_does_not_reference_domainpatrol_or_embed_a_secret():
    text = SERVICE_PATH.read_text(encoding="utf-8").lower()
    assert "domainpatrol" not in text
    assert "discord.com/api" not in text
    assert "token=" not in text
