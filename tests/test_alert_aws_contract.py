"""Validate outbound requests against botocore's SES/SQS API models offline."""
import botocore.session
from botocore.validate import validate_parameters

from test_alert_delivery import add_event, env  # noqa: F401 — shared pytest fixture


def test_email_request_matches_real_ses_api(env):
    add_event(env)
    env["worker"].tick()
    model = botocore.session.get_session().get_service_model("sesv2")
    validate_parameters(env["ses"].calls[0], model.operation_model("SendEmail").input_shape)
    assert env["ses"].calls[0]["Destination"]["ToAddresses"] == [env["settings"].recipient]


def test_queue_requests_match_real_sqs_api(env, monkeypatch):
    model = botocore.session.get_session().get_service_model("sqs")
    calls = []
    original = env["sqs"].receive_message
    def receive(**kwargs):
        validate_parameters(kwargs, model.operation_model("ReceiveMessage").input_shape)
        calls.append(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(env["sqs"], "receive_message", receive)
    env["worker"].tick()
    assert calls[0]["QueueUrl"] == env["settings"].queue_url
