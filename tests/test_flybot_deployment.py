from pathlib import Path


SERVICE_PATH = Path(__file__).parents[1] / "deploy" / "flybot" / "flybot.service"
DEPLOY_PATH = Path(__file__).parents[1] / "deploy" / "flybot" / "deploy.ps1"


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


def test_deploy_script_requires_existing_secret_and_never_accepts_token_value():
    text = DEPLOY_PATH.read_text(encoding="utf-8")
    assert "/etc/flytest/flybot.env" in text
    assert "FLYTEST_DISCORD_BOT_TOKEN" in text
    assert "FLYTEST_DISCORD_CHANNEL_ID" in text
    assert "param(" in text
    assert "Token" not in text.split("param(", 1)[1].split(")", 1)[0]
    assert "/etc/domainpatrol.env" not in text
    assert "systemctl restart flybot.service" in text


def test_deploy_script_normalizes_bash_script_line_endings_before_ssh():
    text = DEPLOY_PATH.read_text(encoding="utf-8")
    assert '$remoteScript = $remoteScript -replace "`r`n", "`n"' in text


def test_deploy_script_writes_bash_script_as_utf8_bytes_to_ssh():
    text = DEPLOY_PATH.read_text(encoding="utf-8")
    assert "StandardInput.BaseStream" in text
    assert "$remoteScript | & ssh" not in text
